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
import time
from datetime import datetime

import gobject
import gtk
import pango

from d_rats.ui.main_common import MainWindowElement
from d_rats import inputdialog
from d_rats import qst

class ChatQM(MainWindowElement):
    __gsignals__ = {
        "user-sent-qm" : (gobject.SIGNAL_RUN_LAST,
                          gobject.TYPE_NONE,
                          (gobject.TYPE_STRING,))
        }

    def _send_qm(self, view, path, col):
        model = view.get_model()
        iter = model.get_iter(path)
        text = model.get(iter, 0)[0]
        self.emit("user-sent-qm", text)

    def _add_qm(self, button, store):
        d = inputdialog.TextInputDialog(title=_("Add Quick Message"))
        d.label.set_text(_("Enter text for the new quick message:"))
        r = d.run()
        if r == gtk.RESPONSE_OK:
            key = time.strftime("%Y%m%d%H%M%S")
            store.append((d.text.get_text(), key))
            self._config.set("quick", key, d.text.get_text())
        d.destroy()

    def _rem_qm(self, button, view):
        (store, iter) = view.get_selection().get_selected()
        key, = store.get(iter, 1)
        store.remove(iter)
        self._config.remove_option("quick", key)

    def __init__(self, wtree, config):
        MainWindowElement.__init__(self, wtree, config, "chat")

        qm_add, qm_rem, qm_list = self._getw("qm_add", "qm_remove",
                                             "qm_list")

        store = gtk.ListStore(gobject.TYPE_STRING, gobject.TYPE_STRING)
        qm_list.set_model(store)
        qm_list.set_headers_visible(False)
        qm_list.connect("row-activated", self._send_qm)

        r = gtk.CellRendererText()
        col = gtk.TreeViewColumn("", r, text=0)
        qm_list.append_column(col)

        for key, msg in self._config.items("quick"):
            store.append((msg, key))

        qm_add.connect("clicked", self._add_qm, store)
        qm_rem.connect("clicked", self._rem_qm, qm_list)

class ChatQST(MainWindowElement):
    __gsignals__ = {
        "qst-fired" : (gobject.SIGNAL_RUN_LAST,
                       gobject.TYPE_NONE,
                       (gobject.TYPE_STRING, gobject.TYPE_BOOLEAN)),
        }

    def _send_qst(self, view, path, col):
        store = view.get_model()
        id = store[path][0]

        q, c = self._qsts[id]
        self._qsts[id] = (q, 0)

    def _toggle_qst(self, rend, path, store, enbcol, idcol, fcol):
        val = store[path][enbcol] = not store[path][enbcol]
        id = store[path][idcol]
        freq = store[path][fcol]

        self._config.set(id, "enabled", val)

        q, c = self._qsts[id]
        self._qsts[id] = q, self._remaining_for(freq) * 60

    def _add_qst(self, button, view):
        d = qst.QSTEditDialog(self._config,
                              "qst_%s" % time.strftime("%Y%m%d%H%M%S"))
        if d.run() == gtk.RESPONSE_OK:
            d.save()
            self.reconfigure()
        d.destroy()

    def _rem_qst(self, button, view):
        (model, iter) = view.get_selection().get_selected()

        ident, = model.get(iter, 0)
        self._config.remove_section(ident)
        self._store.remove(iter)

    def _edit_qst(self, button, view):
        (model, iter) = view.get_selection().get_selected()

        ident, = model.get(iter, 0)

        d = qst.QSTEditDialog(self._config, ident)
        if d.run() == gtk.RESPONSE_OK:
            d.save()
            self.reconfigure()
        d.destroy()

    def __init__(self, wtree, config):
        MainWindowElement.__init__(self, wtree, config, "chat")

        qst_add, qst_rem, qst_edit, qst_list = self._getw("qst_add",
                                                          "qst_remove",
                                                          "qst_edit",
                                                          "qst_list")

        self._store = gtk.ListStore(gobject.TYPE_STRING,
                                    gobject.TYPE_STRING,
                                    gobject.TYPE_STRING,
                                    gobject.TYPE_FLOAT,
                                    gobject.TYPE_STRING,
                                    gobject.TYPE_BOOLEAN)
        qst_list.set_model(self._store)
        qst_list.connect("row-activated", self._send_qst)

        def render_remaining(col, rend, model, iter):
            id, e = model.get(iter, 0, 5)
            q, c = self._qsts[id]

            if not e:
                s = ""
            elif c > 90:
                s = "%i mins" % (c / 60)
            else:
                s = "%i sec" % c

            rend.set_property("text", s)

        typ = gtk.TreeViewColumn("Type",
                                 gtk.CellRendererText(), text=1)
        frq = gtk.TreeViewColumn("Freq",
                                 gtk.CellRendererText(), text=2)

        r = gtk.CellRendererProgress()
        cnt = gtk.TreeViewColumn("Remaining", r, value=3)
        cnt.set_cell_data_func(r, render_remaining)

        msg = gtk.TreeViewColumn("Content",
                                 gtk.CellRendererText(), text=4)

        r = gtk.CellRendererToggle()
        r.connect("toggled", self._toggle_qst, self._store, 5, 0, 2)
        enb = gtk.TreeViewColumn("On", r, active=5)

        qst_list.append_column(typ)
        qst_list.append_column(frq)
        qst_list.append_column(cnt)
        qst_list.append_column(enb)
        qst_list.append_column(msg)

        self._qsts = {}
        self.reconfigure()

        qst_add.connect("clicked", self._add_qst, qst_list)
        qst_rem.connect("clicked", self._rem_qst, qst_list)
        qst_edit.connect("clicked", self._edit_qst, qst_list)

        gobject.timeout_add(1000, self._tick)

    def _remaining_for(self, freq):
        if freq.startswith(":"):
            n_min = int(freq[1:])
            c_min = datetime.now().minute
            cnt = n_min - c_min
            if n_min <= c_min:
                cnt += 60
        else:
                cnt = int(freq)

        return cnt

    def _qst_fired(self, q, content):
        self.emit("qst-fired", content, q.raw)

    def _tick(self):
        iter = self._store.get_iter_first()
        while iter:
            i, t, f, p, c, e = self._store.get(iter, 0, 1, 2, 3, 4, 5)
            if e:
                q, cnt = self._qsts[i]
                cnt -= 1
                if cnt <= 0:
                    q.fire()
                    cnt = self._remaining_for(f) * 60

                self._qsts[i] = (q, cnt)
            else:
                cnt = 0

            if f.startswith(":"):
                period = 3600
            else:
                period = int(f) * 60

            p = (float(cnt) / period) * 100.0
            self._store.set(iter, 3, p)

            iter = self._store.iter_next(iter)

        return True

    def reconfigure(self):
        self._store.clear()

        qsts = [x for x in self._config.sections() if x.startswith("qst_")]
        for i in qsts:
            t = self._config.get(i, "type")
            c = self._config.get(i, "content")
            f = self._config.get(i, "freq")
            e = self._config.getboolean(i, "enabled")
            self._store.append((i, t, f, 0.0, c, e))
                              
            qc = qst.get_qst_class(t)
            q = qc(self._config, c)
            q.connect("qst-fired", self._qst_fired)

            self._qsts[i] = (q, self._remaining_for(f) * 60)

