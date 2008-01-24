#!/usr/bin/python

import os
import sys
import time
from threading import Thread

import serial
import gtk

import chatgui
import config

from utils import hexprint
from qst import QST

class SerialCommunicator:

    def __init__(self, port=0, rate=9600):
        self.pipe = serial.Serial(port=port, timeout=2, baudrate=rate)
        self.pipe.setXonXoff(True)
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

        if ">" in data:
            call, data = data.split(">", 1)
            self.gui.display("%s>" % call, "blue")

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
    
    def refresh_config(self):
        if self.comm:
            self.comm.disable()
            self.comm.close()

        rate=self.config.config.get("settings", "rate")
        port=self.config.config.get("settings", "port")
        call=self.config.config.get("user", "callsign")
        self.comm = SerialCommunicator(rate=rate, port=port)
        self.comm.enable(self.chatgui)

        self.chatgui.comm = self.comm

        self.chatgui.display("Serial info: %s\n" % str(self.comm), ("blue"))
        self.chatgui.display("My Call: %s\n" % call, "blue")

        self.refresh_qsts()

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
