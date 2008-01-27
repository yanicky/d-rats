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

import gtk
import pygtk
import gobject
import time

from threading import Thread

from config import make_choice

class QST:
    def __init__(self, gui, config, text=None, freq=None):
        self.gui = gui
        self.config = config

        self.text = "[QST] %s" % text
        self.freq = freq
        self.enabled = False

    def enable(self):
        self.enabled = True
        print "Starting QST `%s'" % self.text
        self.thread = Thread(target=self.thread)
        self.thread.start()

    def disable(self):
        self.enabled = False
        self.thread.join()

    def thread(self):
        while self.enabled:
            for i in range(0, 60 * self.freq):
                if not self.enabled:
                    return
                time.sleep(1)

            print "Tick: %s" % self.text
            gtk.gdk.threads_enter()
            self.gui.tx_msg(self.text)
            gtk.gdk.threads_leave()

class SelectGUI:
    def sync_gui(self, load=True):
        pass

    def ev_cancel(self, widget, data=None):
        print "Cancel"
        self.window.hide()

    def ev_okay(self, widget, data=None):
        print "Okay"
        self.sync_gui(load=False)
        self.window.hide()

    def ev_add(self, widget, data=None):
        msg = self.msg.get_text(self.msg.get_start_iter(),
                                self.msg.get_end_iter())
        tme = int(self.c_tme.child.get_text())

        iter = self.list_store.append()
        self.list_store.set(iter, 0, True, 1, tme, 2, msg)

        self.msg.set_text("")
        
    def ev_delete(self, widget, data=None):
        (list, iter) = self.list.get_selection().get_selected()
        list.remove(iter)

    def make_b_controls(self):
        times = ["1", "5", "10", "20", "30", "60"]

        self.msg = gtk.TextBuffer()
        self.entry = gtk.TextView(self.msg)
        self.c_tme = make_choice(times)
        self.c_tme.set_size_request(80,-1)
        b_add = gtk.Button("Add", gtk.STOCK_ADD)

        self.tips.set_tip(self.entry, "Enter new QST text")
        self.tips.set_tip(b_add, "Add new QST")
        self.tips.set_tip(self.c_tme, "Minutes between transmissions")

        vbox = gtk.VBox(True, 5)

        vbox.pack_start(self.c_tme)
        vbox.pack_start(b_add)

        b_add.connect("clicked",
                      self.ev_add,
                      None)
