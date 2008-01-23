import gtk
import pygtk
import gobject
import time

from threading import Thread

from config import make_choice

class QST:
    def __init__(self, gui, config, text=None, freq=None):
        self.gui = gui
        self.config = config

        self.text = "[QST] %s" % text
        self.freq = freq
        self.enabled = False

    def enable(self):
        self.enabled = True
        print "Starting QST `%s'" % self.text
        self.thread = Thread(target=self.thread)
        self.thread.start()

    def disable(self):
        self.enabled = False
        self.thread.join()

    def thread(self):
        while self.enabled:
            for i in range(0, 60 * self.freq):
                if not self.enabled:
                    return
                time.sleep(1)

            print "Tick: %s" % self.text
            gtk.gdk.threads_enter()
            self.gui.tx_msg(self.text)
            gtk.gdk.threads_leave()

class SelectGUI:
    def sync_gui(self, load=True):
        pass

    def ev_cancel(self, widget, data=None):
        print "Cancel"
        self.window.hide()

    def ev_okay(self, widget, data=None):
        print "Okay"
        self.sync_gui(load=False)
        self.window.hide()

    def ev_add(self, widget, data=None):
        msg = self.e_msg.get_text()
        tme = int(self.c_tme.child.get_text())

        iter = self.list_store.append()
        self.list_store.set(iter, 0, msg, 1, tme)

        self.e_msg.set_text("")
        
    def ev_delete(self, widget, data=None):
        (list, iter) = self.list.get_selection().get_selected()
        list.remove(iter)

    def make_b_controls(self):
        times = ["1", "5", "10", "20", "30", "60"]

        self.e_msg = gtk.Entry()
        self.c_tme = make_choice(times)
        b_add = gtk.Button("Add", gtk.STOCK_ADD)

        b_add.connect("clicked",
                      self.ev_add,
                      None)
        self.e_msg.connect("activate",
                           self.ev_add,
                           None)

        hbox = gtk.HBox(False, 0)

        hbox.pack_start(self.e_msg, 0,0,0)
        hbox.pack_start(self.c_tme, 0,0,0)
        hbox.pack_start(b_add, 0,0,0)

        self.c_tme.child.set_text("60")

        self.e_msg.show()
        self.c_tme.show()
        b_add.show()
        hbox.show()

        return hbox        

    def ev_reorder(self, widget, data):
        (list, iter) = self.list.get_selection().get_selected()

        pos = int(list.get_path(iter)[0])

        try:
            if data > 0:
                target = list.get_iter(pos-1)
            else:
                target = list.get_iter(pos+1)
        except:
            return

        if target:
            list.swap(iter, target)

    def make_s_controls(self):
        vbox = gtk.VBox(True, 0)

        b_raise = gtk.Button("", gtk.STOCK_GO_UP)
        b_lower = gtk.Button("", gtk.STOCK_GO_DOWN)
        b_del = gtk.Button("Remove", gtk.STOCK_DISCARD)

        b_raise.connect("clicked",
                        self.ev_reorder,
                        1)

        b_lower.connect("clicked",
                        self.ev_reorder,
                        -1)

        b_del.connect("clicked",
                      self.ev_delete,
                      None)

        vbox.pack_start(b_raise, 0,0,0)
        vbox.pack_start(b_del, 0,0,0)
        vbox.pack_start(b_lower, 0,0,0)

        b_raise.show()
        b_lower.show()
        b_del.show()

        vbox.show()

        return vbox

    def make_display(self, side):
        hbox = gtk.HBox(False, 0)

        self.list = gtk.TreeView(self.list_store)

        r = gtk.CellRendererText()
        col = gtk.TreeViewColumn("Message", r, text=0)
        col.set_resizable(True)
        self.list.append_column(col)

        r = gtk.CellRendererText()
        col = gtk.TreeViewColumn("Period (min)", r, text=1)
        self.list.append_column(col)

        hbox.pack_start(self.list, 1,1,1)
        hbox.pack_start(side, 0,0,0)

        self.list.show()
        hbox.show()

        return hbox

    def make_action_buttons(self):
        hbox = gtk.HBox(False, 0)

        okay = gtk.Button("OK", gtk.STOCK_OK)
        cancel = gtk.Button("Cancel", gtk.STOCK_CANCEL)

        okay.connect("clicked",
                     self.ev_okay,
                     None)
        cancel.connect("clicked",
                       self.ev_cancel,
                       None)

        hbox.pack_end(cancel, 0,0,0)
        hbox.pack_end(okay, 0,0,0)

        okay.show()
        cancel.show()
        hbox.show()

        return hbox

    def show(self):
        self.sync_gui(load=True)
        self.window.show()

    def __init__(self, title="--"):
        self.list_store = gtk.ListStore(gobject.TYPE_STRING,
                                        gobject.TYPE_INT)

        self.window = gtk.Window(gtk.WINDOW_TOPLEVEL)
        self.window.set_title(title)

        vbox = gtk.VBox(False, 10)

        vbox.pack_start(self.make_display(self.make_s_controls()),1,1,1)
        vbox.pack_start(self.make_b_controls(), 0,0,0)
        vbox.pack_start(self.make_action_buttons(), 0,0,0)
        vbox.show()

        self.e_msg.grab_focus()

        self.window.add(vbox)

        self.window.set_geometry_hints(None, min_width=450, min_height=300)

class QSTGUI(SelectGUI):
    def __init__(self, config):
        SelectGUI.__init__(self, "QST Configuration")
        self.config = config

    def load_qst(self, section):
        freq = self.config.config.getint(section, "freq")
        content = self.config.config.get(section, "content")

        iter = self.list_store.append()
        self.list_store.set(iter, 0, content, 1, freq)

    def save_qst(self, model, path, iter, data=None):
        pos = path[0]

        text, freq = model.get(iter, 0, 1)

        section = "qst_%i" % int(pos)
        self.config.config.add_section(section)
        self.config.config.set(section, "freq", str(freq))
        self.config.config.set(section, "content", text)

    def sync_gui(self, load=True):
        sections = self.config.config.sections()

        qsts = [x for x in sections if x.startswith("qst_")]

        if load:
            for sec in qsts:
                self.load_qst(sec)
        else:
            for sec in qsts:
                self.config.config.remove_section(sec)

            self.list_store.foreach(self.save_qst, None)
            self.config.save()
            self.config.refresh_app()

if __name__ == "__main__":
    #g = SelectGUI("Test GUI")
    import config

    c = config.UnixAppConfig(None)
    
    g = QSTGUI(c)
    g.show()
    gtk.main()