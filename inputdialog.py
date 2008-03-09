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

from config import make_choice

class TextInputDialog(gtk.Dialog):
    def respond_ok(self, entry, data=None):
        self.response(gtk.RESPONSE_OK)

    def __init__(self, **args):
        buttons = (gtk.STOCK_CANCEL, gtk.RESPONSE_CANCEL,
                   gtk.STOCK_OK, gtk.RESPONSE_OK)
        gtk.Dialog.__init__(self, buttons=buttons, **args)

        self.label = gtk.Label()
        self.label.set_size_request(300,100)
        self.vbox.pack_start(self.label, 1, 1, 0)
       
        self.text = gtk.Entry()
        self.text.connect("activate", self.respond_ok, None)
        self.vbox.pack_start(self.text, 1, 1, 0)

        self.label.show()
        self.text.show()

class ChoiceDialog(gtk.Dialog):
    def __init__(self, choices, **args):
        buttons = (gtk.STOCK_CANCEL, gtk.RESPONSE_CANCEL,
                   gtk.STOCK_OK, gtk.RESPONSE_OK)
        gtk.Dialog.__init__(self, buttons=buttons, **args)

        self.label = gtk.Label()
        self.label.set_size_request(300,100)
        self.vbox.pack_start(self.label, 1, 1, 0)
        self.label.show()

        self.choice = make_choice(choices, False, choices[0])
        self.vbox.pack_start(self.choice, 1, 1, 0)
        self.choice.show()

class ExceptionDialog(gtk.MessageDialog):
    def __init__(self, exception, **args):
        gtk.MessageDialog.__init__(self, buttons=gtk.BUTTONS_OK, **args)
        self.set_property("text", "An error has occurred")
        self.format_secondary_text(str(exception))

if __name__ == "__main__":
    d = TextInputDialog("Foo")
    d.label.set_text("Enter a filter RegEx")
    d.run()
    d.destroy()

    print d.text.get_text()
