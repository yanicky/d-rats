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
import comm

from utils import hexprint,filter_to_ascii
import qst

ASCII_XON = chr(17)
ASCII_XOFF = chr(19)

DRATS_VERSION = "0.1.17"
LOGTF = "%m-%d-%Y_%H:%M:%S"

MAINAPP = None

gobject.threads_init()

class SocketClosedError(Exception):
    pass

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
            self.state = True
            print "Assuming IXANY behavior"

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

class ChatBuffer:
    def __init__(self, path, infunc, connfunc):
        self.enabled = False

        self.inbuf = ""
        self.outbuf = ""

        self.infunc = infunc
        self.connfunc = connfunc

        self.path = path

        self.lock = Lock()
        self.thread = None

    def connect(self):
        try:
            self.path.connect()
            self.connfunc(self.path.is_connected())
        except Exception, e:
            self.infunc("Unable to connect: %s" % e)
            self.connfunc(False)
            return False

        self.infunc("Connected: %s" % str(self.path))
        return True

    def write(self, buf):
        self.lock.acquire()
        self.outbuf += buf
        self.lock.release()

    def read(self, count):
        self.lock.acquire()
        data = self.inbuf[:count]
        self.lock.release()

        if len(data) == count:
            print "Got enough"
            return data

        print "Delaying for another read"
        time.sleep(0.2)

        self.lock.acquire()
        data += self.inbuf[:count - len(data)]
        self.lock.release()

        return data        

    def close(self):
        if self.enabled:
            self.stop_watch()
        self.path.disconnect()

    def incoming(self, data):
        gobject.idle_add(self.infunc, data)

    def disconnected(self):
        self.path.disconnect()
        self.enabled = False
        gobject.idle_add(self.connfunc, False)

    def start_watch(self):
        if not self.path.is_connected():
            if not self.connect():
                print "Unable to connect: %s" % e
                return

        if self.enabled:
            print "Attempt to reconnect main comm channel!"
            return

        self.enabled = True
        self.thread = Thread(target=self.serial_thread)
        self.thread.start()

    def stop_watch(self):
        self.enabled = False
        if self.thread:
            self.thread.join()

    def serial_thread(self):
        while self.enabled:
            self.lock.acquire()
            out = self.outbuf
            self.outbuf = ""
            self.lock.release()

            if out:
                try:
                    self.path.write(out)
                except comm.DataPathIOError, e:
                    self.incoming("Write error")
                except comm.DataPathNotConnectedError, e:
                    self.incoming("Disconnected")
                    self.disconnected()

            try:
                inp = ""
                while True:
                    _inp = self.path.read(64)
                    if len(_inp) == 0:
                        break
                    else:
                        inp += _inp
            except comm.DataPathIOError, e:
                self.incoming("Read error")
            except comm.DataPathNotConnectedError, e:
                self.incoming("Disconnected")
                self.disconnected()

            if inp:
                print "Got data %s" % filter_to_ascii(inp)
                self.lock.acquire()
                self.inbuf += inp
                self.lock.release()
                self.incoming(inp)

            if not inp and not out:
                time.sleep(0.2)

    def send_text(self, text):
        self.lock.acquire()
        self.outbuf += text
        self.lock.release()

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

    def incoming_chat(self, data):
        self.chatgui.display_line(data, "incomingcolor")

    def connected(self, is_connected):
        self.chatgui.set_connected(is_connected)

    def refresh_comm(self, rate, port):
        if self.comm:
            self.comm.close()
            
        try:
            swf = self.config.getboolean("settings", "swflow")
        except:
            swf = False

        if ":" in port:
            (_, host, port) = port.split(":")
            self.comm = ChatBuffer(comm.SocketDataPath((host, int(port))),
                                   self.incoming_chat,
                                   self.connected)
        else:
            self.comm = ChatBuffer(comm.SerialDataPath((port, int(rate))),
                                   self.incoming_chat,
                                   self.connected)
                                   
        if self.comm.connect():
            self.comm.start_watch()

    def _static_gps(self):
        lat = 0.0
        lon = 0.0
        alt = 0.0

        try:
            lat = self.config.get("user", "latitude")
            lon = self.config.get("user", "longitude")
            alt = self.config.get("user", "altitude")
        except Exception, e:
            print "Invalid static position: %s" % e

        print "Static position: %s,%s" % (lat,lon)
        return gps.StaticGPSSource(lat, lon, alt)

    def refresh_gps(self):
        port = self.config.get("settings", "gpsport")
        enab = self.config.getboolean("settings", "gpsenabled")

        print "GPS: %s on %s" % (enab, port)

        if enab:
            if self.gps:
                self.gps.stop()
            self.gps = gps.GPSSource(port)
            self.gps.start()
        else:
            if self.gps:
                self.gps.stop()

            self.gps = self._static_gps()

    def refresh_config(self):
        rate = self.config.getint("settings", "rate")
        port = self.config.get("settings", "port")
        call = self.config.get("user", "callsign")
        enc = self.config.get("settings", "encoding")
        com = self.config.getboolean("settings", "compression")
        units = self.config.get("user", "units")

        ddt.set_compression(com)
        ddt.set_encoding(enc)

        gps.set_units(units)

        self.refresh_comm(rate, port)

        self.chatgui.display("My Call: %s\n" % call, "blue", "italic")

        self.refresh_qsts()
        self.refresh_gps()
        self.chatgui.refresh_config()
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

    def TEMP_migrate_config(self):
        import platform

        if os.name != "posix":
            return

        p = platform.get_platform()
        fn = p.config_file("drats.config")
        if os.path.exists(fn):
            print "Migrating broken UNIX config filename"
            newfn = p.config_file("d-rats.config")
            os.rename(fn, newfn)            
            
    def __init__(self, **args):
        global MAINAPP
        MAINAPP = self

        self.comm = None
        self.qsts = []
        self.seen_callsigns = {}
        self.position = None

        # REMOVE ME in 0.1.13
        self.TEMP_migrate_config()

        self.config = config.AppConfig(self, **args)

        self.gps = self._static_gps()

        self.maybe_redirect_stdout()

        self.chatgui = chatgui.MainChatGUI(self.config, self)

        self.chatgui.display("D-RATS v%s " % DRATS_VERSION, "red")
        self.chatgui.display("(Copyright 2008 Dan Smith KI4IFW)\n",
                             "blue", "italic")
        
        self.refresh_config()
        
        if self.config.getboolean("prefs", "dosignon"):
            self.chatgui.tx_msg(self.config.get("prefs", "signon"))
            
    def get_position(self):
        p = self.gps.get_position()
        p.set_station(self.config.get("user", "callsign"))
        return p

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
        self.comm.stop_watch()

        print "Closing serial..."
        self.comm.close()

        if self.gps:
            print "Stopping GPS..."
            self.gps.stop()

        print "Done.  Exit."

def get_mainapp():
    return MAINAPP
