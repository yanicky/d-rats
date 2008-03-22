#!/usr/bin/python
#
# Copyright 2008 Dan Smith <dsmith@danplanet.com>
#
# This program is free software: you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation, either version 3 of the License, or
# (at your option) any later version.
#
# This program is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU General Public License for more details.
#
# You should have received a copy of the GNU General Public License
# along with this program.  If not, see <http://www.gnu.org/licenses/>.

import os
import sys
import time
import re
from threading import Thread, Lock
from select import select
import socket

import serial
import gtk
import gobject

import chatgui
import config
import ddt
import gps

from utils import hexprint,filter_to_ascii
import qst

ASCII_XON = chr(17)
ASCII_XOFF = chr(19)

DRATS_VERSION = "0.1.11"
LOGTF = "%m-%d-%Y_%H:%M:%S"

MAINAPP = None

gobject.threads_init()

class SWFSerial(serial.Serial):
    __swf_debug = False

    def __init__(self, **kwargs):
        print "Software XON/XOFF control initialized"
        serial.Serial.__init__(self, **kwargs)

        self.state = True

    def is_xon(self):
        char = serial.Serial.read(self, 1)
        if char == ASCII_XOFF:
            if self.__swf_debug:
                print "************* Got XOFF"
            self.state = False
        elif char == ASCII_XON:
            if self.__swf_debug:
                print "------------- Got XON"
            self.state = True
        elif len(char) == 1:
            print "Aiee! Read a non-XOFF char: 0x%02x `%s`" % (ord(char),
                                                                   char)

        return self.state

    def write(self, data):
        old_to = self.timeout
        self.timeout = 0.01
        chunk = 8
        pos = 0
        while pos < len(data):
            if self.__swf_debug:
                print "Sending %i-%i of %i" % (pos, pos+chunk, len(data))
            serial.Serial.write(self, data[pos:pos+chunk])
            self.flush()
            pos += chunk
            while not self.is_xon():
                if self.__swf_debug:
                    print "We're XOFF, waiting"
                time.sleep(0.01)

        self.timeout = old_to

    def read(self, len):
        return serial.Serial.read(self, len)

class SocketSerial:
    def __init__(self, port, timeout=0.25):
        (_, self.host, self.port) = port.split(":")

        self.portstr = "Network (%s:%s)" % (self.host, self.port)
        self.timeout = timeout

        self.connect()

    def connect(self):

        try:
            self.socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            self.socket.connect((self.host, int(self.port)))
            self.socket.settimeout(0.25)
        except:
            return False
        
        try:
            r = self.socket.recv(1)
        except:
            return True

        return r != ''

    def reconnect(self, iter=10, timeout=5):
        for i in range(iter):
            if self.connect():
                print "Reconnected"
                return True
            else:
                print "Retrying..."
                time.sleep(timeout)

        return False

    def read(self, length):
        data = ""
        end = time.time() + self.timeout
        while len(data) < length:
            if time.time() > end:
                break

            try:
                inp = self.socket.recv(length - len(data))
                data += inp
            except Exception, e:
                continue

            if inp == "":
                print "Got nothing, socket must be dead!"
                if not self.reconnect():
                    raise Exception("Socket closed")
            
        return data

    def write(self, buf):
        try:
            self.socket.sendall(buf)
        except Exception, e:
            print "Socket write failed: %s" % e
            self.reconnect()

    def getBaudrate(self):
        return 0

    def flush(self):
        return

    def close(self):
        self.socket.close()
        self.socket = None

    def flushInput(self):
        return

class SerialCommunicator:

    def __init__(self, port=0, rate=9600, swf=False):
        self.enabled = False
        self.pipe = None
        self.opened = False
        
        self.port = port
        self.rate = rate
        self.swf = swf

        self.lock = Lock()
        self.incoming_data = ""
        self.outgoing_data = ""

        self.state = True

    def write(self, buf):
        if self.enabled:
            return self.pipe.write(buf)

    def read(self, len):
        if self.enabled:
            return self.pipe.read(len)

    def close(self):
        if self.opened:
            self.pipe.close()
            self.opened = False
            return True
        else:
            return False

    def open(self):
        if self.opened:
            return self.opened

        try:
            if self.port.startswith("net:"):
                self.pipe = SocketSerial(port=self.port)
            elif self.swf:
                self.pipe = SWFSerial(port=self.port,
                                      baudrate=self.rate,
                                      timeout=0.25,
                                      writeTimeout=5,
                                      xonxoff=0)
            else:
                self.pipe = serial.Serial(port=self.port,
                                          baudrate=self.rate,
                                          timeout=0.25,
                                          writeTimeout=5,
                                          xonxoff=1)
            self.opened = True
        except Exception, e:
            print "Failed to open serial port: %s" % e
            self.opened = False

        return self.opened

    def enable(self, gui):
        if not self.opened:
            print "Attempt to enable a non-opened serial line"
            return False

        self.gui = gui
        if not self.enabled:
            self.enabled = True
            self.thread = Thread(target=self.watch_serial)
            self.thread.start()
            return True
        else:
            return False

    def disable(self):
        if self.enabled:
            self.enabled = False
            print "Waiting for chat watch thread..."
            self.thread.join()

    def send_text(self, text):
        self.lock.acquire()
        self.outgoing_data += text
        self.lock.release()

    def incoming_chat(self):
        self.lock.acquire()
        data = self.incoming_data
        self.incoming_data = ""
        self.lock.release()

        if self.gui.config.getboolean("prefs", "eolstrip"):
            data = data.replace("\n", "")
            data = data.replace("\r", "")
        else:
            data = data.rstrip("\n")
            if os.linesep != "\n":
                data = data.replace("\n", os.linesep)

        self.gui.display_line(data, "incomingcolor")

    def watch_serial(self):
        data = ""
        newdata = ""
        
        print "Starting chat watch thread"

        while self.enabled:
            self.lock.acquire()
            out = self.outgoing_data
            self.outgoing_data = ""
            self.lock.release()

            if out:
                try:
                    print "Sending %s" % out
                    self.pipe.write(out)
                    print "Done with send"
                except Exception, e:
                    print "Exception during write: %s" % e
                    break

            try:
                newdata = self.pipe.read(64)
            except Exception, e:
                print "Serial read failed: %s" % e
                break
            
            if len(newdata) > 0:
                data += newdata
                #print "Data chunk:"
                #hexprint(newdata)
            else:
                if data:
                    print "No more data, queuing: %s" % filter_to_ascii(data)
                    self.lock.acquire()
                    self.incoming_data += data
                    self.lock.release()

                    gobject.idle_add(self.incoming_chat)
                    data = ""
                    
                time.sleep(0.25)

        if self.enabled:
            print "Exited loop due to error, going offline"
            self.enabled = False
            gobject.idle_add(self.gui.set_connected, False)

    def __str__(self):
        if self.enabled:
            return "Connected: %s @ %i baud" % (self.pipe.portstr,
                                                self.pipe.getBaudrate())
        else:
            return "Unable to connect to serial port: %s" % self.port
            
