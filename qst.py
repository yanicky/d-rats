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
import copy
import re
import threading

from commands import getstatusoutput as run
from miscwidgets import make_choice, ListWidget
import miscwidgets
import mainapp
import platform
import inputdialog
import cap

try:
    import feedparser
    HAVE_FEEDPARSER = True
except ImportError, e:
    print "FeedParser not available"
    HAVE_FEEDPARSER = False

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
            if self.gui.menu_ag.get_action("enableqst").get_active():
                self.fire()
            else:
                print "Not firing because QSTs are disabled"

            self.reschedule()

        return True

class QSTExec(QSTText):
    size_limit = 256

    def do_qst(self):
        s, o = run(self.text)
        if s:
            print "Command failed with status %i" % s

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
        self.fix = None

    def set_fix(self, fix):
        self.fix = fix

    def do_qst(self):
        if not self.fix:
            fix = self.mainapp.get_position()
        else:
            fix = self.fix

        fix.comment = self.text[:20]

        if fix.valid:
            return fix.to_NMEA_GGA()
        else:
            return None

class QSTGPSA(QSTGPS):
    def do_qst(self):
        if not self.fix:
            fix = self.mainapp.get_position()
        else:
            fix = self.fix

        if not "::" in self.text:
            fix.comment = self.text

        if fix.valid:
            return fix.to_APRS(symtab=self.config.get("settings", "aprssymtab"),
                               symbol=self.config.get("settings", "aprssymbol"))
        else:
            return None

class QSTThreadedText(QSTText):
    def __init__(self, *a, **k):
        QSTText.__init__(self, *a, **k)

        self.thread = None

    def threaded_fire(self):
        msg = self.do_qst()
        if not msg:
            print "Skipping QST because no data was returned"
            return

        gobject.idle_add(self.gui.tx_msg,
                         "%s%s" % (self.prefix, msg),
                         self.raw)

    def fire(self):
        if self.thread:
            print "QST thread still running, not starting another"
            return

        # This is a race, but probably pretty safe :)
        self.thread = threading.Thread(target=self.threaded_fire)
        self.thread.start()
        print "Started a thread for QST data..."

class QSTRSS(QSTThreadedText):
    def __init__(self, gui, config, text=None, freq=None):
        QSTThreadedText.__init__(self, gui, config, text, freq)

        self.last_id = ""

    def do_qst(self):
        rss = feedparser.parse(self.text)

        entry = rss.entries[-1]
        if entry.id != self.last_id:
            self.last_id = entry.id
            text = str(entry.description)

            text = re.sub("<[^>]*?>", "", text)
            text = text[:8192]

            return text
        else:
            return None

class QSTCAP(QSTThreadedText):
    def __init__(self, *args, **kwargs):
        QSTThreadedText.__init__(self, *args, **kwargs)

        self.last_date = None

    def determine_starting_item(self):
        cp = cap.CAPParserURL(self.text)
        if cp.events:
            lastev = cp.events[-1]
            delta = datetime.timedelta(seconds=1)
            self.last_date = (lastev.effective - delta)
        else:
            self.last_date = datetime.datetime.now()

    def do_qst(self):
        if self.last_date is None:
            self.determine_starting_item()

        print "Last date is %s" % self.last_date

        cp = cap.CAPParserURL(self.text)
        newev = cp.events_effective_after(self.last_date)
        if not newev:
            return None

        self.last_date = newev[-1].effective

        str = ""

        for i in newev:
            print "Sending CAP that is effective %s" % i.effective
            str += "\r\n-----\r\n%s\r\n-----\r\n" % i.report()

        return str        

