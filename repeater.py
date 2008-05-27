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

import threading
import time
import socket
import ConfigParser

import gtk
import gobject

from comm import SWFSerial
from config import make_choice
import miscwidgets
import platform

def call_with_lock(lock, fn, *args):
    lock.acquire()
    r = fn(*args)
    lock.release()
    return r

IN = 0
OUT = 1
PEEK = 2

def DEBUG(str):
    pass
    #print str

class DataPath:
    def __init__(self, id, condition):
        self.id = id
        self.in_buffer = ""
        self.out_buffer = ""
        self.lock = threading.Lock()
        self.thread = None
        self.enabled = True
        self.condition = condition
        self.min_buffer = 512

    def signal(self):
        self.condition.acquire()
        print "Signaling %s" % time.time()
        self.condition.notify()
        self.condition.release()

    def hasIncoming(self):
        r = call_with_lock(self.lock, len, self.in_buffer)
        return r > 0

    def hasOutgoing(self):
        r = call_with_lock(self.lock, len, self.out_buffer)
        return r > 0

    def l_drain_buffer(self, buffer):
        if buffer == IN:
            b = self.in_buffer
            self.in_buffer = ""
        elif buffer == OUT:
            b = self.out_buffer
            self.out_buffer = ""

        return b

    def l_append_buffer(self, buffer, value):
        if buffer == IN:
            self.in_buffer += value
            self.signal()
        elif buffer == OUT:
            self.out_buffer += value

    def read(self):
        if not self.enabled:
            raise Exception("Closed")
        return call_with_lock(self.lock,
                              self.l_drain_buffer, IN)

    def write(self, buf):
        if not self.enabled:
            raise Exception("Closed")
        return call_with_lock(self.lock,
                              self.l_append_buffer, OUT, buf)

    def stop(self):
        print "Stopping %s" % self.id
        self.enabled = False

        if self.thread:
            self.thread.join()

        print "Stopped %s" % self.id
    
class LoopDataPath(DataPath):
    def hasIncoming(self):
        return False

    def l_drain_buffer(self, buffer):
        if buffer != PEEK:
            return ""

        b = self.in_buffer
        self.in_buffer = ""

        return b

    def l_append_buffer(self, buffer, value):
        self.in_buffer += value

    def peek(self):
        if not self.enabled:
            raise Exception("Closed")
        return call_with_lock(self.lock,
                              self.l_drain_buffer, PEEK)

class SerialDataPath(DataPath):
    def serial_outgoing(self):
        out = call_with_lock(self.lock,
                             self.l_drain_buffer, OUT)
        if len(out) > 0:
            self.pipe.write(out)
        
    def serial_incoming(self):
        inp = "foo"
        data = ""

        while inp:
            inp = self.pipe.read(64)
            data += inp

            if len(data) > self.min_buffer:
                call_with_lock(self.lock,
                               self.l_append_buffer, IN, data)
                data = ""

        if data:
            call_with_lock(self.lock,
                           self.l_append_buffer, IN, data)

    def serial_thread(self):
        while self.enabled:
            try:
                self.serial_outgoing()
            except Exception, e:
                print "Got exception during write: %s" % e

            try:
                self.serial_incoming()
            except Exception, e:
                print "Got Exception during read: %s" % e

        self.pipe.close()

    def __init__(self, id, condition, port, rate):
        DataPath.__init__(self, id, condition)

        self.pipe = SWFSerial(port=port,
                              baudrate=rate,
                              timeout=0.1,
                              writeTimeout=5)
        self.thread = threading.Thread(target=self.serial_thread)
        self.thread.start()

