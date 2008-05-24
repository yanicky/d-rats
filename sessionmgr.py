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

    ST_OPEN = 0
    ST_CLSD = 1
    ST_SYNC = 2

    def __init__(self, name):
        self.name = name
        self.inq = transport.BlockQueue()
        self.handler = None
        self.state_event = threading.Event()
        self.state = self.ST_CLSD

    def send_blocks(self, blocks):
        for b in blocks:
            self._sm.outgoing(self, b)

    def recv_blocks(self):
        return self.inq.dequeue_all()

    def close(self, force=False):
        if force:
            self.state = self.ST_CLSD

        if self._sm:
            self._sm.stop_session(self)

    def notify(self):
        pass

    def read(self):
        pass

    def write(self, dest="CQCQCQ"):
        pass

    def set_state(self, state):
        if state not in [self.ST_OPEN, self.ST_CLSD, self.ST_SYNC]:
            return False

        self.state = state
        self.state_event.set()

    def get_state(self):
        return self.state

    def wait_for_state_change(self, timeout=None):
        before = self.state

        self.state_event.clear()
        self.state_event.wait(timeout)

        return self.state != before

class ControlSession(Session):
    stateless = True

    T_PNG = 0
    T_END = 1
    T_ACK = 2
    T_NEW_STRM = 3
    T_NEW_XFER = 4
    T_NEW = 5 # General purpose session

    def ack_req(self, dest, data):
        f = DDT2EncodedFrame()
        f.type = self.T_ACK
        f.seq = 0
        f.d_station = dest
        f.data = data
        self._sm.outgoing(self, f)

    def ctl(self, frame):
        if frame.type == self.T_ACK:
            try:
                id = int(frame.data)
                session = self._sm.sessions[id]
                session.set_state(session.ST_OPEN)
                print "Signaled waiting session thread"
            except Exception, e:
                print "Failed to lookup new session event: %s" % e
        elif frame.type == self.T_END:
            print "End of session %s" % frame.data

            try:
                id = int(frame.data)
            except Exception, e:
                print "Session end request had invalid ID: %s" % e
                return

            try:
                session = self._sm.sessions[id]
                session.set_state(session.ST_CLSD)
                self._sm.stop_session(session)
            except Exception, e:
                print "Session %s ended but not registered" % id
                return

            self.ack_req(frame.s_station, frame.data)

        elif frame.type == self.T_NEW:
            try:
                id = int(frame.data)
            except Exception, e:
                print "Session request had invalid ID: %s" % e
                return

            print "ACK'ing session request for %i" % id

            s = StatefulSession("session")
            self._sm._register_session(id, s, frame.s_station)

            self.ack_req(frame.s_station, frame.data)
        else:
            print "Unknown control message type %i" % frame.type
            

    def new_session(self, session):
        f = DDT2EncodedFrame()
        f.type = self.T_NEW
        f.seq = 0
        f.d_station = session._st
        f.data = str(session._id)

        wait_time = 5

        for i in range(0,10):
            self._sm.outgoing(self, f)

            f.event.wait(10)
            f.event.clear()

            print "Sent request, blocking..."
            session.wait_for_state_change(wait_time)

            state = session.get_state()

            if state == session.ST_CLSD:
                print "Trying again..."
            elif state == session.ST_SYNC:
                print "Waiting for synchronization"
                wait_time = 15
            else:
                print "Established session"
                session.set_state(session.ST_OPEN)
                return True

        session.set_state(session.ST_CLSD)
        print "Failed to establish session"
        return False
        
    def end_session(self, session):
        if session.stateless:
            return

        while session.get_state() == session.ST_SYNC:
            print "Waiting for session in SYNC"
            session.wait_for_state_change(2)

        f = DDT2EncodedFrame()
        f.type = self.T_END
        f.seq = 0
        f.d_station = session._st
        f.data = str(session._id)

        for i in range(0, 10):
            print "Sending End-of-Session"
            self._sm.outgoing(self, f)

            f.event.wait(10)
            f.event.clear()

            print "Sent, waiting for response"
            session.wait_for_state_change(15)

        session.set_state(session.ST_CLSD)
        print "Session closed"
        return False
            
    def __init__(self):
        self.name = "control"
        self.handler = self.ctl

        self.pending_reqs = {}

