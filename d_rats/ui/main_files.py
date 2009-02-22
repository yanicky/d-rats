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

import gobject
import gtk

from d_rats.ui.main_common import MainWindowElement

class FilesTab(MainWindowElement):
    __gsignals__ = {
        }

    def _r_loc(self, button):
        pass

    def _del(self, button):
        pass

    def _init_toolbar(self):

        def populate_tb(tb, buttons):
            c = 0
            for i, l, f in buttons:
                icon = gtk.Image()
                icon.set_from_file("images/%s" % i)
                icon.show()
                item = gtk.ToolButton(icon, l)
                item.show()
                tb.insert(item, c)
                c += 1

        ltb, = self._getw("local_toolbar")
        lbuttons = [("files-refresh.png", _("Refresh"), self._r_loc),
                    ("msg-delete.png", _("Delete"), self._del),
                    ]

        populate_tb(ltb, lbuttons)

        rtb, = self._getw("remote_toolbar")
        rbuttons = [("files-refresh.png", _("Refresh"), self._r_loc),
                    ("msg-delete.png", _("Delete"), self._del),
                    ]
        
        populate_tb(rtb, lbuttons)

    def __init__(self, wtree, config):
        MainWindowElement.__init__(self, wtree, config, "files")

        self._init_toolbar()
