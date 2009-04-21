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
        }

    def _update(self):
        self.__view.queue_draw()

        return True

    def _mh(self, _action, station):
        action = _action.get_name()

        def conntest(size):
            if size >= 2048:
                return

            size *= 2

            ev = main_events.Event(None,
                                   "Attempting block of %i with %s" % (size,
                                                                       station))
            self.emit("event", ev)
            self.emit("ping-station-echo", station, "0" * size,
                      conntest, size)

        if action == "ping":
            self.emit("ping-station", station)
        elif action == "conntest":
            conntest(128)

    def _make_station_menu(self, station):
        xml = """
<ui>
  <popup name="menu">
    <menuitem action="ping"/>
    <menuitem action="conntest"/>
  </popup>
</ui>
"""
        ag = gtk.ActionGroup("menu")
        actions = [("ping", _("Ping")),
                   ("conntest", _("Test Connectivity"))]

        for action, label in actions:
            a = gtk.Action(action, label, None, None)
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
                return
            else:
                view.set_cursor_on_cell(pathinfo[0])

        (model, iter) = view.get_selection().get_selected()
        station, = model.get(iter, 0)

        menu = self._make_station_menu(station)
        menu.popup(None, None, None, event.button, event.time)

    def __init__(self, wtree, config):
        MainWindowTab.__init__(self, wtree, config, "main")

        frame, self.__view, = self._getw("stations_frame", "stations_view")

        store = gtk.ListStore(gobject.TYPE_STRING,
                              gobject.TYPE_INT,
                              gobject.TYPE_STRING)
        store.set_sort_column_id(1, gtk.SORT_DESCENDING)
        self.__view.set_model(store)
        self.__view.set_tooltip_column(2)
        self.__view.connect("button_press_event", self._mouse_cb)

        def render_with_time(col, rend, model, iter):
            call, ts = model.get(iter, 0, 1)
            sec = time.time() - ts

            if sec < 60:
                msg = call
            else:
                msg = "%s (%02i:%02i)" % (call, sec / 3600, (sec % 3600) / 60)

            rend.set_property("text", msg)

        r = gtk.CellRendererText()
        col = gtk.TreeViewColumn(_("Stations"), r, text=0)
        col.set_cell_data_func(r, render_with_time)
        self.__view.append_column(col)

        self.__calls = []

        gobject.timeout_add(30000, self._update)

    def saw_station(self, station):
        store = self.__view.get_model()

        ts = time.time()
        msg = "%s %s %s %s" % (_("Station"),
                               station,
                               _("last seen at"),
                               time.asctime(time.localtime(ts)))

        if station != "CQCQCQ" and station not in self.__calls:
            self.__calls.append(station)
            store.append((station, ts, msg))
            self.__view.queue_draw()
        else:
            iter = store.get_iter_first()
            while iter:
                call, = store.get(iter, 0)
                if call == station:
                    store.set(iter, 1, ts, 2, msg)
                    break
                iter = store.iter_next(iter)
            
