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
import datetime

from commands import getstatusoutput as run
from config import make_choice
import mainapp

class QSTText:
    def __init__(self, gui, config, text=None, freq=None):
        self.gui = gui
        self.config = config

        self.prefix = "[QST] "
        self.text = text
        self.freq = freq
        self.enabled = False
        self.raw = False
        
        self.reschedule()        

    def _reschedule(self):
        if self.freq.startswith(":"):
            tmins = int(self.freq[1:])
            nmins = datetime.datetime.now().minute

            delta = tmins - nmins
            if delta <= 0:
                delta = 60 + delta

            print "Scheduling %s for %i mins from now" % (self.text, delta)
            self.next = time.time() + (delta * 60)
        else:
            self.next = time.time() + (int(self.freq) * 60)

    def reschedule(self):
        try:
            self._reschedule()
        except Exception, e:
            print "Failed to reschedule %s: %s" % (self.text, e)
            self.next = time.time() + 3600

    def reset(self):
        self.next = 0
        if not self.enabled:
            self.fire()

    def remaining(self):
        delta = int(self.next - time.time())
        if delta >= 0:
            return delta
        else:
            return 0

    def enable(self):
        if self.freq[0] != "0":
            self.enabled = True
            print "Starting QST `%s'" % self.text
            gobject.timeout_add(1000, self.tick)
        else:
            print "Not starting idle thread for 0-time QST"

    def disable(self):
        self.enabled = False

    def do_qst(self):
        return self.text

    def fire(self):
        if self.gui.sendable:
            print "Tick: %s" % self.text
            msg = self.do_qst()
            if msg:
                self.gui.tx_msg("%s%s" % (self.prefix, msg), self.raw)
            else:
                print "Skipping QST because GUI is not sendable"

    def tick(self):
        if not self.enabled:
            return False

        if self.remaining() == 0:
            self.fire()
            self.reschedule()

        return True

class QSTExec(QSTText):
    size_limit = 256

    def do_qst(self):
        s, o = run(self.text)
        if s:
            print "Command failed with status %i" % status

        if o and len(o) <= self.size_limit:
            print "Sending command output: %s" % o
            return o
        else:
            print "Command output length %i exceeds limit of %i" % (len(o),
                                                                    self.size_limit)

class QSTFile(QSTText):
    def do_qst(self):
        try:
            f = file(self.text)
        except:
            print "Unable to open file `%s'" % self.text
            return

        text = f.read()
        f.close()

        return text

