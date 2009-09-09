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
import traceback
import sys

import utils
import ddt2
import comm

class BlockQueue(object):
    def __init__(self):
        self._lock = threading.Lock()
        self._queue = []

    def enqueue(self, block):
        self._lock.acquire()
        self._queue.insert(0, block)
        self._lock.release()

    def requeue(self, block):
        self._lock.acquire()
        self._queue.append(block)
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

    # BE CAREFUL WITH THESE!

    def lock(self):
        self._lock.acquire()

    def unlock(self):
        self._lock.release()

class Transporter(object):
    def __init__(self, pipe, inhandler=None, **kwargs):
        self.inq = BlockQueue()
        self.outq = BlockQueue()
        self.pipe = pipe
        self.inbuf = ""
        self.enabled = True
        self.inhandler = inhandler
        self.compat = kwargs.get("compat", False)
        self.warmup_length = kwargs.get("warmup_length", 8)
        self.warmup_timeout = kwargs.get("warmup_timeout", 3)
        self.force_delay = kwargs.get("force_delay", 0)

        self.thread = threading.Thread(target=self.worker)
        self.thread.setDaemon(True)
        self.thread.start()

        self.last_xmit = 0

    def __send(self, data):
        for i in range(0, 10):
            try:
                return self.pipe.write(data)
            except comm.DataPathIOError, e:
                if not self.pipe.can_reconnect:
                    break
                print "Data path IO error: %s" % e
                try:
                    time.sleep(i)
                    print "Attempting reconnect..."
                    self.pipe.reconnect()
                except comm.DataPathNotConnectedError:
                    pass

        raise comm.DataPathIOError("Unable to reconnect")

    def __recv(self, size):
        data = ""
        for i in range(0, 10):
            try:
                return self.pipe.read(size - len(data))
            except comm.DataPathIOError, e:
                if not self.pipe.can_reconnect:
                    break
                print "Data path IO error: %s" % e
                try:
                    time.sleep(i) 
                    print "Attempting reconnect..."
                    self.pipe.reconnect()
                except comm.DataPathNotConnectedError:
                    pass

        raise comm.DataPathIOError("Unable to reconnect")

    def get_input(self):
        while True:
            chunk = self.__recv(64)
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
            self.inbuf = self.inbuf[e:]

            f = ddt2.DDT2EncodedFrame()
            try:
                if f.unpack(block):
                    print "Got a block: %s" % f
                    self._handle_frame(f)
                elif self.compat:
                    self._send_text_block(block)
                else:
                    print "Found a broken block (S:%i E:%i len(buf):%i" % (\
                        s, e, len(self.inbuf))
            except Exception, e:
                print "Failed to process block:"
                utils.log_exception()

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
        f.data = utils.filter_to_ascii(string)
        
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
        delayed = False

        while True:
            f = self.outq.dequeue()
            if not f:
                break

            if self.force_delay and not delayed:
                print "Waiting %i sec before transmitting" % self.force_delay
                time.sleep(self.force_delay)
                delayed = True

            if ((time.time() - self.last_xmit) > self.warmup_timeout) and \
                    (self.warmup_timeout > 0):
                warmup_f = ddt2.DDT2EncodedFrame()
                warmup_f.seq = 0
                warmup_f.session = 0
                warmup_f.type = 254
                warmup_f.s_station = "!"
                warmup_f.d_station = "!"
                warmup_f.data = ("\x01" * self.warmup_length)
                warmup_f.set_compress(False)
                print "Sending warm-up: %s" % warmup_f
                self.__send(warmup_f.get_packed())

            print "Sending block: %s" % f
            self.__send(f.get_packed())
            f.sent_event.set()
            self.last_xmit = time.time()

    def worker(self):
        while self.enabled:
            try:
                self.get_input()
            except Exception, e:
                print "Exception while getting input: %s" % e
                self.enabled = False
                break

            self.parse_blocks()
            self.parse_gps()
            if self.inbuf:
                if self.compat:
                    self._send_text_block(self.inbuf)
                else:
                    print "### Unconverted data: %s" % self.inbuf
                
            self.inbuf = ""
            try:
                self.send_frames()
            except Exception, e:
                print "Exception while sending frames: %s" % e
                self.enabled = False
                break

    def disable(self):
        self.inhandler = None
        self.enabled = False
        self.thread.join()
        
    def send_frame(self, frame):
        self.outq.enqueue(frame)

    def recv_frame(self):
        return self.inq.dequeue()

    def flush_blocks(self, id):
        # This should really call a flush method in the blockqueue with a
        # test function
        self.outq.lock()
        for b in self.outq._queue[:]:
            if b.session == id:
                print "Flushing block: %s" % b
                try:
                    self.outq._queue.remove(b)
                except ValueError:
                    print "Block disappeared while flushing?"
        self.outq.unlock()

    def __str__(self):
        return str(self.pipe)

class TestPipe(object):
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