class QSTStation(QSTGPSA):
    def do_qst(self):
        try:
            (group, station) = self.text.split("::", 1)
            markers = self.gui.map.get_markers()
            # Ugh, this is sloppy
            self.fix = copy.copy(markers[group][station][0])
            self.fix.comment = "VIA %s" % self.config.get("user", "callsign")
        except Exception, e:
            print "QSTStation Error: %s" % e
            return None

        print "Sending position for %s/%s: %s" % (group, station, self.fix)

        return QSTGPSA.do_qst(self)

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
        self.entry = gtk.Button("Foo")
        self.entry.show()
        return self.entry

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
    
    def __init__(self, config, gui):
        self.columns = [
            (gtk.CellRendererToggle, "Enabled", bool),
            (gtk.CellRendererText, "Period", str),
            (gtk.CellRendererText, "Type", str),
            (gtk.CellRendererText, "Message", str),
            ]
        self.config = config
        self.gui = gui
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
        types = ["Text", "Exec", "File", "GPS", "GPS-A", "Station"]

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
        self.tips.set_tip(self.c_typ, "`Text' sends a message, `Exec' runs a program, `File' sends the contents of a text file", "`GPS' sends a position beacon, `GPS-A' sends an APRS beacon")

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

    def get_station(self):
        markers = self.gui.map.get_markers()
        
        stations = []

        for gname, group in markers.items():
            for station in group.keys():
                stations.append("%s::%s" % (gname, station))

        d = inputdialog.ChoiceDialog(sorted(stations))
        d.label.set_text("Select a station whose position will be sent")
        r = d.run()
        station = d.choice.get_active_text()
        d.destroy()
        if r == gtk.RESPONSE_OK:
            self.msg.set_text(station)
        
    def type_changed(self, widget, data=None):
        if widget.get_active_text() in ["File", "Exec"]:
            p = platform.get_platform()
            f = p.gui_open_file()
            if not f:
                return

            self.msg.set_text(f)
        elif widget.get_active_text() in ["Station"]:
            self.get_station()
        elif widget.get_active_text() in ["GPS", "GPS-A"]:
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

class QSTEditWidget(gtk.VBox):
    def to_qst(self):
        pass

    def from_qst(self):
        pass

    def __str__(self):
        return "Unknown"

    def reset(self):
        pass

class QSTTextEditWidget(QSTEditWidget):
    def __init__(self):
        QSTEditWidget.__init__(self, False, 2)

        self.__tb = gtk.TextBuffer()
        
        ta = gtk.TextView(self.__tb)
        ta.show()

        self.pack_start(ta, 1, 1, 1)

    def __str__(self):
        return self.__tb.get_text(self.__tb.get_start_iter(),
                                  self.__tb.get_end_iter())

    def reset(self):
        self.__tb.set_text("")
    
    def to_qst(self):
        return "Text", str(self)

    def from_qst(self, content):
        self.__tb.set_text(content)

class QSTFileEditWidget(QSTEditWidget):
    label_text = "Choose a text file.  The contents will be used " + \
        "when the QST is sent."

    def __init__(self):
        QSTEditWidget.__init__(self, False, 2)
        
        lab = gtk.Label(self.label_text)
        lab.set_line_wrap(True)
        lab.show()
        self.pack_start(lab, 1, 1, 1)
        
        self.__fn = miscwidgets.FilenameBox()
        self.__fn.show()
        self.pack_start(self.__fn, 0, 0, 0)

    def __str__(self):
        return "Read: %s" % self.__fn.get_filename()

    def reset(self):
        self.__fn.set_filename("")

    def to_qst(self):
        return "File", self.__fn.get_filename()

    def from_qst(self, content):
        self.__fn.set_filename(content)

class QSTExecEditWidget(QSTFileEditWidget):
    label_text = "Choose a script to execute.  The output will be used " + \
        "when the QST is sent"

    def __str__(self):
        return "Run: %s" % self.__fn.get_filename()

class QSTGPSEditWidget(QSTEditWidget):
    msg_limit = 20
    type = "GPS"

    def __init__(self):
        QSTEditWidget.__init__(self, False, 2)

        lab = gtk.Label("Enter your GPS message:")
        lab.set_line_wrap(True)
        lab.show()
        self.pack_start(lab, 1, 1, 1)

        hbox = gtk.HBox(False, 2)
        hbox.show()
        self.pack_start(hbox, 0, 0, 0)

        self.__msg = gtk.Entry(self.msg_limit)
        self.__msg.set_text("ON D-RATS")
        self.__msg.show()
        hbox.pack_start(self.__msg, 1, 1, 1)

        dprs = gtk.Button("DPRS")
        dprs.show()
        dprs.set_sensitive(False)
        hbox.pack_start(dprs, 0, 0, 0)
        
    def __str__(self):
        return "Message: %s" % self.__msg.get_text()

    def reset(self):
        self.__msg.set_text("")

    def to_qst(self):
        return self.type, self.__msg.get_text()

    def from_qst(self, content):
        self.__msg.set_text(content)

