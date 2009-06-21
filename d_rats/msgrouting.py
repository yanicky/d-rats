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

import sys
import threading
import time
import os
from glob import glob

import gobject

import formgui
import signals

CALL_TIMEOUT_RETRY = 300

class MessageRouter(gobject.GObject):
    __gsignals__ = {
        "get-station-list" : signals.GET_STATION_LIST,
        "user-send-form" : signals.USER_SEND_FORM,
        }
    _signals = __gsignals__

    def __init__(self, config):
        gobject.GObject.__init__(self)

        self.__config = config

        self.__sent_call = {}
        self.__sent_port = {}
        self.__file_to_call = {}

        self.__thread = None
        self.__enabled = False

    def _sleep(self):
        t = self.__config.getint("settings", "msg_flush")
        time.sleep(t)

    def _p(self, string):
        print "[MR] %s" % string
        import sys
        sys.stdout.flush()

    def _get_queue(self):
        queue = {}

        qd = os.path.join(self.__config.form_store_dir(), _("Outbox"))
        fl = glob(os.path.join(qd, "*.xml"))
        for f in fl:
            form = formgui.FormFile(f)
            call = form.get_path_dst()
            del form

            if not call:
                continue
            elif not queue.has_key(call):
                queue[call] = [f]
            else:
                queue[call].append(f)
        
        return queue

    def _send_form(self, call, port, filename):
        self.__sent_call[call] = time.time()
        self.__sent_port[port] = time.time()
        self.__file_to_call[filename] = call
        self.emit("user-send-form", call, port, filename, "Foo")

    def _sent_recently(self, call):
        if self.__sent_call.has_key(call):
            return (time.time() - self.__sent_call[call]) < CALL_TIMEOUT_RETRY
        return False

    def _port_free(self, port):
        return not self.__sent_port.has_key(port)

    def _run_one(self):
        plist = self.emit("get-station-list")
        slist = {}

        for port, stations in plist.items():
            for station in stations:
                slist[station] = port

        queue = self._get_queue()
        for call, callq in queue.items():
            if not slist.has_key(call):
                self._p("No route for station %s" % call)
                continue # station unknown

            if self._sent_recently(call):
                self._p("Call %s is busy" % call)
                continue

            port = slist[call]
            if not self._port_free(port):
                self._p("I think port %s is busy" % port)
                continue # likely already a transfer going here so skip it

            msg = callq[0]
            self._p("Sending %s to %s" % (msg, call))
            self._send_form(call, port, msg)

    def _run(self):
        while self.__enabled:
            if self.__config.getboolean("settings", "msg_forward"):
                self._run_one()
            self._sleep()

    def start(self):
        self.__enabled = True
        self.__thread = threading.Thread(target=self._run)
        self.__thread.start()

    def stop(self):
        self.__enabled = False
        self.__thread.join()

    def form_xfer_done(self, fn, port, failed):
        self._p("File %s on %s done" % (fn, port))

        call = self.__file_to_call.get(fn, None)
        if call and self.__sent_call.has_key(call):
            # This callsign completed (or failed) a transfer
            del self.__sent_call[call]
            del self.__file_to_call[fn]

        if self.__sent_port.has_key(port):
            # This port is not open for another transfer
            del self.__sent_port[port]

