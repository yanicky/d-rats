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

import pygtk
import gtk
import pango
import serial
import gobject
import time
import os
import re

import xmodem
import ddt

from threading import Thread

from xfergui import FileTransferGUI
from qst import QSTGUI, QuickMsgGUI
import mainapp

class ChatGUI:
    def ev_delete(self, widget, event, data=None):
        self.window.set_default_size(*self.window.get_size())
        return False

    def sig_destroy(self, widget, data=None):
        print "Window destroyed"

    def sig_send_button(self, widget, data=None):
        text = data.get_text()
        if text == "":
            return

        # FIXME: Need to limit this number
        iter = self.history.append()
        self.history.set(iter, 0, text)

        self.tx_msg(text)
        
        data.set_text("")

    def ev_focus(self, widget, event, data=None):
        if self.window.get_urgency_hint():
            self.window.set_urgency_hint(False)

    def display(self, string, *attrs):
        #string = string.rstrip("\r")

        # Filter incoming to just ASCII-printable
        c = '?'
        xlate = ([c] * 32) +    \
                [chr(x) for x in range(32,126)] + \
                ([c] * 130)

        xlate[ord('\n')] = '\n'
        xlate[ord('\r')] = '\r'

        string = string.translate("".join(xlate))

        end = self.main_buffer.get_end_iter()

        self.main_buffer.insert_with_tags_by_name(end,
                                                  string,
                                                  *attrs)

        #print "Displaying: %s" % list(string)

        adj = self.scroll.get_vadjustment()
        adj.value = adj.upper
        self.scroll.set_vadjustment(adj)

    def display_line(self, text, *attrs):
        stamp = time.strftime("%H:%M:%S: ")

        ignore = self.config.config.get("prefs", "ignorere")
        notice = self.config.config.get("prefs", "noticere")

        if ignore and re.search(ignore, text):
            attrs += ("ignorecolor", )
        elif notice and re.search(notice, text):
            attrs += ("noticecolor", )

        self.display(stamp + text + os.linesep, *attrs)

    def tx_msg(self, string):
        call = self.config.config.get("user", "callsign")
        message = "%s> %s" % (call, string)

        self.display_line(message, "outgoingcolor")
        self.mainapp.comm.send_text(message)

        if self.config.config.getboolean("prefs", "blinkmsg"):
            self.window.set_urgency_hint(True)

    def make_entry_box(self):
        hbox = gtk.HBox(False, 0)
        
        button = gtk.Button("Send")
        entry = gtk.Entry()

        self.history = gtk.ListStore(gobject.TYPE_STRING)
        completion = gtk.EntryCompletion()
        completion.set_model(self.history)
        completion.set_text_column(0)
        completion.set_minimum_key_length(1)
        entry.set_completion(completion)

        button.connect("clicked",
                       self.sig_send_button,
                       entry)
        entry.connect("activate",
                      self.sig_send_button,
                      entry)
        
        hbox.pack_start(entry, 1, 1, 1)
        hbox.pack_start(button, 0, 0, 1)
        
        entry.show()
        button.show()

        self.entry = entry
        self.send_button = button
        
        return hbox

    def make_display(self):
        self.textview = gtk.TextView(self.main_buffer)
        self.textview.set_editable(False)
        self.textview.set_wrap_mode(gtk.WRAP_WORD)

        self.scroll = gtk.ScrolledWindow()
        self.scroll.set_policy(gtk.POLICY_NEVER, gtk.POLICY_AUTOMATIC)
        self.scroll.add(self.textview)

        self.textview.show()

        return self.scroll

    def toggle_sendable(self, state):
        self.entry.set_sensitive(state)
        self.send_button.set_sensitive(state)
        if state:
            self.mainapp.comm.enable(self)
        else:
            self.mainapp.comm.disable()
        
    def make_main_pane(self):
        vbox = gtk.VBox(False, 0)
        disp = self.make_display()
        ebox = self.make_entry_box()

        vbox.pack_start(disp, 1, 1, 1)
        vbox.pack_start(ebox, 0, 0, 1)

        disp.show()
        ebox.show()

        return vbox

    def refresh_colors(self, first_time=False):

        fontname = self.config.config.get("prefs", "font")
        font = pango.FontDescription(fontname)
        self.textview.modify_font(font)

        tags = self.main_buffer.get_tag_table()
        
        if first_time:
            tag = gtk.TextTag("red")
            tag.set_property("foreground", "Red")
            tags.add(tag)

            tag = gtk.TextTag("blue")
            tag.set_property("foreground", "Blue")
            tags.add(tag)

            tag = gtk.TextTag("green")
            tag.set_property("foreground", "Green")
            tags.add(tag)

            tag = gtk.TextTag("grey")
            tag.set_property("foreground", "Grey")
            tags.add(tag)

            tag = gtk.TextTag("bold")
            tag.set_property("weight", pango.WEIGHT_BOLD)
            tags.add(tag)

            tag = gtk.TextTag("italic")
            tag.set_property("style", pango.STYLE_ITALIC)
            tags.add(tag)

        for i in ["incomingcolor", "outgoingcolor",
                  "noticecolor", "ignorecolor"]:
            if tags.lookup(i):
                tags.remove(tags.lookup(i))

            tag = gtk.TextTag(i)
            tag.set_property("foreground", self.config.config.get("prefs", i))
            tags.add(tag)

    def set_window_defaults(self, window):
        window.set_geometry_hints(None, min_width=400, min_height=200)

        try:
            h = self.config.config.getint("state", "main_size_x")
            w = self.config.config.getint("state", "main_size_y")
            window.set_default_size(h, w)
        except Exception, e:
            print "Failed to set window size: %s" % e

        window.set_border_width(1)
        window.set_title("D-RATS")

    def make_window(self):
        self.window = gtk.Window(gtk.WINDOW_TOPLEVEL)

        self.set_window_defaults(self.window)

        self.window.add(self.mainpane)

        self.root = mainpane

        self.window.connect("delete_event", self.ev_delete)
        self.window.connect("destroy", self.sig_destroy)
        self.window.connect("focus", self.ev_focus)
        self.window.show()

        self.entry.grab_focus()

    def __init__(self, config, mainapp):
        self.config = config
        self.mainapp = mainapp
        self.tips = gtk.Tooltips()

        self.main_buffer = gtk.TextBuffer()

        self.mainpane = self.make_main_pane()
        self.mainpane.show()

        self.window = None

        self.refresh_colors(first_time=True)

    def show(self):
        if not self.window:
            self.make_window()

        self.window.show()

