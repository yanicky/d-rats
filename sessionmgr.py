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

import time
import threading

from ddt2 import DDT2EncodedFrame
import transport

class Block:
    def __init__(self):
        self.seq = 0
        self.type = 0
        self.data = ""
        self.source = ""
        self.destination = ""
        self.consistent = False

    def set_seq(self, seq):
        self.seq = int(seq)

    def set_type(self, type):
        self.type = int(type)

    def set_data(self, data):
        self.data = data

    def set_station(self, src, dst):
        self.source = src
        self.destination = dst

    def get_info(self):
        return (self.seq, self.type, self.source, self.destination)

    def get_consistent(self):
        return self.consistent

    def get_data(self):
        return self.data

class Session:
    _sm = None
    _id = None
    _st = None

    def __init__(self, name):
        self.name = name
        self.inq = transport.BlockQueue()
        self.handler = None

    def send_blocks(self, blocks):
        for b in blocks:
            self._sm.outgoing(self, b)

    def recv_blocks(self):
        return self.inq.dequeue_all()

    def close(self):
        if self._sm:
            self._sm.stop_session(self)

    def notify(self):
        pass

class ControlSession(Session):
    stateless = True

    T_NEW = 0
    T_END = 1
    T_ACK = 2

    def ctl(self, frame):
        if frame.type == self.T_ACK:
            try:
                id = int(frame.data)
                ev = self.pending_reqs[id]
                ev.set()
                print "Signaled waiting session thread"
            except Exception, e:
                print "Failed to lookup new session event: %s" % e
        elif frame.type == self.T_END:
            print "End of session %s" % frame.data
        elif frame.type == self.T_NEW:
            try:
                id = int(frame.data)
            except Exception, e:
                print "Session request had invalid ID: %s" % e
                return

            print "ACK'ing session request for %i" % id

            s = StatefulSession("session")
            self._sm._register_session(id, s, frame.s_station)

            f = DDT2EncodedFrame()
            f.type = self.T_ACK
            f.seq = 0
            f.d_station = frame.s_station
            f.data = frame.data
            self._sm.outgoing(self, f)
        else:
            print "Unknown control message type %i" % frame.type
            

    def new_session(self, name, dest, id):
        ev = threading.Event()
        self.pending_reqs[id] = ev

        f = DDT2EncodedFrame()
        f.type = self.T_NEW
        f.seq = 0
        f.d_station = dest
        f.data = str(id)

        for i in range(0,10):
            self._sm.outgoing(self, f)

            f.event.wait(10)
            f.event.clear()

            print "Sent request, blocking..."
            ev.wait(5)

            if not ev.isSet():
                print "Trying again..."
            else:
                print "Established session"
                del self.pending_reqs[id]
                return True


        del self.pending_reqs[id]
        print "Failed to establish session"
        return False
        

    def __init__(self):
        self.name = "control"
        self.handler = self.ctl

        self.pending_reqs = {}

class StatelessSession(Session):
    stateless = True

class StatefulSession(Session):
    stateless = False

    T_SYN = 0
    T_ACK = 1
    T_NAK = 2
    T_FIN = 3
    T_DAT = 4

    def __init__(self, name, bsize=512):
        Session.__init__(self, name)
        self.outq = transport.BlockQueue()
        self.enabled = True
        self.bsize = bsize
        self.iseq = -1
        self.oseq = 0

        self.outstanding = None

        self.data = transport.BlockQueue()

        self.ts = 0

        self.event = threading.Event()
        self.thread = threading.Thread(target=self.worker)
        self.thread.start()

    def notify(self):
        self.event.set()

    def close(self):
        self.enabled = False
        self.thread.join()

        Session.close(self)

    def send_blocks(self):
        if not self.outstanding:
            self.outstanding = self.outq.dequeue()

        if self.outstanding and time.time() - self.ts > 3:
            self._sm.outgoing(self, self.outstanding)
            t = time.time()
            print "Waiting for block to be sent..." 
            self.outstanding.event.wait()
            self.outstanding.event.clear()
            print "Block sent after: %f" % (time.time() - t)

            self.ts = time.time()

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
                    self.outstanding = None
                else:
                    print "Got ACK but no block sent!"
            elif b.type == self.T_DAT:
                print "Sending ACK for %s" % b.data
                self.send_ack(b.seq)
                if b.seq == self.iseq + 1:
                    print "Queuing data for %i" % b.seq
                    self.data.enqueue(b.data)
                    self.iseq = (self.iseq + 1) % 256
                else:
                    print "Dropping duplicate block %i" % b.seq
            else:
                print "Got unknown type: %i" % b.type

    def worker(self):
        def cmp_blocks(a, b):
            return a.seq - b.seq

        while self.enabled:
            if not self.event.isSet():
                self.event.wait(3)
                self.event.clear()
            print "Session loop"
            self.send_blocks()
            self.recv_blocks()

    def read(self, count):
        buf = ""
        i = 0

        while i < count and i+len(self.data.peek()) < count:
            b += self.data.pop()

        return b

    def write(self, buf):
        while buf:
            chunk = buf[:self.bsize]
            buf = buf[self.bsize:]

            f = DDT2EncodedFrame()
            f.seq = self.oseq
            f.type = self.T_DAT
            f.data = chunk

            self.outq.enqueue(f)

            self.oseq = (self.oseq + 1) % 256

        self.event.set()

