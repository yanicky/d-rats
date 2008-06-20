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

import os
import struct
import time
import socket
from threading import Thread

import sessionmgr
from ddt2 import DDT2RawData

class ChatSession(sessionmgr.StatelessSession):
    __cb = None
    __cb_data = None

    type = sessionmgr.T_STATELESS

    compress = False

    def incoming_data(self, frame):
        if not self.__cb:
            return

        args = { "From" : frame.s_station,
                 "To" : frame.d_station,
                 "Msg" : frame.data,
                 }

        print "Calling chat callback with %s" % args

        self.__cb(self.__cb_data, args)

    def register_cb(self, cb, data=None):
        self.__cb = cb
        self.__cb_data = data

        self.handler = self.incoming_data

    def write_raw(self, data):
        f = DDT2RawData()
        f.data = data

        print "Sending raw: %s" % data

        self._sm.outgoing(self, f)

class FileTransferSession(sessionmgr.StatefulSession):
    type = sessionmgr.T_FILEXFER

    def internal_status(self, vals):
        print "XFER STATUS: %s" % vals["msg"]

    def status(self, msg):
        vals = dict(self.stats)

        vals["msg"] = msg
        vals["filename"] = self.filename

        self.status_cb(vals)

    def __init__(self, name, status_cb=None):
        sessionmgr.StatefulSession.__init__(self, name)

        if not status_cb:
            self.status_cb = self.internal_status
        else:
            self.status_cb = status_cb

        self.sent_size = self.recv_size = 0
        self.retries = 0
        self.filename = ""

        self.stats["total_size"] = 0

    def send_file(self, filename):
        stat = os.stat(filename)
        if not stat:
            return False

        f = file(filename, "rb")
        if not f:
            return False

        try:
            self.write(struct.pack("I", stat.st_size) + \
                           os.path.basename(filename))
        except sessionmgr.SessionClosedError, e:
            print "Session closed while sending file information"
            return False

        self.filename = os.path.basename(filename)

        for i in range(10):
            print "Waiting for start"
            try:
                resp = self.read()
            except sessionmgr.SessionClosedError, e:
                print "Session closed while waiting for start ack"
                return False

            if not resp:
                self.status("Waiting for response")
            elif resp == "OK":
                self.status("Negotiation Complete")
                break
            else:
                print "Got unknown start: `%s'" % resp

            time.sleep(2)

        if resp != "OK":
            return False

        self.stats["total_size"] = stat.st_size
        self.stats["sent_size"] = 0

        while True:
            d = f.read(1024)
            if not d:
                break

            self.status("Sending")
            try:
                self.write(d, timeout=20)
            except sessionmgr.SessionClosedError:
                break

            self.status("Sent")

        self.write(f.read(), timeout=20)
        f.close()

        self.close()

        if self.stats["sent_size"] != self.stats["total_size"]:
            self.status("Failed to send file (incomplete)")
            return False
        else:
            self.status("Complete")
            return True

    def recv_file(self, dir):
        self.status("Waiting for transfer to start")
        for i in range(10):
            try:
                data = self.read()
            except sessionmgr.SessionClosedError, e:
                print "Session closed while waiting for start"
                return None

            if data:
                break
            else:
                time.sleep(2)

        if not data:
            self.status("No start block received!")
            return None

        size, = struct.unpack("I", data[:4])
        name = data[4:]

        if os.path.isdir(dir):
            filename = os.path.join(dir, name)
        else:
            filename = dir

        self.status("Receiving file %s of size %i" % (name, size))
        self.stats["recv_size"] = 0
        self.stats["total_size"] = size

        f = file(filename, "wb", 0)
        if not f:
            print "Can't open file %s/%s" + (dir, name)
            return None

        try:
            self.write("OK")
        except sessionmgr.SessionClosedError, e:
            print "Session closed while sending start ack"
            return None

        self.status("Negotiation Complete")

        while True:
            try:
                d = self.read()
                self.status("Receiving")
            except sessionmgr.SessionClosedError:
                print "SESSION IS CLOSED"
                break

            if d:
                f.write(d)
                self.status("Recevied block")

        f.close()

        if self.stats["recv_size"] != self.stats["total_size"]:
            self.status("Failed to receive file (incomplete)")
            return None
        else:
            self.status("Complete")
            return filename

class FormTransferSession(FileTransferSession):
    type = sessionmgr.T_FORMXFER

class SocketSession(sessionmgr.StatefulSession):
    type = sessionmgr.T_SOCKET

    def __init__(self, name, status_cb=None):
        sessionmgr.StatefulSession.__init__(self, name)

        if status_cb:
            self.status_cb = status_cb
        else:
            self.status_cb = self._status

    def _status(self, msg):
        print "Socket Status: %s" % msg

class SocketListener:
    def __init__(self, sm, dest, sport, dport, addr='0.0.0.0'):
        self.sm = sm
        self.dest = dest
        self.sport = sport
        self.dport = dport
        self.addr = addr
        self.enabled = True
        self.lsock = None
        self.dsock = None
        self.thread = Thread(target=self.listener)
        self.thread.start()

    def stop(self):
        self.enabled = False
        if self.lsock:
            self.lsock.close()
        self.thread.join()

    def listener(self):
        sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        sock.setsockopt(socket.SOL_SOCKET,
                        socket.SO_REUSEADDR,
                        1)
        sock.settimeout(0.25)
        sock.bind(('0.0.0.0', self.sport))
        sock.listen(0)

        self.lsock = sock

        name = "TCP:%i" % self.dport

        while self.enabled:
            try:
                (self.dsock, addr) = sock.accept()
            except socket.timeout:
                continue
            except Exception, e:
                print "Socket exception: %s" % e
                self.enabled = False
                break

            print "%i: Incoming socket connection from %s" % (self.dport, addr)

            s = self.sm.start_session(name=name,
                                      dest=self.dest,
                                      cls=SocketSession)

            while s.get_state() != s.ST_CLSD:
                s.wait_for_state_change(10)

            print "%s ended" % name
            self.dsock = None

        sock.close()
