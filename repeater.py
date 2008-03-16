#!/usr/bin/python

import threading
import time
import socket

import gtk
import gobject

from mainapp import SWFSerial
from config import make_choice
import miscwidgets

def call_with_lock(lock, fn, *args):
    lock.acquire()
    r = fn(*args)
    lock.release()
    return r

IN = 0
OUT = 1
PEEK = 2

class DataPath:
    def __init__(self, id):
        self.id = id
        self.in_buffer = ""
        self.out_buffer = ""
        self.lock = threading.Lock()
        self.thread = None
        self.enabled = True

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
        self.enabled = False

        if self.thread:
            self.thread.join()
    
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

        if data:
            call_with_lock(self.lock,
                           self.l_append_buffer, IN, data)

    def serial_thread(self):
        while self.enabled:
            self.serial_outgoing()
            self.serial_incoming()

            time.sleep(0.25)            
    
        self.pipe.close()

    def __init__(self, id, port, rate):
        DataPath.__init__(self, id)

        self.pipe = SWFSerial(port=port, baudrate=rate, timeout=0.25)
        self.thread = threading.Thread(target=self.serial_thread)
        self.thread.start()

class TcpDataPath(DataPath):
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

        while inp:
            try:
                inp = self.socket.recv(64)
            except:
                break

            data += inp

        if data:
            call_with_lock(self.lock,
                           self.l_append_buffer, IN, data)

    def tcp_thread(self):
        while self.enabled:
            self.tcp_outgoing()
            self.tcp_incoming()
            time.sleep(0.25)

        self.socket.close()

    def __init__(self, id, socket):
        DataPath.__init__(self, id)

        self.socket = socket
        self.socket.setblocking(False)
        self.thread = threading.Thread(target=self.tcp_thread)
        self.thread.start()

class Repeater:
    def __init__(self):
        self.paths = []
        self.thread = None
        self.enabled = True
        self.socket = None
        self.repeat_thread = None

    def accept_new(self):
        if not self.socket:
            return

        try:
            (csocket, addr) = self.socket.accept()
        except:
            return

        path = TcpDataPath("Network (%s:%s)" % csocket.getpeername(), csocket)
        path.write("D-RATS Network Proxy: Ready")
        self.paths.append(path)

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
        targets.remove(exclude)

        for t in targets:
            print "Sending to %s" % t.id
            try:
                t.write(data)
            except:
                print "Removing stale %s" % t.id
                self.paths.remove(t)

    def _repeat(self):
        while self.enabled:
            self.accept_new()

            data = {}
            for p in self.paths:
                if p.hasIncoming():
                    print "Got data from %s" % p.id
                    data = p.read()
                    self.send_data(p, data)

            time.sleep(0.1)
         
    def repeat(self):
        self.repeat_thread = threading.Thread(target=self._repeat)
        self.repeat_thread.start()

    def stop(self):
        self.enabled = False

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
            self.dev_list.add_item(entry.get_text(),
                                   int(baud.get_active_text()))
            entry.set_text("")
        except:
            pass

    def sig_destroy(self, widget, data=None):
        self.button_off(None)
        gtk.main_quit()

    def ev_delete(self, widget, event, data=None):
        self.button_off(None)
        gtk.main_quit()        

    def make_side_buttons(self):
        vbox = gtk.VBox(False, 2)

        but_remove = gtk.Button("Remove")
        but_remove.set_size_request(75, 30)
        but_remove.show()
        vbox.pack_start(but_remove, 0,0,0)

        vbox.show()
        
        return vbox

    def make_add_serial(self):
        hbox = gtk.HBox(False, 2)

        lab = gtk.Label("Add serial device:")
        lab.show()
        hbox.pack_start(lab, 0,0,0)

        entry_serial = gtk.Entry()
        entry_serial.show()
        hbox.pack_start(entry_serial, 1,1,1)

        baud_rates = ["300", "1200", "4800", "9600",
                      "19200", "38400", "115200"]

        baud = make_choice(baud_rates, True, "9600")
        baud.show()
        hbox.pack_start(baud, 0,0,0)

        but_add = gtk.Button("Add")
        but_add.connect("clicked", self.add_serial, (entry_serial, baud))
        but_add.set_size_request(75, 30)
        but_add.show()
        hbox.pack_start(but_add, 0,0,0)

        hbox.show()

        return hbox

    def make_devices(self):
        frame = gtk.Frame("Devices")

        vbox = gtk.VBox(False, 2)
        frame.add(vbox)

        hbox = gtk.HBox(False, 2)

        self.dev_list = miscwidgets.ListWidget([(gobject.TYPE_STRING, "Device"),
                                                (gobject.TYPE_INT, "Baud")])
        self.dev_list.show()

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
        self.net_enabled.set_active(True)
        self.net_enabled.show()

        vbox.pack_start(self.net_enabled, 0,0,0)

        hbox = gtk.HBox(False, 2)

        lab = gtk.Label("Port:")
        lab.show()
        hbox.pack_start(lab, 0,0,0)

        self.entry_port = gtk.Entry()
        self.entry_port.set_text("9000")
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

    def make_settings(self):
        vbox = gtk.VBox(False, 5)

        vbox.pack_start(self.make_devices(), 1,1,1)
        vbox.pack_start(self.make_network(), 0,0,0)

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

        sw = gtk.ScrolledWindow()
        sw.set_policy(gtk.POLICY_NEVER, gtk.POLICY_AUTOMATIC)
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

    def button_on(self, widget, data=None):
        self.but_off.set_sensitive(True)
        self.but_on.set_sensitive(False)
        self.settings.set_sensitive(False)

        self.repeater = Repeater()
        for dev,baud in self.dev_list.get_values():
            s = SerialDataPath("Serial (%s)" % dev, dev, baud)
            self.repeater.paths.append(s)

        try:
            port = int(self.entry_port.get_text())
            enabled = self.net_enabled.get_active()
        except:
            port = 0

        if port and enabled:
            self.repeater.listen_on(port)

        self.tap = LoopDataPath("TAP")
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
            (start, end) = self.traffic_buffer.get_bounds()
            self.traffic_buffer.insert(end, traffic)
        
        return True

    def __init__(self):
        self.repeater = None
        self.tap = None

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

    g = RepeaterGUI()
    gtk.main()
    sys.exit(1)

    r = Repeater()

    s = SerialDataPath("USB1", "/dev/ttyUSB0", 9600)
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

