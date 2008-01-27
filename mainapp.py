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
from qst import QST

class SerialCommunicator:

    def __init__(self, port=0, rate=9600):
        self.pipe = serial.Serial(port=port, timeout=2, baudrate=rate,
                                  xonxoff=1)
        self.enabled = False

    def close(self):
        self.pipe.close()

    def enable(self, gui):
        self.gui = gui
        if not self.enabled:
            self.enabled = True
            self.thread = Thread(target=self.watch_serial)
            self.thread.start()

    def disable(self):
        if self.enabled:
            self.enabled = False
            print "Waiting for thread..."
            self.thread.join()

    def send_text(self, text):
        if self.enabled:
            return self.pipe.write(text)

    def incoming_chat(self, data):
        data = data.replace("\n", "")
        data = data.replace("\r", "")
        
        if os.linesep != "\n":
            data = data.replace("\n", os.linesep)

        stamp = time.strftime("%H:%M:%S")

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
        while self.enabled:
            #size = self.pipe.inWaiting()
            newdata = self.pipe.read(64)
            
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
        return "%s @ %i baud" % (self.pipe.portstr,
                                 self.pipe.getBaudrate())
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
            enab = self.config.config.getboolean(i, "enabled")

            if not enab:
                continue
            
            qst = QST(self.chatgui, self.config,
                      text=text, freq=int(freq))
            qst.enable()

            self.qsts.append(qst)

    def refresh_comm(self, rate, port):
        if self.comm:
            self.comm.disable()
            self.comm.close()
            
        self.comm = SerialCommunicator(rate=rate, port=port)
        self.comm.enable(self.chatgui)
        self.chatgui.comm = self.comm

        self.chatgui.display("Serial info: %s\n" % str(self.comm), ("blue"))
    
    def refresh_config(self):
        rate=self.config.config.getint("settings", "rate")
        port=self.config.config.get("settings", "port")
        call=self.config.config.get("user", "callsign")

        if self.comm:
            if self.comm.pipe.baudrate != rate or \
                self.comm.pipe.portstr != port:
                print "Serial config changed"
                self.refresh_comm(rate, port)
        else:
            self.refresh_comm(rate, port)

        self.chatgui.display("My Call: %s\n" % call, "blue")

        self.refresh_qsts()
        self.chatgui.refresh_colors()
        self.chatgui.refresh_advanced()

    def __init__(self):
        self.comm = None
        self.qsts = []

        gtk.gdk.threads_init()

        if os.name == "posix":
            self.config = config.UnixAppConfig(self)
        elif os.name == "nt":
            self.config = config.Win32AppConfig(self)
        else:
            self.config = config.AppConfig(self)

        self.chatgui = chatgui.ChatGUI(self.config)

        self.refresh_config()

        self.comm.enable(self.chatgui)
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
