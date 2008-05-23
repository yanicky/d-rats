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
        el = self._queue[0]
        self._lock.release()
        
        return el

class Transporter:
    def __init__(self, pipe, inhandler=None):
        self.inq = BlockQueue()
        self.outq = BlockQueue()
        self.pipe = pipe
        self.inbuf = ""
        self.enabled = True
        self.inhandler = inhandler

        self.thread = threading.Thread(target=self.worker)
        self.thread.start()

    def get_input(self):
        while True:
            chunk = self.pipe.read(64)
            if not chunk:
                break
            else:
                self.inbuf += chunk

    def parse_blocks(self):
        while ddt2.ENCODED_HEADER in self.inbuf:
            s = self.inbuf.index(ddt2.ENCODED_HEADER)
            e = self.inbuf.index(ddt2.ENCODED_TRAILER) + \
                len(ddt2.ENCODED_TRAILER)

            block = self.inbuf[s:e]
            self.inbuf = self.inbuf[e:]

            f = ddt2.DDT2EncodedFrame()
            if f.unpack(block):
                print "Got a block: %s" % f
                if self.inhandler:
                    self.inhandler(f)
                else:
                    self.inq.enqueue(f)
            else:
                print "Found a broken block"

    def send_frames(self):
        while True:
            f = self.outq.dequeue()
            if not f:
                break

            print "Sending block: %s" % f
            self.pipe.write(f.get_packed())
            f.event.set()

    def worker(self):
        while self.enabled:
            self.get_input()
            self.parse_blocks()
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

        print "Made some data"

    
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

    f = t.recv_block()
    print "Received block: %s" % f

    t.disable()

if __name__ == "__main__":
    test_simple()
