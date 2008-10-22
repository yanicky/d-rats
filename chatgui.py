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
import datetime
import os
import re
import glob
import ConfigParser

import ddt

from xfergui import FileTransferGUI, FormTransferGUI
from qst import QuickMsgGUI, QSTGPS, QSTGPSA, QSTGUI2
from inputdialog import TextInputDialog, ChoiceDialog, ExceptionDialog, EditableChoiceDialog
from miscwidgets import YesNoDialog
from utils import filter_to_ascii
from callsigns import find_callsigns
import mainapp
import formgui
import formbuilder
import gps
import mapdisplay
import sessiongui
import image
import emailgw

from mc_xfergui import MulticastGUI, MulticastRecvGUI

default_station = None

def prompt_for_station(parent=None):
    global default_station

    ma = mainapp.get_mainapp()
    calls = ma.seen_callsigns.list()

    if default_station:
        if default_station in calls:
            calls.remove(default_station)
        calls.insert(0, default_station)

    d = EditableChoiceDialog(calls,
                             title=_("Destination Station"),
                             parent=parent)
    d.label.set_text(_("Select (or enter) a destination station"))
    r = d.run()
    dest = d.choice.get_active_text()
    d.destroy()
    if r == gtk.RESPONSE_CANCEL:
        return None
    else:
        default_station = dest.upper()
        return dest.upper()

class ChatGUI:
    def ev_delete(self, widget, event, data=None):
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

    def highlight_callsigns(self, string, start):
        if "--(EOB)--" in string:
            return
        if "--(EG)--" in string:
            return

        callsigns = find_callsigns(self.config, string)

        for call in callsigns:
            try:
                (b, e) = start.forward_search(call, 0)
            except:
                continue
            if not self.mainapp.seen_callsigns.is_known(call.upper()):
                self.main_buffer.remove_all_tags(b, e)
                self.main_buffer.apply_tag_by_name("callsigncolor", b, e)
            self.main_buffer.apply_tag_by_name("bold", b, e)

    def highlight_notices(self, string, start):
        expr = self.config.get("prefs", "noticere")
        if not expr:
            return

        notices = re.findall(expr, string)

        for notice in notices:
            (b, e) = start.forward_search(notice, 0)
            self.main_buffer.remove_all_tags(b, e)
            self.main_buffer.apply_tag_by_name("noticecolor", b, e)
            self.main_buffer.apply_tag_by_name("bold", b, e)
            
    def _trim_buffer(self):
        try:
            limit = int(float(self.config.get("prefs", "scrollback")))
        except Exception, e:
            print "Unable to get scrollback limit: %s" % e
            return

        count = self.main_buffer.get_line_count()

        if count > limit:
            print "Trimming %i" % count
            start = self.main_buffer.get_start_iter()
            end = self.main_buffer.get_iter_at_line(count - limit)
            self.main_buffer.delete(start, end)

    def display(self, string, *attrs):
        string = filter_to_ascii(string)

        (start, end) = self.main_buffer.get_bounds()
        mark = self.main_buffer.create_mark(None, end, True)

        self.main_buffer.insert_with_tags_by_name(end,
                                                  string,
                                                  *attrs)

        pos = self.main_buffer.get_iter_at_mark(mark)

        if "italic" not in attrs:
            self.highlight_callsigns(string, pos)
        self.highlight_notices(string, pos)

        self.main_buffer.delete_mark(mark)

        self._trim_buffer()
        
        endmark = self.main_buffer.get_mark("end")
        self.textview.scroll_to_mark(endmark, 0.0, True, 0, 1)

    def display_line(self, text, *attrs):
        stamp = time.strftime("%H:%M:%S: ")

        ignore = self.config.get("prefs", "ignorere")

        if ignore and re.search(ignore, text):
            attrs += ("ignorecolor", )

        self.display(stamp + text + os.linesep, *attrs)

    def tx_msg(self, string, raw=False):
        if self.mainapp.chat_session:
            if raw:
                self.mainapp.chat_session.write_raw(string)
                self.display_line(string, "outgoingcolor")
            else:
                call = self.config.get("user", "callsign")
                message = "%s> %s" % (call, string)
                ChatGUI.display_line(self, message, "outgoingcolor")
                self.mainapp.chat_session.write(string)
                self.logfn(message)
        else:
            self.display_line(_("Not connected"), "italic", "red")
            return

        if self.config.getboolean("prefs", "blinkmsg"):
            self.window.set_urgency_hint(True)

    def make_entry_box(self):
        hbox = gtk.HBox(False, 0)
        
        button = gtk.Button(_("Send"))
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
        self.sendable = state
        self.entry.set_sensitive(state)
        self.send_button.set_sensitive(state)
        if state:
            self.mainapp.comm.start_watch()
        else:
            self.mainapp.comm.stop_watch()
        
    def make_main_pane(self):
        vbox = gtk.VBox(False, 0)
        disp = self.make_display()
        ebox = self.make_entry_box()

        vbox.pack_start(disp, 1, 1, 1)
        vbox.pack_start(ebox, 0, 0, 1)

        disp.show()
        ebox.show()

        return vbox

    def _refresh_colors(self, first_time=False):

        fontname = self.config.get("prefs", "font")
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

        regular = ["incomingcolor", "outgoingcolor",
                  "noticecolor", "ignorecolor"]
        reverse = ["callsigncolor", "brokencolor"]

        for i in regular + reverse:
            tag = tags.lookup(i)
            if not tag:
                tag = gtk.TextTag(i)
                tags.add(tag)
                #tags.remove(tags.lookup(i))

            if i in regular:
                tag.set_property("foreground", self.config.get("prefs", i))
            elif i in reverse:
                tag.set_property("background", self.config.get("prefs", i))

    def refresh_config(self, first_time=False):
        self._refresh_colors(first_time)
        self.refresh_advanced()

    def set_window_defaults(self, window):
        window.set_geometry_hints(None, min_width=400, min_height=200)

        try:
            h = self.config.getint("state", "main_size_x")
            w = self.config.getint("state", "main_size_y")
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

    def __init__(self, config, mainapp, logfn=None):
        self.config = config
        self.mainapp = mainapp
        self.logfn = logfn

        self.tips = gtk.Tooltips()

        self.main_buffer = gtk.TextBuffer()
        self.main_buffer.create_mark("end",
                                     self.main_buffer.get_end_iter(),
                                     False)

        self.mainpane = self.make_main_pane()
        self.mainpane.show()

        self.sendable = True

        self.window = None

        self._refresh_colors(first_time=True)

    def show(self):
        if not self.window:
            self.make_window()

        self.window.show()

