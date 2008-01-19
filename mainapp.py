#!/usr/bin/python

import sys
import time
from threading import Thread

import serial
import gtk

import chatgui

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
        self.enabled = False
        print "Waiting for thread..."
        self.thread.join()

    def send_text(self, text):
        return self.pipe.write(text)

    def watch_serial(self):
        while self.enabled:
            size = self.pipe.inWaiting()
            if size > 0:
                data = self.pipe.read(size)
                print "Got Data: %s" % data
                gtk.gdk.threads_enter()
                # FIXME
                self.gui.add_to_main_buffer("Remote: ", data)
                gtk.gdk.threads_leave()
            else:
                time.sleep(1)

    def __str__(self):
        return "Port: %s, %i baud" % (self.pipe.portstr,
                                      self.pipe.getBaudrate())

# FIXME: Need a name
class MainApp:
    def __init__(self):
        gtk.gdk.threads_init()

        self.comm = SerialCommunicator()
        self.chatgui = chatgui.ChatGUI(self.comm)
        self.comm.enable(self.chatgui)

        self.chatgui.add_to_main_buffer("Serial info: ",
                                        str(self.comm))

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
