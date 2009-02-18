#!/usr/bin/python
#
# Copyright 2008 Dan Smith <dsmith@danplanet.com>
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

import gobject
import gtk

from d_rats.ui.main_common import MainWindowElement

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
            store.append((d.text.get_text(),))
        d.destroy()                        

    def _rem_qm(self, button, view):
        (store, iter) = view.get_selection().get_selected()
        store.remove(iter)

    def __init__(self, wtree, config):
        MainWindowElement.__init__(self, wtree, config, "chat")

        qm_add, qm_rem, qm_list = self._getw("qm_add", "qm_remove",
                                             "qm_list")

        store = gtk.ListStore(gobject.TYPE_STRING)
        qm_list.set_model(store)
        qm_list.set_headers_visible(False)
        qm_list.connect("row-activated", self._send_qm)

        r = gtk.CellRendererText()
        col = gtk.TreeViewColumn("", r, text=0)
        qm_list.append_column(col)

        for key, msg in self._config.items("quick"):
            store.append((msg,))

        qm_add.connect("clicked", self._add_qm, store)
        qm_rem.connect("clicked", self._rem_qm, qm_list)

class ChatQST(MainWindowElement):
    def _send_qst(self, view, path, col):
        model = view.get_model()
        iter = model.get_iter(path)
        text = model.get(iter, 4)
        print "Sending QST: %s" % text
        # FIXME: Do this

    def _toggle_qst(self, rend, path, store, enbcol, idcol):
        val = store[path][enbcol] = not store[path][enbcol]
        id = store[path][idcol]

        self._config.set(id, "enabled", val)

    def __init__(self, wtree, config):
        MainWindowElement.__init__(self, wtree, config, "chat")

        qst_add, qst_rem, qst_list = self._getw("qst_add", "qst_remove",
                                                "qst_list")

        store = gtk.ListStore(gobject.TYPE_STRING,
                              gobject.TYPE_STRING,
                              gobject.TYPE_STRING,
                              gobject.TYPE_FLOAT,
                              gobject.TYPE_STRING,
                              gobject.TYPE_BOOLEAN)
        qst_list.set_model(store)
        qst_list.connect("row-activated", self._send_qst)

        typ = gtk.TreeViewColumn("Type",
                                 gtk.CellRendererText(), text=1)
        frq = gtk.TreeViewColumn("Freq",
                                 gtk.CellRendererText(), text=2)
        cnt = gtk.TreeViewColumn("Remaining",
                                 gtk.CellRendererProgress(), text=3)
        msg = gtk.TreeViewColumn("Content",
                                 gtk.CellRendererText(), text=4)
        r = gtk.CellRendererToggle()
        r.connect("toggled", self._toggle_qst, store, 5, 0)
        enb = gtk.TreeViewColumn("On", r, active=5)

        qst_list.append_column(typ)
        qst_list.append_column(frq)
        qst_list.append_column(cnt)
        qst_list.append_column(enb)
        qst_list.append_column(msg)

        qsts = [x for x in self._config.sections() if x.startswith("qst_")]
        for qst in qsts:
            store.append((qst,
                          self._config.get(qst, "type"),
                          self._config.get(qst, "freq"),
                          1.0,
                          self._config.get(qst, "content"),
                          self._config.getboolean(qst, "enabled")))


class ChatTab(MainWindowElement):
    __gsignals__ = {
        "user-sent-message" : (gobject.SIGNAL_RUN_LAST,
                               gobject.TYPE_NONE,
                               (gobject.TYPE_STRING, gobject.TYPE_STRING))
        }

    def display_line(self, text, *attrs):
        """Display a single line of text with datestamp"""
        line = "[DATE] %s%s" % (text, os.linesep)

        display, = self._getw("display")
        buffer = display.get_buffer()

        buffer.insert_at_cursor(line)

    def _send_button(self, button, dest, entry, buffer):
        station = dest.get_active_text()
        text = entry.get_text()
        entry.set_text("")

        self.display_line(text)
        self.emit("user-sent-message", station, text)

    def _send_qm(self, qm, msg):
        self.display_line(msg)
        self.emit("user-sent-message", "CQCQCQ", msg)

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
        self._qm.connect("user-sent-qm", self._send_qm)
        self._qst = ChatQST(wtree, config)



