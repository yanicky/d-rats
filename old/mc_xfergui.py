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
import gobject

import ddt
import ddt_multicast

from xfergui import FileTransferGUI

from threading import Thread

class MulticastGUI(gtk.Dialog):
    def build_display(self):
        self.col_call = 0
        self.col_prog = 1
        self.col_stat = 2

        self.store = gtk.ListStore(gobject.TYPE_STRING,
                                   gobject.TYPE_INT,
                                   gobject.TYPE_STRING)

        self.view = gtk.TreeView(self.store)
        self.view.set_rules_hint(True)

        l = [(self.col_call, "Station", gtk.CellRendererText),
             (self.col_prog, "Progress", gtk.CellRendererProgress),
             (self.col_stat, "Status", gtk.CellRendererText)]


        r = gtk.CellRendererText()
        c = gtk.TreeViewColumn("Station", r, text=self.col_call)
        c.set_resizable(True)
        c.set_sort_column_id(self.col_call)
        self.view.append_column(c)

        r = gtk.CellRendererProgress()
        c = gtk.TreeViewColumn("Progress", r, value=self.col_prog)
        c.set_resizable(True)
        c.set_sort_column_id(self.col_prog)
        self.view.append_column(c)

        r = gtk.CellRendererText()
        c = gtk.TreeViewColumn("Status", r, text=self.col_stat)
        c.set_resizable(True)
        c.set_sort_column_id(self.col_stat)
        self.view.append_column(c)

        sw = gtk.ScrolledWindow()
        sw.add(self.view)
        sw.set_policy(gtk.POLICY_NEVER, gtk.POLICY_AUTOMATIC)
        self.view.show()

        return sw        

    def build_stats(self):
        self.values = {}

        vbox = gtk.VBox(True, 2)

        for v,l in (("totalsize", "Total Size"),
                    ("wiresize", "Wire Size"),
                    ("errors", "Resent Blocks")):
            box = gtk.HBox(True, 2)
            lab = gtk.Label(l)
            val = gtk.Label("")

            box.pack_start(lab, 0,0,0)
            box.pack_start(val, 0,0,0)
            box.show()
            lab.show()
            val.show()

            self.values[v] = val
            vbox.pack_start(box, 0,0,0)
            
        status = gtk.Label("")
        status.show()
        vbox.pack_start(status, 0,0,0)
        self.values["_message"] = status

        return vbox

    def build_gui(self):
        display = self.build_display()
        stats = self.build_stats()

        self.vbox.pack_start(display, 1,1,1)
        self.vbox.pack_start(stats, 0,0,0)

        display.show()
        stats.show()

    def _button_start(self, widget, data=None):
        self.button_start.set_sensitive(False)
        self.transfer.start_transfer()

    def _button_cancel(self, widget, data=None):
        widget.set_sensitive(False)
        print "Cancel"        
        self.transfer.cancel()
        self.button_start.set_sensitive(False)
        self.button_cancel.set_sensitive(False)
        self.button_close.set_sensitive(True)

    def _button_close(self, widget, data=None):
        self.response(gtk.RESPONSE_OK)

    def _update(self, msg, vals):
        if msg:
            self.values["_message"].set_text(msg)

        for k,v in vals.items():
            if self.values.has_key(k):
                self.values[k].set_text(str(v))

    def update(self, msg, vals):
        gobject.idle_add(self._update, msg, vals)

    def _station_joined(self, station):
        print "%s joined" % station
        iter = self.store.append()
        self.store.set(iter,
                       self.col_call, station,
                       self.col_prog, 0,
                       self.col_stat, "Joined")
        self.button_start.set_sensitive(True)

    def station_joined(self, station):
        gobject.idle_add(self._station_joined, station)

    def __station_update(self, store, path, iter, data):
        (station, percent, status) = data

        this = self.store.get(iter, self.col_call)[0]
        if this == station:
            self.store.set(iter,
                           self.col_prog, percent,
                           self.col_stat, status)
            return True
        else:
            return False

    def _station_update(self, station, percent, status):
        print "Update of %s to %i: %s" % (station, percent, status)
        self.store.foreach(self.__station_update, (station, percent, status))

    def station_update(self, station, percent, status):
        gobject.idle_add(self._station_update, station, percent, status)

    def build_action(self):

        bstart = gtk.Button("Start")
        bstart.connect("clicked", self._button_start, None)
        bstart.set_sensitive(False)
        bstart.show()

        bcancel = gtk.Button("Cancel")
        bcancel.connect("clicked", self._button_cancel, None)
        bcancel.set_sensitive(True)
        bcancel.show()

        bclose = gtk.Button("Close")
        bclose.connect("clicked", self._button_close, None)
        bclose.set_sensitive(False)
        bclose.show()

        self.action_area.pack_start(bstart)
        self.action_area.pack_start(bcancel)
        self.action_area.pack_start(bclose)

        self.button_start = bstart
        self.button_cancel = bcancel
        self.button_close = bclose

    def transfer_finished(self):
        self.button_cancel.set_sensitive(False)
        self.button_close.set_sensitive(True)

    def transfer_thread(self):
        print "Thread started"

        self.transfer.send_file(self._filename,
                                self.station_joined,
                                self.station_update)
        gobject.idle_add(self.transfer_finished)
       
    def run(self):
        self.thread = Thread(target=self.transfer_thread)
        print "Starting"
        self.thread.start()
        print "Thread started"

        gtk.Dialog.run(self)

    def __init__(self, filename, pipe, block_size=512, parent=None):
        self._filename = filename
        self._pipe = pipe

        gtk.Dialog.__init__(self, title="Multicast", parent=parent)

        self.set_default_size(500,350)
        
        self.build_gui()
        self.build_action()

        self.transfer = ddt_multicast.DDTMulticastTransfer(self._pipe,
                                                           "Sender",
                                                           self.update)

        self.transfer.block_size = block_size

class MulticastRecvGUI(FileTransferGUI):
    def ddt_xfer(self):
        station = self.chatgui.config.get("user", "callsign")

        xfer = ddt_multicast.DDTMulticastTransfer(self.chatgui.mainapp.comm.path,
                                                  station,
                                                  status_fn=self.update)
        self.xfer = xfer

        xfer.recv_file(self.filename)

        gobject.idle_add(self.ddt_finish)

if __name__=="__main__":
    import serial
    s = serial.Serial(port="/dev/ttyUSB1", timeout=0.25)
    d = MulticastGUI("mainapp.py", s)

    d.station_joined("N7AAM")
    d.station_joined("KE7FTE")
    d.station_joined("K7TKK")

    d.station_update("N7AAM", 32, "In progress")
    d.station_update("KE7FTE", 100, "Complete")
    d.station_update("K7TKK", 95, "In progress")

    d.update("Sending block 7", {"wiresize" : 38722,
                                 "totalsize" : 32768,
                                 "filename" : "ocem_logo.jpg",
                                 "errors" : 3})
    
    d.run()
    gtk.main()
