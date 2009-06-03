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

class DRatsPluginServer(SimpleXMLRPCServer, gobject.GObject):
    __gsignals__ = {
        "user-send-chat" : signals.USER_SEND_CHAT,
        "get-station-list" : signals.GET_STATION_LIST,
        "user-send-file" : signals.USER_SEND_FILE,
        }
    _signals = __gsignals__

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
            ports = self.emit("get-station-list")
            port = utils.port_for_station(ports, station)
            if not port:
                raise Exception("Port not specified and station not heard")

        sname = os.path.basename(filename)

        print "Sending file %s to %s on port %s" % (filename, station, port)
        self.emit("user-send-file", station, port, filename, sname)

        return 0

    def __init__(self):
        SimpleXMLRPCServer.__init__(self, ("localhost", 9100))
        gobject.GObject.__init__(self)
        self.__thread = None
        self.register_function(self.__send_chat, "send_chat")
        self.register_function(self.__list_ports, "list_ports")
        self.register_function(self.__send_file, "send_file")

    def serve_background(self):
        self.__thread = Thread(target=self.serve_forever)
        self.__thread.start()
        print "Started serve_forever() thread"
                               
