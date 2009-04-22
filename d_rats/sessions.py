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
import random
import zlib
from threading import Thread
import UserDict
import gobject

import sessionmgr
from ddt2 import DDT2RawData, DDT2EncodedFrame
from version import DRATS_VERSION
import platform
import gps
import utils

import station_status

session_types = {
    4 : "General",
    5 : "File",
    6 : "Form",
    7 : "Socket",
    8 : "PFile",
    9 : "PForm",
}

class SniffSession(sessionmgr.StatelessSession, gobject.GObject):
    __gsignals__ = {
        "incoming_frame" : (gobject.SIGNAL_RUN_LAST,
                            gobject.TYPE_NONE,
                            (gobject.TYPE_STRING,    # Src
                             gobject.TYPE_STRING,    # Dst
                             gobject.TYPE_STRING,    # Summary
                             ))
        }

    def __init__(self, *a, **k):
        sessionmgr.StatelessSession.__init__(self, *a, **k)
        gobject.GObject.__init__(self)

        self.handler = self._handler

    def decode_control(self, frame):
        if frame.type == sessionmgr.ControlSession.T_ACK:
            l, r = struct.unpack("BB", frame.data)
            return _("Control: ACK") + " " + \
                _("Local") + ":%i " % l + \
                _("Remote") + ":%i" % r
        elif frame.type == sessionmgr.ControlSession.T_END:
            return _("Control: END session %s") % frame.data
        elif frame.type >= sessionmgr.ControlSession.T_NEW:
            id, = struct.unpack("B", frame.data[0])
            name = frame.data[1:]
            stype = session_types.get(frame.type,
                                      "Unknown type %i" % frame.type)
            return _("Control: NEW session") +" %i: '%s' (%s)" % (id, name, stype)
        else:
            return _("Control: UNKNOWN")

    def _handler(self, frame):
        hdr = "%s->%s" % (frame.s_station, frame.d_station)

        if frame.s_station == "!":
            # Warm-up frame
            return

        if frame.session == 1:
            msg = "(%s: %s)" % (_("chat"), frame.data)
        elif frame.session == 0:
            msg = self.decode_control(frame)
        else:
            msg = "(S:%i L:%i)" % (frame.session, len(frame.data))

        self.emit("incoming_frame",
                  frame.s_station, frame.d_station,
                  "%s %s" % (hdr, msg))