class ChatFilter:
    def __init__(self, tabs):
        self.exclusive = True
        self.tabs = tabs
      
    def is_active(self):
        current = self.tabs.get_current_page()
        me = self.tabs.page_num(self.tab_child)

        print "current: %i me: %i" % (current, me)

        return current == me
 
    def set_waiting(self, state):
        if state and not self.is_active():
            self.label.set_markup("<span foreground='red'>%s</span>" % \
                                      self.label.get_text())
        else:
            self.label.set_markup(self.label.get_text())

class MainChatGUI(ChatGUI):
    
    def display_line(self, string, *attrs):
        for f in self.filters:
            if f.text and f.text in string:
                f.root.display_line(string, *attrs)
                f.set_waiting(True)
                if f.exclusive:
                    return

        ChatGUI.display_line(self, string, *attrs)
        self.filters[0].set_waiting(True)

    def sig_destroy(self, widget, data=None):
        if self.config.config.getboolean("prefs", "dosignoff"):
            self.tx_msg(self.config.config.get("prefs", "signoff"))

        h, w = self.window.get_size()
        print "Setting %s size to %i,%i" % (self.window.get_title(), h,w)
        self.config.config.set("state", "main_size_x", h)
        self.config.config.set("state", "main_size_y", w)

        gtk.main_quit()

    def tx_file(self, filename):
        try:
            f = file(filename)
        except:
            self.display_line("Unable to open file `%s'" % filename,
                              "red", "italic")
            return

        filedata = f.read()
        f.close()

        notice = "Sending file %s" % filename
        self.display_line(notice + os.linesep,
                          "blue", "italic")
        self.tx_msg("%s\n%s" % (notice, filedata))

    def send_text_file(self):
        fc = gtk.FileChooserDialog("Select a text file to send",
                                   None,
                                   gtk.FILE_CHOOSER_ACTION_OPEN,
                                   (gtk.STOCK_CANCEL, gtk.RESPONSE_CANCEL,
                                    gtk.STOCK_OPEN, gtk.RESPONSE_OK))
        d = self.config.config.get("prefs", "download_dir")
        fc.set_current_folder(d)

        result = fc.run()
        if result == gtk.RESPONSE_CANCEL:
            fc.destroy()
            return
        else:
            filename = fc.get_filename()
            fc.destroy()
            self.tx_file(filename)
  
    def select_page(self, tabs, page, page_num, data=None):
        page = tabs.get_nth_page(page_num)
        label = tabs.get_tab_label(page)
        label.set_markup(label.get_text())

    def make_main_pane(self,):
        vbox1 = gtk.VBox(False, 0)
        vbox2 = gtk.VBox(False, 0)
        disp = self.make_display()
        ebox = self.make_entry_box()

        vbox2.pack_start(disp, 1, 1, 1)
        vbox2.pack_start(ebox, 0, 0, 1)

        self.tabs = gtk.Notebook()
        self.tabs.set_property("show-tabs", False)
        tab_label = gtk.Label("Main")
        self.tabs.append_page(vbox2, tab_label)
        self.tabs.connect("switch-page",
                          self.select_page,
                          None)

        main_filter = ChatFilter(self.tabs)
        main_filter.text = None
        main_filter.label = tab_label
        main_filter.tab_child = vbox2
        self.filters.append(main_filter)

        vbox1.pack_start(self.menubar, 0, 1, 0)
        vbox1.pack_start(self.tabs, 1, 1, 1)

        disp.show()
        ebox.show()
        self.tabs.show()
        vbox1.show()
        vbox2.show()

        return vbox1

    def show_about(self):
        d = gtk.AboutDialog()

        d.set_name("D-RATS")
        d.set_version(mainapp.DRATS_VERSION)
        d.set_copyright("Copyright 2008 Dan Smith (KI4IFW)")
        d.set_website("http://d-rats.danplanet.com")
        d.set_authors(("Dan Smith <dsmith@danplanet.com>",))
        
        d.run()
        d.destroy()

    def menu_handler(self, _action):
        action = _action.get_name()

        xfer = self.config.xfer()

        if action == "quit":
            self.sig_destroy(None)
        elif action == "send":
            xfer = FileTransferGUI(self, xfer)
            xfer.do_send()
        elif action == "recv":
            xfer = FileTransferGUI(self, xfer)
            xfer.do_recv()
        elif action == "config":
            self.config.show()
        elif action == "qsts":
            qsts = QSTGUI(self.config)
            qsts.show()
        elif action == "clear":
            self.main_buffer.set_text("")
        elif action == "quickmsg":
            qm = QuickMsgGUI(self.config)
            qm.show()
        elif action == "sendtext":
            self.send_text_file()
        elif action == "about":
            self.show_about()

    def make_menubar(self):
        menu_xml = """
        <ui>
          <menubar name='MenuBar'>
            <menu action='file'>
              <menuitem action='sendtext'/>
              <menuitem action='send'/>
              <menuitem action='recv'/>
              <separator/>
              <menuitem action='config'/>
              <menuitem action='qsts'/>
              <menuitem action='quickmsg'/>
              <separator/>
              <menuitem action='quit'/>
            </menu>
            <menu action='view'>
              <menuitem action='clear'/>
              <menuitem action='advanced'/>
            </menu>
            <menu action='help'>
              <menuitem action='about'/>
            </menu>
          </menubar>
        </ui>
        """

        actions = [('file', None, "_File", None, None, self.menu_handler),
                   ('send', None, "_Send File", None, None, self.menu_handler),
                   ('recv', None, "_Receive File", None, None, self.menu_handler),
                   ('config', None, "Main _Settings", None, None, self.menu_handler),
                   ('qsts', None, "_Auto QST Settings", None, None, self.menu_handler),
                   ('quickmsg', None, 'Quick _Messages', None, None, self.menu_handler),
                   ('quit', None, "_Quit", None, None, self.menu_handler),
                   ('sendtext', None, 'Send _Text File', None, None, self.menu_handler),
                   ('view', None, "_View", None, None, self.menu_handler),
                   ('clear', None, '_Clear', None, None, self.menu_handler),
                   ('help', None, '_Help', None, None, self.menu_handler),
                   ('about', None, '_About', None, None, self.menu_handler)]

        advanced = gtk.ToggleAction("advanced", "_Advanced", None, None)
        advanced.connect("toggled", self.show_advanced, None)

        uim = gtk.UIManager()
        ag = gtk.ActionGroup("MenuBar")

        ag.add_actions(actions)
        ag.add_action(advanced)

        uim.insert_action_group(ag, 0)
        menuid = uim.add_ui_from_string(menu_xml)

        return uim.get_widget("/MenuBar")

    def refresh_advanced(self):
        for i in self.adv_controls:
            i.refresh()

    def show_advanced(self, action, data=None):
        w, h = self.window.get_size()
        height = 200

        if not action.get_active():
            self.advpane.hide()
            self.window.resize(w, h-height)
        else:
            print "Showing advpane"
            self.advpane.show()
            self.window.resize(w, h+height)
            self.pane.set_position(h)
        
    def make_advanced(self):
        nb = gtk.Notebook()
        nb.set_tab_pos(gtk.POS_BOTTOM)

        self.adv_controls = []

        qm = QuickMessageControl(self, self.config)
        qm.show()
        nb.append_page(qm.root, gtk.Label("Quick Messages"))
        self.adv_controls.append(qm)

        qm = QSTMonitor(self, self.mainapp)
        qm.show()
        nb.append_page(qm.root, gtk.Label("QST Monitor"))
        self.adv_controls.append(qm)

        return nb

    def make_window(self):
        self.window = gtk.Window(gtk.WINDOW_TOPLEVEL)

        self.advpane = self.make_advanced()

        self.pane = gtk.VPaned()
        self.pane.add1(self.mainpane)
        self.pane.add2(self.advpane)
        self.pane.show()

        self.set_window_defaults(self.window)

        self.window.add(self.pane)
        self.window.connect("delete_event", self.ev_delete)
        self.window.connect("destroy", self.sig_destroy)
        self.window.connect("focus", self.ev_focus)
        self.window.show()

        self.entry.grab_focus()

    def activate_filter(self, _, text):
        filter = ChatFilter(self.tabs)

        filter.root = ChatGUI(self.config, self.mainapp)
        filter.tab_child = filter.root.mainpane
        filter.label = gtk.Label(text)
        filter.text = text

        self.tabs.append_page(filter.tab_child, filter.label)
        self.tabs.set_tab_reorderable(filter.tab_child, True)
        self.tabs.set_property("show-tabs", True)

        self.filters.append(filter)

    def popup(self, view, menu, data=None):
        filter_item = gtk.MenuItem(label="Filter on this string")
        
        bounds = self.main_buffer.get_selection_bounds()
        if not bounds:
            return

        text = self.main_buffer.get_text(bounds[0], bounds[1])
        filter_item.connect("activate",
                            self.activate_filter,
                            text)

        filter_item.show()
        menu.prepend(filter_item)

    def __init__(self, config, _mainapp):
        self.menubar = self.make_menubar()
        self.menubar.show()
        self.filters = []

        ChatGUI.__init__(self, config, _mainapp)

        self.display("D-RATS v%s " % mainapp.DRATS_VERSION, "red")
        self.display("(Copyright 2008 Dan Smith KI4IFW)\n",
                     "blue", "italic")
        
        self.textview.connect("populate-popup",
                              self.popup,
                              None)

        self.show()

    def main(self):
        gtk.gdk.threads_init()
        gtk.gdk.threads_enter()
        gtk.main()
        gtk.gdk.threads_leave()

