#!/usr/bin/python

import sys
import os

import xmodem

class STDIOHelper:
    def __init__(self):
        pass
    
    def read(self, count):
        debug.write("doing read of %i\n" % count)
        data = ""
        while len(data) < count:
            _data = os.read(sys.stdin.fileno(), count - len(data))
            data += _data
            debug.write("Read %i/%i/%i\n" % (len(_data), len(data), count))

        return data

    def write(self, buf):
        count = 0
        debug.write("doing write: %s\n" % buf)
        while count < len(buf):
            r = os.write(sys.stdin.fileno(), buf[count:])
            count += r
            debug.write("Wrote %i/%i/%i\n" % (r, count, len(buf)))

print "Going..."
i = file(sys.argv[1], "r")
global debug
debug = file("debug", "w", 0)
print "Opened"
x = xmodem.XModem(debug="sx.debug")
h = STDIOHelper()
h.write("Starting...\n")
try:
    x.send_xfer(h, i)
except Exception, e:
    x.debug("Exception: %s" % str(e))