class ChatSession(sessionmgr.StatelessSession, gobject.GObject):
    __gsignals__ = {
        "incoming-chat-message" : (gobject.SIGNAL_RUN_LAST,
                                   gobject.TYPE_NONE,
                                   (gobject.TYPE_STRING,  # Src Station
                                    gobject.TYPE_STRING,  # Dst Station
                                    gobject.TYPE_STRING)),# Message
        "outgoing-chat-message" : (gobject.SIGNAL_RUN_LAST,
                                   gobject.TYPE_NONE,
                                   (gobject.TYPE_STRING,  # Src Station
                                    gobject.TYPE_STRING,  # Dst Station
                                    gobject.TYPE_STRING)),# Message
        "ping-request" : (gobject.SIGNAL_RUN_LAST,
                          gobject.TYPE_NONE,
                          (gobject.TYPE_STRING,  # Src Station
                           gobject.TYPE_STRING,  # Dst Station
                           gobject.TYPE_STRING)),# Content
        "ping-response" : (gobject.SIGNAL_RUN_LAST,
                           gobject.TYPE_NONE,
                           (gobject.TYPE_STRING,  # Src Station
                            gobject.TYPE_STRING,  # Dst Station
                            gobject.TYPE_STRING)),# Content
        "incoming-gps-fix" : (gobject.SIGNAL_RUN_LAST,
                              gobject.TYPE_NONE,
                              (gobject.TYPE_PYOBJECT,)),
        "station-status" : (gobject.SIGNAL_RUN_LAST,
                            gobject.TYPE_NONE,
                            (gobject.TYPE_STRING,  # Station
                             gobject.TYPE_INT,     # Status type
                             gobject.TYPE_STRING)),# Status message
        "get-status" : (gobject.SIGNAL_ACTION,
                        gobject.TYPE_PYOBJECT,
                        ()),
        }

    __cb = None
    __cb_data = None

    type = sessionmgr.T_STATELESS

    T_DEF = 0
    T_PNG_REQ = 1
    T_PNG_RSP = 2
    T_PNG_ERQ = 3
    T_PNG_ERS = 4
    T_STATUS  = 5

    compress = False

    def __init__(self, *args, **kwargs):
        sessionmgr.StatelessSession.__init__(self, *args, **kwargs)
        gobject.GObject.__init__(self)

        self.set_ping_function()
        self.handler = self.incoming_data

        self.__ping_handlers = {}

    def set_ping_function(self, func=None):
        if func is not None:
            self.pingfn = func
        else:
            self.pingfn = self.ping_data

    def ping_data(self):
        p = platform.get_platform()
        return _("Running") + " D-RATS %s (%s)" % (DRATS_VERSION,
                                                   p.os_version_string())

    def _emit(self, signal, *args):
        gobject.idle_add(self.emit, signal, *args)

    def _incoming_chat(self, frame):
        self._emit("incoming-chat-message",
                   frame.s_station,
                   frame.d_station,
                   unicode(frame.data, "utf-8"))

    def _incoming_gps(self, fix):
        self._emit("incoming-gps-fix", fix)

    def incoming_data(self, frame):
        print "Got chat frame: %s" % frame
        if frame.type == self.T_DEF:
            fix = gps.parse_GPS(frame.data)
            if fix and fix.valid:
                self._incoming_gps(fix)
            else:
                self._incoming_chat(frame)

        elif frame.type == self.T_PNG_REQ:
            self._emit("ping-request",
                       frame.s_station, frame.d_station, "Request")

            if frame.d_station == "CQCQCQ":
                delay = random.randint(0,50) / 10.0
                print "Broadcast ping, waiting %.1f sec" % delay
                time.sleep(delay)
            elif frame.d_station != self._sm.station:
                return # Not for us

            frame.d_station = frame.s_station
            frame.type = self.T_PNG_RSP

            try:
                frame.data = self.pingfn()
            except Exception, e:
                print "Ping function failed: %s" % e
                return

            self._sm.outgoing(self, frame)

            try:
                s, m = self.emit("get-status")
                self.advertise_status(s, m)
            except Exception, e:
                print "Exception while getting status for ping reply:"
                utils.log_exception()

            self._emit("ping-response",
                       frame.s_station,
                       frame.d_station,
                       unicode(frame.data, "utf-8"))
        elif frame.type == self.T_PNG_RSP:
            print "PING OUT"
            self._emit("ping-response",
                       frame.s_station, frame.d_station, frame.data)
        elif frame.type == self.T_PNG_ERQ:
            self._emit("ping-request", frame.s_station, frame.d_station,
                       "%s %i %s" % (_("Echo request of"),
                                     len(frame.data),
                                     _("bytes")))

            if frame.d_station == "CQCQCQ":
                delay = random.randint(0, 100) / 10.0
                print "Broadcast ping echo, waiting %.1f sec" % delay
                time.sleep(delay)
            elif frame.d_station != self._sm.station:
                return # Not for us

            frame.d_station = frame.s_station
            frame.type = self.T_PNG_ERS

            self._sm.outgoing(self, frame)

            self._emit("ping-response", frame.s_station, frame.d_station,
                       "%s %i %s" % (_("Echo of"),
                                    len(frame.data),
                                    _("bytes")))
        elif frame.type == self.T_PNG_ERS:
            self._emit("ping-response", frame.s_station, frame.d_station,
                       "%s %i %s" % (_("Echo of"),
                                     len(frame.data),
                                     _("bytes")))
            if self.__ping_handlers.has_key(frame.s_station):
                cb, data = self.__ping_handlers[frame.s_station]
                try:
                    cb(*data)
                except Exception:
                    print "Exception while running ping callback"
                    utils.log_exception()
        elif frame.type == self.T_STATUS:
            try:
                s = int(frame.data[0])
            except Exception:
                print "Unable to parse station status: %s" % {frame.s_station :
                                                                  frame.data}
                s = 0

            self._emit("station-status", frame.s_station, s, frame.data[1:])

    def write_raw(self, data):
        f = DDT2RawData()
        f.data = data
        f.type = self.T_DEF

        print "Sending raw: %s" % data

        self._sm.outgoing(self, f)

    def write(self, data):
        self._emit("outgoing-chat-message", self._sm.station, self._st, data)
        sessionmgr.StatelessSession.write(self, data)

    def ping_station(self, station):
        f = DDT2EncodedFrame()
        f.d_station = station
        f.type = self.T_PNG_REQ
        f.data = "Ping Request"
        f.set_compress(False)
        self._sm.outgoing(self, f)

        self._emit("ping-request", f.s_station, f.d_station, "Request")

    def ping_echo_station(self, station, data, cb=None, *cbdata):
        if cb:
            self.__ping_handlers[station] = (cb, cbdata)

        f = DDT2EncodedFrame()
        f.d_station = station
        f.type = self.T_PNG_ERQ
        f.data = data
        f.set_compress(False)
        self._sm.outgoing(self, f)
        self._emit("ping-request", f.s_station, f.d_station,
                   "%s %i %s" % (_("Echo of"),
                                 len(data),
                                 _("bytes")))

    def advertise_status(self, stat, msg):
        if stat > station_status.STATUS_MAX or stat < station_status.STATUS_MIN:
            raise Exception("Status integer %i out of range" % stat)
        f = DDT2EncodedFrame()
        f.d_station = "CQCQCQ"
        f.type = self.T_STATUS
        f.data = "%i%s" % (stat, msg)
        self._sm.outgoing(self, f)

