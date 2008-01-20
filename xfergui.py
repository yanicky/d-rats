import pygtk
import gtk

import os

class FileTransferGUI:

    def make_label_value(self, labeltext):
        box = gtk.HBox(True, 0)

        label = gtk.Label(labeltext)
        value = gtk.Label("--")

        self.values[labeltext] = value

        box.pack_start(label, 0, 0, 0)
        box.pack_start(value, 0, 0, 0)

        label.show()
        value.show()
        box.show()
        
        return box

    def __init__(self):
        self.values = {}

        box = gtk.VBox(False, 0)

        self.bar = gtk.ProgressBar()
        self.bar.set_text("Waiting...")
        self.bar.set_fraction(0.5)
        
        box.pack_start(self.bar)
        box.pack_start(self.make_label_value("File"))
        box.pack_start(self.make_label_value("Size"))
        box.pack_start(self.make_label_value("Errors"))

        self.bar.show()
        box.show()

        self.window = gtk.Window(gtk.WINDOW_TOPLEVEL)
        self.window.set_title("File Transfer")
        self.window.set_resizable(False)
        self.window.set_geometry_hints(None, min_width=300, min_height=150)
        self.window.add(box)

    def show_xfer(self):
        self.values["File"].set_text(os.path.basename(self.filename))
        self.window.show()

    def update(self, status, bytecount, errors):
        self.values["Size"].set_text("%i KB" % (bytecount / 1024))
        self.values["Errors"].set_text("%i" % errors)
        self.bar.set_text(status)

    def do_send(self):
        fc = gtk.FileChooserDialog("Select file to send",
                                   None,
                                   gtk.FILE_CHOOSER_ACTION_OPEN,
                                   (gtk.STOCK_CANCEL, gtk.RESPONSE_CANCEL,
                                    gtk.STOCK_OPEN, gtk.RESPONSE_OK))
        fc.run()
        self.filename = fc.get_filename()
        fc.destroy()

        self.show_xfer()

    def do_recv(self):
        fc = gtk.FileChooserDialog("Receive file",
                                   None,
                                   gtk.FILE_CHOOSER_ACTION_SAVE,
                                   (gtk.STOCK_CANCEL, gtk.RESPONSE_CANCEL,
                                    gtk.STOCK_SAVE, gtk.RESPONSE_OK))
        fc.run()
        self.filename = fc.get_filename()
        fc.destroy()

        self.show_xfer()