class QSTGPSAEditWidget(QSTGPSEditWidget):
    msg_limit = 20
    type = "GPS-A"

class QSTRSSEditWidget(QSTEditWidget):
    label_string = "Enter the URL of an RSS feed:"
    def __init__(self):
        QSTEditWidget.__init__(self, False, 2)

        lab = gtk.Label(self.label_string)
        lab.show()
        self.pack_start(lab, 1, 1, 1)

        self.__url = gtk.Entry()
        self.__url.set_text("http://")
        self.__url.show()
        self.pack_start(self.__url, 0, 0, 0)

    def __str__(self):
        return "Source: %s" % self.__url.get_text()

    def to_qst(self):
        return "RSS", self.__url.get_text()

    def from_qst(self, content):
        self.__url.set_text(content)

    def reset(self):
        self.__url.set_text("")

class QSTCAPEditWidget(QSTRSSEditWidget):
    label_string = "Enter the URL of a CAP feed:"

    def to_qst(self):
        __, val = QSTRSSEditWidget.to_qst(self)

        return "CAP", val

class QSTStationEditWidget(QSTEditWidget):
    def ev_group_sel(self, group, station):
        marks = self.__markers[group.get_active_text()]
    
        store = station.get_model()
        store.clear()
        for i in sorted(marks.keys()):
            station.append_text(i)
        if len(marks.keys()):
            station.set_active(0)

    def __init__(self):
        QSTEditWidget.__init__(self, False, 2)

        lab = gtk.Label("Choose a station whose position will be sent")
        lab.show()
        self.pack_start(lab, 1, 1, 1)

        hbox = gtk.HBox(True, 2)

        # This is really ugly, but to fix it requires more work
        self.__markers = mainapp.get_mainapp().chatgui.map.get_markers()

        self.__group = miscwidgets.make_choice(self.__markers.keys(),
                                               False,
                                               "Stations")
        self.__group.show()
        hbox.pack_start(self.__group, 0, 0, 0)

        self.__station = miscwidgets.make_choice([], False)
        self.__station.show()
        hbox.pack_start(self.__station, 0, 0, 0)

        self.__group.connect("changed", self.ev_group_sel, self.__station)
        self.ev_group_sel(self.__group, self.__station)

        hbox.show()
        self.pack_start(hbox, 0, 0, 0)

    def to_qst(self):
        if not self.__group.get_active_text():
            return None, None
        elif not self.__station.get_active_text():
            return None, None
        else:
            return "Station", "%s::%s" % (self.__group.get_active_text(),
                                          self.__station.get_active_text())

