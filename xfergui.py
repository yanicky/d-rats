import os
from threading import Thread

import pygtk
import gtk

import xmodem

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

    def __init__(self, chatgui):
        self.values = {}
        self.chatgui = chatgui
        self.is_send = None
        self.total_size = 5000

        box = gtk.VBox(False, 0)

        self.bar = gtk.ProgressBar()
        self.bar.set_text("Waiting...")
        self.bar.set_fraction(0)
        
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

    def xfer(self):
        x = xmodem.XModemCRC(debug="stdout", status_fn=self.update)

        if self.is_send:
            i = file(self.filename)
            x.send_xfer(self.chatgui.comm.pipe, i)
        else:
            x.recv_xfer(self.chatgui.comm.pipe)

    def show_xfer(self):
        self.values["File"].set_text(os.path.basename(self.filename))
        self.window.show()

        self.chatgui.toggle_sendable(False)
        self.chatgui.comm.disable()

        self.xfer_thread = Thread(target=self.xfer)
        self.xfer_thread.start()

    def update(self, status, bytecount, errors):
        gtk.gdk.threads_enter()
        self.values["Size"].set_text("%i KB" % (bytecount / 1024))
        self.values["Errors"].set_text("%i" % errors)
        self.bar.set_text(status)
        if self.total_size:
            self.bar.set_fraction(float(bytecount) / self.total_size)
        gtk.gdk.threads_leave()

    def do_send(self):
        fc = gtk.FileChooserDialog("Select file to send",
                                   None,
                                   gtk.FILE_CHOOSER_ACTION_OPEN,
                                   (gtk.STOCK_CANCEL, gtk.RESPONSE_CANCEL,
                                    gtk.STOCK_OPEN, gtk.RESPONSE_OK))
        fc.run()
        self.filename = fc.get_filename()
        fc.destroy()

        self.is_send = True

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

        self.is_send = False

        self.show_xfer()
