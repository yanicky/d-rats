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

class StationsList(MainWindowTab):
    __gsignals__ = {
        "get-station-list" : (gobject.SIGNAL_ACTION,
                              gobject.TYPE_PYOBJECT,
                              ()),
        }

    def _update(self):
        self.__view.queue_draw()

        return True

    def __init__(self, wtree, config):
        MainWindowTab.__init__(self, wtree, config, "main")

        frame, self.__view, = self._getw("stations_frame", "stations_view")

        store = gtk.ListStore(gobject.TYPE_STRING, gobject.TYPE_INT)
        store.set_sort_column_id(1, gtk.SORT_DESCENDING)
        self.__view.set_model(store)

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
        if station != "CQCQCQ" and station not in self.__calls:
            self.__calls.append(station)
            store.append((station, time.time()))
            self.__view.queue_draw()
        else:
            iter = store.get_iter_first()
            while iter:
                call, = store.get(iter, 0)
                if call == station:
                    store.set(iter, 1, time.time())
                    break
                iter = store.iter_next(iter)
            