class MainApp:
    def setup_autoid(self):
        idtext = "(ID)"

    def refresh_qsts(self):
        for i in self.qsts:
            print "Disabling QST %s" % i.text
            i.disable()
            print "Done"

        self.qsts = []

        sections = self.config.config.sections()
        qsts = [x for x in sections if x.startswith("qst_")]

        for i in qsts:
            print "Doing QST %s" % i
            text = self.config.get(i, "content")
            freq = self.config.get(i, "freq")
            qtyp = self.config.get(i, "type")
            enab = self.config.getboolean(i, "enabled")

            if not enab:
                continue
            
            qstclass = qst.get_qst_class(qtyp)
            if not qstclass:
                print "Unknown QST type: %s" % qtyp
                continue
            
            qstinst = qstclass(self.chatgui, self.config,
                               text=text, freq=freq)
            qstinst.enable()

            self.qsts.append(qstinst)

    def refresh_comm(self, rate, port):
        if self.comm:
            self.comm.disable()
            
        try:
            swf = self.config.getboolean("settings", "swflow")
        except:
            swf = False

        self.comm = SerialCommunicator(rate=rate, port=port, swf=swf)
        if self.comm.open():
            self.comm.enable(self.chatgui)
            
        self.chatgui.display_line(str(self.comm), "italic")

    def refresh_config(self):
        rate = self.config.getint("settings", "rate")
        port = self.config.get("settings", "port")
        call = self.config.get("user", "callsign")
        enc = self.config.get("settings", "encoding")
        com = self.config.getboolean("settings", "compression")

        ddt.set_compression(com)
        ddt.set_encoding(enc)

        if self.comm and self.comm.enabled:
            if self.comm.pipe.getBaudrate() != rate or \
                self.comm.pipe.portstr != port:
                print "Serial config changed"
                self.refresh_comm(rate, port)
        else:
            self.refresh_comm(rate, port)

        self.chatgui.display("My Call: %s\n" % call, "blue", "italic")

        self.refresh_qsts()
        self.chatgui.refresh_colors()
        self.chatgui.refresh_advanced()

    def maybe_redirect_stdout(self):
        try:
            if self.config.getboolean("prefs", "debuglog"):
                dir = self.config.get("prefs", "download_dir")
                logfile = os.path.join(dir, "debug.log")
                sys.stdout = file(logfile, "w", 0)
                sys.stderr = sys.stdout
            elif os.name == "nt":
                class Blackhole(object):
                    softspace=0
                    def write(self, text):
                        pass

                sys.stdout = Blackhole()
                del Blackhole

        except Exception, e:
            print "Unable to open debug log: %s" % e
            
    def __init__(self, **args):
        global MAINAPP
        MAINAPP = self

        self.comm = None
        self.qsts = []
        self.seen_callsigns = {}

        self.config = config.AppConfig(self, **args)

        self.maybe_redirect_stdout()

        self.chatgui = chatgui.MainChatGUI(self.config, self)

        self.chatgui.display("D-RATS v%s " % DRATS_VERSION, "red")
        self.chatgui.display("(Copyright 2008 Dan Smith KI4IFW)\n",
                             "blue", "italic")
        
        self.refresh_config()
        
        if self.config.getboolean("prefs", "dosignon"):
            self.chatgui.tx_msg(self.config.get("prefs", "signon"))
            
    def get_position(self):
        fix = gps.GPSPosition()
        try:
            lat = float(self.config.get("user", "latitude"))
            lon = float(self.config.get("user", "longitude"))
            alt = float(self.config.get("user", "altitude"))
        except Exception, e:
            print "Invalid position: %s" % e
            return None

        fix.from_coords(lat, lon, alt)
        fix.set_station(self.config.get("user", "callsign"), "D-RATS")

        return fix

    def main(self):
        try:
            gtk.main()
        except KeyboardInterrupt:
            pass
        except Exception, e:
            print "Got exception on close: %s" % e

        print "Saving config..."
        self.config.save()

        print "Disabling watch thread..."
        self.comm.disable()

        print "Closing serial..."
        self.comm.close()

        print "Done.  Exit."


def get_mainapp():
    return MAINAPP