class ChatFilter:
    def __init__(self, filterstring, tabs, root):
        self.exclusive = True
        self.tabs = tabs
        if root:
            self.root = root
            self.tab_child = root.mainpane
        self.mainapp = mainapp.get_mainapp()
        self.logfn = self.mainapp.config.platform.log_file(filterstring)
        do_log = mainapp.get_mainapp().config.getboolean("prefs",
                                                         "logenabled")
        if do_log:
            try:
                self.load_back_log()
                self.logfile = file(self.logfn, "a", 0)
                if not self.logfile:
                    print "Failed to open log: %s" % self.logfn
                else:
                    print "Opened log: %s" % self.logfn
            except Exception, e:
                print "Failed to open log `%s': %s" % (self.logfn, e)
                self.logfile = None
        else:
            self.logfile = None

    def load_back_log(self):
        if not self.mainapp.config.getboolean("prefs", "logresume"):
            print "Not resuming log for filter"
            return

        try:
            f = file(self.logfn, "r")
        except:
            f = None
        if not f:
            print "Unable to load back log"
            return

        try:
            f.seek(-512, 2)
        except:
            f.seek(0)

        old_log = f.read(512)
        f.close()

        try:
            i = old_log.index(os.linesep)
            old_log = old_log[i+1:]
            self.root.display(old_log, "grey")
        except Exception, e:
            print "Unable to load old log: %s" % e            

    def set_exclusive(self, exclusive):
        self.exclusive = exclusive

    def is_active(self):
        current = self.tabs.get_current_page()
        me = self.tabs.page_num(self.tab_child)

        return current == me
 
    def set_waiting(self, state):
        if state and not self.is_active():
            self.label.set_markup("<span foreground='red'>%s</span>" % \
                                      self.label.get_text())
        else:
            self.label.set_markup(self.label.get_text())

    def log(self, string):
        string = filter_to_ascii(string)
        if self.logfile:
            stamp = time.strftime(mainapp.LOGTF)
            self.logfile.write("%s: %s%s" % (stamp, string, os.linesep))
        self.set_waiting(True)

