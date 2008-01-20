import os
from threading import Thread

import pygtk
import gtk

import xmodem

class FileTransferGUI:

    def cancel_xfer(self, widget, data=None):
        print "Cancel transfer"

    def close_gui(self, widget, data=None):
        self.window.destroy()

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

    def make_buttons(self):
        box = gtk.HBox(True, 0)

        self.cancel_btn = gtk.Button("Cancel", gtk.STOCK_CANCEL)
        self.close_btn = gtk.Button("Close", gtk.STOCK_CLOSE)

        self.close_btn.set_sensitive(False)

        self.cancel_btn.connect("clicked",
                                self.cancel_xfer,
                                None)
        self.close_btn.connect("clicked",
                               self.close_gui,
                               None)

        box.pack_start(self.cancel_btn, 1, 1, 0)
        box.pack_start(self.close_btn, 1, 1, 0)

        self.cancel_btn.show()
        self.close_btn.show()
        box.show()
        
        return box

    def __init__(self, chatgui):
        self.values = {}
        self.chatgui = chatgui
        self.is_send = None
        self.total_size = None

        box = gtk.VBox(False, 0)

        self.bar = gtk.ProgressBar()
        self.bar.set_text("Waiting...")
        self.bar.set_fraction(0)
        
        box.pack_start(self.bar, 0, 0, 0)
        box.pack_start(self.make_label_value("File"), 0, 0, 0)
        box.pack_start(self.make_label_value("Size"), 0, 0, 0)
        box.pack_start(self.make_label_value("Errors"), 0, 0, 0)
        box.pack_start(self.make_buttons(), 0, 0, 0)

        self.bar.show()
        box.show()

        self.window = gtk.Window(gtk.WINDOW_TOPLEVEL)
        self.window.set_title("File Transfer")
        self.window.set_resizable(False)
        self.window.set_geometry_hints(None, min_width=300)
        self.window.add(box)

    def xfer(self):
        x = xmodem.XModem1K(debug="stdout", status_fn=self.update)

        if self.is_send:
            s = os.stat(self.filename)
            self.total_size = s.st_size
            local = file(self.filename)
            func = x.send_xfer
        else:
            local = file(self.filename, "w")
            func = x.recv_xfer

        try:
            func(self.chatgui.comm.pipe, local)
        except xmodem.FatalError, e:
            self.update("Failed (%s)" % e,
                        0,
                        x.total_errors,
                        running=False)

        gtk.gdk.threads_enter()
        self.chatgui.toggle_sendable(True)
        gtk.gdk.threads_leave()
        self.chatgui.comm.enable(self.chatgui)

        self.close_btn.set_sensitive(True)
        self.cancel_btn.set_sensitive(False)

    def show_xfer(self):
        self.values["File"].set_text(os.path.basename(self.filename))
        self.window.show()

        self.chatgui.toggle_sendable(False)
        self.chatgui.comm.disable()

        self.xfer_thread = Thread(target=self.xfer)
        self.xfer_thread.start()

    def update(self, status, bytecount, errors, running=True):
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

if __name__ == "__main__":
    g = FileTransferGUI(None)
    g.window.show()
    gtk.main()
