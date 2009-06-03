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

import os
from SimpleXMLRPCServer import SimpleXMLRPCServer
from threading import Thread

import gobject

import signals
import utils
import rpcsession

class DRatsPluginServer(SimpleXMLRPCServer, gobject.GObject):
    __gsignals__ = {
        "user-send-chat" : signals.USER_SEND_CHAT,
        "get-station-list" : signals.GET_STATION_LIST,
        "user-send-file" : signals.USER_SEND_FILE,
        "submit-rpc-job" : signals.SUBMIT_RPC_JOB,
        }
    _signals = __gsignals__

    def __get_port(self, station):
        ports = self.emit("get-station-list")
        port = utils.port_for_station(ports, station)
        if not port:
            raise Exception("Station %s not heard" % station)

        return port

    def __send_chat(self, port, message):
        """Send a chat @message on @port"""
        print "Sending chat on port %s: %s" % (port, message)
        self.emit("user-send-chat", "CQCQCQ", port, message, False)

        return 0

    def __list_ports(self):
        """Return a list of port names"""
        slist = self.emit("get-station-list")
        return slist.keys()

    def __send_file(self, station, filename, port=None):
        """Send a file to @station specified by @filename on optional port.
        If @port is not specified, the last-heard port for @station will be
        used.  An exception will be thrown if the last port cannot be
        determined"""
        if not port:
            port = self.__get_port(station)

        sname = os.path.basename(filename)

        print "Sending file %s to %s on port %s" % (filename, station, port)
        self.emit("user-send-file", station, port, filename, sname)

        return 0

    def __submit_rpcjob(self, station, rpcname, port=None, params={}):
        """Submit an RPC job to @station of type @rpcname.  Optionally
        specify the @port to be used.  The @params structure is a key=value
        list of function(value) items to call on the job object before
        submission.  Returns a job specifier to be used with get_result()."""
        if not rpcname.isalpha() or not rpcname.startswith("RPC"):
            raise Exception("Invalid RPC function call name")

        if not port:
            port = self.__get_port(station)

        job = eval("rpcsession.%s('%s', 'New Job')" % (rpcname, station))
        for key, val in params:
            func = job.__getattribute__(key)
            func(val)

        ident = self.__idcount
        self.__idcount += 1

        def record_result(job, state, result, ident):
            self.__persist[ident] = result
        job.connect("state-change", record_result, ident)

        self.emit("submit-rpc-job", job, port)

        return ident

    def __get_result(self, ident):
        """Get the result of job @ident.  Returns a structure, empty until
        completion"""
        if self.__persist.has_key(ident):
            result = self.__persist[ident]
            del self.__persist[ident]
        else:
            result = {}

        return result

    def __init__(self):
        SimpleXMLRPCServer.__init__(self, ("localhost", 9100))
        gobject.GObject.__init__(self)

        self.__thread = None
        self.__idcount = 0
        self.__persist = {}
                    
        self.register_function(self.__send_chat, "send_chat")
        self.register_function(self.__list_ports, "list_ports")
        self.register_function(self.__send_file, "send_file")
        self.register_function(self.__submit_rpcjob, "submit_rpcjob")
        self.register_function(self.__get_result, "get_result")

    def serve_background(self):
        self.__thread = Thread(target=self.serve_forever)
        self.__thread.start()
        print "Started serve_forever() thread"
                               
