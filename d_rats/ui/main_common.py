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

from d_rats import inputdialog

def ask_for_confirmation(question, parent=None):
    d = gtk.MessageDialog(buttons=gtk.BUTTONS_YES_NO,
                          parent=parent,
                          message_format=question)
    r = d.run()
    d.destroy()

    return r == gtk.RESPONSE_YES

def display_error(message, parent=None):
    d = gtk.MessageDialog(buttons=gtk.BUTTONS_OK,
                          parent=parent,
                          message_format=message)
    r = d.run()
    d.destroy()

    return r == gtk.RESPONSE_OK

def prompt_for_station(station_list, parent=None):
    d = inputdialog.EditableChoiceDialog(station_list)
    d.label.set_text(_("Select (or enter) a destination station"))
    r = d.run()
    station = d.choice.get_active_text()
    d.destroy()
    if r != gtk.RESPONSE_OK:
        return None
    else:
        return station[:8].upper()

class MainWindowElement(gobject.GObject):
    def __init__(self, wtree, config, prefix):
        self._prefix = prefix
        self._wtree = wtree
        self._config = config

        gobject.GObject.__init__(self)

    def _getw(self, *names):
        widgets = []

        for _name in names:
            name = "%s_%s" % (self._prefix, _name)
            widgets.append(self._wtree.get_widget(name))

        return tuple(widgets)

    def reconfigure(self):
        pass

class MainWindowTab(MainWindowElement):
    def reconfigure(self):
        pass

    def selected(self):
        pass

    def deselected(self):
        pass