class QuickMessageControl:
    def __init__(self, gui, config):
        self.gui = gui
        self.config = config
        
        self.root = gtk.VBox(False, 5)

        self.store = gtk.ListStore(gobject.TYPE_STRING)
        self.list = gtk.TreeView(self.store)
        self.list.set_rules_hint(True)

        r = gtk.CellRendererText()
        col = gtk.TreeViewColumn("Quick messages", r, text=0)
        self.list.append_column(col)

        self.list.connect("row-activated", self.implicit_send, None)

        self.root.pack_start(self.list, 1,1,1)

        send = gtk.Button("Send")
        send.set_size_request(100, -1)
        send.connect("clicked", self.send, None)

        self.root.pack_start(send, 0,0,0)

        self.list.show()
        send.show()

        self.gui.tips.set_tip(self.list, "Double-click to send")

        self.visible = False

    def send(self, widget, data=None):
        (list, iter) = self.list.get_selection().get_selected()

        text = list.get(iter, 0)[0]

        self.gui.tx_msg(text)

    def implicit_send(self, view, path, column, data=None):
        self.send(self.list)

    def refresh(self):
        self.store.clear()
        
        msgs = self.config.config.options("quick")
        for msg in msgs:
            text = self.config.config.get("quick", msg)

            iter = self.store.append()
            self.store.set(iter, 0, text)

    def show(self):
        self.refresh()
        self.root.show()
        self.visible = True

    def hide(self):
        self.root.hide()
        self.visible = False

