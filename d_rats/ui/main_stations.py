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

import gtk
import gobject

import time
import os

from d_rats.ui.main_common import MainWindowTab
from d_rats.ui import main_events
from d_rats.ui import conntest
from d_rats.sessions import rpc
from d_rats import station_status
from d_rats import signals
from d_rats import image

class StationsList(MainWindowTab):
    __gsignals__ = {
        "event" : signals.EVENT,
        "notice" : signals.NOTICE,
        "get-station-list" : signals.GET_STATION_LIST,
        "ping-station" : signals.PING_STATION,
        "ping-station-echo" : signals.PING_STATION_ECHO,
        "incoming-chat-message" : signals.INCOMING_CHAT_MESSAGE,
        "submit-rpc-job" : signals.SUBMIT_RPC_JOB,
        "user-send-file" : signals.USER_SEND_FILE,
        }

    _signals = __gsignals__

    def _update(self):
        self.__view.queue_draw()

        return True

    def _mh(self, _action, station, port):
        action = _action.get_name()

        model = self.__view.get_model()
        iter = model.get_iter_first()
        while iter:
            _station, = model.get(iter, 0)
            if _station == station:
                break
            iter = model.iter_next(iter)

        if action == "ping":
            # FIXME: Use the port we saw the user on
            self.emit("ping-station", station, port)
        elif action == "conntest":
            ct = conntest.ConnTestAssistant(station, port)
            ct.connect("ping-echo-station",
                       lambda a, *v: self.emit("ping-station-echo", *v))
            ct.run()
        elif action == "remove":
            self.__calls.remove(station)
            model.remove(iter)
        elif action == "reset":
            model.set(iter, 1, time.time())
        elif action == "reqpos":
            job = rpc.RPCPositionReport(station, "Position Request")
            def log_result(job, state, result):
                msg = result.get("rc", "(Error)")
                if msg != "OK":
                    event = main_events.Event(None,
                                              "%s %s: %s" % (station,
                                                             _("says"),
                                                             msg))
                    self.emit("event", event)
                print "Result: %s" % str(result)
            job.set_station(station)
            job.connect("state-change", log_result)

            # FIXME: Send on the port where we saw this user
            self.emit("submit-rpc-job", job, port)
        elif action == "clearall":
            model.clear()
            self.__calls = []
        elif action == "pingall":
            stationlist = self.emit("get-station-list")
            for port in stationlist.keys():
                print "Doing CQCQCQ ping on port %s" % port
                self.emit("ping-station", "CQCQCQ", port)
        elif action == "reqposall":
            job = rpc.RPCPositionReport("CQCQCQ", "Position Request")
            job.set_station(".")
            stationlist = self.emit("get-station-list")
            for port in stationlist.keys():
                self.emit("submit-rpc-job", job, port)
        elif action == "sendfile":
            fn = self._config.platform.gui_open_file()
            if not fn:
                return

            fnl = fn.lower()
            if fnl.endswith(".jpg") or fnl.endswith(".jpeg") or \
                    fnl.endswith(".png") or fnl.endswith(".gif"):
                fn = image.send_image(fn)
                if not fn:
                    return

            name = os.path.basename(fn)
            self.emit("user-send-file", station, port, fn, name)
        elif action == "version":
            def log_result(job, state, result):
                if state == "complete":
                    msg = "Station %s running D-RATS %s on %s" % (\
                        job.get_dest(),
                        result.get("version", "Unknown"),
                        result.get("os", "Unknown"))
                    print "Station %s reports version info: %s" % (\
                        job.get_dest(), result)

                else:
                    msg = "No version response from %s" % job.get_dest()
                event = main_events.Event(None, msg)
                self.emit("event", event)

            job = rpc.RPCGetVersion(station, "Version Request")
            job.connect("state-change", log_result)
            self.emit("submit-rpc-job", job, port)

    def _make_station_menu(self, station, port):
        xml = """
<ui>
  <popup name="menu">
    <menuitem action="ping"/>
    <menuitem action="conntest"/>
    <menuitem action="reqpos"/>
    <menuitem action="sendfile"/>
    <menuitem action="version"/>
    <separator/>
    <menuitem action="remove"/>
    <menuitem action="reset"/>
    <separator/>
    <menuitem action="clearall"/>
    <menuitem action="pingall"/>
    <menuitem action="reqposall"/>
  </popup>
</ui>
"""
        ag = gtk.ActionGroup("menu")
        actions = [("ping", _("Ping"), None),
                   ("conntest", _("Test Connectivity"), None),
                   ("reqpos", _("Request Position"), None),
                   ("sendfile", _("Send file"), None),
                   ("remove", _("Remove"), gtk.STOCK_DELETE),
                   ("reset", _("Reset"), gtk.STOCK_JUMP_TO),
                   ("version", _("Get version"), gtk.STOCK_ABOUT)]

        for action, label, stock in actions:
            a = gtk.Action(action, label, None, stock)
            a.connect("activate", self._mh, station, port)
            a.set_sensitive(station is not None)
            ag.add_action(a)

        actions = [("clearall", _("Clear All"), gtk.STOCK_CLEAR),
                   ("pingall", _("Ping All Stations"), None),
                   ("reqposall", _("Request all positions"), None)]
        for action, label, stock in actions:
            a = gtk.Action(action, label, None, stock)
            a.connect("activate", self._mh, station, port)
            ag.add_action(a)

        uim = gtk.UIManager()
        uim.insert_action_group(ag, 0)
        uim.add_ui_from_string(xml)

        return uim.get_widget("/menu")

    def _mouse_cb(self, view, event):
        if event.button != 3:
            return

        if event.window == view.get_bin_window():
            x, y = event.get_coords()
            pathinfo = view.get_path_at_pos(int(x), int(y))
            if pathinfo is None:
                station = None
                port = None
            else:
                view.set_cursor_on_cell(pathinfo[0])
                (model, iter) = view.get_selection().get_selected()
                station, port = model.get(iter, 0, 5)

        menu = self._make_station_menu(station, port)
        menu.popup(None, None, None, event.button, event.time)

    def __init__(self, wtree, config):
        MainWindowTab.__init__(self, wtree, config, "main")

        frame, self.__view, = self._getw("stations_frame", "stations_view")

        store = gtk.ListStore(gobject.TYPE_STRING,  # Station
                              gobject.TYPE_INT,     # Timestamp
                              gobject.TYPE_STRING,  # Message
                              gobject.TYPE_INT,     # Status
                              gobject.TYPE_STRING,  # Status message
                              gobject.TYPE_STRING)  # Port
        store.set_sort_column_id(1, gtk.SORT_DESCENDING)
        self.__view.set_model(store)

        try:
            self.__view.set_tooltip_column(2)
        except AttributeError:
            print "This version of GTK is old; disabling station tooltips"

        self.__view.connect("button_press_event", self._mouse_cb)

        def render_call(col, rend, model, iter):
            call, ts, status = model.get(iter, 0, 1, 3)
            sec = time.time() - ts

            if sec < 60:
                msg = call
            else:
                msg = "%s (%02i:%02i)" % (call, sec / 3600, (sec % 3600) / 60)

            if status == station_status.STATUS_ONLINE:
                color = "blue"
            elif status == station_status.STATUS_UNATTENDED:
                color = "#CC9900"
            elif status == station_status.STATUS_OFFLINE:
                color = "grey"
            else:
                color = "black"

            rend.set_property("markup", "<span color='%s'>%s</span>" % (color,
                                                                        msg))

        r = gtk.CellRendererText()
        col = gtk.TreeViewColumn(_("Stations"), r, text=0)
        col.set_cell_data_func(r, render_call)
        self.__view.append_column(col)

        self.__calls = []

        status, msg = self._getw("stations_status", "stations_smsg")

        status.set_tooltip_text(_("This is the state other stations will " +
                                  "see when requesting your status"))
        msg.set_tooltip_text(_("This is the message other stations will " +
                               "see when requesting your status"))

        def set_status(cb):
            self.__status = cb.get_active_text()

        def set_smsg(e):
            self.__smsg = e.get_text()
            self._config.set("state", "status_msg", self.__smsg)

        status.connect("changed", set_status)
        msg.connect("changed", set_smsg)

        status.set_active(0)
        msg.set_text(self._config.get("state", "status_msg"))
        set_status(status)
        set_smsg(msg)

        gobject.timeout_add(30000, self._update)

    def saw_station(self, station, port, status=0, smsg=""):
        status_changed = False

        if station == "CQCQCQ":
            return

        store = self.__view.get_model()

        ts = time.time()
        msg = "%s <b>%s</b> %s <i>%s</i>\r\n%s: <b>%s</b>" % \
            (_("Station"),
             station,
             _("last seen at"),
             time.strftime("%X %x",
                           time.localtime(ts)),
             _("Port"),
             port)

        if station not in self.__calls:
            if smsg:
                msg += "\r\nStatus: <b>%s</b> (<i>%s</i>)" % (\
                    station_status.STATUS_MSGS.get(status, "Unknown"),
                    smsg)
            self.__calls.append(station)
            store.append((station, ts, msg, status, smsg, port))
            self.__view.queue_draw()
            status_changed = True
        else:
            iter = store.get_iter_first()
            while iter:
                call, _status, _smsg = store.get(iter, 0, 3, 4)
                if call == station:
                    status_changed = (status and (_status != status) or \
                                          (smsg and (_smsg != smsg)))

                    if _status > 0 and status == 0:
                        status = _status
                    if not smsg:
                        smsg = _smsg

                    msg += "\r\nStatus: <b>%s</b> (<i>%s</i>)" % (\
                        station_status.STATUS_MSGS.get(status,
                                                       "Unknown"),
                        smsg)
                    store.set(iter, 1, ts, 2, msg, 3, status, 4, smsg, 5, port)
                    break
                iter = store.iter_next(iter)

        if status_changed and status > 0 and \
                self._config.getboolean("prefs", "chat_showstatus"):
            status_msg = station_status.STATUS_MSGS.get(status, "Unknown")
            self.emit("incoming-chat-message",
                      station,
                      "CQCQCQ",
                      "%s %s: %s (%s %s)" % (_("Now"), status_msg, smsg,
                                             _("Port"), port))
            
    def get_status(self):
        sval = station_status.STATUS_VALS[self.__status]

        return sval, self.__smsg

    def get_stations(self):
        stations = []
        store = self.__view.get_model()
        iter = store.get_iter_first()
        while iter:
            call, ts, port = store.get(iter, 0, 1, 5)
            station = station_status.Station(call)
            station.set_heard(ts)
            station.set_port(port)
            stations.append(station)
            iter = store.iter_next(iter)

        return stations