class QSTGPS(QSTText):
    def __init__(self, gui, config, text=None, freq=None):
        QSTText.__init__(self, gui, config, text, freq)

        self.prefix = ""
        self.raw = True
        self.mainapp = mainapp.get_mainapp()

    def do_qst(self):
        fix = self.mainapp.get_position()
        fix.comment = self.text[:20]
        if fix.valid:
            return fix.to_NMEA_GGA()
        else:
            return None

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

    def ev_apply(self, widget, data=None):
        print "Apply"
        self.sync_gui(load=False)

    def ev_delete(self, widget, data=None):
        (list, iter) = self.list.get_selection().get_selected()
        list.remove(iter)

    def ev_add(self, widget, data=None):
        print "ADD event"

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

    def ev_edited_text(self, renderer, path, new_text, colnum):
        iter = self.list_store.get_iter(path)
        self.list_store.set(iter, colnum, new_text)

    def ev_edited_int(self, renderer, path, new_text, colnum):
        try:
            val = int(new_text)
            iter = self.list_store.get_iter(path)
            self.list_store.set(iter, colnum, val)
        except:
            print "Non-integral new text: %s" % new_text

    def make_b_controls(self):
        b = gtk.Button("Foo")
        b.show()
        return b

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
        self.list.set_rules_hint(True)

        sw = gtk.ScrolledWindow()
        sw.set_policy(gtk.POLICY_AUTOMATIC, gtk.POLICY_AUTOMATIC)
        sw.add(self.list)
        sw.show()

        i=0
        for R,c,t in self.columns:
            r = R()
            if R == gtk.CellRendererToggle:
                r.set_property("activatable", True)
                r.connect("toggled", self.toggle, i)
                col = gtk.TreeViewColumn(c, r, active=i)
            elif R == gtk.CellRendererText:
                r.set_property("editable", True)
                if t == int:
                    r.connect("edited", self.ev_edited_int, i)
                elif t == str:
                    r.connect("edited", self.ev_edited_text, i)
                col = gtk.TreeViewColumn(c, r, text=i)

            self.list.append_column(col)

            i += 1

        hbox.pack_start(sw, 1,1,1)
        hbox.pack_start(side, 0,0,0)

        self.list.show()
        hbox.show()

        return hbox

    def make_action_buttons(self):
        hbox = gtk.HBox(False, 0)

        okay = gtk.Button("OK", gtk.STOCK_OK)
        cancel = gtk.Button("Cancel", gtk.STOCK_CANCEL)
        apply = gtk.Button("Apply", gtk.STOCK_APPLY)

        okay.connect("clicked",
                     self.ev_okay,
                     None)
        cancel.connect("clicked",
                       self.ev_cancel,
                       None)
        apply.connect("clicked",
                      self.ev_apply,
                      None)        

        hbox.pack_end(cancel, 0,0,0)
        hbox.pack_end(apply, 0,0,0)
        hbox.pack_end(okay, 0,0,0)

        okay.set_size_request(100, -1)
        apply.set_size_request(100, -1)
        cancel.set_size_request(100, -1)
        
        okay.show()
        cancel.show()
        apply.show()
        hbox.show()

        return hbox

    def show(self):
        self.sync_gui(load=True)
        self.window.show()

    def __init__(self, title="--"):
        self.tips = gtk.Tooltips()
        # SET LIST STORE
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
    column_bool = 0
    column_time = 1
    column_type = 2
    column_text = 3
    
    def __init__(self, config):
        self.columns = [
            (gtk.CellRendererToggle, "Enabled", bool),
            (gtk.CellRendererText, "Period", str),
            (gtk.CellRendererText, "Type", str),
            (gtk.CellRendererText, "Message", str),
            ]
        self.config = config
        self.list_store = gtk.ListStore(gobject.TYPE_BOOLEAN,
                                        gobject.TYPE_STRING,
                                        gobject.TYPE_STRING,
                                        gobject.TYPE_STRING)
        
        SelectGUI.__init__(self, "QST Configuration")

        # Unset editability of the type field

        c = self.list.get_column(self.column_type)
        r = c.get_cell_renderers()[0]
        r.set_property("editable", False)

    def ev_add(self, widget, data=None):
        msg = self.msg.get_text(self.msg.get_start_iter(),
                                self.msg.get_end_iter())
        tme = self.c_tme.child.get_text()

        
        model = self.c_typ.get_model()
        typ = model[self.c_typ.get_active()][0]
        
        iter = self.list_store.append()
        self.list_store.set(iter,
                            self.column_bool, True,
                            self.column_time, tme,
                            self.column_type, typ,
                            self.column_text, msg)

        self.msg.set_text("")

    def make_b_controls(self):
        times = ["1", "5", "10", "20", "30", "60", ":15", ":30", ":45"]
        types = ["Text", "Exec", "File", "GPS"]

        self.msg = gtk.TextBuffer()
        self.entry = gtk.TextView(self.msg)
        self.entry.set_wrap_mode(gtk.WRAP_WORD)

        self.c_tme = make_choice(times)
        self.c_tme.set_size_request(80, -1)

        self.c_typ = make_choice(types, False)
        self.c_typ.set_size_request(80, -1)
        self.c_typ.set_active(0)
        self.c_typ.connect("changed", self.type_changed)

        b_add = gtk.Button("Add", gtk.STOCK_ADD)

        self.tips.set_tip(self.entry, "Enter new QST text")
        self.tips.set_tip(b_add, "Add new QST")
        self.tips.set_tip(self.c_tme, "Minutes between transmissions")
        self.tips.set_tip(self.c_typ, "`Text' sends a message, `Exec' runs a program, `File' sends the contents of a text file")

        vbox = gtk.VBox(True, 5)

        vbox.pack_start(self.c_tme)
        vbox.pack_start(self.c_typ)
        vbox.pack_start(b_add)

        b_add.connect("clicked",
                      self.ev_add,
                      None)
