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

from d_rats.ui.main_common import MainWindowTab
from d_rats.ui import main_events
from d_rats.ui import conntest
from d_rats import station_status

class StationsList(MainWindowTab):
    __gsignals__ = {
        "get-station-list" : (gobject.SIGNAL_ACTION,
                              gobject.TYPE_PYOBJECT,
                              ()),
        "ping-station" : (gobject.SIGNAL_RUN_LAST,
                          gobject.TYPE_NONE,
                          (gobject.TYPE_STRING,)),
        "ping-station-echo" : (gobject.SIGNAL_RUN_LAST,
                               gobject.TYPE_NONE,
                               (gobject.TYPE_STRING,    # Station
                                gobject.TYPE_STRING,    # Data
                                gobject.TYPE_PYOBJECT,  # Callback
                                gobject.TYPE_PYOBJECT)),# Callback data
        "display-incoming-chat" : (gobject.SIGNAL_RUN_LAST,
                                   gobject.TYPE_NONE,
                                   (gobject.TYPE_STRING,  # Station
                                    gobject.TYPE_STRING)),# Text
        }

    def _update(self):
        self.__view.queue_draw()

        return True

    def _mh(self, _action, station):
        action = _action.get_name()

        model = self.__view.get_model()
        iter = model.get_iter_first()
        while iter:
            _station, = model.get(iter, 0)
            if _station == station:
                break
            iter = model.iter_next(iter)

        if action == "ping":
            self.emit("ping-station", station)
        elif action == "conntest":
            ct = conntest.ConnTestAssistant(station)
            ct.connect("ping-echo-station",
                       lambda a, *v: self.emit("ping-station-echo", *v))
            ct.run()
        elif action == "remove":
            self.__calls.remove(station)
            model.remove(iter)
        elif action == "reset":
            model.set(iter, 1, time.time())
        elif action == "clearall":
            model.clear()

    def _make_station_menu(self, station):
        xml = """
<ui>
  <popup name="menu">
    <menuitem action="ping"/>
    <menuitem action="conntest"/>
    <menuitem action="remove"/>
    <menuitem action="reset"/>
    <separator/>
    <menuitem action="clearall"/>
  </popup>
</ui>
"""
        ag = gtk.ActionGroup("menu")
        actions = [("ping", _("Ping"), None),
                   ("conntest", _("Test Connectivity"), None),
                   ("remove", _("Remove"), gtk.STOCK_DELETE),
                   ("reset", _("Reset"), gtk.STOCK_JUMP_TO)]

        for action, label, stock in actions:
            a = gtk.Action(action, label, None, stock)
            a.connect("activate", self._mh, station)
            a.set_sensitive(station is not None)
            ag.add_action(a)

        actions = [("clearall", _("Clear All"), gtk.STOCK_CLEAR)]
        for action, label, stock in actions:
            a = gtk.Action(action, label, None, stock)
            a.connect("activate", self._mh, station)
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
            else:
                view.set_cursor_on_cell(pathinfo[0])
                (model, iter) = view.get_selection().get_selected()
                station, = model.get(iter, 0)

        menu = self._make_station_menu(station)
        menu.popup(None, None, None, event.button, event.time)

    def __init__(self, wtree, config):
        MainWindowTab.__init__(self, wtree, config, "main")

        frame, self.__view, = self._getw("stations_frame", "stations_view")

        store = gtk.ListStore(gobject.TYPE_STRING,  # Station
                              gobject.TYPE_INT,     # Timestamp
                              gobject.TYPE_STRING,  # Message
                              gobject.TYPE_INT,     # Status
                              gobject.TYPE_STRING)  # Status message
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

    def saw_station(self, station, status=0, smsg=""):
        status_changed = False

        if station == "CQCQCQ":
            return

        store = self.__view.get_model()

        ts = time.time()
        msg = "%s <b>%s</b> %s <i>%s</i>" % (_("Station"),
                                             station,
                                             _("last seen at"),
                                             time.strftime("%X %x",
                                                           time.localtime(ts)))

        if station not in self.__calls:
            if smsg:
                msg += "\r\nStatus: <b>%s</b> (<i>%s</i>)" % (\
                    station_status.STATUS_MSGS.get(status, "Unknown"),
                    smsg)
            self.__calls.append(station)
            store.append((station, ts, msg, status, smsg))
            self.__view.queue_draw()
            status_changed = True
        else:
            iter = store.get_iter_first()
            while iter:
                call, _status, _smsg = store.get(iter, 0, 3, 4)
                if call == station:
                    status_changed = (_status != status or _smsg != smsg)

                    if _status > 0 and status == 0:
                        status = _status
                    if not smsg:
                        smsg = _smsg

                    msg += "\r\nStatus: <b>%s</b> (<i>%s</i>)" % (\
                        station_status.STATUS_MSGS.get(status,
                                                       "Unknown"),
                        smsg)
                    store.set(iter, 1, ts, 2, msg, 3, status, 4, smsg)
                    break
                iter = store.iter_next(iter)

        if status_changed and status > 0 and \
                self._config.getboolean("prefs", "chat_showstatus"):
            status_msg = station_status.STATUS_MSGS.get(status, "Unknown")
            self.emit("display-incoming-chat",
                      station,
                      "%s %s: %s" % (_("Now"), status_msg, smsg))
            
    def get_status(self):
        sval = station_status.STATUS_VALS[self.__status]

        return sval, self.__smsg
