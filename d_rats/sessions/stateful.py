#!/usr/bin/python
#
# Copyright 2009 Dan Smith <dsmith@danplanet.com>
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
import time

from d_rats import transport
from d_rats.ddt2 import DDT2EncodedFrame
from d_rats.sessions import base

class StatefulSession(base.Session):
    stateless = False
    type = base.T_GENERAL

    T_SYN = 0
    T_ACK = 1
    T_NAK = 2
    T_DAT = 4

    IDLE_TIMEOUT = 90

    def __init__(self, name, **kwargs):
        base.Session.__init__(self, name)
        self.outq = transport.BlockQueue()
        self.enabled = True

        self.bsize = kwargs.get("blocksize", 1024)
        self.iseq = -1
        self.oseq = 0

        self.outstanding = None

        self.data = transport.BlockQueue()
        self.data_waiting = threading.Condition()

        self.ts = 0
        self.attempts = 0
        self.ack_timeout = 8

        self.event = threading.Event()
        self.thread = threading.Thread(target=self.worker)
        self.thread.setDaemon(True)
        self.thread.start()

    def notify(self):
        self.event.set()

    def close(self, force=False):

        import traceback
        import sys
        traceback.print_stack(file=sys.stdout)

        print "Got close request, joining thread..."
        self.enabled = False
        self.notify()

        # Free up any block listeners
        if isinstance(self.outstanding, list):
            for b in self.outstanding:
                b.sent_event.set()
                b.sent_event.clear()
                b.ackd_event.set()
                
        elif self.outstanding:
            b.sent_event.set()                

        self.thread.join()
        print "Thread is done, continuing with close"

        base.Session.close(self, force)

    def queue_next(self):
        if not self.outstanding:
            self.outstanding = self.outq.dequeue()
            self.ts = 0
            self.attempts = 0

    def is_timeout(self):
        if self.ts == 0:
            return True

        if (time.time() - self._sm.last_frame) < 3:
            return False

        if (time.time() - self.ts) < self.ack_timeout:
            return False

        return True

    def send_blocks(self):
        self.queue_next()

        if self.outstanding and self.is_timeout():
            if self.attempts:
                self.stats["retries"] += 1

            if self.attempts == 10:
                print "Too many retries, closing..."
                self.set_state(self.ST_CLSD)
                self.enabled = False
                return

            self.attempts += 1
            print "Attempt %i" % self.attempts

            self._sm.outgoing(self, self.outstanding)
            t = time.time()
            print "Waiting for block to be sent..." 
            self.outstanding.sent_event.wait()
            self.outstanding.sent_event.clear()
            self.ts = time.time()
            print "Block sent after: %f" % (self.ts - t)

    def send_ack(self, seq):
        f = DDT2EncodedFrame()
        f.seq = 0
        f.type = self.T_ACK
        f.data = str(seq)

        self._sm.outgoing(self, f)

    def recv_blocks(self):
        blocks = self.inq.dequeue_all()

        for b in blocks:
            if b.type == self.T_ACK:
                # FIXME: lock here
                if self.outstanding:
                    print "Got ACK for %s" % b.data
                    self.outstanding.ackd_event.set()
                    self.stats["sent_size"] += len(self.outstanding.data)
                    self.attempts = 0
                    self.outstanding = None
                else:
                    print "Got ACK but no block sent!"
            elif b.type == self.T_DAT:
                print "Sending ACK for %s" % b.data
                self.send_ack(b.seq)
                self.stats["recv_wire"] += len(b.data)
                if b.seq == self.iseq + 1:
                    print "Queuing data for %i" % b.seq
                    self.stats["recv_size"] += len(b.data)

                    self.data_waiting.acquire()
                    self.data.enqueue(b.data)
                    self.data_waiting.notify()
                    self.data_waiting.release()

                    self.iseq = (self.iseq + 1) % 256
                else:
                    print "Dropping duplicate block %i" % b.seq
            else:
                print "Got unknown type: %i" % b.type

    def worker(self):
        while self.enabled:
            self.send_blocks()
            self.recv_blocks()

            if not self.outstanding and self.outq.peek():
                print "Short-circuit"
                continue # Short circuit because we have things to send

            print "Session loop (%s:%s)" % (self._id, self.name)

            if self.outstanding:
                print "Outstanding data, short sleep"
                self.event.wait(1)
            else:
                print "Deep sleep"
                self.event.wait(self.IDLE_TIMEOUT)
                if not self.event.isSet():
                    print "Session timed out!"
                    self.set_state(self.ST_CLSD)
                    self.enabled = False                    
                else:
                    print "Awoke from deep sleep to some data"
                    
            self.event.clear()
            
    def _block_read_for(self, count):
        waiting = self.data.peek_all()

        if not count and not waiting:
            self.data_waiting.wait(1)
            return

        if count > len("".join(waiting)):
            self.data_waiting.wait(1)
            return

    def _read(self, count):
        self.data_waiting.acquire()

        self._block_read_for(count)

        if count == None:
            b = self.data.dequeue_all()
            # BlockQueue.dequeue_all() returns the blocks in poppable order,
            # which is newest first
            b.reverse()
            buf = "".join(b)
        else:
            buf = ""
            i = 0
            while True:
                next = self.data.peek() or ''
                if len(next) > 0 and (len(next) + i) < count:
                    buf += self.data.dequeue()
                else:
                    break

        self.data_waiting.release()

        return buf

    def read(self, count=None):
        while self.get_state() == self.ST_SYNC:
            print "Waiting for session to open"
            self.wait_for_state_change(5)

        if self.get_state() != self.ST_OPEN:
            raise base.SessionClosedError("State is %i" % self.get_state())

        buf = self._read(count)

        if not buf and self.get_state() != self.ST_OPEN:
            raise base.SessionClosedError()

        return buf

    def write(self, buf, timeout=0):
        while self.get_state() == self.ST_SYNC:
            print "Waiting for session to open"
            self.wait_for_state_change(5)

        if self.get_state() != self.ST_OPEN:
            raise base.SessionClosedError("State is %s" % self.get_state())

        blocks = []

        while buf:
            chunk = buf[:self.bsize]
            buf = buf[self.bsize:]

            f = DDT2EncodedFrame()
            f.seq = self.oseq
            f.type = self.T_DAT
            f.data = chunk
            f.sent_event.clear()

            self.outq.enqueue(f)
            blocks.append(f)

            self.oseq = (self.oseq + 1) % 256

        self.queue_next()
        self.event.set()

        while timeout is not None and \
                blocks and \
                self.get_state() != self.ST_CLSD:
            block = blocks[0]
            del blocks[0]

            print "Waiting for block %i to be ack'd" % block.seq
            block.sent_event.wait()
            if block.sent_event.isSet():
                print "Block %i is sent, waiting for ack" % block.seq
                block.ackd_event.wait(timeout)
                if block.ackd_event.isSet() and block.sent_event.isSet():
                    print "%i ACKED" % block.seq
                else:
                    print "%i Not ACKED (probably canceled)" % block.seq
                    break
            else:
                print "Block %i not sent?" % block.seq

