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


if __name__ == "__main__":
    import sys
    sys.path.insert(0, ".")
    from d_rats import mainapp
    from d_rats import platform

    import gettext
    lang = gettext.translation("D-RATS", localedir="./locale", languages=["en"])
    lang.install()
    print sys.path

import os

import libxml2
import gtk
import gtk.glade
import gobject

from d_rats.ui.main_messages import MessagesTab
from d_rats.ui.main_chat import ChatTab
from d_rats.ui.main_events import EventTab
from d_rats.ui.main_files import FilesTab
from d_rats.ui.main_common import MainWindowElement, prompt_for_station
from d_rats.version import DRATS_VERSION
from d_rats import formbuilder

class MainWindow(MainWindowElement):
    __gsignals__ = {
        "config-changed" : (gobject.SIGNAL_RUN_LAST,
                            gobject.TYPE_NONE,
                            ()),
        "show-map-station" : (gobject.SIGNAL_RUN_LAST,
                              gobject.TYPE_NONE,
                              (gobject.TYPE_STRING,)),
        "ping-station" : (gobject.SIGNAL_RUN_LAST,
                          gobject.TYPE_NONE,
                          (gobject.TYPE_STRING,)),
        }

    def _delete(self, window, event):
        window.set_default_size(*window.get_size())

    def _destroy(self, window):
        w, h = window.get_size()
        
        maximized = window.maximize_initially
        self._config.set("state", "main_maximized", maximized)
        if not maximized:
            self._config.set("state", "main_size_x", w)
            self._config.set("state", "main_size_y", h)

        gtk.main_quit()

    def _connect_menu_items(self, window):
        def do_save_and_quit(but):
            window.set_default_size(*window.get_size())
            window.destroy()

        def do_about(but):
            d = gtk.AboutDialog()
            d.set_transient_for(self._wtree.get_widget("mainwindow"))

            verinfo = "GTK %s\nPyGTK %s\n" % ( \
                ".".join([str(x) for x in gtk.gtk_version]),
                ".".join([str(x) for x in gtk.pygtk_version]))

            d.set_name("D-RATS")
            d.set_version(DRATS_VERSION)
            d.set_copyright("Copyright 2009 Dan Smith (KK7DS)")
            d.set_website("http://www.d-rats.com")
            d.set_authors(("Dan Smith <dsmith@danplanet.com>",))
            d.set_comments(verinfo)

            d.set_translator_credits("Italian: Leo, IZ5FSA")
        
            d.run()
            d.destroy()

        def do_debug(but):
            path = self._config.platform.config_file("debug.log")
            if os.path.exists(path):
                self._config.platform.open_text_file(path)
            else:
                d = gtk.MessageDialog(buttons=gtk.BUTTONS_OK,
                                      parent=window)
                d.set_property("text",
                               "Debug log not available")
                d.run()
                d.destroy()

        def do_prefs(but):
            saved = self._config.show(parent=window)
            if saved:
                self.emit("config-changed")
                for tabs in self.tabs.values():
                    tabs.reconfigure()

        def do_map(but):
            call = self._config.get("user", "callsign")
            self.emit("show-map-station", call)

        def do_message_templates(but):
            d = formbuilder.FormManagerGUI(self._config.form_source_dir())

        def do_ping(but):
            station = prompt_for_station([])
            if station:
                self.emit("ping-station", station)            

        quit = self._wtree.get_widget("main_menu_quit")
        quit.connect("activate", do_save_and_quit)

        about = self._wtree.get_widget("main_menu_about")
        about.connect("activate", do_about)

        debug = self._wtree.get_widget("main_menu_debuglog")
        debug.connect("activate", do_debug)

        menu_prefs = self._wtree.get_widget("main_menu_prefs")
        menu_prefs.connect("activate", do_prefs)

        menu_map = self._wtree.get_widget("main_menu_map")
        img = gtk.Image()
        img.set_from_file("images/map.png")
        menu_map.set_image(img)
        menu_map.connect("activate", do_map)

        menu_templates = self._wtree.get_widget("main_menu_msgtemplates")
        menu_templates.connect("activate", do_message_templates)

        ping = self._wtree.get_widget("main_menu_ping")
        img = gtk.Image()
        img.set_from_file("images/event_ping.png")
        ping.set_image(img)
        ping.connect("activate", do_ping)

    def _page_name(self, index=None):
        if index is None:
            index = self._tabs.get_current_page()

        tablabels = ["messages", "chat", "files", "event"]
        return tablabels[index]

    def _tab_switched(self, tabs, page, page_num):
        tab = self._page_name(page_num)
        self.tabs[self._current_tab].deselected()
        self._current_tab = tab
        self.tabs[self._current_tab].selected()

    def __init__(self, config):
        # FIXME
        wtree = gtk.glade.XML("ui/mainwindow.glade", "mainwindow")

        MainWindowElement.__init__(self, wtree, config, "")

        self._tabs = self._wtree.get_widget("main_tabs")
        self._tabs.connect("switch-page", self._tab_switched)

        self.tabs = {}

        self.tabs["chat"] = ChatTab(wtree, config)
        self.tabs["messages"] = MessagesTab(wtree, config)
        self.tabs["event"] = EventTab(wtree, config)
        self.tabs["files"] = FilesTab(wtree, config)

        self._current_tab = "messages"

        ic = "incomingcolor"
        self.tabs["chat"]._display_line("D-RATS v%s" % DRATS_VERSION, ic)
        self.tabs["chat"]._display_line("Copyright 2009 Dan Smith (KK7DS)", ic)
        self.tabs["chat"]._display_line("")
        

        window = self._wtree.get_widget("mainwindow")
        window.connect("destroy", self._destroy)
        window.connect("delete_event", self._delete)

        self._connect_menu_items(window)

        h = self._config.getint("state", "main_size_x")
        w = self._config.getint("state", "main_size_y")
        if self._config.getboolean("state", "main_maximized"):
            window.maximize()
            window.set_default_size(h, w)
        else:
            window.resize(h, w)

    def set_status(self, msg):
        sb = self._wtree.get_widget("statusbar")

        id = sb.get_context_id("default")
        sb.pop(id)
        sb.push(id, msg)

if __name__ == "__main__":
    wtree = gtk.glade.XML("ui/mainwindow.glade", "mainwindow")

    from d_rats import config
    conf = config.DratsConfig(None)

    def test(chat, station, msg):
        print "%s->%s" % (station, msg)

    chat = ChatTab(wtree, conf)
    chat.connect("user-sent-message", test)

    msgs = MessagesTab(wtree, conf)

    gtk.main()
