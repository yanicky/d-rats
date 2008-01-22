#!/usr/bin/python

import gtk
import pygtk

import ConfigParser

class AppConfig:
    def init_config(self):
        self.config.add_section("user")
        self.config.set("user", "name", "A. Mateur")
        self.config.set("user", "callsign", "W1AW")

        self.config.add_section("prefs")
        self.config.set("prefs", "autoid", "True")
        self.config.set("prefs", "autoid_freq", "10")
        self.config.set("prefs", "autoreceive", "False")
        self.config.set("prefs", "download_dir", "")

        self.config.add_section("settings")
        self.config.set("settings", "port", self.default_port)
        self.config.set("settings", "rate", "9600")

    id2label = {"name" : "Name",
                "callsign" : "Callsign",
                "autoid" : "Automatic ID",
                "autoid_freq": "Freqency",
                "autoreceive" : "Auto File Receive",
                "download_dir" : "Download directory",
                "port" : "Serial port",
                "rate" : "Baud rate"}

    def default_filename(self):
        return "drats.config"

    def make_sb(self, id, child):
        hbox = gtk.HBox(True, 0)

        label = gtk.Label(self.id2label[id])

        hbox.pack_start(label, 0, 0, 0)
        hbox.pack_end(child, 1, 1, 0)

        self.fields[id] = child

        label.show()
        child.show()
        hbox.show()

        return hbox

    def port_list(self):
        return ["Port1", "Port2"]

    def make_choice(self, options):
        sel = gtk.combo_box_entry_new_text()

        for o in options:
            sel.append_text(o)

        return sel

    def make_bool(self):
        return gtk.CheckButton("Enabled")

    def make_buttons(self):
        hbox = gtk.HBox(True, 0)

        save = gtk.Button("Save", gtk.STOCK_SAVE)
        save.connect("clicked",
                     self.save_button,
                     None)

        cancel = gtk.Button("Cancel", gtk.STOCK_CANCEL)
        cancel.connect("clicked",
                       self.cancel_button,
                       None)

        hbox.pack_start(cancel, 0, 0, 0)
        hbox.pack_start(save, 0, 0, 0)

        save.show()
        cancel.show()
        hbox.show()

        return hbox

    def destroy(self, widget, data=None):
        self.window.hide()

    def delete(self, widget, event, data=None):
        self.window.hide()

    def save_button(self, widget, data=None):
        self.sync_gui(load=False)
        self.save()
        self.window.hide()

    def cancel_button(self, widget, data=None):
        self.sync_gui(load=True)
        self.window.hide()

    def build_gui(self):
        self.window = gtk.Window(gtk.WINDOW_TOPLEVEL)

        self.window.connect("delete_event", self.delete)
        self.window.connect("destroy", self.destroy)

        baud_rates = ["300", "1200", "4800", "9600",
                      "19200", "38400", "115200"]

        vbox = gtk.VBox(False, 0)

        vbox.pack_start(self.make_sb("callsign", gtk.Entry()))
        vbox.pack_start(self.make_sb("name", gtk.Entry()))

        vbox.pack_start(self.make_sb("port",
                                     self.make_choice(self.port_list())))
        vbox.pack_start(self.make_sb("rate",
                                     self.make_choice(baud_rates)))

        vbox.pack_start(self.make_sb("autoid", self.make_bool()))
        vbox.pack_start(self.make_sb("autoid_freq", gtk.Entry()))
        vbox.pack_start(self.make_sb("autoreceive", self.make_bool()))
        vbox.pack_start(self.make_sb("download_dir", gtk.Entry()))

        vbox.pack_start(self.make_buttons())

        # Disable unsupported functions
        for i in ("autoid", "autoreceive", "autoid_freq", "download_dir"):
            self.fields[i].set_sensitive(False)
        
        self.window.add(vbox)

        vbox.show()

    def show(self):
        self.window.show()
        self.sync_gui(load=True)

    def sync_gui(self, load=True):
        text_v = [("user", "callsign"),
                  ("user", "name"),
                  ("prefs", "download_dir")]

        bool_v = [("prefs", "autoid"),
                  ("prefs", "autoreceive")]

        choice_v = [("settings", "port"),
                    ("settings", "rate")]

        # Text
        for s, k in text_v:
            if load:
                self.fields[k].set_text(self.config.get(s, k))
            else:
                self.config.set(s, k, self.fields[k].get_text())

        # Booleans
        for s, k in bool_v:
            if load:
                self.fields[k].set_active(self.config.getboolean(s,k))
            else:
                self.config.set(s, k, str(self.fields[k].get_active()))

        # Choices
        for s, k in choice_v:
            if load:
                self.fields[k].child.set_text(self.config.get(s, k))
            else:
                self.config.set(s, k, self.fields[k].child.get_text())

    def __init__(self, _file=None):
        if not _file:
            _file = self.default_filename()

        self.config = ConfigParser.ConfigParser()
        self.config.read(_file)
        self.fields = {}

        if not self.config.has_section("user"):
            self.init_config()

        self.build_gui()

    def save(self, _file=None):
        if not _file:
            _file = self.default_filename()

        f = file(_file, "w")
        self.config.write(f)
        f.close()

class UnixAppConfig(AppConfig):
    default_port = "/dev/ttyS0"

    def port_list(self):
        return ["/dev/ttyS0", "/dev/ttyS1",
                "/dev/ttyUSB0", "/dev/ttyUSB1"]

class Win32AppConfig(AppConfig):
    default_port = "COM1"

    def default_filename(self):
        # FIXME!
        return "c:\drats.config"

    def port_list(self):
        return ["COM1", "COM2", "COM3", "COM4"]

if __name__ == "__main__":
    g = UnixAppConfig()
    g.show()
    gtk.main()