class NotifyDict(UserDict.UserDict):
    def __init__(self, cb, data={}):
        UserDict.UserDict.__init__(self)
        self.cb = cb
        self.data = data

    def __setitem__(self, name, value):
        self.data[name] = value
        self.cb()

class BaseFileTransferSession:
    def internal_status(self, vals):
        print "XFER STATUS: %s" % vals["msg"]

    def status(self, msg):
        vals = dict(self.stats)

        vals["msg"] = msg
        vals["filename"] = self.filename

        self.status_cb(vals)

        self.last_status = msg

    def status_tick(self):
        self.status(self.last_status)

    def __init__(self, name, status_cb=None, **kwargs):
        if not status_cb:
            self.status_cb = self.internal_status
        else:
            self.status_cb = status_cb

        self.sent_size = self.recv_size = 0
        self.retries = 0
        self.filename = ""

        self.stats["total_size"] = 0
        self.last_status = ""

        # Replace the regular dict with NotifyDict
        self.stats = NotifyDict(self.status_tick, self.stats)

    def get_file_data(self, filename):
        f = file(filename, "rb")
        data = f.read()
        f.close()

        return data

    def put_file_data(self, filename, data):
        f = file(filename, "wb")
        f.write(data)
        f.close()
    
    def send_file(self, filename):
        data = self.get_file_data(filename)
        if not data:
            return False

        try:
            self.write(struct.pack("I", len(data)) + \
                           os.path.basename(filename))
        except sessionmgr.SessionClosedError, e:
            print "Session closed while sending file information"
            return False

        self.filename = os.path.basename(filename)

        offset = None

        for i in range(10):
            print "Waiting for start"
            try:
                resp = self.read()
            except sessionmgr.SessionClosedError, e:
                print "Session closed while waiting for start ack"
                return False

            if not resp:
                self.status(_("Waiting for response"))
            elif resp == "OK":
                self.status(_("Negotiation Complete"))
                offset = 0
                break
            elif resp.startswith("RESUME:"):
                resume, _offset = resp.split(":", 1)
                print "Got RESUME request at %s" % _offset
                try:
                    offset = int(_offset)
                except Exception, e:
                    print "Unable to parse RESUME value: %s" % e
                    offset = 0
                self.status(_("Resuming at") + "%i" % offset)
                break
            else:
                print "Got unknown start: `%s'" % resp

            time.sleep(2)

        if offset is None:
            print "Did not get start response"
            return False

        self.stats["total_size"] = len(data)
        self.stats["sent_size"] = offset
        self.stats["start_time"] = time.time()
        
        try:
            self.status("Sending")
            self.write(data[offset:], timeout=120)
        except sessionmgr.SessionClosedError:
            print "Session closed while doing write"
            pass

        self.close()

        if self.stats["sent_size"] != self.stats["total_size"]:
            self.status(_("Failed to send file (incomplete)"))
            return False
        else:
            actual = os.stat(filename).st_size
            self.stats["sent_size"] = self.stats["total_size"] = actual
            self.status(_("Complete"))
            return True

    def recv_file(self, dir):
        self.status(_("Waiting for transfer to start"))
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
            self.status(_("No start block received!"))
            return None

        size, = struct.unpack("I", data[:4])
        name = data[4:]

        if os.path.isdir(dir):
            filename = os.path.join(dir, name)
        else:
            filename = dir

        partfilename = filename + ".part"

        if os.path.exists(partfilename):
            data = BaseFileTransferSession.get_file_data(self, partfilename)
            offset = os.path.getsize(partfilename)
            print "Part file exists, resuming at %i" % offset
        else:
            data = ""
            offset = 0

        self.status(_("Receiving file") + \
                        " %s " % name + \
                        _("of size") + \
                        " %i" % size)
        self.stats["recv_size"] = offset
        self.stats["total_size"] = size
        self.stats["start_time"] = time.time()

        try:
            if offset:
                print "Sending resume at %i" % offset
                self.write("RESUME:%i" % offset)
            else:
                self.write("OK")
        except sessionmgr.SessionClosedError, e:
            print "Session closed while sending start ack"
            return None

        self.status(_("Waiting for first block"))

        while True:
            try:
                d = self.read()
            except sessionmgr.SessionClosedError:
                print "SESSION IS CLOSED"
                break

            if d:
                data += d
                self.status(_("Receiving"))

        try:
            self.put_file_data(filename, data)
            if os.path.exists(partfilename):
                print "Removing old file part"
                os.remove(partfilename)
        except Exception, e:
            print "Failed to write transfer data: %s" % e
            BaseFileTransferSession.put_file_data(self, partfilename, data)
            return None

        if self.stats["recv_size"] != self.stats["total_size"]:
            self.status(_("Failed to receive file (incomplete)"))
            return None
        else:
            actual = os.stat(filename).st_size
            self.stats["recv_size"] = self.stats["total_size"] = actual
            self.status(_("Complete"))
            return filename

