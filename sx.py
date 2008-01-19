#!/usr/bin/python

import sys
import os

import xmodem

global x

from ptyhelper import safe_read, safe_write

class STDIOHelper:
    def __init__(self, timeout=4):
        self.timeout = timeout
    
    def read(self, count):
        return safe_read(sys.stdin.fileno(), count, self.timeout)
    
    def write(self, buf):
        return safe_write(sys.stdout.fileno(), buf, self.timeout)

i = file(sys.argv[1], "r")
x = xmodem.XModem(debug="sx.debug")
h = STDIOHelper()
h.write("Starting...\n")
try:
    x.send_xfer(h, i)
except Exception, e:
    x.debug("Exception: %s" % str(e))
