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

import gobject

import sessionmgr
import sessions
import ddt2

ASCII_FS = "\x1C"
ASCII_GS = "\x1D"
ASCII_RS = "\x1E"
ASCII_US = "\x1F"

class UnknownRPCCall(Exception):
    pass

def encode_dict(source):
    elements = []
    for k, v in source.items():
        if not isinstance(k, str):
            raise Exception("Cannot encode non-string dict key")

        if not isinstance(v, str):
            raise Exception("Cannoy encode non-string dict value")

        elements.append(k + ASCII_US + v)
    return ASCII_RS.join(elements)

def decode_dict(string):
    result = {}
    elements = string.split(ASCII_RS)
    for element in elements:
        try:
            k, v = element.split(ASCII_US)
        except ValueError:
            raise Exception("Malformed dict encoding")
        result[k] = v

    return result

class RPCJob(gobject.GObject):
    __gsignals__ = {
        "state-change" : (gobject.SIGNAL_RUN_LAST,
                          gobject.TYPE_NONE,
                          (gobject.TYPE_STRING, gobject.TYPE_PYOBJECT)),
        }

    STATES = ["complete", "timeout", "running"]

    def __init__(self, dest, desc):
        gobject.GObject.__init__(self)
        self.__dest = dest
        self.__desc = desc
        self._args = {}

    def get_dest(self):
        return self.__dest

    def get_desc(self):
        return self.__desc

    def set_state(self, state, result={}):
        if not isinstance(result, dict):
            raise Exception("Value of result property must be dict")

        if state in self.STATES:
            gobject.idle_add(self.emit, "state-change", state, result)
        else:
            raise Exception("Invalid status `%s'" % state)

    def unpack(self, raw):
        self._args = {}

        if not raw:
            self._args = {}
        else:
            self._args = decode_dict(raw)

    def pack(self):
        return encode_dict(self._args)

class RPCFileListJob(RPCJob):
    def set_file_list(self, list):
        self._args = {}
        for item in list:
            self._args[item] = ""

    def get_file_list(self):
        return self._args.keys()

class RPCFormListJob(RPCJob):
    def get_form_list(self):
        return []

class RPCPullFileJob(RPCJob):
    def set_file(self, filename):
        self._args = {"fn" : filename}

    def get_file(self):
        return self._args.get("fn", None)

class RPCPullFormJob(RPCJob):
    def set_form(self, form):
        self._args = {"fn" : form}

    def get_form(self):
        return self._args.get("fn", None)

class RPCPositionReport(RPCJob):
    def set_station(self, station):
        self._args = {"st" : station}

    def get_station(self):
        return self._args.get("st", "ERROR")

class RPCSession(gobject.GObject, sessionmgr.StatelessSession):
    __gsignals__ = {
        "exec-job" : (gobject.SIGNAL_RUN_LAST,
                      gobject.TYPE_NONE,
                      (RPCJob,)),
        }

    type = sessionmgr.T_RPC

    T_RPCREQ = 0
    T_RPCACK = 1

    def __init__(self, *args, **kwargs):
        gobject.GObject.__init__(self)
        sessionmgr.StatelessSession.__init__(self, *args, **kwargs)
        self.__jobs = {}
        self.__jobq = []
        self.__jobc = 0

        self.__t_retry = 30

        self.__enabled = True

        gobject.timeout_add(1000, self.__worker)

        self.handler = self.incoming_data

    def notify(self):
        pass

    def __decode_rpccall(self, frame):
        jobtype, args = frame.data.split(ASCII_GS)
        # FIXME: Make this more secure
        if not (jobtype.isalpha() and jobtype.startswith("RPC")):
            raise UnknownRPCCall("Unknown call `%s'" % jobtype)

        job = eval("%s('%s', 'New job')" % (jobtype, frame.s_station))
        job.unpack(args)
        
        return job

    def __encode_rpccall(self, job):
        return "%s%s%s" % (job.__class__.__name__, ASCII_GS, job.pack())

    def __get_seq(self):
        self.__jobc += 1
        return self.__jobc

    def __job_to_frame(self, job, id):
        frame = ddt2.DDT2EncodedFrame()
        frame.type = self.T_RPCREQ
        frame.seq = id
        frame.data = self.__encode_rpccall(job)
        frame.d_station = job.get_dest()
            
        return frame

    def __send_job_status(self, id, station, state, result):
        frame = ddt2.DDT2EncodedFrame()
        frame.type = self.T_RPCACK
        frame.seq = id
        frame.data = result
        frame.d_station = station

        return frame

    def __job_state(self, job, state, _result, id):
        print "Job state: %s for %i: %s" % (state, id, _result)

        if state == "running":
            return

        result = encode_dict(_result)
        f = self.__send_job_status(id, job.get_dest(), state, result)
        self._sm.outgoing(self, f)

    def incoming_data(self, frame):
        if frame.type == self.T_RPCREQ:
            try:
                job = self.__decode_rpccall(frame)
            except UnknownRPCCall, e:
                print "Unable to execute RPC from %s: %s" % (frame.s_station, e)
                return

            job.connect("state-change", self.__job_state, frame.seq)
            self.emit("exec-job", job)

        elif frame.type == self.T_RPCACK:
            if self.__jobs.has_key(frame.seq):
                ts, att, job = self.__jobs[frame.seq]
                del self.__jobs[frame.seq]
                job.set_state("complete", decode_dict(frame.data))
            else:
                print "Unknown job %i" % frame.seq

        else:
            print "Unknown RPC frame type %i" % frame.type

    def __send_job(self, job, id):
        print "Sending job `%s' to %s" % (job.get_desc(), job.get_dest())
        frame = self.__job_to_frame(job, id)
        job.frame = frame
        self._sm.outgoing(self, frame)

    def __worker(self):
        for id, (ts, att, job) in self.__jobs.items():
            if job.frame and not job.frame.sent_event.isSet():
                # Reset timer until the block is sent
                self.__jobs[id] = (time.time(), att, job)
            elif (time.time() - ts) > self.__t_retry:
                print "Cancelling job %i due to timeout" % id
                del self.__jobs[id]
                job.set_state("timeout")

        return True

    def submit(self, job):
        id = self.__get_seq()
        self.__send_job(job, id)
        self.__jobs[id] = (time.time(), 0, job)

    def stop(self):
        self.__enabled = False
