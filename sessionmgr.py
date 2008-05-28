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
import os
import struct

from ddt2 import DDT2EncodedFrame
import transport

T_STATELESS = 0
T_GENERAL   = 1
T_FILEXFER  = 2
T_FORMXFER  = 3

class SessionClosedError(Exception):
    pass

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
    type = None

    ST_OPEN = 0
    ST_CLSD = 1
    ST_CLSW = 2
    ST_SYNC = 3

    def __init__(self, name):
        self.name = name
        self.inq = transport.BlockQueue()
        self.handler = None
        self.state_event = threading.Event()
        self.state = self.ST_CLSD

        self.stats = { "sent_size" : 0,
                       "recv_size" : 0,
                       "sent_wire" : 0,
                       "recv_wire" : 0,
                       "retries"   : 0,
                       }

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
    T_NEW = 3

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
                print "Signaled waiting session thread"
            except Exception, e:
                print "Failed to lookup new session event: %s" % e

            if session.get_state() == session.ST_CLSW:
                session.set_state(session.ST_CLSD)
            elif session.get_state() == session.ST_OPEN:
                pass
            elif session.get_state() == session.ST_SYNC:
                session.set_state(session.ST_OPEN)
            else:
                print "ACK for session in invalid state: %i" % session.get_state()
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

            #self.ack_req(frame.s_station, frame.data)

            frame.d_station = frame.s_station
            self._sm.outgoing(self, frame)

        elif frame.type >= self.T_NEW:
            try:
                id = int(frame.data)
            except Exception, e:
                print "Session request had invalid ID: %s" % e
                return

            print "ACK'ing session request for %i" % id

            try:
                c = self.stypes[frame.type]
                print "Got type: %s" % c
                s = c("session")
                s.set_state(s.ST_OPEN)
            except Exception, e:
                print "Can't start session type `%s': %s" % (frame.type, e)
                return
                
            self._sm._register_session(id, s, frame.s_station, "new,in")

            self.ack_req(frame.s_station, frame.data)
        else:
            print "Unknown control message type %i" % frame.type
            

    def new_session(self, session):
        f = DDT2EncodedFrame()
        f.type = self.T_NEW + session.type
        f.seq = 0
        f.d_station = session._st
        f.data = str(session._id)

        wait_time = 5

        for i in range(0,10):
            self._sm.outgoing(self, f)

            f.sent_event.wait(10)
            f.sent_event.clear()

            print "Sent request, blocking..."
            session.wait_for_state_change(wait_time)

            state = session.get_state()

            if state == session.ST_CLSD:
                print "Session is closed"
                break
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

        session.set_state(session.ST_CLSW)

        for i in range(0, 10):
            print "Sending End-of-Session"
            self._sm.outgoing(self, f)

            f.sent_event.wait(10)
            f.sent_event.clear()

            print "Sent, waiting for response"
            session.wait_for_state_change(15)

            if session.get_state() == session.ST_CLSD:
                print "Session closed"
                return True

        session.set_state(session.ST_CLSD)
        print "Session closed because no response"
        return False
            
    def __init__(self):
        Session.__init__(self, "control")
        self.handler = self.ctl

        import sessions

        self.stypes = { self.T_NEW + T_GENERAL  : StatefulSession,
                        self.T_NEW + T_FILEXFER : sessions.FileTransferSession,
                        self.T_NEW + T_FORMXFER : sessions.FormTransferSession,
                        }

class StatelessSession(Session):
    stateless = True
    type = T_STATELESS

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
    type = T_GENERAL

    T_SYN = 0
    T_ACK = 1
    T_NAK = 2
    T_DAT = 4

    def __init__(self, name, bsize=1024):
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

        if self.outstanding and time.time() - self.ts > 8:
            self.stats["retries"] += 1
            self._sm.outgoing(self, self.outstanding)
            t = time.time()
            print "Waiting for block to be sent..." 
            self.outstanding.sent_event.wait()
            self.outstanding.sent_event.clear()
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
                    self.outstanding.ackd_event.set()
                    self.stats["sent_size"] += len(self.outstanding.data)
                    self.stats["retries"] -= 1
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

    def read(self, count=None):
        buf = ""
        i = 0

        if self.get_state() not in [self.ST_OPEN, self.ST_SYNC]:
            raise SessionClosedError("State is %i" % self.get_state())

        while self.get_state() != self.ST_OPEN:
            print "Waiting for session to open"
            self.wait_for_state_change(5)

        if count == None:
            b = self.data.dequeue_all()
            return "".join(b)

        while True:
            next = self.data.peek() or ''
            if len(next) > 0 and (len(next) + i) < count:
                buf += self.data.dequeue()
            else:
                break

        if not buf and self.get_state() != self.ST_OPEN:
            raise SessionClosedError()

        return buf

    def write(self, buf, timeout=0):
        f = None
        
        if self.get_state() not in [self.ST_OPEN, self.ST_SYNC]:
            raise SessionClosedError("State is %s" % self.get_state())

        while self.get_state() != self.ST_OPEN:
            print "Waiting for session to open"
            self.wait_for_state_change(5)

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

        if timeout and f:
            print "Waiting for last block to be ack'd"
            f.ackd_event.wait(timeout)
            print "ACKED"

class SessionManager:
    def __init__(self, pipe, station):
        self.pipe = pipe
        self.station = station

        self.sessions = {}

        self.tport = transport.Transporter(self.pipe, self.incoming)

        self.session_cb = {}

        self.control = ControlSession()
        self._register_session(0, self.control, "CQCQCQ", "new,out")

    def fire_session_cb(self, session, reason):
        print "=-=-=-=-=-=-=-=- FIRING SESSION CB"
        for f,d in self.session_cb.items():
            try:
                f(d, reason, session)
            except Exception, e:
                print "Exception in session CB: %s" % e

    def register_session_cb(self, function, data):
        self.session_cb[function] = data

        for i,s in self.sessions.items():
            self.fire_session_cb(s, "new,existing")

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

    def _register_session(self, id, session, dest, reason):
        print "Registered session %i: %s" % (id, session.name)
        session._sm = self
        session._id = id
        session._st = dest
        self.sessions[id] = session

        print ""
        self.fire_session_cb(session, reason)

    def _deregister_session(self, id):
        if self.sessions.has_key(id):
            self.fire_session_cb(self.sessions[id], "end")

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

        s.set_state(s.ST_SYNC)
        self._register_session(id, s, dest, "new,out")

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
        S = sm.start_session("xfer", "KI4IFW", cls=sessions.FileTransferSession)
        S.send_file("inputdialog.py")
    else:
        def h(data, reason, session):
            print "Session CB: %s" % reason
            if reason == "new,in":
                print "Receiving file"
                t = threading.Thread(target=session.recv_file,
                                     args=("/tmp",))
                t.start()
                print "Done"

        sm.register_session_cb(h, None)

    try:
        while True:
            time.sleep(30)
    except Exception, e:
        print "------- Closing"

    sm.shutdown()

#    blocks = s.recv_blocks()
#    for b in blocks:
#        print "Chat message: %s: %s" % (b.get_info()[2], b.get_data())