#        self.e_msg.connect("activate",
#                           self.ev_add,
#                           None)

        hbox = gtk.HBox(False, 5)

        hbox.pack_start(self.entry, 1,1,0)
        hbox.pack_start(vbox, 0,0,0)

        self.c_tme.child.set_text("60")

        self.entry.show()
        self.c_tme.show()
        b_add.show()
        vbox.show()
        hbox.show()

        return hbox        

    def ev_reorder(self, widget, data):
        (list, iter) = self.list.get_selection().get_selected()

        pos = int(list.get_path(iter)[0])

        try:
            if data > 0:
                target = list.get_iter(pos-1)
            else:
                target = list.get_iter(pos+1)
        except:
            return

        if target:
            list.swap(iter, target)

    def make_s_controls(self):
        vbox = gtk.VBox(True, 0)

        b_raise = gtk.Button("", gtk.STOCK_GO_UP)
        b_lower = gtk.Button("", gtk.STOCK_GO_DOWN)

        try:
            b_del = gtk.Button("Remove", gtk.STOCK_DISCARD)
        except AttributeError:
            b_del = gtk.Button("Remove")

        b_del.set_size_request(80, -1)

        b_raise.connect("clicked",
                        self.ev_reorder,
                        1)

        b_lower.connect("clicked",
                        self.ev_reorder,
                        -1)

        b_del.connect("clicked",
                      self.ev_delete,
                      None)

        self.tips.set_tip(b_raise, "Move item up in list")
        self.tips.set_tip(b_lower, "Move item down in list")
        self.tips.set_tip(b_del, "Discard item from list")

        vbox.pack_start(b_raise, 0,0,0)
        vbox.pack_start(b_del, 0,0,0)
        vbox.pack_start(b_lower, 0,0,0)

        b_raise.show()
        b_lower.show()
        b_del.show()

        vbox.show()

        return vbox

    def toggle(self, render, path, data=None):
        column = data
        self.list_store[path][column] = not self.list_store[path][column]

    def make_display(self, side):
        hbox = gtk.HBox(False, 5)

        self.list = gtk.TreeView(self.list_store)

        r = gtk.CellRendererToggle()
        r.set_property("activatable", True)
        col = gtk.TreeViewColumn("Enabled", r, active=0)
        r.connect("toggled", self.toggle, 0)
        self.list.append_column(col)

        r = gtk.CellRendererText()
        col = gtk.TreeViewColumn("Period (min)", r, text=1)
        self.list.append_column(col)

        r = gtk.CellRendererText()
        col = gtk.TreeViewColumn("Message", r, text=2)
        col.set_resizable(True)
        self.list.append_column(col)

        hbox.pack_start(self.list, 1,1,1)
        hbox.pack_start(side, 0,0,0)

        self.list.show()
        hbox.show()

        return hbox

    def make_action_buttons(self):
        hbox = gtk.HBox(False, 0)

        okay = gtk.Button("OK", gtk.STOCK_OK)
        cancel = gtk.Button("Cancel", gtk.STOCK_CANCEL)

        okay.connect("clicked",
                     self.ev_okay,
                     None)
        cancel.connect("clicked",
                       self.ev_cancel,
                       None)

        hbox.pack_end(cancel, 0,0,0)
        hbox.pack_end(okay, 0,0,0)

        okay.set_size_request(100, -1)
        cancel.set_size_request(100, -1)
        
        okay.show()
        cancel.show()
        hbox.show()

        return hbox

    def show(self):
        self.sync_gui(load=True)
        self.window.show()

    def __init__(self, title="--"):
        self.tips = gtk.Tooltips()
        self.list_store = gtk.ListStore(gobject.TYPE_BOOLEAN,
                                        gobject.TYPE_INT,
                                        gobject.TYPE_STRING)

        self.window = gtk.Window(gtk.WINDOW_TOPLEVEL)
        self.window.set_title(title)

        vbox = gtk.VBox(False, 10)

        vbox.pack_start(self.make_display(self.make_s_controls()),1,1,1)
        vbox.pack_start(self.make_b_controls(), 0,0,0)

        rule = gtk.HSeparator()
        rule.show()
        vbox.pack_start(rule, 0,0,0)
        
        vbox.pack_start(self.make_action_buttons(), 0,0,0)
        vbox.show()

        self.entry.grab_focus()

        self.window.add(vbox)

        self.window.set_geometry_hints(None, min_width=450, min_height=300)

class QSTGUI(SelectGUI):
    def __init__(self, config):
        SelectGUI.__init__(self, "QST Configuration")
        self.config = config

    def load_qst(self, section):
        freq = self.config.config.getint(section, "freq")
        content = self.config.config.get(section, "content")
        enabled = self.config.config.getboolean(section, "enabled")

        iter = self.list_store.append()
        self.list_store.set(iter, 0, enabled, 1, freq, 2, content)

    def save_qst(self, model, path, iter, data=None):
        pos = path[0]

        text, freq, enabled = model.get(iter, 2, 1, 0)

        section = "qst_%i" % int(pos)
        self.config.config.add_section(section)
        self.config.config.set(section, "freq", str(freq))
        self.config.config.set(section, "content", text)
        self.config.config.set(section, "enabled", str(enabled))

    def sync_gui(self, load=True):
        sections = self.config.config.sections()

        qsts = [x for x in sections if x.startswith("qst_")]

        if load:
            for sec in qsts:
                self.load_qst(sec)
        else:
            for sec in qsts:
                self.config.config.remove_section(sec)

            self.list_store.foreach(self.save_qst, None)
            self.config.save()
            self.config.refresh_app()

if __name__ == "__main__":
    #g = SelectGUI("Test GUI")
    import config

    c = config.UnixAppConfig(None)
    
    g = QSTGUI(c)
    g.show()
    gtk.main()
