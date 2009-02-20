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

import libxml2
import gtk
import gtk.glade
import gobject

from d_rats.ui.main_messages import MessagesTab
from d_rats.ui.main_chat import ChatTab
from d_rats.ui.main_events import EventTab
from d_rats.ui.main_common import MainWindowElement

class MainWindow(MainWindowElement):
    def _open_prefs(self, menuitem):
        win = self._wtree.get_widget("mainwindow")
        self._config.show(parent=win)

    def __init__(self, config):
        # FIXME
        wtree = gtk.glade.XML("ui/mainwindow.glade", "mainwindow")

        MainWindowElement.__init__(self, wtree, config, "")

        self.tabs = {}

        self.tabs["chat"] = ChatTab(wtree, config)
        self.tabs["messages"] = MessagesTab(wtree, config)
        self.tabs["event"] = EventTab(wtree, config)

        menu_prefs = self._wtree.get_widget("main_menu_prefs")
        menu_prefs.connect("activate", self._open_prefs)

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
