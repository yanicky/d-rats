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

import sessionmgr

class ChatSession(sessionmgr.StatelessSession):
    __cb = None
    __cb_data = None

    type = sessionmgr.T_STATELESS

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

        self.write(struct.pack("I", stat.st_size) + \
                       os.path.basename(filename))

        self.filename = os.path.basename(filename)

        for i in range(10):
            print "Waiting for start"
            resp = self.read()

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

        self.status("Complete")

        self.close()

        print "Finished sending file"

    def recv_file(self, dir):
        self.status("Waiting for transfer to start")
        for i in range(10):
            data = self.read()
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

        self.write("OK")
        self.status("Negotiation Complete")

        while True:
            try:
                d = self.read(512)
                self.status("Receiving")
            except sessionmgr.SessionClosedError:
                print "SESSION IS CLOSED"
                break

            if d:
                f.write(d)
                self.status("Recevied block")

        f.close()

        self.status("Complete")

        return filename

class FormTransferSession(FileTransferSession):
    type = sessionmgr.T_FORMXFER
