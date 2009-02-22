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

import time
from datetime import datetime

import gobject
import gtk

from d_rats.ui.main_common import MainWindowElement

EVENT_INFO       = 0
EVENT_FILE_XFER  = 1
EVENT_FORM_XFER  = 2
EVENT_PING       = 3
EVENT_POS_REPORT = 4

EVENT_GROUP_NONE = -1

_EVENT_TYPES = {EVENT_INFO : None,
                EVENT_FILE_XFER : None,
                EVENT_FORM_XFER : None,
                EVENT_PING : None,
                EVENT_POS_REPORT : None,
                }

class Event:
    def __init__(self, group_id, message, evtype=EVENT_INFO):
        self._group_id = group_id

        if evtype not in _EVENT_TYPES.keys():
            raise Exception("Invalid event type %i" % evtype)
        self._evtype = evtype
        self._message = message
        self._isfinal = False
        self._details = ""

    def set_as_final(self):
        "This event ends a series of events in the given group"
        self._isfinal = True

    def set_details(self, details):
        self._details = details

class FileEvent(Event):
    def __init__(self, group_id, message):
        Event.__init__(self, group_id, message, EVENT_FILE_XFER)

class FormEvent(Event):
    def __init__(self, group_id, message):
        Event.__init__(self, group_id, message, EVENT_FORM_XFER)

class PingEvent(Event):
    def __init__(self, group_id, message):
        Event.__init__(self, group_id, message, EVENT_PING)

class PosReportEvent(Event):
    def __init__(self, group_id, message):
        Event.__init__(self, group_id, message, EVENT_POS_REPORT)

def filter_rows(model, iter, evtab):
    search = evtab._wtree.get_widget("event_searchtext").get_text().upper()

    icon, message = model.get(iter, 1, 3)

    if search and search not in message.upper():
        return False

    if evtab._filter_icon is None:
        return True
    else:
        return icon == evtab._filter_icon

class EventTab(MainWindowElement):
    def _type_selected(self, typesel, filtermodel):
        filter = typesel.get_active_text()
        print "Filter on %s" % filter

        if filter == _("All"):
            t = None
        elif filter == _("File Transfers"):
            t = EVENT_FILE_XFER
        elif filter == _("Form Transfers"):
            t = EVENT_FORM_XFER
        elif filter == _("Pings"):
            t = EVENT_PING
        elif filter == _("Position Reports"):
            t = EVENT_POS_REPORT

        if t is None:
            self._filter_icon = None
        else:
            self._filter_icon = _EVENT_TYPES[t]

        filtermodel.refilter()

    def _search_text(self, searchtext, filtermodel):
        filtermodel.refilter()

    def _load_pixbufs(self):
        _EVENT_TYPES[EVENT_INFO] = \
            gtk.gdk.pixbuf_new_from_file("images/event_info.png")
        _EVENT_TYPES[EVENT_FILE_XFER] = \
            gtk.gdk.pixbuf_new_from_file("images/folder.png")
        _EVENT_TYPES[EVENT_FORM_XFER] = \
            gtk.gdk.pixbuf_new_from_file("images/message.png")
        _EVENT_TYPES[EVENT_PING] = \
            gtk.gdk.pixbuf_new_from_file("images/event_ping.png")
        _EVENT_TYPES[EVENT_POS_REPORT] = \
            gtk.gdk.pixbuf_new_from_file("images/event_posreport.png")

    def __init__(self, wtree, config):
        MainWindowElement.__init__(self, wtree, config, "event")

        eventlist, = self._getw("list")

        self.store = gtk.ListStore(gobject.TYPE_INT,    # 0: id
                                   gobject.TYPE_OBJECT, # 1: icon
                                   gobject.TYPE_INT,    # 2: timestamp
                                   gobject.TYPE_STRING, # 3: message
                                   gobject.TYPE_STRING, # 4: details
                                   )
        self._filter_icon = None
        filter = self.store.filter_new()
        filter.set_visible_func(filter_rows, self)
        eventlist.set_model(filter)

        col = gtk.TreeViewColumn("", gtk.CellRendererPixbuf(), pixbuf=1)
        eventlist.append_column(col)

        def render_time(col, rend, model, iter):
            val, = model.get(iter, 2)
            stamp = datetime.fromtimestamp(val)
            rend.set_property("text", stamp.strftime("%Y-%m-%d %H:%M:%S"))

        r = gtk.CellRendererText()
        col = gtk.TreeViewColumn(_("Time"), r, text=2)
        col.set_cell_data_func(r, render_time)
        col.set_sort_column_id(2)
        eventlist.append_column(col)

        r = gtk.CellRendererText()
        col = gtk.TreeViewColumn(_("Description"), r, text=3)
        eventlist.append_column(col)

        self.store.set_sort_column_id(2, gtk.SORT_DESCENDING)

        typesel, = self._getw("typesel")
        typesel.set_active(0)
        typesel.connect("changed", self._type_selected, filter)

        filtertext, = self._getw("searchtext")
        filtertext.connect("changed", self._search_text, filter)

        self._load_pixbufs()

        event = Event(EVENT_GROUP_NONE, _("D-RATS Started"))
        self.event(event)

    def event(self, event):
        iter = None
        if event._group_id != EVENT_GROUP_NONE:
            iter = self.store.get_iter_first()
            while iter:
                group, = self.store.get(iter, 0)
                if group == event._group_id:
                    break
                iter = self.store.iter_next(iter)

        if not iter:
            iter = self.store.append()

        if event._isfinal:
            gid = EVENT_GROUP_NONE
        else:
            gid = event._group_id

        self.store.set(iter,
                       0, gid,
                       1, _EVENT_TYPES[event._evtype],
                       2, time.time(),
                       3, event._message,
                       4, event._details)