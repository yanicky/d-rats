import pygtk
import gtk
import serial
import gobject
import time
from threading import Thread


class ChatGUI:
    def ev_delete(self, widget, event, data=None):
        return False
    
    def sig_destroy(self, widget, data=None):
        self.watching_serial = False
        print "Waiting for thread to end..."
        self.sw_thread.join()
        print "Done"
        gtk.main_quit()

    def sig_send_button(self, widget, data=None):
        text = data.get_text()
        if text == "":
            return

        self.add_to_main_buffer(text)
        self.tx_msg(text)
        
        data.set_text("")

    def add_to_main_buffer(self, string):
        self.main_buffer.insert_at_cursor(string + "\n")

        adj = self.scroll.get_vadjustment()
        adj.value = adj.upper
        self.scroll.set_vadjustment(adj)

    def tx_msg(self, string):
        self.pipe.write(string + "\n")

    def make_entry_box(self):
        hbox = gtk.HBox(False, 0)
        
        entry = gtk.Entry()
        button = gtk.Button("Send")
        
        button.connect("clicked",
                       self.sig_send_button,
                       entry)
        entry.connect("activate",
                      self.sig_send_button,
                      entry)
        
        hbox.pack_start(entry, 1, 1, 1)
        hbox.pack_start(button, 1, 1, 1)
        
        entry.show()
        button.show()

        self.entry = entry
        
        return hbox

    def make_main_pane(self):
        vbox = gtk.VBox(False, 0)
        display = gtk.TextView(self.main_buffer)
        self.scroll = gtk.ScrolledWindow()
        self.scroll.add(display)

        ebox = self.make_entry_box()

        vbox.pack_start(self.scroll, 1, 1, 1)
        vbox.pack_start(ebox, 0, 0, 1)

        ebox.show()
        self.scroll.show()
        display.show()

        return vbox

    def setup_serial(self, port=None, baudrate=None):
        self.pending_data = ""
        self.pipe = serial.Serial(port=port, timeout=2, baudrate=baudrate)
        self.watching_serial = True
        
    def __init__(self):
        self.main_buffer = gtk.TextBuffer()

        self.setup_serial(port=0, baudrate=115200)

        pane = self.make_main_pane()

        self.window = gtk.Window(gtk.WINDOW_TOPLEVEL)

        self.window.set_title("D-STAR Chat (%s)" % self.pipe.portstr)
        self.window.set_border_width(10)
        self.window.add(pane)
        self.window.connect("delete_event", self.ev_delete)
        self.window.connect("destroy", self.sig_destroy)

        pane.show()
        self.window.show()

        self.entry.grab_focus()

    def do_serial(self):
        self.add_to_main_buffer(self.pending_data)
        self.pending_data = ""

    def watch_serial(self):
        while self.watching_serial:
            size = self.pipe.inWaiting()
            if size > 0:
                data = self.pipe.read(size)
                print "Got Data: %s" % data
                gtk.gdk.threads_enter()
                self.add_to_main_buffer(data)
                gtk.gdk.threads_leave()
                #self.pending_data += data
                #gobject.idle_add(self.do_serial)
            else:
                print "No data this time"
                time.sleep(1)

        return True

    def main(self):
        gtk.gdk.threads_init()
        self.sw_thread = Thread(target=self.watch_serial)
        self.sw_thread.start()
        print "Started thread"
        gtk.gdk.threads_enter()
        gtk.main()
        gtk.gdk.threads_leave()

if __name__ == "__main__":
    gui = ChatGUI()
    gui.main()