class TcpDataPath(DataPath):
    def hasIncoming(self):
        if not self.enabled:
            raise Exception("Socket Closed")
        else:
            return DataPath.hasIncoming(self)

    def tcp_outgoing(self):
        out = call_with_lock(self.lock,
                             self.l_drain_buffer, OUT)
        if len(out) > 0:
            try:
                self.socket.send(out)
            except:
                self.enabled = False

    def tcp_incoming(self):
        inp = "foo"
        data = ""

        while True:
            try:
                DEBUG("Read...")
                inp = self.socket.recv(64)
                DEBUG("Read returned")
                if inp == "":
                    DEBUG("Socket returned nothing; closed")
                    self.enabled = False
                    break
                data += inp
            except socket.error, info:
                if "timed out" in str(info):
                    DEBUG("Socket read timed out")
                else:
                    DEBUG("Socket error: %s" % info)
                    self.enabled = False
                break
            except Exception, e:
                DEBUG("Exception during socket read: %s" % e)
                self.enabled = False
                break

            DEBUG("Socket returned data: %s" % inp)

            if len(data) > self.min_buffer:
                # If the data is above the low water mark, go ahead
                # and start filling the output buffer
                DEBUG("Hit low-water mark")
                call_with_lock(self.lock,
                               self.l_append_buffer, IN, data)
                data = ""

        DEBUG("Done with tcp_incoming")

        if data:
            call_with_lock(self.lock,
                           self.l_append_buffer, IN, data)

    def tcp_thread(self):
        while self.enabled:
            self.tcp_outgoing()
            self.tcp_incoming()

        self.socket.close()

    def __init__(self, id, condition, socket):
        DataPath.__init__(self, id, condition)

        self.socket = socket
        #self.socket.setblocking(False)
        self.socket.settimeout(0.1)
        self.thread = threading.Thread(target=self.tcp_thread)
        self.thread.start()

class TcpOutgoingDataPath(TcpDataPath):
    def __init__(self, id, condition, host):
        try:
            _, host, port = host.split(":")
            port = int(port)
        except Exception, e:
            print "Unable to parse host `%s': %s" % (host, e)
            return

        _socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        _socket.connect((host, port))
        TcpDataPath.__init__(self, id, condition, _socket)

class Repeater:
    def __init__(self, id="D-RATS Network Proxy"):
        self.paths = []
        self.thread = None
        self.enabled = True
        self.socket = None
        self.repeat_thread = None
        self.id = id
        self.condition = threading.Condition()

    def accept_new(self):
        if not self.socket:
            return

        try:
            (csocket, addr) = self.socket.accept()
        except:
            return

        path = TcpDataPath("Network (%s:%s)" % csocket.getpeername(),
                           self.condition,
                           csocket)
        try:
            path.write(self.id)
            self.paths.append(path)
        except:
            path.disconnect()

    def listen_on(self, port):
        self.socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        self.socket.setblocking(0)
        self.socket.setsockopt(socket.SOL_SOCKET,
                               socket.SO_REUSEADDR,
                               1)
        self.socket.bind(('0.0.0.0', port))
        self.socket.listen(0)

    def send_data(self, exclude, data):
        targets = list(self.paths)
        if exclude in targets:
            targets.remove(exclude)

        for t in targets:
            print "Sending to %s" % t.id
            try:
                t.write(data)
            except:
                print "Removing stale %s" % t.id
                self.paths.remove(t)
                t.stop()

    def _repeat(self):
        while self.enabled:
            self.condition.acquire()
            self.condition.wait(5)
            self.accept_new()
            self.condition.release()

            data = {}
            for p in self.paths:
                try:
                    if p.hasIncoming():
                        print "Got data from %s" % p.id
                        data = p.read()
                        self.send_data(p, data)
                except:
                    print "%s closed" % p.id
                    self.paths.remove(p)
                    p.stop()

    def repeat(self):
        self.repeat_thread = threading.Thread(target=self._repeat)
        self.repeat_thread.start()

    def stop(self):
        self.enabled = False

        self.condition.acquire()
        self.condition.notify()
        self.condition.release()

        if self.repeat_thread:
            print "Stopping repeater"
            self.repeat_thread.join()

        for p in self.paths:
            print "Stopping %s" % p.id
            p.stop()

        if self.socket:
            self.socket.close()

        print "EXIT"

