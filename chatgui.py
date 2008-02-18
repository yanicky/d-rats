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
import glob
import ConfigParser

import xmodem
import ddt

from threading import Thread

from xfergui import FileTransferGUI, FormTransferGUI
from qst import QSTGUI, QuickMsgGUI
from inputdialog import TextInputDialog, ChoiceDialog
from utils import filter_to_ascii
import mainapp
import formgui
import formbuilder

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
        string = filter_to_ascii(string)

        end = self.main_buffer.get_end_iter()

        self.main_buffer.insert_with_tags_by_name(end,
                                                  string,
                                                  *attrs)
        
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

        ChatGUI.display_line(self, message, "outgoingcolor")
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
            self.mainapp.comm.disable()
            self.tx_file(filename)
            self.mainapp.comm.enable(self)
  
    def select_page(self, tabs, page, page_num, data=None):
        page = tabs.get_nth_page(page_num)
        label = tabs.get_tab_label(page)
        label.set_markup(label.get_text())

        mi = self.menu_ag.get_action("unfilter")
        mi.set_sensitive(page_num != 0)

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

    def filter_view(self):
        d = TextInputDialog("Create filter")
        d.label.set_text("Enter a regular expression to define the filter:")
        
        res = d.run()
        if res == gtk.RESPONSE_OK:
            self.activate_filter(None, d.text.get_text())            

        d.destroy()

    def filter_kill(self):
        tab = self.tabs.get_nth_page(self.tabs.get_current_page())

        for i in range(0, len(self.filters)):
            f = self.filters[i]
            if f.tab_child == tab and \
                    f.text is not None:
                del self.filters[i]
                self.tabs.remove_page(i)
                break

        if len(self.filters) == 1:
            self.tabs.set_show_tabs(False)

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
        elif action == "filter":
            self.filter_view()
        elif action == "unfilter":
            self.filter_kill()
        elif action == "manageform":
            formbuilder.FormManagerGUI(self.config.form_source_dir())

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
              <menuitem action='manageform'/>
              <separator/>
              <menuitem action='quit'/>
            </menu>
            <menu action='view'>
              <menuitem action='clear'/>
              <menuitem action='filter'/>
              <menuitem action='unfilter'/>
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
                   ('manageform', None, '_Manage Form Templates', None, None, self.menu_handler),
                   ('quit', None, "_Quit", None, None, self.menu_handler),
                   ('sendtext', None, 'Broadcast _Text File', None, None, self.menu_handler),
                   ('view', None, "_View", None, None, self.menu_handler),
                   ('clear', None, '_Clear', None, None, self.menu_handler),
                   ('filter', None, '_Filter by string', None, None, self.menu_handler),
                   ('unfilter', None, '_Remove current filter', None, None, self.menu_handler),
                   ('help', None, '_Help', None, None, self.menu_handler),
                   ('about', None, '_About', None, None, self.menu_handler)]

        advanced = gtk.ToggleAction("advanced", "_Advanced", None, None)
        try:
            advanced.set_active(self.config.config.getint("state",
                                                          "main_advanced") != 0)
        except Exception, e:
            print "Unable to get advanced state: %s" % e

        advanced.connect("toggled", self.show_advanced, None)

        uim = gtk.UIManager()
        self.menu_ag = gtk.ActionGroup("MenuBar")

        self.menu_ag.add_actions(actions)
        self.menu_ag.add_action(advanced)

        uim.insert_action_group(self.menu_ag, 0)
        menuid = uim.add_ui_from_string(menu_xml)

        return uim.get_widget("/MenuBar")

    def refresh_advanced(self):
        for i in self.adv_controls:
            i.refresh()

    def refresh_window(self, size):
        gtk.gdk.threads_enter()
        self.advpane.show()
        self.pane.set_position(size)
        self.window.queue_draw()
        gtk.gdk.threads_leave()

    def show_advanced(self, action, data=None):
        w, h = self.window.get_size()

        screen_height = gtk.gdk.screen_height()
        ypos = self.window.get_position()[1]
        max_y = screen_height - 60
        height_delta = 200

        if h+ypos+height_delta > max_y:
            height_delta = max_y - (h + ypos)

        if not action.get_active():
            self.advpane.hide()
            self.window.resize(w, self.pane.get_position())
            self.config.config.set("state", "main_advanced", 0)
        else:
            self.window.resize(w, h+height_delta)
            self.config.config.set("state", "main_advanced", h)
        
        print "New window size: %ix%i" % self.window.get_size()

        # No idea why, but Win32 has some issue such that doing the resize
        # and the pane show at the same time causes a missed refresh
        gobject.idle_add(self.refresh_window, h)

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

        fm = FormManager(self)
        fm.show()
        nb.append_page(fm.root, gtk.Label("Form Manager"))
        self.adv_controls.append(fm)

        return nb

    def make_window(self):
        self.window = gtk.Window(gtk.WINDOW_TOPLEVEL)

        self.advpane = self.make_advanced()

        self.pane = gtk.VPaned()
        self.pane.add1(self.mainpane)
        self.pane.add2(self.advpane)
        self.pane.show()
        
        try:
            ph = self.config.config.getint("state", "main_advanced")
            if ph > 0:
                self.advpane.show()
                print "Pane Height: %i" % ph
                self.pane.set_position(ph)
        except Exception, e:
            print "Unable to get advanced state: %s" % e

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
        self.config = config # Set early for make_menubar()

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
        gtk.main()

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
        c.set_sort_column_id(self.col_period)
        self.view.append_column(c)

        r = gtk.CellRendererProgress()
        c = gtk.TreeViewColumn("Remaining", r,
                               value=self.col_remain, text=self.col_status)
        c.set_sort_column_id(self.col_status)
        self.view.append_column(c)

        r = gtk.CellRendererText()
        c = gtk.TreeViewColumn("Message", r, text=self.col_msg)
        c.set_sort_column_id(self.col_msg)
        c.set_resizable(True)
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

    def update_at_idle(self):
        gtk.gdk.threads_enter()
        self.store.foreach(self.update, None)
        gtk.gdk.threads_leave()
        
    def update_thread(self):
        while self.enabled:
            time.sleep(1)
            gobject.idle_add(self.update_at_idle)

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

