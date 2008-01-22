import os
from threading import Thread

import pygtk
import gtk

import xmodem

class FileTransferGUI:

    def cancel_xfer(self, widget, data=None):
        self.xfer.cancel()

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

    def __init__(self, chatgui, xfer_agent):
        self.values = {}
        self.chatgui = chatgui
        self.is_send = None
        self.total_size = None
        self.xfer_agent = xfer_agent

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
        xa = self.xfer_agent(debug="stdout", status_fn=self.update)

        self.xfer = xa

        if self.is_send:
            s = os.stat(self.filename)
            self.total_size = s.st_size
            local = file(self.filename, "rb")
            func = xa.send_xfer
        elif self.xfer_agent == xmodem.YModem:
            name, size = xa.rx_ymodem_header(self.chatgui.comm.pipe)
            self.total_size = size

            self.filename = os.path.join(self.filename, name)
            print "Target filename: %s" % self.filename
            local = file(self.filename, "wb")
            func = xa.recv_xfer
        else:
            local = file(self.filename, "wb")
            func = xa.recv_xfer

        gtk.gdk.threads_enter()
        self.values["File"].set_text(os.path.basename(self.filename))
        gtk.gdk.threads_leave()

        try:
            func(self.chatgui.comm.pipe, local)
        except xmodem.FatalError, e:
            self.update("Failed (%s)" % e,
                        0,
                        xa.total_errors,
                        running=False)
        except xmodem.CancelledError, e:
            self.update(str(e), 0, 0, False)

        local.close()

        gtk.gdk.threads_enter()
        self.chatgui.toggle_sendable(True)
        self.close_btn.set_sensitive(True)
        self.cancel_btn.set_sensitive(False)
        gtk.gdk.threads_leave()
        self.chatgui.comm.enable(self.chatgui)


    def show_xfer(self):
        self.window.show()

        self.chatgui.toggle_sendable(False)
        self.chatgui.comm.disable()

        self.xfer_thread = Thread(target=self.xfer)
        self.xfer_thread.start()

    def update(self, status, bytecount, errors, running=True):
        gtk.gdk.threads_enter()

        if self.total_size:
            size_str = "%i KB (%i KB total)" % (bytecount / 1024,
                                                self.total_size / 1024)
        else:
            size_str = "%i KB"
            
        self.values["Size"].set_text(size_str)
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
        if self.xfer_agent == xmodem.YModem:
            title = "Select destination folder"
            stock = gtk.FILE_CHOOSER_ACTION_SELECT_FOLDER
        else:
            title = "Save received file as..."
            stock = gtk.FILE_CHOOSER_ACTION_SAVE
            
        fc = gtk.FileChooserDialog(title,
                                   None,
                                   stock,
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