class RepeaterGUI:
    def add_serial(self, widget, widgets):
        entry, baud = widgets

        try:
            d = entry.get_active_text()
            r = int(baud.get_active_text())
            self.dev_list.add_item(d, r)
            l = eval(self.config.get("settings", "devices"))
            l.append((d,r))
            self.config.set("settings", "devices", str(l))
        except Exception, e:
            print "Error adding serial port: %s" % e
            pass

    def sig_destroy(self, widget, data=None):
        self.button_off(None)
        self.save_config(self.config)
        gtk.main_quit()

    def ev_delete(self, widget, event, data=None):
        self.button_off(None)
        self.save_config(self.config)
        gtk.main_quit()        

    def make_side_buttons(self):
        vbox = gtk.VBox(False, 2)

        but_remove = gtk.Button("Remove")
        but_remove.set_size_request(75, 30)
        but_remove.connect("clicked", self.button_remove)
        but_remove.show()
        vbox.pack_start(but_remove, 0,0,0)

        vbox.show()
        
        return vbox

    def make_add_serial(self):
        p = platform.get_platform()

        rates = ["300", "1200", "4800", "9600",
                 "19200", "38400", "115200"]
        ports = p.list_serial_ports()
        if len(ports) > 0:
            default_port = ports[0]
        else:
            default_port = None
        
        hbox = gtk.HBox(False, 2)

        lab = gtk.Label("Add serial or net path:")
        lab.show()
        hbox.pack_start(lab, 0,0,0)

        serial = make_choice(ports, True, default_port)
        serial.show()
        hbox.pack_start(serial, 1,1,1)

        baud = make_choice(rates, True, "9600")
        baud.set_size_request(75, -1)
        baud.show()
        hbox.pack_start(baud, 0,0,0)

        but_add = gtk.Button("Add")
        but_add.connect("clicked", self.add_serial, (serial, baud))
        but_add.set_size_request(75, 30)
        but_add.show()
        hbox.pack_start(but_add, 0,0,0)

        hbox.show()

        return hbox

    def load_devices(self):
        try:
            l = eval(self.config.get("settings", "devices"))
            for d,r in l:
                self.dev_list.add_item(d, r)
        except Exception, e:
            print "Unable to load devices: %s" % e

    def make_devices(self):
        frame = gtk.Frame("Paths")

        vbox = gtk.VBox(False, 2)
        frame.add(vbox)

        hbox = gtk.HBox(False, 2)

        self.dev_list = miscwidgets.ListWidget([(gobject.TYPE_STRING, "Device"),
                                                (gobject.TYPE_INT, "Baud")])
        self.dev_list.show()
        self.load_devices()

        hbox.pack_start(self.dev_list, 1,1,1)
        hbox.pack_start(self.make_side_buttons(), 0,0,0)
        hbox.show()

        vbox.pack_start(hbox, 1,1,1)
        vbox.pack_start(self.make_add_serial(), 0,0,0)
        
        vbox.show()
        frame.show()

        return frame

    def make_network(self):
        frame = gtk.Frame("Network")

        vbox = gtk.VBox(False, 2)
        frame.add(vbox)

        self.net_enabled = gtk.CheckButton("Accept incoming connections")
        try:
            accept = self.config.getboolean("settings", "acceptnet")
        except:
            accept = True

        self.net_enabled.set_active(accept)
        self.net_enabled.show()

        vbox.pack_start(self.net_enabled, 0,0,0)

        hbox = gtk.HBox(False, 2)

        lab = gtk.Label("Port:")
        lab.show()
        hbox.pack_start(lab, 0,0,0)

        self.entry_port = gtk.Entry()
        try:
            port = self.config.get("settings", "netport")
        except:
            port = "9000"
        
        self.entry_port.set_text(port)
        self.entry_port.set_size_request(100, -1)
        self.entry_port.show()
        hbox.pack_start(self.entry_port, 0,0,0)

        hbox.show()
        vbox.pack_start(hbox, 0,0,0)

        vbox.show()
        frame.show()

        return frame

    def make_bottom_buttons(self):
        hbox = gtk.HBox(False, 2)

        self.but_on = gtk.Button("On")
        self.but_on.set_size_request(75, 30)
        self.but_on.connect("clicked", self.button_on)
        self.but_on.show()
        hbox.pack_start(self.but_on, 0,0,0)

        self.but_off = gtk.Button("Off")
        self.but_off.set_size_request(75, 30)
        self.but_off.connect("clicked", self.button_off)
        self.but_off.set_sensitive(False)
        self.but_off.show()
        hbox.pack_start(self.but_off, 0,0,0)

        hbox.show()

        return hbox        

    def make_id(self):
        frame = gtk.Frame("Identification")

        hbox = gtk.HBox(False, 2)

        self.entry_id = gtk.Entry()
        try:
            deftxt = self.config.get("settings", "idstr")
        except:
            deftxt = "D-RATS Repeater Proxy: W1AW"

        self.entry_id.set_text(deftxt)
        self.entry_id.show()
        hbox.pack_start(self.entry_id, 1,1,1)

        try:
            idfreq = self.config.get("settings", "idfreq")
        except:
            idfreq = "30"

        self.id_freq = make_choice(["Never", "30", "60", "120"],
                                   True,
                                   idfreq)
        self.id_freq.set_size_request(75, -1)
        self.id_freq.show()
        hbox.pack_start(self.id_freq, 0,0,0)

        hbox.show()
        frame.add(hbox)
        frame.show()

        return frame

    def make_settings(self):
        vbox = gtk.VBox(False, 5)

        vbox.pack_start(self.make_devices(), 1,1,1)
        vbox.pack_start(self.make_network(), 0,0,0)
        vbox.pack_start(self.make_id(), 0,0,0)

        vbox.show()

        self.settings = vbox

        return vbox

    def make_connected(self):
        frame = gtk.Frame("Connected Paths")

        self.conn_list = miscwidgets.ListWidget([(gobject.TYPE_STRING,
                                                  "ID")])
        self.conn_list.show()

        frame.add(self.conn_list)
        frame.show()

        return frame

    def make_traffic(self):
        frame = gtk.Frame("Traffic Monitor")

        self.traffic_buffer = gtk.TextBuffer()
        self.traffic_view = gtk.TextView(buffer=self.traffic_buffer)
        self.traffic_view.set_wrap_mode(gtk.WRAP_WORD)
        self.traffic_view.show()

        self.traffic_buffer.create_mark("end",
                                        self.traffic_buffer.get_end_iter(),
                                        False)

        sw = gtk.ScrolledWindow()
        sw.set_policy(gtk.POLICY_AUTOMATIC, gtk.POLICY_AUTOMATIC)
        sw.add(self.traffic_view)
        sw.show()

        frame.add(sw)
        frame.show()

        return frame

    def make_monitor(self):
        vbox = gtk.VBox(False, 5)

        vbox.pack_start(self.make_connected(), 1,1,1)
        vbox.pack_start(self.make_traffic(), 1,1,1)

        vbox.show()

        return vbox

    def sync_config(self):
        idstr = self.entry_id.get_text()
        idfreq = self.id_freq.get_active_text()
        port = self.entry_port.get_text()
        acceptnet = str(self.net_enabled.get_active())
        devices = self.dev_list.get_values()

        self.config.set("settings", "idstr", idstr)
        self.config.set("settings", "idfreq", idfreq)
        self.config.set("settings", "netport", port)
        self.config.set("settings", "acceptnet", acceptnet)
        self.config.set("settings", "devices", devices)

    def button_remove(self, widget):
        self.dev_list.remove_selected()

    def button_on(self, widget, data=None):
        self.tick = 0

        self.save_config(self.config)

        self.but_off.set_sensitive(True)
        self.but_on.set_sensitive(False)
        self.settings.set_sensitive(False)

        self.repeater = Repeater(self.entry_id.get_text())
        for dev,baud in self.dev_list.get_values():
            if dev.startswith("net:"):
                p = TcpOutgoingDataPath("Network (%s)" % dev,
                                        self.repeater.condition,
                                        dev)
            else:
                p = SerialDataPath("Serial (%s)" % dev,
                                   self.repeater.condition,
                                   dev,
                                   baud)
            self.repeater.paths.append(p)

        try:
            port = int(self.entry_port.get_text())
            enabled = self.net_enabled.get_active()
        except:
            port = 0

        if port and enabled:
            self.repeater.listen_on(port)

        self.tap = LoopDataPath("TAP", self.repeater.condition)
        self.repeater.paths.append(self.tap)

        self.repeater.repeat()

    def button_off(self, widget, data=None):
        self.but_off.set_sensitive(False)
        self.but_on.set_sensitive(True)
        self.settings.set_sensitive(True)

        if self.repeater:
            self.repeater.stop()
            self.repeater = None
            self.tap = None

    def update(self):
        if self.repeater:
            paths = self.repeater.paths
            l = [(x.id,) for x in paths]
        else:
            l = []

        if ("TAP",) in l:
            l.remove(("TAP",))

        self.conn_list.set_values(l)            

        if self.tap:
            traffic = self.tap.peek()
            end = self.traffic_buffer.get_end_iter()
            self.traffic_buffer.insert(end, traffic)

            count = self.traffic_buffer.get_line_count()
            if count > 200:
                start = self.traffic_buffer.get_start_iter()
                limit = self.traffic_buffer.get_iter_at_line(count - 200)
                self.traffic_buffer.delete(start, limit)

            endmark = self.traffic_buffer.get_mark("end")
            self.traffic_view.scroll_to_mark(endmark, 0.0, True, 0, 1)
        try:
            limit = int(self.id_freq.get_active_text())
            if (self.tick / 60) == limit:
                self.repeater.send_data(None, self.entry_id.get_text())
                self.tick = 0
        except:
            pass

        self.tick += 1

        return True

    def load_config(self):
        self.config_fn = self.platform.config_file("repeater.config")
        config = ConfigParser.ConfigParser()
        config.add_section("settings")
        config.set("settings", "devices", "[]")
        config.set("settings", "acceptnet", "True")
        config.set("settings", "netport", "9000")
        config.set("settings", "idstr", "D-RATS Repeater Proxy: W1AW")
        config.set("settings", "idfreq", "30")
        config.read(self.config_fn)

        return config

    def save_config(self, config):
        self.sync_config()
        f = file(self.config_fn, "w")
        config.write(f)
        f.close()

    def __init__(self):
        self.repeater = None
        self.tap = None
        self.tick = 0

        self.platform = platform.get_platform()

        self.config = self.load_config()

        self.window = gtk.Window(gtk.WINDOW_TOPLEVEL)
        self.window.set_default_size(450, 380)
        self.window.connect("delete_event", self.ev_delete)
        self.window.connect("destroy", self.sig_destroy)
        self.window.set_title("D-RATS Repeater Proxy")

        vbox = gtk.VBox(False, 5)

        self.tabs = gtk.Notebook()
        self.tabs.append_page(self.make_settings(), gtk.Label("Settings"))
        self.tabs.append_page(self.make_monitor(), gtk.Label("Monitor"))
        self.tabs.show()

        vbox.pack_start(self.tabs, 1,1,1)
        vbox.pack_start(self.make_bottom_buttons(), 0,0,0)
        vbox.show()

        self.window.add(vbox)
        self.window.show()

        gobject.timeout_add(1000, self.update)

if __name__=="__main__":
    import sys

    if True:
        f = file("repeater.log", "w", 0)
        if f:
            sys.stdout = f
            sys.stderr = f
        else:
            print "Failed to open log"

    g = RepeaterGUI()
    gtk.main()
    sys.exit(1)

    r = Repeater()

    s = SerialDataPath("USB1", "/dev/ttyUSB0", r.condition, 9600)
    r.paths.append(s)

    r.listen_on(9000)
    r.repeat()

    try:
        while True:
            time.sleep(1)
    except:
        print "Interrupted"
        pass

    r.stop()

