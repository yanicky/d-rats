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

import struct
import zlib
import base64

import threading

ENCODED_HEADER = "[SOB]"
ENCODED_TRAILER = "[EOB]"

def update_crc(c, crc):
    for _ in range(0,8):
        c <<= 1

        if (c & 0400) != 0:
            v = 1
        else:
            v = 0
            
        if (crc & 0x8000):
            crc <<= 1
            crc += v
            crc ^= 0x1021
        else:
            crc <<= 1
            crc += v

    return crc & 0xFFFF

def calc_checksum(data):
    checksum = 0
    for i in data:
        checksum = update_crc(ord(i), checksum)

    checksum = update_crc(0, checksum)
    checksum = update_crc(0, checksum)

    return checksum

def encode(data):
    return base64.encodestring(data)

def decode(data):
    return base64.decodestring(data)

class DDT2Frame:
    format = "!BHBBHH8s8s"

    def __init__(self):
        self.seq = 0
        self.session = 0
        self.type = 0
        self.d_station = ""
        self.s_station = ""
        self.data = ""
        self.magic = 0xDD

        self.sent_event = threading.Event()
        self.ackd_event = threading.Event()

    def get_packed(self):
        data = zlib.compress(self.data, 9)
        length = len(data)
        
        checksum = calc_checksum(data)

        val = struct.pack(self.format,
                          self.magic,
                          self.seq,
                          self.session,
                          self.type,
                          checksum,
                          length,
                          self.s_station,
                          self.d_station)

        return val + data

    def unpack(self, val):
        header = val[:25]
        data = val[25:]

        (magic, self.seq, self.session, self.type,
         checksum, length,
         self.s_station, self.d_station) = struct.unpack(self.format, header)

        self.s_station = self.s_station.replace("\x00", "")
        self.d_station = self.d_station.replace("\x00", "")

        if calc_checksum(data) != checksum:
            print "Checksum failed: %s" % calc_checksum(self.data)
            return False

        self.data = zlib.decompress(data)

        return True

    def __str__(self):
        return "DDT2: %i:%i:%i %s->%s (%s...)" % (self.seq,
                                                  self.session,
                                                  self.type,
                                                  self.s_station,
                                                  self.d_station,
                                                  self.data[:20])

class DDT2EncodedFrame(DDT2Frame):
    def get_packed(self):
        raw = DDT2Frame.get_packed(self)

        encoded = encode(raw)

        return ENCODED_HEADER + encoded + ENCODED_TRAILER

    def unpack(self, val):
        try:
            h = val.index(ENCODED_HEADER) + len(ENCODED_TRAILER)
            t = val.rindex(ENCODED_TRAILER)
            payload = val[h:t]
        except Exception, e:
            print "Block has no header/trailer: %s" % e
            return False

        try:
            decoded = decode(payload)
        except Exception, e:
            print "Unable to decode frame: %s" % e
            return False

        return DDT2Frame.unpack(self, decoded)

def test_symmetric():
    fin = DDT2EncodedFrame()
    fin.type = 1
    fin.session = 2
    fin.seq = 3
    fin.s_station = "FOO"
    fin.d_station = "BAR"
    fin.data = "This is a test"

    p = fin.get_packed()

    print p

    fout = DDT2EncodedFrame()
    fout.unpack(p)

    #print fout.__dict__
    print fout

def test_crap():
    f = DDT2EncodedFrame()
    f.unpack("[SOB]foobar[EOB]")

if __name__ == "__main__":
    test_symmetric()
    test_crap()
