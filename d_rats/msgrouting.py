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
import gobject
import time
import os
from glob import glob

import formgui
import signals

class MessageRouter(threading.Thread, gobject.GObject):
    __gsignals__ = {
        "get-station-list" : signals.GET_STATION_LIST,
        "user-send-form" : signals.USER_SEND_FORM,
        }
    _signals = __gsignals__

    def __init__(self, config):
        threading.Thread.__init__(self)
        gobject.GObject.__init__(self)

        self.__config = config

    def _sleep(self):
        t = self.__config.getint("settings", "msg_flush")
        time.sleep(t)

    def _p(self, string):
        print "[MR] %s" % string

    def _get_queue(self):
        queue = {}

        qd = os.path.join(self.__config.form_store_dir(), _("Outbox"))
        fl = glob(os.path.join(qd, "*.xml"))
        for f in fl:
            form = formgui.FormFile("", f)
            call = form.get_path_dst()
            if not call:
                continue
            elif not queue.has_key(call):
                queue[call] = [f]
            else:
                queue[call].append(f)
        
        return queue

    def _send_form(self, call, port, filename):
        self.emit("user-send-form", call, port, filename, "Foo")

    def _run_one(self):
        plist = self.emit("get-station-list")
        slist = {}
        avail_ports = plist.keys()

        for port, stations in plist.items():
            for station in stations:
                slist[station] = port

        queue = self._get_queue()
        for call, callq in queue.items():
            if not slist.has_key(call):
                print "No route for station %s" % call
                continue # station unknown

            port = slist[call]
            if port not in avail_ports:
                continue # already dispatched one on this port this cycle

            for msg in callq:
                print "Sending %s to %s" % (msg, call)
                avail_ports.remove(port) # No more to this port this round
                self._send_form(call, port, msg)
                break

    def run(self):
        while True:
            if self.__config.getboolean("settings", "msg_forward"):
                self._run_one()
            self._sleep()