class QSTMonitor:
    def make_display(self):

        self.col_index  = 0
        self.col_period = 1
        self.col_remain = 2
        self.col_status = 3
        self.col_msg    = 4

        self.store = gtk.ListStore(gobject.TYPE_INT,
                                   gobject.TYPE_INT,
                                   gobject.TYPE_INT,
                                   gobject.TYPE_STRING,
                                   gobject.TYPE_STRING)
        self.view = gtk.TreeView(self.store)

        self.tips.set_tip(self.view,
                          "Double-click on a row to reset the timer " +
                          "and send now")

        self.view.connect("row-activated", self.reset_qst, None)

        r = gtk.CellRendererText()
        c = gtk.TreeViewColumn("Period", r, text=self.col_period)
        self.view.append_column(c)

        r = gtk.CellRendererProgress()
        c = gtk.TreeViewColumn("Remaining", r,
                               value=self.col_remain, text=self.col_status)
        self.view.append_column(c)

        r = gtk.CellRendererText()
        c = gtk.TreeViewColumn("Message", r, text=self.col_msg)
        self.view.append_column(c)

        return self.view

    def reset_qst(self, view, path, col, data=None):
        iter = self.store.get_iter(path)

        index = self.store.get(iter, self.col_index)[0]

        self.mainapp.qsts[index].reset_timer()

    def update(self, model, path, iter, data=None):
        index = model.get(iter, self.col_index)[0]

        qst = self.mainapp.qsts[index]

        max = qst.freq * 60
        rem = qst.remaining

        if rem < 90:
            status = "%i sec" % rem
        else:
            status = "%i min" % (rem / 60)

        val = (float(rem) / float(max)) * 100.0

        self.store.set(iter,
                       self.col_remain, val,
                       self.col_status, status)

    def update_thread(self):
        while self.enabled:
            self.store.foreach(self.update, None)
            time.sleep(1)

    def add_qst(self, index, qst):

        max = qst.freq * 60
        rem = qst.remaining
        msg = qst.text

        if rem < 90:
            status = "%i sec" % rem
        else:
            status = "%i min" % (rem / 60)

        iter = self.store.append()
        self.store.set(iter,
                       self.col_index, index,
                       self.col_period, max / 60,
                       self.col_remain, (rem / max) * 100,
                       self.col_status, status,
                       self.col_msg, msg)
        

    def refresh(self):
        if self.thread:
            self.enabled = False
            self.thread.join()

        self.store.clear()

        for i in range(0, len(self.mainapp.qsts)):
            self.add_qst(i, self.mainapp.qsts[i])

        self.enabled = True
        self.thread = Thread(target=self.update_thread)
        self.thread.start()

    def __init__(self, gui, mainapp):
        self.gui = gui
        self.mainapp = mainapp
        self.thread = None

        self.tips = gtk.Tooltips()

        self.root = self.make_display()

    def show(self):
        self.root.show()
    
    def hide(self):
        self.root.hide()

if __name__ == "__main__":
    gui = ChatGUI()
    try:
        gui.main()
    except KeyboardInterrupt:
        gui.sig_destroy(None)
