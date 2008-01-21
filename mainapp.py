#!/usr/bin/python

import sys
import time
from threading import Thread

import serial
import gtk

import chatgui
import config

class SerialCommunicator:

    def __init__(self, port=0, rate=9600):
        self.pipe = serial.Serial(port=port, timeout=2, baudrate=rate)
        self.enabled = True

    def enable(self, gui):
        self.gui = gui
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
        if ":" in data:
            call, rest = data.split(":", 1)
            self.gui.display("%s:" % call, "blue")
            self.gui.display("%s\n" % rest)
        else:
            self.gui.display(data + "\n")

    def watch_serial(self):
        while self.enabled:
            size = self.pipe.inWaiting()
            if size > 0:
                data = self.pipe.read(size)
                #print "Got Data: %s" % data
                gtk.gdk.threads_enter()
                self.incoming_chat(data)
                gtk.gdk.threads_leave()
            else:
                time.sleep(1)

    def __str__(self):
        return "%s @ %i baud" % (self.pipe.portstr,
                                 self.pipe.getBaudrate())

class QST:
    def __init__(self, gui, text=None, freq=None):
        self.gui = gui
        self.text = text
        self.freq = freq
        self.enabled = False

    def enable(self):
        self.enabled = True
        self.thread = Thread(target=self.thread)
        self.thread.start()

    def disable(self):
        self.enabled = False
        self.thread.join()

    def thread(self):
        while self.enabled:
            time.sleep(self.freq)
            gtk.gdk.threads_enter()
            self.gui.tx_msg(self.text)
            gtk.gdk.threads_leave()
        

class MainApp:
    def setup_autoid(self):
        idtext = "(ID)"
            
        autoid = QST(self.chatgui,
                     freq=self.config.config.getint("prefs", "autoid_freq"),
                     text=idtext)
        autoid.enable()
        self.qsts.append(autoid)

    def __init__(self):
        gtk.gdk.threads_init()

        self.config = config.AppConfig()

        self.comm = SerialCommunicator(port=self.config.config.getint("settings",
                                                                   "port"),
                                       rate=self.config.config.getint("settings",
                                                                   "rate"))
        self.chatgui = chatgui.ChatGUI(self.comm, self.config)
        self.comm.enable(self.chatgui)

        self.chatgui.display("Serial info: %s\n" % str(self.comm), ("blue"))
        self.chatgui.display("My Call: %s\n" % self.config.config.get("user",
                                                                      "callsign"),
                             "blue")

        self.qsts = []

        if self.config.config.getboolean("prefs", "autoid"):
            self.setup_autoid()
            
    def main(self):

        try:
            gtk.gdk.threads_enter()
            gtk.main()
            gtk.gdk.threads_leave()
            self.config.save()
        except KeyboardInterrupt:
            pass
        
        self.comm.disable()

if __name__ == "__main__":
    app = MainApp()
    sys.exit(app.main())
