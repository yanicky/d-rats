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
from threading import Thread

import serial
import gtk

import chatgui
import config

from utils import hexprint
import qst

LOGTF = "%m-%d-%Y_%H:%M:%S"

class SerialCommunicator:

    def __init__(self, port=0, rate=9600, log=None):
        self.enabled = False
        self.log = None
        self.pipe = None
        self.opened = False
        
        self.logfile = log
        self.port = port
        self.rate = rate

    def write(self, buf):
        if self.enabled:
            return self.pipe.write(buf)

    def read(self, len):
        if self.enabled:
            return self.pipe.read(len)

    def write_log(self, text):
        if not self.log:
            return

        print >>self.log, "%s: %s" % (time.strftime(LOGTF), text)
        self.log.flush()

    def open_log(self):
        if self.logfile:
            self.log = file(self.logfile, "a")
            print >>self.log, "*** Log started @ %s ***" % time.strftime(LOGTF)

    def close_log(self):
        if self.log:
            print >>self.log, "*** Log closed @ %s ***" % time.strftime(LOGTF)
            self.log.close()

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
            self.pipe = serial.Serial(port=self.port,
                                      baudrate=self.rate,
                                      timeout=0.25,
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
            self.open_log()
            self.enabled = True
            self.thread = Thread(target=self.watch_serial)
            self.thread.start()
            return True
        else:
            return False

    def disable(self):
        if self.enabled:
            self.enabled = False
            self.close_log()
            print "Waiting for chat watch thread..."
            self.thread.join()

    def send_text(self, text):
        if self.enabled:
            self.write_log(text)
            return self.pipe.write(text)

    def incoming_chat(self, data):
        if self.gui.config.config.getboolean("prefs", "eolstrip"):
            data = data.replace("\n", "")
            data = data.replace("\r", "")
        else:
            data = data.rstrip("\n")
            if os.linesep != "\n":
                data = data.replace("\n", os.linesep)

        stamp = time.strftime("%H:%M:%S")

        self.write_log("%s%s%s" % (stamp, data, os.linesep))

        self.gui.display("%s " % stamp)

        ignore = self.gui.config.config.get("prefs", "ignorere")
        if ignore and re.search(ignore, data):
            self.gui.display(data + os.linesep, "ignorecolor")
        elif ">" in data:
            call, data = data.split(">", 1)
            self.gui.display("%s>" % call, "incomingcolor")
            self.gui.display("%s%s" % (data, os.linesep))
        else:
            self.gui.display("%s%s" % (data, os.linesep))

    def watch_serial(self):
        data = ""
        newdata = ""
        
        print "Starting chat watch thread"

        while self.enabled:
            #size = self.pipe.inWaiting()
            try:
                newdata = self.pipe.read(64)
            except Exception, e:
                print "Serial read failed: %s" % e
            
            if len(newdata) > 0:
                data += newdata
                #print "Got Data: %s" % newdata
                print "Data chunk:"
                hexprint(newdata)
            else:
                if data:
                    print "No more data, writing: %s" % data
                    gtk.gdk.threads_enter()
                    self.incoming_chat(data)
                    gtk.gdk.threads_leave()
                    data = ""
                    
                time.sleep(1)

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
            text = self.config.config.get(i, "content")
            freq = self.config.config.get(i, "freq")
            qtyp = self.config.config.get(i, "type")
            enab = self.config.config.getboolean(i, "enabled")

            if not enab:
                continue
            
            qstclass = qst.get_qst_class(qtyp)
            if not qstclass:
                print "Unknown QST type: %s" % qtyp
                continue
            
            qstinst = qstclass(self.chatgui, self.config,
                               text=text, freq=int(freq))
            qstinst.enable()

            self.qsts.append(qstinst)

    def refresh_comm(self, rate, port, log=None):
        if self.comm:
            self.comm.disable()
            
        self.comm = SerialCommunicator(rate=rate, port=port, log=log)
        if self.comm.open():
            self.comm.enable(self.chatgui)
            
        self.chatgui.display("%s%s" % (str(self.comm), os.linesep))

        self.chatgui.comm = self.comm

    def refresh_config(self):
        rate=self.config.config.getint("settings", "rate")
        port=self.config.config.get("settings", "port")
        call=self.config.config.get("user", "callsign")

        if self.config.config.getboolean("prefs", "logenabled"):
            base = self.config.config.get("prefs", "download_dir")
            logfile = "%s%s%s" % (base, os.path.sep, "d-rats.log")
        else:
            logfile = None

        if self.comm and self.comm.enabled:
            if self.comm.pipe.baudrate != rate or \
                self.comm.pipe.portstr != port:
                print "Serial config changed"
                self.refresh_comm(rate, port, logfile)
        else:
            self.refresh_comm(rate, port, logfile)

        self.chatgui.display("My Call: %s\n" % call, "blue")

        self.refresh_qsts()
        self.chatgui.refresh_colors()
        self.chatgui.refresh_advanced()

    def __init__(self):
        self.comm = None
        self.qsts = []
        self.log = None

        gtk.gdk.threads_init()

        if os.name == "posix":
            self.config = config.UnixAppConfig(self)
        elif os.name == "nt":
            self.config = config.Win32AppConfig(self)
        else:
            self.config = config.AppConfig(self)

        self.chatgui = chatgui.ChatGUI(self.config)

        self.refresh_config()

        if self.config.config.getboolean("prefs", "dosignon"):
            self.chatgui.tx_msg(self.config.config.get("prefs", "signon"))
            
    def main(self):
        try:
            gtk.gdk.threads_enter()
            gtk.main()
            gtk.gdk.threads_leave()
        except KeyboardInterrupt:
            pass
        
        self.comm.disable()

if __name__ == "__main__":
    app = MainApp()
    sys.exit(app.main())