class PipelinedStatefulSession(StatefulSession):
    T_REQACK = 5

    def __init__(self, *args, **kwargs):
        self.oob_queue = {}
        self.recv_list = []

        if kwargs.has_key("outlimit"):
            self.out_limit = kwargs["outlimit"]
            del kwargs["outlimit"]
        else:
            self.out_limit = 8

        StatefulSession.__init__(self, *args, **kwargs)
        self.outstanding = []
        self.waiting_for_ack = []

    def queue_next(self):
        if self.outstanding is None:
            # This is a silly race condition because the worker thread is
            # started in the init, which might run before we set our values
            # after the superclass init
            return

        count = self.out_limit - len(self.outstanding)
        if len(self.outstanding) >= self.out_limit:
            return

        for i in range(count):
            b = self.outq.dequeue()
            if b:
                if b.seq == 0 and self.outstanding:
                    print "### Pausing at rollover boundary ###"
                    self.outq.requeue(b)
                    break

                print "Queuing %i for send (%i)" % (b.seq, count)
                self.outstanding.append(b)
                self.ts = 0
                self.attempts = 0
            else:
                break

    def send_reqack(self, blocks):
        f = DDT2EncodedFrame()
        f.seq = 0
        f.type = self.T_REQACK
        # FIXME: This needs to support 16-bit block numbers!
        f.data = "".join([chr(x) for x in blocks])

        print "Requesting ack of blocks %s" % blocks
        self._sm.outgoing(self, f)

    def send_blocks(self):
        self.queue_next()

        if not self.outstanding:
            # nothing to send
            return

        if self.outstanding and not self.is_timeout():
            # Not time to try again yet
            return
        
        if self.stats["retries"] >= 10:
            print "Too many retries, closing..."
            self.set_state(self.ST_CLSD)
            self.enabled = False
            return

        # Short circuit to just an ack for outstanding blocks, if
        # we're still waiting for an ack from remote.  Increase the timeout
        # for the ack by four seconds each time to give some backoff
        if self.waiting_for_ack:
            print "Didn't get last ack, asking again"
            self.send_reqack(self.waiting_for_ack)
            self.ts = time.time()
            self.ack_timeout += 4
            return

        toack = []

        last_block = None
        for b in self.outstanding:
            if b.sent_event.isSet():
                self.attempts += 1
                self.stats["retries"] += 1
                b.sent_event.clear()

            print "Sending %i" % b.seq
            self._sm.outgoing(self, b)
            toack.append(b.seq)
            t = time.time()

            if last_block:
                last_block.sent_event.wait()
                self.stats["sent_wire"] += len(last_block.data)

            last_block = b

        self.send_reqack(toack)
        self.waiting_for_ack = toack

        self.attempts = 0
        self.ts = 0

        print "Waiting for block to be sent"
        last_block.sent_event.wait()
        self.stats["sent_wire"] += len(last_block.data)
        self.ts = time.time()
        print "Block sent after: %f" % (self.ts - t)

    def send_ack(self, blocks):
        f = DDT2EncodedFrame()
        f.seq = 0
        f.type = self.T_ACK
        f.data = "".join([chr(x) for x in blocks])

        print "Acking blocks %s (%s)" % (blocks,
                                         {"" : f.data})

        self._sm.outgoing(self, f)

    def recv_blocks(self):
        blocks = self.inq.dequeue_all()
        blocks.reverse()

        def next(i):
            # FIXME: For 16 bit blocks
            return (i + 1) % 256

        def enqueue(_block):
            self.data_waiting.acquire()
            self.data.enqueue(_block.data)
            self.iseq = _block.seq
            self.data_waiting.notify()
            self.data_waiting.release()

        for b in blocks:
            if b.type == self.T_ACK:
                self.waiting_for_ack = False
                acked = [ord(x) for x in b.data]
                print "Acked blocks: %s (/%i)" % (acked, len(self.outstanding))
                for block in self.outstanding[:]:
                    if block.seq in acked:
                        print "Acked block %i" % block.seq
                        block.ackd_event.set()
                        self.stats["sent_size"] += len(block.data)
                        self.outstanding.remove(block)
                    else:
                        print "Block %i outstanding, but not acked" % block.seq
            elif b.type == self.T_DAT:
                print "Got block %i" % b.seq
                # FIXME: For 16-bit blocks
                if b.seq == 0 and self.iseq == 255:
                    # Reset received list, because remote will only send
                    # a block 0 following a block 255 if it has received
                    # our ack of the previous 0-255
                    self.recv_list = []

                if b.seq not in self.recv_list:
                    self.recv_list.append(b.seq)
                    self.stats["recv_size"] += len(b.data)
                    self.oob_queue[b.seq] = b
            elif b.type == self.T_REQACK:
                toack = []

                # FIXME: This needs to support 16-bit block numbers!
                for i in [ord(x) for x in b.data]:
                    if i in self.recv_list:
                        print "Acking block %i" % i
                        toack.append(i)
                    else:
                        print "Naking block %i" % i

                self.send_ack(toack)
            else:
                print "Got unknown type: %i" % b.type

        if self.oob_queue:
            print "Waiting OOO blocks: %s" % self.oob_queue.keys()

        # Process any OOO blocks, if we should
        while next(self.iseq) in self.oob_queue.keys():
            block = self.oob_queue[next(self.iseq)]
            print "Queuing now in-order block %i: %s" % (next(self.iseq),
                                                         block)
            del self.oob_queue[next(self.iseq)]
            enqueue(block)            