class StatelessSession(Session):
    stateless = True

    def read(self):
        f = self.inq.dequeue()

        return f.s_station, f.d_station, f.data

    def write(self, data, dest="CQCQCQ"):
        f = DDT2EncodedFrame()

        f.seq = 0
        f.type = 0
        f.d_station = dest
        f.data = data

        self._sm.outgoing(self, f)

class StatefulSession(Session):
    stateless = False

    T_SYN = 0
    T_ACK = 1
    T_NAK = 2
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

    def close(self, force=False):
        self.enabled = False
        self.thread.join()

        Session.close(self, force)

    def queue_next(self):
        if not self.outstanding:
            self.outstanding = self.outq.dequeue()
            self.ts = 0

    def send_blocks(self):
        self.queue_next()

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
            self.send_blocks()
            self.recv_blocks()

            if not self.outstanding and self.outq.peek():
                print "Short-circuit"
                continue # Short circuit because we have things to send

            print "Session loop"

            if not self.event.isSet():
                print "Waiting..."
                self.event.wait(3)
                if self.event.isSet():
                    print "Session woke up"
                else:
                    print "Session timed out waiting for stuff"
                self.event.clear()

    def read(self, count):
        buf = ""
        i = 0

        while i < count and i+len(self.data.peek()) < count:
            b += self.data.pop()

        return b

    def write(self, buf):
        f = None

        while buf:
            chunk = buf[:self.bsize]
            buf = buf[self.bsize:]

            f = DDT2EncodedFrame()
            f.seq = self.oseq
            f.type = self.T_DAT
            f.data = chunk

            self.outq.enqueue(f)

            self.oseq = (self.oseq + 1) % 256

        self.queue_next()
        self.event.set()

class SessionManager:
    def __init__(self, pipe, station):
        self.pipe = pipe
        self.station = station

        self.sessions = {}

        self.tport = transport.Transporter(self.pipe, self.incoming)

        self.control = ControlSession()
        self._register_session(0, self.control, "CQCQCQ")

    def shutdown(self, force=False):
        del self.sessions[self.control._id]
        for s in self.sessions.values():
            print "Stopping session `%s'" % s.name
            s.close(force)

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

    def _deregister_session(self, id):
        try:
            del self.sessions[id]
        except Exception, e:
            print "No session %s to deregister" % id

    def new_session(self, id, name, dest, cls=None):
        if not cls:
            if dest:
                s = StatefulSession(name)
            else:
                s = StatelessSession(name)
                dest = "CQCQCQ"
        else:
            s = cls(name)

        self._register_session(id, s, dest)

        if dest != "CQCQCQ":
            if not self.control.new_session(s):
                self._deregister_session(id)
        
        return s

    def start_session(self, name, dest=None, cls=None):
        for id in range(0, 256):
            if id not in self.sessions.keys():
                return self.new_session(id, name, dest, cls)

        return None

    def stop_session(self, session):
        for id, s in self.sessions.items():
            if session.name == s.name:
                if session.get_state() != session.ST_CLSD:
                    self.control.end_session(session)
                self._deregister_session(id)
                session.close()
                return True

        return False

    def end_session(self, id):
        try:
            del self.sessions[id]
        except Exception, e:
            print "Unable to deregister session"

if __name__ == "__main__":
    #p = transport.TestPipe(dst="KI4IFW")

    import comm
    import sys
    import sessions

    #if sys.argv[1] == "KI4IFW":
    #    p = comm.SerialDataPath(("/dev/ttyUSB0", 9600))
    #else:
    #    p = comm.SerialDataPath(("/dev/ttyUSB0", 38400))

    p = comm.SocketDataPath(("localhost", 9000))
    #p.make_fake_data("SOMEONE", "CQCQCQ")
    p.connect()
    sm = SessionManager(p, sys.argv[1])
    s = sm.start_session("chat", dest="CQCQCQ", cls=sessions.ChatSession)

    def cb(data, args):
        print "---------[ CHAT DATA ]------------"

    s.register_cb(cb)

    s.write("This is %s online" % sys.argv[1])

    if sys.argv[1] == "KI4IFW":
        f = file("inputdialog.py")
        S = sm.start_session("xfer", "K7TAY")
        if S:
            S.write(f.read())

    time.sleep(30)
    print "------- Closing"
    S.close()

    sm.shutdown()

#    blocks = s.recv_blocks()
#    for b in blocks:
#        print "Chat message: %s: %s" % (b.get_info()[2], b.get_data())