class ChatTab(MainWindowElement):
    __gsignals__ = {
        "user-sent-message" : (gobject.SIGNAL_RUN_LAST,
                               gobject.TYPE_NONE,
                               (gobject.TYPE_STRING,
                                gobject.TYPE_STRING,
                                gobject.TYPE_BOOLEAN))
        }

    def display_line(self, text, *attrs):
        """Display a single line of text with datestamp"""

        if (time.time() - self._last_date) > 600:
            stamp = time.strftime("%Y-%m-%d %H:%M:%S")
        else:
            stamp = time.strftime("%H:%M:%S")

        line = "[%s] %s%s" % (stamp, text, os.linesep)
        self._last_date = time.time()

        display, = self._getw("display")
        buffer = display.get_buffer()

        buffer.insert_at_cursor(line)

    def _send_button(self, button, dest, entry, buffer):
        station = dest.get_active_text()
        text = entry.get_text()
        entry.set_text("")

        self.display_line(text)
        self.emit("user-sent-message", station, text, False)

    def _send_msg(self, qm, msg, raw):
        self.display_line(msg)
        self.emit("user-sent-message", "CQCQCQ", msg, raw)

    def __init__(self, wtree, config):
        MainWindowElement.__init__(self, wtree, config, "chat")

        display, entry, send, dest = self._getw("display", "entry", "send",
                                                "destination")
        buffer = display.get_buffer()

        send.connect("clicked", self._send_button, dest, entry, buffer)
        send.set_flags(gtk.CAN_DEFAULT)
        send.grab_default()

        entry.set_activates_default(True)
        entry.grab_focus()

        self._qm = ChatQM(wtree, config)
        self._qst = ChatQST(wtree, config)
        self._qm.connect("user-sent-qm", self._send_msg, False)
        self._qst.connect("qst-fired", self._send_msg)

        self._last_date = 0

    def reconfigure(self):
        display, = self._getw("display")

        fontname = self._config.get("prefs", "font")
        font = pango.FontDescription(fontname)
        display.modify_font(font)

