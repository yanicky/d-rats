#!/usr/bin/python

import sys
import os

import xmodem

global x

class STDIOHelper:
    def __init__(self):
        pass
    
    def read(self, count):
        x.debug("doing read of %i" % count)
        data = ""
        while len(data) < count:
            _data = os.read(sys.stdin.fileno(), count - len(data))
            data += _data
            x.debug("Read %i/%i/%i" % (len(_data), len(data), count))

        return data

    def write(self, buf):
        count = 0
        x.debug("doing write: %s" % buf)
        while count < len(buf):
            r = os.write(sys.stdin.fileno(), buf[count:])
            count += r
            x.debug("Wrote %i/%i/%i" % (r, count, len(buf)))

i = file(sys.argv[1], "r")
x = xmodem.XModem(debug="sx.debug")
h = STDIOHelper()
h.write("Starting...\n")
try:
    x.send_xfer(h, i)
except Exception, e:
    x.debug("Exception: %s" % str(e))
