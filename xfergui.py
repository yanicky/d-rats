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

import os
from threading import Thread
import tempfile
import base64
import time

import pygtk
import gtk
import gobject

import ddt
import formgui

class FileTransferGUI:

    title = "File Transfer"

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

    def register_cb(self, cb, data=None):
        self.cb = cb
        self.cb_data = data

    def __init__(self, chatgui, xfer_agent):
        self.values = {}
        self.chatgui = chatgui
        self.is_send = None
        self.total_size = None
        self.xfer_agent = xfer_agent

        self.cb = None
        self.cb_data = None
        self._real_filename = None

        box = gtk.VBox(False, 0)

        self.bar = gtk.ProgressBar()
        self.bar.set_fraction(0)
        
        self.status = gtk.Label()
        self.set_status_msg("Initializing...")

        box.pack_start(self.status, 0,0,0)
        box.pack_start(self.bar, 0, 0, 0)
        box.pack_start(self.make_label_value("File"), 0, 0, 0)
        box.pack_start(self.make_label_value("Size"), 0, 0, 0)
        box.pack_start(self.make_label_value("Errors"), 0, 0, 0)
        box.pack_start(self.make_buttons(), 0, 0, 0)

        self.status.show()
        self.bar.show()
        box.show()

        self.window = gtk.Window(gtk.WINDOW_TOPLEVEL)
        self.window.set_title(self.title)
        self.window.set_resizable(False)
        self.window.set_geometry_hints(None, min_width=300)
        self.window.add(box)

    def set_status_msg(self, status):
        self.status.set_markup("<big><b>%s</b></big>" % status)

    def encoded_file(self, filename):
        i = file(filename)
        o = file(tempfile.gettempdir() + os.path.sep + "dratsencode", "w")

        base64.encode(i, o)

        i.close()
        o.close()

        return file(o.name)

    def decode_file(self, tempfile):
        i = file(tempfile)
        o = file(self.filename, "w")

        base64.decode(i, o)

        i.close()
        o.close()

    def ddt_finish(self):
        self.chatgui.toggle_sendable(True)
        self.close_btn.set_sensitive(True)
        self.cancel_btn.set_sensitive(False)

        if self.cb:
            self.cb(self.cb_data,
                    True,
                    self.filename,
                    self._real_filename) #Change this to report real success

    def ddt_xfer(self):
        x = self.xfer_agent(self.chatgui.mainapp.comm.pipe,
                            status_fn=self.update)
        
        self.xfer = x

        try:
            c = self.chatgui.config.get("settings", "write_chunk")
            x.write_chunk = int(float(c))

            d = self.chatgui.config.get("settings", "chunk_delay")
            x.chunk_delay = float(d)

            s = self.chatgui.config.get("settings", "ddt_block_size")
            x.block_size = int(s)
        except Exception, e:
            print "Failed to set chunk values: %s" % e
            raise

        if self.is_send:
            x.send_file(self.filename)
        else:
            x.recv_file(self.filename)

        gobject.idle_add(self.ddt_finish)

    def show_xfer(self):
        self.window.show()

        self.chatgui.toggle_sendable(False)

        self.xfer_thread = Thread(target=self.ddt_xfer)
        self.xfer_thread.start()

    def _update(self, status, vals):
        file = vals["filename"]
        sent = vals["transferred"]
        wire = vals["wiresize"]
        err = vals["errors"]
        tot = vals["totalsize"]

        if tot and wire:
            eff = (sent / float(wire)) * 100.0

        if tot and tot > 2048:
            tot /= 1024
            sent /= 1024
            wire /= 1024
            units = "KB"
        else:
            units = ""

        self.values["File"].set_text(file)
        self._real_filename = file

        if tot and wire:
            size_str = "%i / %i %s (%2.0f%%)" % (sent,
                                                 tot,
                                                 units,
                                                 eff)
        else:
            size_str = "%i" % sent

        err_str = "%i" % err

        self.values["Size"].set_text(size_str)
        self.values["Errors"].set_text(err_str)
        if status:
            self.set_status_msg(status)
        if tot:
            self.bar.set_fraction(float(sent) / tot)

    def update(self, status, vals):
        gobject.idle_add(self._update, status, vals)

    def do_send(self):
        fc = gtk.FileChooserDialog("Select file to send",
                                   None,
                                   gtk.FILE_CHOOSER_ACTION_OPEN,
                                   (gtk.STOCK_CANCEL, gtk.RESPONSE_CANCEL,
                                    gtk.STOCK_OPEN, gtk.RESPONSE_OK))
        d = self.chatgui.config.get("prefs", "download_dir")
        fc.set_current_folder(d)

        result = fc.run()
        self.filename = fc.get_filename()
        fc.destroy()
        if result == gtk.RESPONSE_OK:
            self.is_send = True
            self.show_xfer()

    def do_recv(self):
        title = "Select destination folder"
        stock = gtk.FILE_CHOOSER_ACTION_SELECT_FOLDER
        fc = gtk.FileChooserDialog(title,
                                   None,
                                   stock,
                                   (gtk.STOCK_CANCEL, gtk.RESPONSE_CANCEL,
                                    gtk.STOCK_SAVE, gtk.RESPONSE_OK))
        d = self.chatgui.config.get("prefs", "download_dir")
        fc.set_current_folder(d)

        result = fc.run()
        self.filename = fc.get_filename()
        fc.destroy()
        if result == gtk.RESPONSE_OK:
            self.is_send = False
            self.show_xfer()

    def wait_for_completion(self):
        self.xfer_thread.join()

class FormTransferGUI(FileTransferGUI):

    title = "Form Transfer"

    def do_send(self, form_fn):
        self.filename = form_fn
        self.is_send = True

        self.show_xfer()

    def do_recv(self, dest_dir):
        self.filename = dest_dir
        self.show_xfer()

if __name__ == "__main__":
    g = FormTransferGUI(None)
    g.window.show()
    gtk.main()