class FormManager:
    def id_edited(self, r, path, new_text, colnum):
        iter = self.store.get_iter(path)

        (index, filename, stamp) = self.store.get(iter,
                                                  self.col_index,
                                                  self.col_filen,
                                                  self.col_stamp)

        self.store.set(iter, self.col_ident, new_text)

        self.reg_form(new_text, filename, stamp)
    
    def make_display(self):
        self.col_index = 0
        self.col_ident = 1
        self.col_stamp = 2
        self.col_filen = 3
        self.col_xfert = 4

        self.store = gtk.ListStore(gobject.TYPE_INT,
                                   gobject.TYPE_STRING,
                                   gobject.TYPE_STRING,
                                   gobject.TYPE_STRING,
                                   gobject.TYPE_STRING)

        self.view = gtk.TreeView(self.store)
        self.view.set_rules_hint(True)

        r = gtk.CellRendererText()
        c = gtk.TreeViewColumn("ID", r, text=self.col_ident)
        c.set_resizable(True)
        c.set_sort_column_id(self.col_ident)
        self.view.append_column(c)

        r.set_property("editable", True)
        r.connect("edited", self.id_edited, None)

        r = gtk.CellRendererText()
        c = gtk.TreeViewColumn("Last Edited", r, text=self.col_stamp)
        c.set_sort_column_id(self.col_stamp)
        self.view.append_column(c)

        r = gtk.CellRendererText()
        c = gtk.TreeViewColumn("Last Transferred", r, text=self.col_xfert)
        c.set_sort_column_id(self.col_xfert)
        self.view.append_column(c)

        self.view.show()

        sw = gtk.ScrolledWindow()
        sw.add(self.view)
        sw.show()
        sw.set_policy(gtk.POLICY_NEVER, gtk.POLICY_AUTOMATIC)

        return sw

    def list_add_form(self, index, ident, filen, stamp=None):
        if not stamp:
            stamp = self.get_stamp()

        iter = self.store.append()
        self.store.set(iter,
                       self.col_index, index,
                       self.col_ident, ident,
                       self.col_stamp, stamp,
                       self.col_filen, filen,
                       self.col_xfert, "Never")
        return iter

    def new(self, widget, data=None):
        form_files = glob.glob(os.path.join(self.form_source_dir,
                                            "*.xml"))

        if not form_files:
            d = gtk.MessageDialog(buttons=gtk.BUTTONS_OK)
            d.set_property("text", "No template forms available")
            d.format_secondary_text("Please copy in the template forms to %s or create a new template by going to File->Manage Form Templates" % os.path.abspath(self.form_source_dir))
            d.run()
            d.destroy()
            return            

        forms = {}
        for i in form_files:
            id = os.path.basename(i).replace(".xml", "")
            forms[id] = i

        d = ChoiceDialog(forms.keys(), "Choose a form")
        d.label.set_text("Select a form type to create")
        r = d.run()
        formid = d.choice.get_active_text()
        d.destroy()
        if r == gtk.RESPONSE_CANCEL:
            return

        newfn = time.strftime(os.path.join(self.form_store_dir,
                                           "form_%m%d%Y_%H%M%S.xml"))

        form = formgui.FormFile("New %s form" % formid,
                                forms[formid])
        r = form.run_auto(newfn)
        form.destroy()
        if r == gtk.RESPONSE_CANCEL:
            return

        stamp = self.get_stamp()

        self.list_add_form(0, formid, newfn, stamp)
        self.reg_form(formid, newfn, stamp)

    def delete(self, widget, data=None):
        (list, iter) = self.view.get_selection().get_selected()

        (filename, id) = self.store.get(iter, self.col_filen, self.col_ident)

        list.remove(iter)

        self.unreg_form(filename)
        os.remove(filename)

    def send(self, widget, data=None):
        ft = FormTransferGUI(self.gui, self.config.xfer())

        (list, iter) = self.view.get_selection().get_selected()

        (filename, ) = self.store.get(iter, self.col_filen)

        #FIXME: Only update if successful
        self.store.set(iter, self.col_xfert, self.get_stamp())

        ft.do_send(filename)

    def recv_cb(self, data, success, filename, actual):
        print "Receive Callback for: %s" % filename

        fqfn = os.path.join(self.form_store_dir, filename)

        stamp = self.get_stamp()

        iter = self.list_add_form(0, "Received Form", fqfn)
        self.store.set(iter, self.col_xfert, stamp)
        self.reg_form("Received Form", fqfn, stamp)

    def recv(self, widget, data=None):
        ft = FormTransferGUI(self.gui, self.config.xfer())
        ft.register_cb(self.recv_cb, None)

        newfn = time.strftime(os.path.join(self.form_store_dir,
                                           "form_%m%d%Y_%H%M%S.xml"))
        ft.do_recv(newfn)

    def edit(self, widget, data=None):
        (list, iter) = self.view.get_selection().get_selected()

        (filename, id, stamp) = self.store.get(iter,
                                               self.col_filen,
                                               self.col_ident,
                                               self.col_stamp)

        print "Editing %s" % filename

        form = formgui.FormFile("Edit Form", filename)
        r = form.run_auto()
        form.destroy()
        if r == gtk.RESPONSE_CANCEL:
            return

        stamp = self.get_stamp()
        self.store.set(iter, self.col_stamp, stamp)
        self.reg_form(id, filename, stamp)

    def make_buttons(self):
        box = gtk.VBox(False, 2)

        newb = gtk.Button("New")
        newb.set_size_request(75, 30)
        newb.connect("clicked", self.new, None)
        newb.show()
        box.pack_start(newb, 0,0,0)

        edit = gtk.Button("Edit")
        edit.set_size_request(75, 30)
        edit.connect("clicked", self.edit, None)
        edit.show()
        box.pack_start(edit, 0,0,0)

        delb = gtk.Button("Delete") 
        delb.set_size_request(75, 30)
        delb.connect("clicked", self.delete, None)
        delb.show()
        box.pack_start(delb, 0,0,0)

        sendb = gtk.Button("Send")
        sendb.set_size_request(75, 30)
        sendb.connect("clicked", self.send, None)
        sendb.show()
        box.pack_start(sendb, 0,0,0)

        recvb = gtk.Button("Receive")
        recvb.set_size_request(75, 30)
        recvb.connect("clicked", self.recv, None)
        recvb.show()
        box.pack_start(recvb, 0,0,0)

        box.show()

        return box

    def reg_save(self):
        f = file(self.reg_file, "w")
        self.reg.write(f)
        f.close()

    def reg_form(self, id, file, editstamp):
        sec = os.path.basename(file)

        if not self.reg.has_section(sec):
            self.reg.add_section(sec)

        try :
            self.reg.set(sec, "id", id)
            self.reg.set(sec, "filename", file)
            self.reg.set(sec, "editstamp", editstamp)
            self.reg_save()
        except Exception, e:
            print "Failed to register new form: %s" % e

    def unreg_form(self, file):
        sec = os.path.basename(file)

        if self.reg.has_section(sec):
            try:
                self.reg.remove_section(sec)
                self.reg_save()
            except Exception, e:
                print "Failed to unregister form: %s" % e

    def load_forms(self):
        for i in self.reg.sections():
            try:
                id = self.reg.get(i, "id")
                filename = self.reg.get(i, "filename")
                stamp = self.reg.get(i, "editstamp")
                self.list_add_form(0, id, filename, stamp)
            except Exception, e:
                print "Failed to load form: %s" % e
                self.reg.remove_section(i)

    def get_stamp(self):
        return time.strftime("%b-%d-%Y %H:%M:%S")

    def __init__(self, gui):
        self.gui = gui
        self.config = gui.config

        self.form_source_dir = self.config.form_source_dir()
        self.form_store_dir = self.config.form_store_dir()

        self.reg_file = os.path.join(self.form_store_dir,
                                     "form_reg.conf")

        self.reg = ConfigParser.ConfigParser()
        self.reg.read(self.reg_file)

        box = gtk.HBox(False, 2)

        box.pack_start(self.make_display(), 1,1,1)
        box.pack_start(self.make_buttons(), 0,0,0)

        self.load_forms()

        self.root = box

    def show(self):
        self.root.show()

    def hide(self):
        self.root.hide()

    def refresh(self):
        pass

if __name__ == "__main__":
    import config
    gui = MainChatGUI(config.UnixAppConfig(None, safe=True), None)
    try:
        gui.main()
    except KeyboardInterrupt:
        gui.sig_destroy(None)
