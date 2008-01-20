#!/usr/bin/python

import pygtk
import gtk
import pango
import serial
import gobject
import time
import xmodem

from xfergui import FileTransferGUI

class ChatGUI:
    def ev_delete(self, widget, event, data=None):
        return False
    
    def sig_destroy(self, widget, data=None):
        gtk.main_quit()

    def sig_send_button(self, widget, data=None):
        text = data.get_text()
        if text == "":
            return

        self.tx_msg(text)
        
        data.set_text("")

    def display(self, string, *attrs):
        #string = string.rstrip("\r")

        end = self.main_buffer.get_end_iter()

        self.main_buffer.insert_with_tags_by_name(end,
                                                  string,
                                                  *attrs)

        adj = self.scroll.get_vadjustment()
        adj.value = adj.upper
        self.scroll.set_vadjustment(adj)

    def tx_msg(self, string):
        call = self.config.config.get("user", "callsign")

        self.display("%s: " % call, "red")
        self.display(string + "\n")
        self.comm.send_text(string + "\n")

    def make_entry_box(self):
        hbox = gtk.HBox(False, 0)
        
        entry = gtk.Entry()
        button = gtk.Button("Send")
        
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
        if action == "quit":
            self.sig_destroy(None)
        elif action == "send":
            xfer = FileTransferGUI(self, xmodem.YModem)
            xfer.do_send()
        elif action == "recv":
            xfer = FileTransferGUI(self, xmodem.YModem)
            xfer.do_recv()

    def make_menubar(self):
        menu_xml = """
        <ui>
          <menubar name='MenuBar'>
            <menu action='file'>
              <menuitem action='send'/>
              <menuitem action='recv'/>
              <menuitem action='quit'/>
            </menu>
          </menubar>
        </ui>
        """

        actions = [('file', None, "File", None, None, self.menu_handler),
                   ('send', None, "Send File", None, None, self.menu_handler),
                   ('recv', None, "Receive File", None, None, self.menu_handler),
                   ('quit', None, "Quit", None, None, self.menu_handler)]

        uim = gtk.UIManager()
        ag = gtk.ActionGroup("MenuBar")

        ag.add_actions(actions)

        uim.insert_action_group(ag, 0)
        menuid = uim.add_ui_from_string(menu_xml)

        return uim.get_widget("/MenuBar")
        
    def __init__(self, comm, config):
        self.comm = comm
        self.config = config
        
        self.main_buffer = gtk.TextBuffer()

        tag = gtk.TextTag("red")
        tag.set_property("foreground", "Red")
        self.main_buffer.get_tag_table().add(tag)

        tag = gtk.TextTag("blue")
        tag.set_property("foreground", "Blue")
        self.main_buffer.get_tag_table().add(tag)

        tag = gtk.TextTag("green")
        tag.set_property("foreground", "Green")
        self.main_buffer.get_tag_table().add(tag)

        tag = gtk.TextTag("bold")
        tag.set_property("weight", pango.WEIGHT_BOLD)
        self.main_buffer.get_tag_table().add(tag)

        tag = gtk.TextTag("italic")
        tag.set_property("style", pango.STYLE_ITALIC)
        self.main_buffer.get_tag_table().add(tag)

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

        pane.show()
        self.window.show()

        self.entry.grab_focus()

        self.display("D-RATS ", ("red"))
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