#        self.e_msg.connect("activate",
#                           self.ev_add,
#                           None)

        hbox = gtk.HBox(False, 5)

        sw = gtk.ScrolledWindow()
        sw.set_policy(gtk.POLICY_NEVER, gtk.POLICY_AUTOMATIC)
        sw.add(self.entry)
        sw.show()

        hbox.pack_start(sw, 1,1,0)
        hbox.pack_start(vbox, 0,0,0)

        self.c_tme.child.set_text("60")

        self.entry.show()
        self.c_tme.show()
        self.c_typ.show()
        b_add.show()
        vbox.show()
        hbox.show()

        return hbox        

    def type_changed(self, widget, data=None):
        if widget.get_active_text() in ["File", "Exec"]:
            d = gtk.FileChooserDialog("Select QST file",
                                      buttons=(gtk.STOCK_OPEN, gtk.RESPONSE_OK,
                                               gtk.STOCK_CANCEL, gtk.RESPONSE_CANCEL))
            if d.run() == gtk.RESPONSE_OK:
                self.msg.set_text(d.get_filename())
            d.destroy()   
        elif widget.get_active_text() in ["GPS"]:
            self.msg.set_text("ON D-RATS")

    def load_qst(self, section):
        freq = self.config.get(section, "freq")
        content = self.config.get(section, "content")
        enabled = self.config.getboolean(section, "enabled")
        qsttype = self.config.get(section, "type")

        iter = self.list_store.append()
        self.list_store.set(iter,
                            self.column_bool, enabled,
                            self.column_time, freq,
                            self.column_type, qsttype,
                            self.column_text, content)

    def save_qst(self, model, path, iter, data=None):
        pos = path[0]

        text, freq, enabled, qsttype = model.get(iter,
                                              self.column_text,
                                              self.column_time,
                                              self.column_bool,
                                              self.column_type)

        section = "qst_%i" % int(pos)
        self.config.config.add_section(section)
        self.config.set(section, "freq", freq)
        self.config.set(section, "content", text)
        self.config.set(section, "enabled", str(enabled))
        self.config.set(section, "type", qsttype)

    def sync_gui(self, load=True):
        sections = self.config.config.sections()

        qsts = [x for x in sections if x.startswith("qst_")]

        if load:
            for sec in qsts:
                try:
                    self.load_qst(sec)
                except Exception, e:
                    print "Failed to load QST %s: %s" % (sec, e)
        else:
            for sec in qsts:
                self.config.config.remove_section(sec)

            self.list_store.foreach(self.save_qst, None)
            self.config.save()
            self.config.refresh_app()

class QuickMsgGUI(SelectGUI):
    def __init__(self, config):
        self.columns = [(gtk.CellRendererText, "Message", str)]
        self.config = config
        self.list_store = gtk.ListStore(gobject.TYPE_STRING)

        SelectGUI.__init__(self, "Quick Messages")

    def ev_add(self, widget, data=None):
        msg = self.msg.get_text(self.msg.get_start_iter(),
                                self.msg.get_end_iter())

        iter = self.list_store.append()
        self.list_store.set(iter, 0, msg)

        print "Message: %s" % msg

        self.msg.set_text("")

    def make_b_controls(self):
        self.msg = gtk.TextBuffer()
        self.entry = gtk.TextView(self.msg)
        self.entry.set_wrap_mode(gtk.WRAP_WORD)

        b_add = gtk.Button("Add", gtk.STOCK_ADD)
        b_add.set_size_request(80, -1)
        b_add.connect("clicked",
                      self.ev_add,
                      None)

        self.tips.set_tip(self.entry, "Enter new message text")
        self.tips.set_tip(b_add, "Add new quick message")

        hbox = gtk.HBox(False, 5)

        sw = gtk.ScrolledWindow()
        sw.set_policy(gtk.POLICY_NEVER, gtk.POLICY_AUTOMATIC)
        sw.add(self.entry)
        sw.show()

        hbox.pack_start(sw, 1,1,0)
        hbox.pack_start(b_add, 0,0,0)

        b_add.show()
        self.entry.show()
        hbox.show()

        return hbox

    def load_msg(self, id):
        text = self.config.get("quick", id)

        iter = self.list_store.append()
        self.list_store.set(iter, 0, text)

    def save_msg(self, model, path, iter, data=None):
        pos = path[0]

        text = model.get(iter, 0)[0]

        self.config.set("quick", "msg_%i" % pos, text)

    def sync_gui(self, load=True):
        if not self.config.config.has_section("quick"):
            self.config.config.add_section("quick")

        msgs = self.config.config.options("quick")
        msgs.sort()

        if load:
            for i in msgs:
                self.load_msg(i)
        else:
            old_msgs = [x for x in msgs if x.startswith("msg_")]
            for i in old_msgs:
                self.config.config.remove_option("quick", i)

            self.list_store.foreach(self.save_msg, None)
            self.config.save()
            self.config.refresh_app()        

def get_qst_class(typestr):
    if typestr == "Text":
        return QSTText
    elif typestr == "Exec":
        return QSTExec
    elif typestr == "File":
        return QSTFile
    elif typestr == "GPS":
        return QSTGPS
    else:
        return None

if __name__ == "__main__":
    #g = SelectGUI("Test GUI")
    import config

    c = config.UnixAppConfig(None)
    
    g = QSTGUI(c)
    g.show()

    m = QuickMsgGUI(c)
    m.show()
    
    gtk.main()