class MainChatGUI(ChatGUI):
    
    def update_known_position(self, pos):
        station = pos.station.upper()
        self.mainapp.seen_callsigns.set_call_pos(station, pos)
        self.mainapp.seen_callsigns.set_call_time(station, time.time())

        self.map.set_marker(pos, group=_("Stations"))

        try:
            self.adv_controls["calls"].refresh()
        except Exception, e:
            print "Failed to refresh calls: %s" % e

    def display_line(self, string, *attrs):
        do_main = True

        gps_fix = gps.parse_GPS(string)
        if gps_fix:
            if gps_fix.valid:
                gps_fix.set_relative_to_current(self.mainapp.get_position())
                self.update_known_position(gps_fix)
            string = str(gps_fix)

        for f in self.filters[1:]:
            if f.text and f.text in string:
                f.root.display_line(string, *attrs)
                f.log(string)
                if f.exclusive:
                    do_main = False
            elif not f.text:
                # This is the 'all' filter
                f.root.display_line(string, *attrs)
                f.log(string)

        if do_main:
            ChatGUI.display_line(self, string, *attrs)
            self.filters[0].log(string)

    def ev_delete(self, widget, event, data=None):
        self.window.set_default_size(*self.window.get_size())
        return False

    def sig_destroy(self, widget, data=None):
        if self.config.getboolean("prefs", "dosignoff"):
            self.tx_msg(self.config.get("prefs", "signoff"))

        self.config.set("state", "main_maximized", str(self.is_maximized))

        if not self.is_maximized:
            h, w = self.window.get_size()
            print "Setting %s size to %i,%i" % (self.window.get_title(), h,w)
            self.config.set("state", "main_size_x", h)
            self.config.set("state", "main_size_y", w)

        gtk.main_quit()

    def tx_file(self, filename):
        try:
            f = file(filename)
        except:
            self.display_line(_("Unable to open file") + " `%s'" % filename,
                              "red", "italic")
            return

        filedata = f.read()
        f.close()

        if len(filedata) > (2 << 12):
            self.display_line(_("File to large (must be less than %iK)") % 8,
                              "red", "italic")
            return

        notice = _("Sending file") + " %s" % filename
        self.display_line(notice + os.linesep,
                          "blue", "italic")
        self.tx_msg("%s\n%s" % (notice, filedata))

    def send_text_file(self):
        f = self.config.platform.gui_open_file(self.config.get("prefs",
                                                               "download_dir"))
        if f:
            self.tx_file(f)
  
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
        tab_label = gtk.Label(_("Main"))
        self.tabs.append_page(vbox2, tab_label)
        self.tabs.connect("switch-page",
                          self.select_page,
                          None)

        main_filter = ChatFilter("main", self.tabs, None)
        main_filter.text = None
        main_filter.tab_child = vbox2
        main_filter.label = tab_label
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
        d.set_transient_for(self.window)

        verinfo = "GTK %s\nPyGTK %s\n" % ( \
            ".".join([str(x) for x in gtk.gtk_version]),
            ".".join([str(x) for x in gtk.pygtk_version]))

        d.set_name("D-RATS")
        d.set_version(mainapp.DRATS_VERSION)
        d.set_copyright("Copyright 2008 Dan Smith (KK7DS)")
        d.set_website("http://d-rats.danplanet.com")
        d.set_authors(("Dan Smith <dsmith@danplanet.com>",))
        d.set_comments(verinfo)

        d.set_translator_credits("Italian: Leo, IZ5FSA")
        
        d.run()
        d.destroy()

    def filter_view(self):
        d = TextInputDialog(title=_("Create filter"), parent=self.window)
        d.label.set_text(_("Enter a regular expression to define the filter:"))
        
        res = d.run()
        if res == gtk.RESPONSE_OK:
            self.activate_filter(None, d.text.get_text())            

        d.destroy()

    def filter_kill(self):
        tab = self.tabs.get_nth_page(self.tabs.get_current_page())

        for i in range(0, len(self.filters)):
            f = self.filters[i]
            if f.tab_child == tab:
                del self.filters[i]
                self.save_filters()
                self.tabs.remove_page(i)
                if f.label.get_text() == _("All"):
                    self.config.set("state", "show_all_filter", False)
                    self.menu_ag.get_action("allfilter").set_sensitive(True)
                break

        if len(self.filters) == 1:
            self.tabs.set_show_tabs(False)

    def filter_clear_current(self):
        tab = self.tabs.get_nth_page(self.tabs.get_current_page())

        for i in range(0, len(self.filters)):
            f = self.filters[i]
            if f.tab_child == tab and f.text is not None:
                f.root.main_buffer.set_text("")
                return
        
        self.main_buffer.set_text("")

    def filter_current_log(self):
        tab = self.tabs.get_nth_page(self.tabs.get_current_page())

        for f in self.filters:
            if f.tab_child == tab:
                self.config.platform.open_text_file(f.logfn)
                break

    def do_mcast_send(self):
        f = self.config.platform.gui_open_file(self.config.get("prefs",
                                                               "download_dir"))
        if not f:
            return

        try:
            bsize = self.config.getint("settings", "ddt_block_size")
        except:
            bsize = 512

        self.toggle_sendable(False)
        d = MulticastGUI(f,
                         self.mainapp.comm.path,
                         bsize,
                         parent=self.window)
        d.run()
        d.destroy()
        self.toggle_sendable(True)
        
    def do_file_transfer(self, send, fname=None):
        station = prompt_for_station(self.window)
        if not station:
            return

        if not fname:
            ddir = self.config.get("prefs", "download_dir")
            fname = self.config.platform.gui_open_file(ddir)
            if not fname:
                return

        print "Going to request file send of %s to %s" % (fname, station)
        self.adv_controls["sessions"].send_file(station, fname)
        
    def menu_handler(self, _action):
        action = _action.get_name()

        if action == "quit":
            self.sig_destroy(None)
        elif action == "send":
            self.do_file_transfer(True)
        elif action == "config":
            self.config.show(self.window)
        elif action == "qsts":
            qsts = QSTGUI2(self.config.config)
            qsts.run()
            qsts.destroy()
            self.config.refresh_app()
        elif action == "clear":
            self.filter_clear_current()
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
        elif action == "msend":
            self.do_mcast_send()
        elif action == "mrecv":
            self.toggle_sendable(False)
            t = MulticastRecvGUI(self,
                                 self.config.xfer(),
                                 title=_("Multicast Receive"),
                                 parent=self.window)
            t.do_recv()            
            t.destroy()
            self.toggle_sendable(True)
        elif action == 'thislog':
            self.filter_current_log()
        elif action == "map":
            self.map.show()
        elif action == "ping":
            s = prompt_for_station(self.window)
            if s:
                self.mainapp.chat_session.ping_station(s)
        elif action == "isend":
            f = image.send_image()
            if f:
                self.do_file_transfer(True, f)
        elif action == "debug":
            pform = self.config.platform
            path = pform.config_file("debug.log")
            if os.path.exists(path):
                pform.open_text_file(path)            
            else:
                d = gtk.MessageDialog(buttons=gtk.BUTTONS_OK)
                d.set_property("text",
                               "Debug log not available")
                d.run()
                d.destroy()

    def make_menubar(self):
        menu_xml = """
        <ui>
          <menubar name='MenuBar'>
            <menu action='file'>
              <menuitem action='sendtext'/>
              <menuitem action='send'/>
              <menuitem action='isend'/>
              <!--menuitem action='msend'/-->
              <!--menuitem action='mrecv'/-->
              <menuitem action='ping'/>
              <separator/>
              <menuitem action='config'/>
              <menuitem action='qsts'/>
              <menuitem action='quickmsg'/>
              <menuitem action='manageform'/>
              <separator/>
              <menuitem action='enableqst'/>
              <!--<menuitem action='connect'/>-->
              <menuitem action='quit'/>
            </menu>
            <menu action='view'>
              <menuitem action='clear'/>
              <menuitem action='filter'/>
              <menuitem action='unfilter'/>
              <menuitem action='allfilter'/>
              <menuitem action='thislog'/>
              <separator/>
              <menuitem action='advanced'/>
              <menuitem action='map'/>
            </menu>
            <menu action='help'>
              <menuitem action='debug'/>
              <menuitem action='about'/>
            </menu>
          </menubar>
        </ui>
        """

        actions = [('file', None, _("_File"), None, None, self.menu_handler),
                   ('send', None, _("_Send File"), "F1", None, self.menu_handler),
                   ('msend', None, _("_Multi Send File"), "F3", None, self.menu_handler),
                   ('mrecv', None, _("_Multi Recv File"), "F4", None, self.menu_handler),
                   ('config', None, _("Main _Settings"), None, None, self.menu_handler),
                   ('qsts', None, _("_Auto QST Settings"), "<Control>q", None, self.menu_handler),
                   ('quickmsg', None, _('Quick _Messages'), None, None, self.menu_handler),
                   ('manageform', None, _('_Manage Form Templates'), None, None, self.menu_handler),
                   ('quit', None, _("_Quit"), None, None, self.menu_handler),
                   ('sendtext', None, _('Broadcast _Text File'), "<Control>b", None, self.menu_handler),
                   ('ping', None, _('Ping Station'), None, None, self. menu_handler),
                   ('view', None, _("_View"), None, None, self.menu_handler),
                   ('clear', None, _('_Clear'), "<Control>l", None, self.menu_handler),
                   ('filter', None, _('_Filter by string'), "<Control>f", None, self.menu_handler),
                   ('unfilter', None, _('_Remove current filter'), "<Control>k", None, self.menu_handler),
                   ('allfilter', None, _('Show "_all" filter'), None, None, self.show_allfilter),
                   ('thislog', None, _('Log for this tab'), None, None, self.menu_handler),
                   ('map', None, _('Map'), "<Control>m", None, self.menu_handler),

                   ('help', None, _('_Help'), None, None, self.menu_handler),
                   ('debug', None, _('Show debug log'), None, None, self.menu_handler),
                   ('about', None, _('_About'), None, None, self.menu_handler)]

        advanced = gtk.ToggleAction("advanced", _("_Advanced"), None, None)
        try:
            advanced.set_active(self.config.getint("state",
                                                   "main_advanced") != 0)
        except Exception, e:
            print "Unable to get advanced state: %s" % e

        advanced.connect("toggled", self.show_advanced, None)

        connected = gtk.ToggleAction("connect", _("_Connected"), None, None)
        connected.set_active(True)
        connected.connect("toggled", self.connect, None)

        enableqst = gtk.ToggleAction("enableqst", _("QSTs Enabled"), None, None)
        enableqst.set_active(True)

        isend = gtk.Action("isend", _("Send _Image"), None, None)
        isend.set_sensitive(image.has_image_support())
        isend.connect("activate", self.menu_handler)

        uim = gtk.UIManager()
        self.menu_ag = gtk.ActionGroup("MenuBar")

        self.menu_ag.add_actions(actions)
        self.menu_ag.add_action_with_accel(advanced, "<Control>a")
        self.menu_ag.add_action_with_accel(connected, "<Control>d")
        self.menu_ag.add_action(enableqst)
        self.menu_ag.add_action(isend)

        uim.insert_action_group(self.menu_ag, 0)
        menuid = uim.add_ui_from_string(menu_xml)

        self.accel_group = uim.get_accel_group()

        return uim.get_widget("/MenuBar")

    def refresh_advanced(self):
        for i in self.adv_controls.values():
            i.refresh()

    def refresh_window(self, size):
        self.advpane.show()
        self.pane.set_position(size)
        self.window.queue_draw()

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
            self.config.set("state", "main_advanced", 0)
        else:
            self.window.resize(w, h+height_delta)
            self.config.set("state", "main_advanced", h)
        
        print "New window size: %ix%i" % self.window.get_size()

        # No idea why, but Win32 has some issue such that doing the resize
        # and the pane show at the same time causes a missed refresh
        gobject.idle_add(self.refresh_window, h)

    def connect(self, action, data=None):
        connected = action.get_active()
        if connected:
            if self.mainapp.refresh_comms():
                self.display_line(_("Connected"), "italic", "red")
            else:
                self.display_line(_("Disconnected"), "italic", "red")
        else:
            self.mainapp.stop_comms()
            self.display_line(_("Disconnected"), "italic", "red")

    def set_connected(self, bool):
        action = self.menu_ag.get_action("connect")
        action.set_active(bool)

    def show_allfilter(self, action):
        root = ChatGUI(self.config, self.mainapp, self.log_by_filter)
        all_filter = ChatFilter("all", self.tabs, root)
        all_filter.set_exclusive(False)
        all_filter.label = gtk.Label("All")
        all_filter.text = None
        
        self.config.set("state", "show_all_filter", True)

        self.tabs.append_page(all_filter.tab_child, all_filter.label)
        self.tabs.set_tab_reorderable(all_filter.tab_child, True)
        
        self.filters.append(all_filter)
        self.save_filters()

        self.menu_ag.get_action("allfilter").set_sensitive(False)

    def make_advanced(self):
        nb = gtk.Notebook()
        nb.set_tab_pos(gtk.POS_BOTTOM)

        self.adv_controls = {}

        qm = QuickMessageControl(self, self.config)
        qm.show()
        nb.append_page(qm.root, gtk.Label(_("Quick Messages")))
        self.adv_controls["quick"] = qm

        qm = QSTMonitor(self, self.mainapp)
        qm.show()
        nb.append_page(qm.root, gtk.Label(_("QST Monitor")))
        self.adv_controls["qsts"] = qm

        fm = FormManager(self)
        fm.show()
        nb.append_page(fm.root, gtk.Label(_("Form Manager")))
        self.adv_controls["forms"] = fm

        cc = CallCatcher(self)
        cc.show()
        nb.append_page(cc.root, gtk.Label(_("Callsigns")))
        self.adv_controls["calls"] = cc

        sg = sessiongui.SessionGUI(self)
        sg.show()
        nb.append_page(sg.root, gtk.Label(_("Sessions")))
        self.adv_controls["sessions"] = sg

        return nb

    def ev_window(self, window, event):
        if event.type == gtk.gdk.WINDOW_STATE:
            max = event.new_window_state & gtk.gdk.WINDOW_STATE_MAXIMIZED
            self.is_maximized = (max != 0)
    
    def ev_window_sized(self, window, req):
        def refresh(gui):
            gui.window.queue_draw()
            gui.needs_redraw = False

        if not self.needs_redraw:
            gobject.idle_add(refresh, self)
            self.needs_redraw = True

    def ev_pane_sized(self, window, req):
        self.config.set("state", "main_advanced", int(req.height))

    def make_window(self):
        self.window = gtk.Window(gtk.WINDOW_TOPLEVEL)
        self.is_maximized = False

        self.advpane = self.make_advanced()

        self.pane = gtk.VPaned()
        self.mainpane.connect("size-allocate", self.ev_pane_sized)
        self.pane.pack1(self.mainpane, False, False)
        self.pane.pack2(self.advpane, False, False)
        self.pane.show()
        
        try:
            ph = self.config.getint("state", "main_advanced")
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
        self.window.connect("window-state-event", self.ev_window)
        self.window.connect("size-allocate", self.ev_window_sized)
        self.window.add_accel_group(self.accel_group)
        self.window.show()

        try:
            if self.config.getboolean("state", "main_maximized"):
                self.window.maximize()
        except:
            pass

        self.entry.grab_focus()

    def activate_filter(self, _, text):

        root = ChatGUI(self.config, self.mainapp, self.log_by_filter)
        filter = ChatFilter(text, self.tabs, root)
        filter.label = gtk.Label(text)
        filter.text = text

        self.tabs.append_page(filter.tab_child, filter.label)
        self.tabs.set_tab_reorderable(filter.tab_child, True)
        self.tabs.set_property("show-tabs", True)

        self.filters.append(filter)

        self.save_filters()

    def popup(self, view, menu, data=None):
        filter_item = gtk.MenuItem(label=_("Filter on this string"))
        
        bounds = self.main_buffer.get_selection_bounds()
        if not bounds:
            return

        text = self.main_buffer.get_text(bounds[0], bounds[1])
        filter_item.connect("activate",
                            self.activate_filter,
                            text)

        filter_item.show()
        menu.prepend(filter_item)

    def save_filters(self):
        f = [x.text for x in self.filters]
        self.config.set("state", "filters", str(f))

    def load_filters(self):
        try:
            filters = eval(self.config.get("state", "filters"))
        except Exception, e:
            print "Error loading filters: %s" % e
            return

        for f in filters:
            if f:
                self.activate_filter(None, f)

        if self.config.getboolean("state", "show_all_filter"):
            self.show_allfilter(None)

        self.tabs.set_current_page(0)

        self.filters[0].root = self
        self.filters[0].load_back_log()

    def log_by_filter(self, text):
        tab = self.tabs.get_nth_page(self.tabs.get_current_page())

        all = None

        for i in range(0, len(self.filters)):
            f = self.filters[i]
            if f.tab_child == tab:
                f.log(text)
            elif i > 0 and f.text == None:
                # All filter
                f.log(text)

    def load_static_locations(self):
        dir = os.path.join(self.config.platform.config_dir(),
                           "static_locations")
        if not os.path.isdir(dir):
            os.mkdir(dir)

        files = glob.glob(os.path.join(dir, "*.csv"))
        for f in files:
            self.map.load_static_points(f)     

        if self.config.getboolean("prefs", "restore_stations"):
            stations = self.map.get_markers().get("Stations", {})
            for station, (fix, _, _, _) in stations.items():
                if fix.station == "Me":
                    continue
                self.mainapp.seen_callsigns.set_call_pos(station, fix)

    def save_static_locations(self):
        for group in self.map.get_markers().keys():
            fn = os.path.join(self.config.platform.config_dir(),
                              "static_locations",
                              "%s.csv" % group)
            print "Saving %s to %s" % (group, fn)
            self.map.save_static_group(group, fn)

    def set_loc_from_map(self, _, vals):
        self.config.set("user", "latitude", "%f" % vals["lat"])
        self.config.set("user", "longitude", "%f" % vals["lon"])
        self.mainapp.refresh_gps()
        self._refresh_location()
            
    def __init__(self, config, _mainapp):
        self.needs_redraw = False
        self.config = config # Set early for make_menubar()

        self.menubar = self.make_menubar()
        self.menubar.show()
        self.filters = []

        ChatGUI.__init__(self, config, _mainapp, self.log_by_filter)

        self.textview.connect("populate-popup",
                              self.popup,
                              None)

        self.map = mapdisplay.MapWindow()
        self.map.set_title(_("D-RATS Station Map"))
        self.load_static_locations()

        pos = self.mainapp.get_position()
        self.map.set_center(pos.latitude, pos.longitude)
        self.map.set_zoom(14)
        self.map.add_popup_handler(_("Set as current location"),
                                   self.set_loc_from_map)
        self._refresh_location()

        gobject.timeout_add(10000, self._refresh_location)

        self.load_filters()
        self.show()

    def _refresh_location(self):
        fix = self.mainapp.get_position()
        fix.station = _("Me")
        self.map.set_marker(fix, group=_("Stations"))
        self.map.update_gps_status(self.mainapp.gps.status_string())
        return True

    def refresh_config(self, first_time=False):
        self._refresh_location()
        ChatGUI.refresh_config(self, first_time)        

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
        col = gtk.TreeViewColumn(_("Quick messages"), r, text=0)
        self.list.append_column(col)

        self.list.connect("row-activated", self.implicit_send, None)

        self.root.pack_start(self.list, 1,1,1)

        send = gtk.Button(_("Send"))
        send.set_size_request(100, -1)
        send.connect("clicked", self.send, None)

        self.root.pack_start(send, 0,0,0)

        self.list.show()
        send.show()

        self.gui.tips.set_tip(self.list, _("Double-click to send"))

        self.visible = False

    def send(self, widget, data=None):
        (list, iter) = self.list.get_selection().get_selected()

        text = list.get(iter, 0)[0]

        self.gui.tx_msg(text)

    def implicit_send(self, view, path, column, data=None):
        self.send(self.list)

    def refresh(self):
        self.store.clear()
        
        msgs = self.config.options("quick")
        for msg in msgs:
            text = self.config.get("quick", msg)

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
                                   gobject.TYPE_STRING,
                                   gobject.TYPE_INT,
                                   gobject.TYPE_STRING,
                                   gobject.TYPE_STRING)
        self.view = gtk.TreeView(self.store)

        self.tips.set_tip(self.view,
                          _("Double-click on a row to reset the timer and send now"))

        self.view.connect("row-activated", self.reset_qst, None)

        r = gtk.CellRendererText()
        c = gtk.TreeViewColumn(_("Period"), r, text=self.col_period)
        c.set_sort_column_id(self.col_period)
        self.view.append_column(c)

        r = gtk.CellRendererProgress()
        c = gtk.TreeViewColumn(_("Remaining"), r,
                               value=self.col_remain, text=self.col_status)
        c.set_sort_column_id(self.col_status)
        self.view.append_column(c)

        r = gtk.CellRendererText()
        c = gtk.TreeViewColumn(_("Message"), r, text=self.col_msg)
        c.set_sort_column_id(self.col_msg)
        c.set_resizable(True)
        self.view.append_column(c)

        self.view.show()

        return self.view

    def reset_qst(self, view, path, col, data=None):
        iter = self.store.get_iter(path)

        index = self.store.get(iter, self.col_index)[0]

        self.mainapp.qsts[index].reset()

    def _update(self, model, path, iter, data=None):
        index = model.get(iter, self.col_index)[0]

        qst = self.mainapp.qsts[index]

        try:
            max = int(qst.freq) * 60
        except:
            max = 3600

        rem = qst.remaining()

        if max == 0:
            status = _("Manual")
        elif rem < 90:
            status = "%i " % rem + _("sec")
        else:
            status = "%i " % (rem / 60) + _("min")

        try:
            val = (float(rem) / float(max)) * 100.0
        except:
            val = 0

        self.store.set(iter,
                       self.col_remain, val,
                       self.col_status, status)

    def update(self):
        if self.enabled:
            self.store.foreach(self._update, None)

        return True

    def add_qst(self, index, qst):

        try:
            max = int(qst.freq) * 60
        except:
            max = 3600

        rem = qst.remaining()
        msg = qst.text

        if max == 0:
            status = _("Manual")
        elif rem < 90:
            status = "%i " % rem + _("sec")
        else:
            status = "%i " % (rem / 60) + _("min")

        try:
            val = (float(rem) / float(max)) * 100
        except:
            val = 0

        iter = self.store.append()
        self.store.set(iter,
                       self.col_index, index,
                       self.col_period, qst.freq,
                       self.col_remain, val,
                       self.col_status, status,
                       self.col_msg, msg)
        

    def refresh(self):
        self.enabled = False

        self.store.clear()

        for i in range(0, len(self.mainapp.qsts)):
            self.add_qst(i, self.mainapp.qsts[i])

        self.enabled = True

    def __init__(self, gui, mainapp):
        self.gui = gui
        self.mainapp = mainapp
        self.thread = None

        self.tips = gtk.Tooltips()

        self.root = gtk.ScrolledWindow()
        self.root.add(self.make_display())
        self.root.set_policy(gtk.POLICY_AUTOMATIC, gtk.POLICY_AUTOMATIC)
        self.root.show()

        self.enabled = False
        gobject.timeout_add(1000, self.update)

    def show(self):
        self.root.show()
    
    def hide(self):
        self.root.hide()