class QSTGUI2(gtk.Dialog):
    def ev_add(self, button, typew, intvw):
        self.__index += 1

        id = str(self.__index)
        freq = intvw.get_active_text()
        tstr = typew.get_active_text()
        __, cont = self.__current.to_qst()
        if not cont:
            return

        self.__listbox.add_item(id,
                                True,
                                intvw.get_active_text(),
                                typew.get_active_text(),
                                cont)

        self.__current.reset()

        sec = "qst_%s" % id
        self.__config.add_section(sec)
        self.__config.set(sec, "freq", freq)
        self.__config.set(sec, "enabled", "True")
        self.__config.set(sec, "content", cont)
        self.__config.set(sec, "type", tstr)
        
    def ev_rem(self, button):
        vals = self.__listbox.get_selected()
        if vals is None:
            return

        id = vals[0]

        self.__config.remove_section("qst_%s" % id)
        self.__listbox.remove_selected()

    def ev_type_changed(self, box, types):
        wtype = box.get_active_text()

        if self.__current:
            self.__current.hide()

        self.__current = types[wtype]
        self.__current.show()

    def ev_enable_toggled(self, listw, vals):
        id = vals[0]
        en = vals[1]

        self.__config.set("qst_%s" % id, "enabled", str(en))

    def ev_mod(self, button):
        pass

    def __init__(self, config, parent=None):
        gtk.Dialog.__init__(self,
                            parent=parent,
                            buttons=(gtk.STOCK_CLOSE, gtk.RESPONSE_OK))
        
        self.__index = 0
        self.__config = config

        hbox = gtk.HBox(False, 2)
        self.vbox.pack_start(hbox, 1, 1, 1)
        hbox.show()

        cols = [(gobject.TYPE_STRING, "__id"),
                (gobject.TYPE_BOOLEAN, "Enabled"),
                (gobject.TYPE_STRING, "Interval"),
                (gobject.TYPE_STRING, "Type"),
                (gobject.TYPE_STRING, "Content")]

        self.__listbox = ListWidget(cols)
        hbox.pack_start(self.__listbox, 1, 1, 1)
        self.__listbox.show()
        self.__listbox.connect("item-toggled", self.ev_enable_toggled)

        cbox = gtk.VBox(False, 2)

        types = {
            "Text" : QSTTextEditWidget(),
            "File" : QSTFileEditWidget(),
            "Exec" : QSTExecEditWidget(),
            "GPS"  : QSTGPSEditWidget(),
            "GPS-A": QSTGPSAEditWidget(),
            "RSS"  : QSTRSSEditWidget(),
            "CAP"  : QSTCAPEditWidget(),
            "Station" : QSTStationEditWidget(),
            }

        typew = make_choice(types.keys(), False, default="Text")
        typew.set_size_request(50, -1)
        typew.show()
        cbox.pack_start(typew, 0, 0, 0)

        intervals = ["1", "5", "10", "20", "30", "60", ":30", ":15"]

        intvw = make_choice(intervals, True, default="60")
        intvw.set_size_request(75, -1)
        intvw.show()
        cbox.pack_start(intvw, 0, 0, 0)

        add = gtk.Button(stock=gtk.STOCK_ADD)
        add.show()
        cbox.pack_start(add, 0, 0, 0)

        rem = gtk.Button(stock=gtk.STOCK_DELETE)
        rem.connect("clicked", self.ev_rem)
        rem.show()
        cbox.pack_start(rem, 0, 0, 0)

        mod = gtk.Button(stock=gtk.STOCK_EDIT)
        mod.connect("clicked", self.ev_mod)
        mod.show()
        # FIXME: I don't like this
        # cbox.pack_start(mod, 0, 0, 0)
        
        clr = gtk.Button(stock=gtk.STOCK_CLEAR)
        clr.connect("clicked", lambda x: self.__current.reset())
        clr.show()
        # FIXME: I don't like this
        # cbox.pack_start(clr, 0, 0, 0)
        
        cbox.show()
        hbox.pack_start(cbox, 0, 0, 0)
                            
        for i in types.values():
            i.set_size_request(-1, 80)
            self.vbox.pack_start(i, 0, 0, 0)

        typew.connect("changed", self.ev_type_changed, types)
        add.connect("clicked", self.ev_add, typew, intvw)
        self.__current = None
        self.ev_type_changed(typew, types)
        
        for i in self.__config.sections():
            if not i.startswith("qst_"):
                continue

            qst, id = i.split("_", 2)
            self.__index = max(self.__index, int(id) + 1)
            self.__listbox.add_item(id,
                                    self.__config.getboolean(i, "enabled"),
                                    self.__config.get(i, "freq"),
                                    self.__config.get(i, "type"),
                                    self.__config.get(i, "content"))

        self.set_size_request(600,300)

def get_qst_class(typestr):
    classes = {
        "Text"    : QSTText,
        "Exec"    : QSTExec,
        "File"    : QSTFile,
        "GPS"     : QSTGPS,
        "GPS-A"   : QSTGPSA,
        "Station" : QSTStation,
        "RSS"     : QSTRSS,
        "CAP"     : QSTCAP,
        }

    if not HAVE_FEEDPARSER:
        del classes["RSS"]

    return classes.get(typestr, None)
