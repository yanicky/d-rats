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

import threading
import re
import time
import random

import ddt2

class BlockQueue:
    def __init__(self):
        self._lock = threading.Lock()
        self._queue = []

    def enqueue(self, block):
        self._lock.acquire()
        self._queue.insert(0, block)
        self._lock.release()

    def dequeue(self):
        self._lock.acquire()
        try:
            b = self._queue.pop()
        except IndexError:
            b = None
        self._lock.release()

        return b

    def dequeue_all(self):
        self._lock.acquire()
        l = self._queue
        self._queue = []
        self._lock.release()

        return l

    def peek(self):
        self._lock.acquire()
        try:
            el = self._queue[0]
        except:
            el = None
        self._lock.release()
        
        return el

    def peek_all(self):
        self._lock.acquire()
        q = self._queue
        self._lock.release()

        return q

class Transporter:
    def __init__(self, pipe, inhandler=None, compat=False):
        self.inq = BlockQueue()
        self.outq = BlockQueue()
        self.pipe = pipe
        self.inbuf = ""
        self.enabled = True
        self.inhandler = inhandler
        self.compat = compat

        self.thread = threading.Thread(target=self.worker)
        self.thread.start()

    def get_input(self):
        while True:
            chunk = self.pipe.read(64)
            if not chunk:
                break
            else:
                self.inbuf += chunk

    def _handle_frame(self, frame):
        if self.inhandler:
            self.inhandler(frame)
        else:
            self.inq.enqueue(frame)

    def parse_blocks(self):
        while ddt2.ENCODED_HEADER in self.inbuf and \
                ddt2.ENCODED_TRAILER in self.inbuf:
            s = self.inbuf.index(ddt2.ENCODED_HEADER)
            e = self.inbuf.index(ddt2.ENCODED_TRAILER) + \
                len(ddt2.ENCODED_TRAILER)

            if e < s:
                # Excise the extraneous end
                _tmp = self.inbuf[:e-len(ddt2.ENCODED_TRAILER)] + \
                    self.inbuf[e:]
                self.inbuf = _tmp
                continue

            block = self.inbuf[s:e]
            _tmp = self.inbuf[:s] + self.inbuf[e:]
            self.inbuf = _tmp

            f = ddt2.DDT2EncodedFrame()
            try:
                if f.unpack(block):
                    print "Got a block: %s" % f
                    self._handle_frame(f)
                else:
                    print "Found a broken block"
            except Exception, e:
                print "Failed to unpack what looked like a block: %s" % e

    def _match_gps(self):
        # NMEA-style
        m = re.match("^(.*)((\$GP[A-Z]{3},[^\r]*\r\n?){1,4}([^\r]*\r))(.*)", self.inbuf)
        if m:
            g = m.groups()
            return g[0], g[1], g[-1]
 
        # GPS-A style
        m = re.match("^(.*)(\$\$CRC[A-z0-9]{4},[^\r]*\r\n)(.*)", self.inbuf)
        if m:
            g = m.groups()
            return g[0], g[1], g[2]

        return None

    def _send_text_block(self, string):
        f = ddt2.DDT2EncodedFrame()
        f.seq = 0
        f.session = 1 # Chat (for now)
        f.s_station = "CQCQCQ"
        f.d_station = "CQCQCQ"
        f.data = string
        
        self._handle_frame(f)

    def _parse_gps(self):
        result = self._match_gps()
        if result:
            self.inbuf = result[0] + result[2]
            print "Found GPS string: %s" % {"" : result[1]}
            self._send_text_block(result[1])
        else:
            return None

    def parse_gps(self):
        while self._match_gps():
            self._parse_gps()
            
    def send_frames(self):
        while True:
            f = self.outq.dequeue()
            if not f:
                break

            print "Sending block: %s" % f
            self.pipe.write(f.get_packed())
            f.sent_event.set()

    def worker(self):
        while self.enabled:
            self.get_input()
            self.parse_blocks()
            self.parse_gps()
            if self.inbuf:
                if self.compat:
                    self._send_text_block(self.inbuf)
                else:
                    print "### Unconverted data: %s" % self.inbuf
                
            self.inbuf = ""
            self.send_frames()

    def disable(self):
        self.enabled = False
        self.thread.join()
        
    def send_frame(self, frame):
        self.outq.enqueue(frame)

    def recv_frame(self):
        return self.inq.dequeue()

class TestPipe:
    def make_fake_data(self, src, dst):
        self.buf = ""

        for i in range(10):
            f = ddt2.DDT2EncodedFrame()
            f.s_station = src
            f.d_station = dst
            f.type = 1
            f.seq = i
            f.session = 0
            f.data = "This is a test frame to parse"

            self.buf += "asg;sajd;jsadnkbasdl;b  as;jhd[SOB]laskjhd" + \
                "asdkjh[EOB]a;klsd" + f.get_packed() + "asdljhasd[EOB]" + \
                "asdljb  alsjdljn[asdl;jhas"
            
            if i == 5:
                self.buf += "$GPGGA,075519,4531.254,N,12259.400,W,1,3,0,0.0,M,0,M,,*55\r\nK7HIO   ,GPS Info\r"
            elif i == 7:
                self.buf += "$$CRC6CD1,Hills-Water-Treat-Plt>APRATS,DSTAR*:@233208h4529.05N/12305.91W>Washington County ARES;Hills Water Treat Pl\r\n"

            elif i == 2:
                self.buf += \
"""$GPGGA,023531.36,4531.4940,N,12254.9766,W,1,07,1.3,63.7,M,-21.4,M,,*64\r\n$GPRMC,023531.36,A,4531.4940,N,12254.9766,W,0.00,113.7,010808,17.4,E,A*27\rK7TAY M ,/10-13/\r"""
                

        print "Made some data: %s" % self.buf

    
    def __init__(self, src="Sender", dst="Recvr"):
        self.make_fake_data(src, dst)

    def read(self, count):
        if not self.buf:
            return ""

        num = random.randint(1,count)

        b = self.buf[:num]
        self.buf = self.buf[num:]

        return b

    def write(self, buf):
        pass

def test_simple():
    p = TestPipe()
    t = Transporter(p)
    
    f = ddt2.DDT2EncodedFrame()
    f.seq = 9
    f.type = 8
    f.session = 7
    f.d_station = "You"
    f.s_station = "Me"
    f.data = "ACK"
    t.send_frame(f)

    time.sleep(2)

    f = t.recv_frame()
    print "Received block: %s" % f

    t.disable()

if __name__ == "__main__":
    test_simple()