class FileTransferSession(BaseFileTransferSession, sessionmgr.StatefulSession):
    type = sessionmgr.T_FILEXFER

    def __init__(self, *args, **kwargs):
        sessionmgr.StatefulSession.__init__(self, *args, **kwargs)
        BaseFileTransferSession.__init__(self, *args, **kwargs)

class PipelinedFileTransfer(BaseFileTransferSession, sessionmgr.PipelinedStatefulSession):
    type = sessionmgr.T_PFILEXFER

    def __init__(self, *args, **kwargs):
        sessionmgr.PipelinedStatefulSession.__init__(self, *args, **kwargs)
        BaseFileTransferSession.__init__(self, *args, **kwargs)

    def get_file_data(self, filename):
        f = file(filename, "rb")
        data = f.read()
        f.close()

        return zlib.compress(data, 9)

    def put_file_data(self, filename, zdata):
        try:
            data = zlib.decompress(zdata)
            f = file(filename, "wb")
            f.write(data)
            f.close()
        except zlib.error, e:
            raise e

class BaseFormTransferSession:
    pass

class FormTransferSession(BaseFormTransferSession, FileTransferSession):
    type = sessionmgr.T_FORMXFER

class PipelinedFormTransfer(BaseFormTransferSession, PipelinedFileTransfer):
    type = sessionmgr.T_PFORMXFER

class SocketSession(sessionmgr.PipelinedStatefulSession):
    type = sessionmgr.T_SOCKET

    IDLE_TIMEOUT = None

    def __init__(self, name, status_cb=None):
        sessionmgr.PipelinedStatefulSession.__init__(self, name)

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
        self.thread.setDaemon(True)
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