class FormManager:
    def val_edited(self, r, path, new_text, colnum):
        iter = self.store.get_iter(path)

        self.store.set(iter, colnum, new_text)

        (index, filename, stamp, statm, ident, xfert) = \
            self.store.get(iter,
                           self.col_index,
                           self.col_filen,
                           self.col_stamp,
                           self.col_statm,
                           self.col_ident,
                           self.col_xfert)
        
        self.reg_form(ident, filename, stamp, xfert, statm)
    
    def row_clicked(self, view, path, col):
        self.edit(None)

    def _make_menu(self):
        (list, iter) = self.view.get_selection().get_selected()

        def mh(_action):
            action = _action.get_name()
            if action == "email":
                self.do_email(iter)
            elif action == "delete":
                self.delete(None)

        xml = """
<ui>
  <popup name="menu">
    <menuitem action="email"/>
    <menuitem action="delete"/>
  </popup>
</ui>
"""
        ag = gtk.ActionGroup("menu")

        email = gtk.Action("email", _("Email"), None, None)
        email.connect("activate", mh)
        ag.add_action(email)

        delete = gtk.Action("delete", _("Delete"), None, None)
        delete.connect("activate", mh)
        ag.add_action(delete)

        uim = gtk.UIManager()
        uim.insert_action_group(ag, 0)
        uim.add_ui_from_string(xml)

        return uim.get_widget("/menu")

    def make_menu(self, view, event):
        if event.button != 3:
            return

        if event.window == view.get_bin_window():
            x, y = event.get_coords()
            pathinfo = view.get_path_at_pos(int(x), int(y))
            if pathinfo is None:
                return
            else:
                view.set_cursor_on_cell(pathinfo[0])

        menu = self._make_menu()
        if menu:
            menu.set_size_request(100, -1)
            menu.popup(None, None, None, event.button, event.time)

    def make_display(self):
        self.col_index = 0
        self.col_statm = 1
        self.col_ident = 2
        self.col_stamp = 3
        self.col_filen = 4
        self.col_xfert = 5

        self.store = gtk.ListStore(gobject.TYPE_INT,
                                   gobject.TYPE_STRING,
                                   gobject.TYPE_STRING,
                                   gobject.TYPE_STRING,
                                   gobject.TYPE_STRING,
                                   gobject.TYPE_STRING)

        self.view = gtk.TreeView(self.store)
        self.view.set_rules_hint(True)

        choices = gtk.ListStore(gobject.TYPE_STRING)
        for i in [_("New"), _("Low"), _("Med"), _("Hi"), _("Done")]:
            choices.append([i])

        r = gtk.CellRendererCombo()
        r.set_property("model", choices)
        r.set_property("text-column", 0)
        r.set_property("editable", True)
        r.connect("edited", self.val_edited, self.col_statm)
        c = gtk.TreeViewColumn(_("Status"), r, text=self.col_statm)
        c.set_resizable(True)
        c.set_sort_column_id(self.col_statm)
        self.view.append_column(c)

        r = gtk.CellRendererText()
        c = gtk.TreeViewColumn(_("ID"), r, text=self.col_ident)
        c.set_resizable(True)
        c.set_sort_column_id(self.col_ident)
        self.view.append_column(c)

        r.set_property("editable", True)
        r.connect("edited", self.val_edited, self.col_ident)

        r = gtk.CellRendererText()
        c = gtk.TreeViewColumn(_("Last Edited"), r, text=self.col_stamp)
        c.set_sort_column_id(self.col_stamp)
        self.view.append_column(c)

        r = gtk.CellRendererText()
        c = gtk.TreeViewColumn(_("Last Transferred"), r, text=self.col_xfert)
        c.set_sort_column_id(self.col_xfert)
        self.view.append_column(c)

        self.view.connect("row-activated", self.row_clicked)
        self.view.connect("button_press_event", self.make_menu)

        self.view.show()

        sw = gtk.ScrolledWindow()
        sw.add(self.view)
        sw.show()
        sw.set_policy(gtk.POLICY_NEVER, gtk.POLICY_AUTOMATIC)

        return sw

    def list_add_form(self,
                      index,
                      ident,
                      filen,
                      stamp=None,
                      xfert=_("Never"),
                      statm=_("New")):
        if not stamp:
            stamp = self.get_stamp()

        iter = self.store.append()
        self.store.set(iter,
                       self.col_index, index,
                       self.col_ident, ident,
                       self.col_stamp, stamp,
                       self.col_filen, filen,
                       self.col_xfert, xfert,
                       self.col_statm, statm)
        return iter

    def new(self, widget, data=None):
        form_files = glob.glob(os.path.join(self.form_source_dir,
                                            "*.xml"))

        if not form_files:
            d = gtk.MessageDialog(buttons=gtk.BUTTONS_OK, parent=self.gui.window)
            d.set_property("text", _("No template forms available"))
            d.format_secondary_text(_("Please copy in the template forms to %s or create a new template by going to File->Manage Form Templates") % os.path.abspath(self.form_source_dir))
            d.run()
            d.destroy()
            return            

        forms = {}
        for i in form_files:
            id = os.path.basename(i).replace(".xml", "")
            forms[id] = i

        d = ChoiceDialog(forms.keys(),
                         title=_("Choose a form"),
                         parent=self.gui.window)
        d.label.set_text(_("Select a form type to create"))
        r = d.run()
        formid = d.choice.get_active_text()
        d.destroy()
        if r == gtk.RESPONSE_CANCEL:
            return

        newfn = time.strftime(os.path.join(self.form_store_dir,
                                           "form_%m%d%Y_%H%M%S.xml"))

        try:
            form = formgui.FormFile(_("New %s form") % formid,
                                    forms[formid],
                                    buttons=(_("Send"), 999))
            r = form.run_auto(newfn)
            form.destroy()
            if r == gtk.RESPONSE_CANCEL:
                return
        except Exception, e:
            d = ExceptionDialog(e, parent=self.gui.window)
            d.run()
            d.destroy()
            return

        stamp = self.get_stamp()

        iter = self.list_add_form(0, formid, newfn, stamp)
        self.reg_form(formid, newfn, stamp)

        if r == 999:
            path = self.store.get_path(iter)
            self.view.set_cursor(path)
            self.send(widget)

    def delete(self, widget, data=None):
        d = YesNoDialog(parent=self.gui.window,
                        title=_("Confirm Delete"),
                        buttons=(gtk.STOCK_YES, gtk.RESPONSE_YES,
                                 gtk.STOCK_NO, gtk.RESPONSE_NO))
        d.set_text(_("Really delete this form?"))
        r = d.run()
        d.destroy()
        if r != gtk.RESPONSE_YES:
            return

        (list, iter) = self.view.get_selection().get_selected()

        (filename, id) = self.store.get(iter, self.col_filen, self.col_ident)

        list.remove(iter)

        self.unreg_form(filename)
        os.remove(filename)

    def send(self, widget, data=None):
        dest = prompt_for_station(self.gui.window)
        if not dest:
            return

        (list, iter) = self.view.get_selection().get_selected()
        (filename, name) = self.store.get(iter, self.col_filen, self.col_ident)

        self.gui.adv_controls["sessions"].send_form(dest, filename, name)

    def edit(self, widget, data=None):
        (list, iter) = self.view.get_selection().get_selected()

        (filename, id, stamp) = self.store.get(iter,
                                               self.col_filen,
                                               self.col_ident,
                                               self.col_stamp)

        print "Editing %s" % filename

        try:
            form = formgui.FormFile(_("Edit Form"),
                                    filename,
                                    buttons=(_("Send"), 999))
            r = form.run_auto()
            form.destroy()
            if r == gtk.RESPONSE_CANCEL:
                return
        except Exception, e:
            d = ExceptionDialog(e, parent=self.gui.window)
            d.run()
            d.destroy()
            return            

        stamp = self.get_stamp()
        self.store.set(iter, self.col_stamp, stamp)
        self.reg_form(id, filename, stamp)

        if r == 999:
            self.send(widget)

    def reply(self, widget, data=None):
        (list, iter) = self.view.get_selection().get_selected()

        (filename,) = self.store.get(iter, self.col_filen)

        save_fields = [
            ("_auto_number", "_auto_number", lambda x: str(int(x)+1)),
            ("_auto_subject", "_auto_subject", lambda x: "RE: %s" % x),
            ("_auto_sender", "_auto_recip", None)
            ]

        fields = {}

        try:
            oform = formgui.FormFile("", filename)

            for sf, df, xform in save_fields:
                oldval = oform.get_field_value(sf)
                if not oldval:
                    continue

                if xform:
                    fields[df] = xform(oldval)
                else:
                    fields[df] = oldval

                print "%s -> %s: %s" % (sf, df, fields[df])

        except Exception, e:
            print "Failed to get old number: %s" % e
            number = 1

        try:
            template = os.path.join(self.form_source_dir, oform.id + ".xml")
            newfn = time.strftime(os.path.join(self.form_store_dir,
                                               "form_%m%d%Y_%H%M%S.xml"))

            form = formgui.FormFile(_("Reply to")+" `%s'" % oform.id, template)

            for field, value in fields.items():
                form.set_field_value(field, value)
            r = form.run_auto(newfn)
            form.destroy()
            if r == gtk.RESPONSE_CANCEL:
                return
        except Exception, e:
            d = ExceptionDialog(e, parent=self.gui.window)
            d.run()
            d.destroy()
            return

        stamp = self.get_stamp()

        self.list_add_form(0, oform.id, newfn, stamp)
        self.reg_form(oform.id, newfn, stamp)        

    def do_email(self, iter):
        (filename,) = self.store.get(iter, self.col_filen)

        form = formgui.FormFile("", filename)

        if form.id != "email":
            d = gtk.MessageDialog(buttons=gtk.BUTTONS_OK)
            d.set_property("text", "Only email forms can be emailed")
            d.run()
            d.destroy()
        else:
            def cb(status, msg):
                self.gui.display(msg + "\r\n", "italic")

            srv = emailgw.FormEmailService(self.gui.config)
            srv.send_email_background(form, cb)

    def make_buttons(self):
        box = gtk.VBox(False, 2)

        newb = gtk.Button(_("New"))
        newb.set_size_request(75, 30)
        newb.connect("clicked", self.new, None)
        newb.show()
        box.pack_start(newb, 0,0,0)

        edit = gtk.Button(_("Edit"))
        edit.set_size_request(75, 30)
        edit.connect("clicked", self.edit, None)
        edit.show()
        box.pack_start(edit, 0,0,0)

        reply = gtk.Button(_("Reply"))
        reply.set_size_request(75, 30)
        reply.connect("clicked", self.reply, None)
        reply.show()
        box.pack_start(reply, 0,0,0)

        delb = gtk.Button(_("Delete"))
        delb.set_size_request(75, 30)
        delb.connect("clicked", self.delete, None)
        delb.show()
        box.pack_start(delb, 0,0,0)

        sendb = gtk.Button(_("Send"))
        sendb.set_size_request(75, 30)
        sendb.connect("clicked", self.send, None)
        sendb.show()
        box.pack_start(sendb, 0,0,0)

        box.show()

        return box

    def reg_save(self):
        f = file(self.reg_file, "w")
        self.reg.write(f)
        f.close()

    def reg_form(self, id, file, editstamp, xferstamp=_("Never"), status=_("New")):
        sec = os.path.basename(file)

        if not self.reg.has_section(sec):
            self.reg.add_section(sec)

        try :
            self.reg.set(sec, "id", id)
            self.reg.set(sec, "filename", file)
            self.reg.set(sec, "editstamp", editstamp)
            self.reg.set(sec, "xferstamp", xferstamp)
            self.reg.set(sec, "status", status)
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
                try:
                    statm = self.reg.get(i, "status")
                    xfert = self.reg.get(i, "xferstamp")
                except:
                    statm = _("New")
                self.list_add_form(0, id, filename, stamp, xfert, statm)
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

