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

from d_rats.ui.main_common import MainWindowElement, MainWindowTab
from d_rats.ui.main_common import ask_for_confirmation, display_error
from d_rats import inputdialog
from d_rats import qst

class LoggedTextBuffer(gtk.TextBuffer):
    def __init__(self, logfile):
        gtk.TextBuffer.__init__(self)
        self.__logfile = file(logfile, "a", 0)

    def get_logfile(self):
        return self.__logfile.name

    def insert_with_tags_by_name(self, iter, text, *attrs):
        gtk.TextBuffer.insert_with_tags_by_name(self, iter, text, *attrs)
        self.__logfile.write(text)

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
        if not ask_for_confirmation(_("Really delete?"),
                                    self._wtree.get_widget("mainwindow")):
            return

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
        if not ask_for_confirmation(_("Really delete?"),
                                    self._wtree.get_widget("mainwindow")):
            return

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

class ChatTab(MainWindowTab):
    __gsignals__ = {
        "user-sent-message" : (gobject.SIGNAL_RUN_LAST,
                               gobject.TYPE_NONE,
                               (gobject.TYPE_STRING,
                                gobject.TYPE_STRING,
                                gobject.TYPE_BOOLEAN))
        }

    def display_line(self, text, incoming, *attrs):
        """Display a single line of text with datestamp"""

        if (time.time() - self._last_date) > 600:
            stamp = time.strftime("%Y-%m-%d %H:%M:%S")
        else:
            stamp = time.strftime("%H:%M:%S")

        line = "[%s] %s" % (stamp, text)
        self._last_date = time.time()

        self._display_line(line, incoming, "default", *attrs)

        self._notice()

    def _highlight_tab(self, num):
        child = self.__filtertabs.get_nth_page(num)
        label = self.__filtertabs.get_tab_label(child)
        mkup = "<span color='red'>%s</span>" % label.get_text()
        label.set_markup(mkup)

    def _unhighlight_tab(self, num):
        child = self.__filtertabs.get_nth_page(num)
        label = self.__filtertabs.get_tab_label(child)
        label.set_markup(label.get_text())

    def _display_matching_filter(self, text):
        for filter, (tabnum, display) in self.__filters.items():
            if filter and filter in text:
                return tabnum, display

        return self.__filters[None]

    def _display_selected(self):
        cur = self.__filtertabs.get_current_page()
        return cur, self.__filtertabs.get_nth_page(cur).child

    def _maybe_highlight_header(self, buffer, mark):
        start = buffer.get_iter_at_mark(mark)
        try:
            s, e = start.forward_search("] ", 0)
        except:
            return
        try:
            s, end = e.forward_search(": ", 0)
        except:
            return

        # If we get here, we saw '] FOO: ' so highlight between
        # the start and the end
        buffer.apply_tag_by_name("bold", start, end)
        
    def _display_line(self, text, apply_filters, *attrs):
        if apply_filters:
            tabnum, display = self._display_matching_filter(text)
        else:
            tabnum, display = self._display_selected()

        buffer = display.get_buffer()

        (start, end) = buffer.get_bounds()
        mark = buffer.create_mark(None, end, True)
        buffer.insert_with_tags_by_name(end, text + os.linesep, *attrs)
        self._maybe_highlight_header(buffer, mark)
        buffer.delete_mark(mark)

        endmark = buffer.get_mark("end")
        display.scroll_to_mark(endmark, 0.0, True, 0, 1)

        if tabnum != self.__filtertabs.get_current_page():
            self._highlight_tab(tabnum)

    def _send_button(self, button, dest, entry):
        station = dest.get_active_text()
        text = entry.get_text()
        if not text:
            return
        entry.set_text("")

        self.emit("user-sent-message", station, text, False)

    def _send_msg(self, qm, msg, raw):
        self.emit("user-sent-message", "CQCQCQ", msg, raw)

    def _bcast_file(self, but):
        dir = self._config.get("prefs", "download_dir")
        fn = self._config.platform.gui_open_file(dir)
        if not fn:
            return

        try:
            f = file(fn)
        except Exception, e:
            display_error(_("Unable to open file %s: %s") % (fn, e))
            return

        data = f.read()
        f.close()

        if len(data) > (2 << 12):
            display_error(_("File is too large to send (>8KB)"))
            return

        self.emit("user-sent-message", "CQCQCQ", "\r\n" + data, False)

    def _clear(self, but):
        num, display = self._display_selected()
        display.get_buffer().set_text("")

    def _tab_selected(self, tabs, page, num):
        self._unhighlight_tab(num)

        delf = self._wtree.get_widget("main_menu_delfilter")
        delf.set_sensitive(num != 0)

    def _save_filters(self):
        f = self.__filters.keys()
        while None in f:
            f.remove(None)
        self._config.set("state", "filters", str(f))

    def _add_filter(self, but):
        d = inputdialog.TextInputDialog(title=_("Create filter"))
        d.label.set_text(_("Enter a filter search string:"))
        r = d.run()
        text = d.text.get_text()
        d.destroy()

        if r == gtk.RESPONSE_OK:
            self._build_filter(text)
            self._save_filters()

    def _del_filter(self, but):
        idx = self.__filtertabs.get_current_page()
        page = self.__filtertabs.get_nth_page(idx)
        text = self.__filtertabs.get_tab_label(page).get_text()

        del self.__filters[text]
        self.__filtertabs.remove_page(idx)

        self._save_filters()

    def _view_log(self, but):
        num, display = self._display_selected()
        fn = display.get_buffer().get_logfile()
        self._config.platform.open_text_file(fn)

    def __init__(self, wtree, config):
        MainWindowTab.__init__(self, wtree, config, "chat")

        entry, send, dest = self._getw("entry", "send", "destination")
        self.__filtertabs, = self._getw("filtertabs")
        self.__filters = {}

        self.__filtertabs.remove_page(0)
        self.__filtertabs.connect("switch-page", self._tab_selected)

        addf = self._wtree.get_widget("main_menu_addfilter")
        addf.connect("activate", self._add_filter)

        delf = self._wtree.get_widget("main_menu_delfilter")
        delf.connect("activate", self._del_filter)

        vlog = self._wtree.get_widget("main_menu_viewlog")
        vlog.connect("activate", self._view_log)

        send.connect("clicked", self._send_button, dest, entry)
        send.set_flags(gtk.CAN_DEFAULT)
        send.connect("expose-event", lambda w, e: w.grab_default())

        entry.set_activates_default(True)
        entry.grab_focus()

        self._qm = ChatQM(wtree, config)
        self._qst = ChatQST(wtree, config)
        self._qm.connect("user-sent-qm", self._send_msg, False)
        self._qst.connect("qst-fired", self._send_msg)

        self._last_date = 0

        bcast = self._wtree.get_widget("main_menu_bcast")
        bcast.connect("activate", self._bcast_file)

        clear = self._wtree.get_widget("main_menu_clear")
        clear.connect("activate", self._clear)

        self.reconfigure()

    def _reconfigure_colors(self, buffer):
        tags = buffer.get_tag_table()

        if not tags.lookup("incomingcolor"):
            for color in ["red", "blue", "green", "grey"]:
                tag = gtk.TextTag(color)
                tag.set_property("foreground", color)
                tags.add(tag)

            tag = gtk.TextTag("bold")
            tag.set_property("weight", pango.WEIGHT_BOLD)
            tags.add(tag)

            tag = gtk.TextTag("italic")
            tag.set_property("style", pango.STYLE_ITALIC)
            tags.add(tag)

            tag = gtk.TextTag("default")
            tag.set_property("indent", -40)
            tag.set_property("indent-set", True)
            tags.add(tag)

        regular = ["incomingcolor", "outgoingcolor",
                   "noticecolor", "ignorecolor"]
        reverse = ["brokencolor"]

        for i in regular + reverse:
            tag = tags.lookup(i)
            if not tag:
                tag = gtk.TextTag(i)
                tags.add(tag)

            if i in regular:
                tag.set_property("foreground", self._config.get("prefs", i))
            elif i in reverse:
                tag.set_property("background", self._config.get("prefs", i))

    def _build_filter(self, text):
        if text is not None:
            ffn = self._config.platform.filter_filename(text)
        else:
            ffn = "Main"
        fn = self._config.platform.log_file(ffn)
        buffer = LoggedTextBuffer(fn)
        buffer.create_mark("end", buffer.get_end_iter(), False)

        display = gtk.TextView(buffer)
        display.set_wrap_mode(gtk.WRAP_WORD_CHAR)
        display.set_editable(False)
        display.set_cursor_visible(False)

        sw = gtk.ScrolledWindow()
        sw.set_policy(gtk.POLICY_AUTOMATIC, gtk.POLICY_AUTOMATIC)
        sw.add(display)

        display.show()
        sw.show()

        if text:
            lab = gtk.Label(text)
        else:
            lab = gtk.Label(_("Main"))

        lab.show()
        tabnum = self.__filtertabs.append_page(sw, lab)

        self.__filters[text] = (tabnum, display)

        self._reconfigure_colors(buffer)

    def _reconfigure_filters(self):
        for filter, (tabnum, display) in self.__filters.items():
            self.__filtertabs.remove_page(tabnum)

        self.__filters = {}

        filters = eval(self._config.get("state", "filters"))
        while None in filters:
            filters.remove(None)
        filters.insert(0, None) # Main catch-all

        for filter in filters:
            self._build_filter(filter)

    def reconfigure(self):
        if not self.__filters.has_key(None):
            # First time only
            self._reconfigure_filters()

        for num, display in self.__filters.values():
            self._reconfigure_colors(display.get_buffer())

        fontname = self._config.get("prefs", "font")
        font = pango.FontDescription(fontname)
        display.modify_font(font)

    def selected(self):
        MainWindowTab.selected(self)

        make_visible = ["main_menu_bcast", "main_menu_clear",
                        "main_menu_addfilter", "main_menu_delfilter",
                        "main_menu_viewlog"]
        
        for name in make_visible:
            item = self._wtree.get_widget(name)
            item.set_property("visible", True)

    def deselected(self):
        MainWindowTab.deselected(self)

        make_invisible = ["main_menu_bcast", "main_menu_clear",
                          "main_menu_addfilter", "main_menu_delfilter",
                          "main_menu_viewlog"]
        
        for name in make_invisible:
            item = self._wtree.get_widget(name)
            item.set_property("visible", False)
