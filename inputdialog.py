#!/usr/bin/python

import gtk

class TextInputDialog(gtk.Dialog):
    def respond_ok(self, entry, data=None):
        self.response(gtk.RESPONSE_OK)

    def __init__(self, title=None):
        buttons = (gtk.STOCK_CANCEL, gtk.RESPONSE_CANCEL,
                   gtk.STOCK_OK, gtk.RESPONSE_OK)
        gtk.Dialog.__init__(self, title, buttons=buttons)

        self.label = gtk.Label()
        self.label.set_size_request(300,100)
        self.vbox.pack_start(self.label, 1, 1, 0)
       
        self.text = gtk.Entry()
        self.text.connect("activate", self.respond_ok, None)
        self.vbox.pack_start(self.text, 1, 1, 0)

        self.label.show()
        self.text.show()

if __name__ == "__main__":
    d = TextInputDialog("Foo")
    d.label.set_text("Enter a filter RegEx")
    d.run()
    d.destroy()

    print d.text.get_text()