class CallCatcher:
    def mh(self, _action):
        action = _action.get_name()

        if action == "lookup":
            self.mnu_lookup(None)
        elif action == "echoposgps":
            self.mnu_echo_position(None, False)
        elif action == "echoposgpsa":
            self.mnu_echo_position(None, True)
        elif action == "remove":
            self.but_remove(None)
        elif action == "reset":
            self.but_reset(None, True)
        elif action == "forget":
            self.but_reset(None, False)
        elif action == "ping":
            self.mnu_ping()
        else:
            print "Unknown action `%s'" % action

    def make_menu(self):
        a = [('echoposgps', None, _('Echo position (GPS)'), None, None, self.mh),
             ('echoposgpsa', None, _('Echo position (GPS-A)'), None, None, self.mh),
             ('remove', None, _('Remove'), None, None, self.mh),
             ('reset', None, _('Reset'), None, None, self.mh),
             ('forget', None, _('Forget'), None, None, self.mh),
             ('lookup', None, _('Lookup (QRZ)'), None, None, self.mh),
             ('ping', None, _('Ping Station'), None, None, self.mh)]

        xml = """
<ui>
  <popup name="Menu">
    <menuitem action='echoposgps'/>
    <menuitem action='echoposgpsa'/>
    <separator/>
    <menuitem action='remove'/>
    <menuitem action='reset'/>
    <menuitem action='forget'/>
    <menuitem action='ping'/>
  </popup>
</ui>
"""

        ag = gtk.ActionGroup("Menu")
        ag.add_actions(a)

        uim = gtk.UIManager()
        uim.insert_action_group(ag, 0)
        uim.add_ui_from_string(xml)

        return uim.get_widget("/Menu")
 

    def mouse_cb(self, view, event, data=None):
        if event.button != 3:
            return

        list, paths = self.view.get_selection().get_selected_rows()

        menu = self.make_menu()
        menu.popup(None,None,None,event.button,event.time)

    def make_display(self):
        self.col_call = 0
        self.col_disp = 1
        self.col_time = 2
        self.col_pos  = 3

        self.store = gtk.ListStore(gobject.TYPE_STRING,
                                   gobject.TYPE_STRING,
                                   gobject.TYPE_INT,
                                   gobject.TYPE_STRING)

        self.view = gtk.TreeView(self.store)
        self.view.get_selection().set_mode(gtk.SELECTION_MULTIPLE)

        r = gtk.CellRendererText()
        c = gtk.TreeViewColumn(_("Callsign"), r, text=self.col_call)
        c.set_sort_column_id(self.col_call)
        c.set_resizable(True)
        self.view.append_column(c)

        r = gtk.CellRendererText()
        c = gtk.TreeViewColumn(_("Last Seen"), r, text=self.col_disp)
        c.set_sort_column_id(self.col_time)
        c.set_resizable(True)
        self.view.append_column(c)

        r = gtk.CellRendererText()
        c = gtk.TreeViewColumn(_("Last Position"), r, text=self.col_pos)
        c.set_sort_column_id(self.col_pos)
        c.set_resizable(True)
        self.view.append_column(c)

        def cb(view, path, col, me):
            me.but_address(None)

        self.view.connect("row-activated", cb, self)
        self.view.connect("button_press_event", self.mouse_cb)

        self.view.show()

        sw = gtk.ScrolledWindow()
        sw.add(self.view)
        sw.set_policy(gtk.POLICY_NEVER, gtk.POLICY_AUTOMATIC)
        sw.show()

        return sw

    def make_controls(self):
        vbox = gtk.VBox(False, 2)

        remove = gtk.Button(_("Remove"))
        remove.set_size_request(75, 30)
        remove.connect("clicked", self.but_remove)
        self.gui.tips.set_tip(remove, _("Remove callsign from list"))
        remove.show()
        vbox.pack_start(remove, 0,0,0)

        address = gtk.Button(_("Address"))
        address.set_size_request(75, 30)
        address.connect("clicked", self.but_address)
        self.gui.tips.set_tip(address, _("Address a message to selected call"))
        address.show()
        vbox.pack_start(address, 0,0,0)

        reset = gtk.Button(_("Reset"))
        reset.set_size_request(75, 30)
        reset.connect("clicked", self.but_reset, True)
        self.gui.tips.set_tip(reset, _("Reset last seen time for selected call"))
        reset.show()
        vbox.pack_start(reset, 0,0,0)

        forget = gtk.Button(_("Forget"))
        forget.set_size_request(75, 30)
        forget.connect("clicked", self.but_reset, False)
        self.gui.tips.set_tip(forget, _("Forget when this call was last seen"))
        forget.show()
        vbox.pack_start(forget, 0,0,0)

        clear = gtk.Button(_("Clear All"))
        clear.set_size_request(75, 30)
        clear.connect("clicked", self.but_clear)
        self.gui.tips.set_tip(clear, _("Clear all recorded callsigns"))
        clear.show()
        vbox.pack_start(clear, 0,0,0)

        vbox.show()
        
        return vbox

    def _get_first_selected(self):
        (list, paths) = self.view.get_selection().get_selected_rows()
        return list, list.get_iter(paths[0])

    def mnu_lookup(self, widget):
        list, iter = self._get_first_selected()
        (call,) = list.get(iter, self.col_call)

        url = "http://qrz.com/%s" % call
        self.mainapp.config.platform.open_html_file(url)

    def mnu_ping(self):
        list, iter = self._get_first_selected()
        (call,) = list.get(iter, self.col_call)

        self.mainapp.chat_session.ping_station(call)

    def but_remove(self, widget):
        (list, paths) = self.view.get_selection().get_selected_rows()

        calls = []

        for path in paths:
            iter = list.get_iter(path)
            (call,) = list.get(iter, self.col_call)
            calls.append(call)

        for call in calls:
            try:
                self.mainapp.seen_callsigns.remove(call)
                self.gui.map.del_marker(call, _("Stations"))
            except Exception, e:
                print "Failed to delete: %s" % e

        self.refresh()

    def but_address(self, widget):
        list, iter = self._get_first_selected()
        (call,) = list.get(iter, self.col_call)

        text = self.gui.entry.get_text()

        self.gui.entry.set_text("%s: %s" % (call, text))
        self.gui.entry.grab_focus()

    def but_reset(self, widget, now):
        (list, paths) = self.view.get_selection().get_selected_rows()

        for path in paths:
            iter = list.get_iter(path)
            (call,) = list.get(iter, self.col_call)

            try:
                if now:
                    self.mainapp.seen_callsigns.set_call_time(time.time())
                else:
                    self.mainapp.seen_callsigns.set_call_time(0)
            except Exception, e:
                pass

        self.refresh()

    def but_clear(self, widget):
        self.mainapp.seen_callsigns.clear()
        self.refresh()

    def mnu_echo_position(self, widget, aprs=False):
        (list, paths) = self.view.get_selection().get_selected_rows()

        mycall = self.mainapp.config.get("user", "callsign")

        qsts = []

        for path in paths:
            iter = list.get_iter(path)
            (call,) = list.get(iter, self.col_call)

            pos = self.mainapp.get_call_pos(call)
            if not pos:
                continue

            if aprs:
                c = QSTGPSA
            else:
                c = QSTGPS

            q = c(self.gui, self.mainapp.config, "via %s" % mycall)
            q.set_fix(pos)

            qsts.append(q)

        for qst in qsts:
            qst.fire()

    def show(self):
        self.root.show()

    def hide(self):
        self.root.hide()

    def update_time(self, iter):
        (stamp,) = self.store.get(iter, self.col_time)
        now = time.time()
        
        delta = datetime.datetime.fromtimestamp(now) - \
            datetime.datetime.fromtimestamp(stamp)

        if stamp == 0:
            string = _("Never")
        else:
            string = time.strftime("%H:%M:%S %m/%d/%Y ", time.localtime(stamp))

        since = ""
        if stamp and delta.days > 1:
            since = "%i %s " % (delta.days, _("days"))
        elif stamp and delta.days == 1:
            since = "%i %s " % (delta.days, _("day"))

        if stamp and delta.seconds > 60:
            since += "%i:%02i" % ((delta.seconds / 3600),
                                   (delta.seconds % 3600) / 60)

        if since:
            string += "(%s)" % since

        self.store.set(iter,
                       self.col_disp, string)
        
    def refresh(self):
        def format_pos(pos):
            if pos == None:
                return _("Unknown")
            else:
                cur = self.mainapp.get_position()
                return cur.fuzzy_to(pos)

        self.store.clear()

        for c in self.mainapp.seen_callsigns.list():
            t = self.mainapp.seen_callsigns.get_call_time(c)
            p = self.mainapp.seen_callsigns.get_call_pos(c)
            iter = self.store.append()
            self.store.set(iter,
                           self.col_call, c,
                           self.col_time, t,
                           self.col_pos, format_pos(p))
            self.update_time(iter)

    def update_all_times(self):
        def update(model, path, iter, catcher):
            catcher.update_time(iter)

        self.store.foreach(update, self)

        return True

    def __init__(self, gui):
        self.gui = gui
        self.mainapp = gui.mainapp

        box = gtk.HBox(False, 2)
        box.pack_start(self.make_display(), 1,1,1)
        box.pack_start(self.make_controls(), 0,0,0)
        box.show()

        self.root = box

        gobject.timeout_add(60 * 1000, self.update_all_times)
