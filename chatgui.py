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
import xmodem

from xfergui import FileTransferGUI
from qst import QSTGUI

class ChatGUI:
    def ev_delete(self, widget, event, data=None):
        return False
    
    def sig_destroy(self, widget, data=None):
        if self.config.config.getboolean("prefs", "dosignoff"):
            self.tx_msg(self.config.config.get("prefs", "signoff"))

        gtk.main_quit()

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
        xlate = ([c] * 10) +    \
                ['\n', '\r'] +  \
                ([c] * 20) +    \
                [chr(x) for x in range(32,126)] + \
                ([c] * 130)
        string = string.translate("".join(xlate))

        end = self.main_buffer.get_end_iter()

        self.main_buffer.insert_with_tags_by_name(end,
                                                  string,
                                                  *attrs)

        #print "Displaying: %s" % list(string)

        adj = self.scroll.get_vadjustment()
        adj.value = adj.upper
        self.scroll.set_vadjustment(adj)

    def tx_msg(self, string):
        call = self.config.config.get("user", "callsign")

        self.display("%s " % time.strftime("%H:%M:%S"))
        self.display("%s> " % call, "outgoingcolor")
        self.display(string + "\n")
        self.comm.send_text("%s> %s\n" % (call, string))

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

    def make_main_pane(self, menubar):
        vbox = gtk.VBox(False, 0)
        display = gtk.TextView(self.main_buffer)
        display.Editable = False
        display.set_wrap_mode(gtk.WRAP_WORD)
        self.scroll = gtk.ScrolledWindow()
        self.scroll.add(display)

        ebox = self.make_entry_box()

        vbox.pack_start(menubar, 0, 1, 0)
        vbox.pack_start(self.scroll, 1, 1, 1)
        vbox.pack_start(ebox, 0, 0, 1)

        ebox.show()
        self.scroll.show()
        display.show()

        return vbox

    def toggle_sendable(self, state):
        self.entry.set_sensitive(state)
        self.send_button.set_sensitive(state)
        
    def menu_handler(self, _action):
        action = _action.get_name()

        xfer_name = self.config.config.get("settings", "xfer")
        xfer = xmodem.__dict__[xfer_name]

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

    def make_menubar(self):
        menu_xml = """
        <ui>
          <menubar name='MenuBar'>
            <menu action='file'>
              <menuitem action='send'/>
              <menuitem action='recv'/>
              <separator/>
              <menuitem action='config'/>
              <menuitem action='qsts'/>
              <separator/>
              <menuitem action='quit'/>
            </menu>
            <menu action='view'>
              <menuitem action='clear'/>
              <menuitem action='advanced'/>
            </menu>
          </menubar>
        </ui>
        """

        actions = [('file', None, "_File", None, None, self.menu_handler),
                   ('send', None, "_Send File", None, None, self.menu_handler),
                   ('recv', None, "_Receive File", None, None, self.menu_handler),
                   ('config', None, "_Main Settings", None, None, self.menu_handler),
                   ('qsts', None, "_Auto QST Settings", None, None, self.menu_handler),
                   ('quit', None, "_Quit", None, None, self.menu_handler),
                   ('view', None, "_View", None, None, self.menu_handler),
                   ('clear', None, '_Clear', None, None, self.menu_handler),
                   ('advanced', None, '_Advanced', None, None, self.menu_handler)]

        uim = gtk.UIManager()
        ag = gtk.ActionGroup("MenuBar")

        ag.add_actions(actions)

        uim.insert_action_group(ag, 0)
        menuid = uim.add_ui_from_string(menu_xml)

        return uim.get_widget("/MenuBar")

    def refresh_colors(self, first_time=False):

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
        
    def __init__(self, config):
        self.comm = None
        self.config = config
        
        self.main_buffer = gtk.TextBuffer()
        self.refresh_colors(first_time=True)

        self.window = gtk.Window(gtk.WINDOW_TOPLEVEL)

        menubar = self.make_menubar()
        menubar.show()
        pane = self.make_main_pane(menubar)

        self.window.set_title("D-RATS")
        
        self.window.set_geometry_hints(None, min_width=400, min_height=200)
        self.window.set_default_size(640, 480)
        self.window.set_border_width(1)
        self.window.add(pane)
        self.window.connect("delete_event", self.ev_delete)
        self.window.connect("destroy", self.sig_destroy)
        self.window.connect("focus", self.ev_focus)

        pane.show()
        self.window.show()

        self.entry.grab_focus()

        self.display("D-RATS v0.1.3 ", ("red"))
        self.display("(Copyright 2008 Dan Smith KI4IFW)\n", "blue", "italic")

    def main(self):
        gtk.gdk.threads_init()
        self.sw_thread = Thread(target=self.watch_serial)
        self.sw_thread.start()
        print "Started thread"
        gtk.gdk.threads_enter()
        gtk.main()
        gtk.gdk.threads_leave()

if __name__ == "__main__":
    gui = ChatGUI()
    try:
        gui.main()
    except KeyboardInterrupt:
        gui.sig_destroy(None)