class SessionManager:
    def __init__(self, pipe, station):
        self.pipe = pipe
        self.station = station

        self.sessions = {}

        self.tport = transport.Transporter(self.pipe, self.incoming)

        self.control = ControlSession()
        self._register_session(0, self.control, "CQCQCQ")

    def shutdown(self):
        for s in self.sessions.values():
            print "Stopping session `%s'" % s.name
            s.close()

        self.tport.disable()

    def incoming(self, frame):
        if frame.d_station != "CQCQCQ" and \
                frame.d_station != self.station:
            print "Received frame for station `%s'" % frame.d_station
            return

        if not frame.session in self.sessions.keys():
            print "Incoming frame for unknown session `%i'" % frame.session
            return

        session = self.sessions[frame.session]

        if session.stateless == False and \
                session._st != frame.s_station:
            print "Received frame from invalid station `%s' (expecting `%s'" % (frame.s_station, session._st)
            return

        if session.handler:
            session.handler(frame)
        else:
            session.inq.enqueue(frame)
            session.notify()

        print "Received block %i:%i for session `%s'" % (frame.seq,
                                                         frame.type,
                                                         session.name)

    def outgoing(self, session, block):
        if not block.d_station:
            block.d_station = session._st
            
        block.s_station = self.station

        block.session = session._id

        self.tport.send_frame(block)

    def _register_session(self, id, session, dest):
        print "Registered session %i: %s" % (id, session.name)
        session._sm = self
        session._id = id
        session._st = dest
        self.sessions[id] = session

    def new_session(self, id, name, dest):
        if dest:
            s = StatefulSession(name)
            if not self.control.new_session(name, dest, id):
                return None
        else:
            s = StatelessSession(name)
            dest = "CQCQCQ"
        
        self._register_session(id, s, dest)
        return s

    def start_session(self, name, dest=None):
        for id in range(0, 256):
            if id not in self.sessions.keys():
                return self.new_session(id, name, dest)

        return None

    def stop_session(self, session):
        for id, s in self.sessions.items():
            if session.name == s.name:
                del self.sessions[id]
                return True

        return False

if __name__ == "__main__":
    #p = transport.TestPipe(dst="KI4IFW")

    import comm
    import sys

    if sys.argv[1] == "KI4IFW":
        p = comm.SerialDataPath(("/dev/ttyUSB0", 9600))
    else:
        p = comm.SerialDataPath(("/dev/ttyUSB0", 38400))

    #p = comm.SocketDataPath(("localhost", 9000))
    #p.make_fake_data("SOMEONE", "CQCQCQ")
    p.connect()
    sm = SessionManager(p, sys.argv[1])
    s = sm.start_session("chat")

    if sys.argv[1] == "KI4IFW":
        f = file("inputdialog.py")
        S = sm.start_session("xfer", "K7TAY")
        if S:
            S.write(f.read())

    try:
        time.sleep(300)
    except:
        pass

    

    sm.shutdown()

    blocks = s.recv_blocks()
    for b in blocks:
        print "Chat message: %s: %s" % (b.get_info()[2], b.get_data())
