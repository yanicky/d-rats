#!/usr/bin/python

import gtk
import pygtk

import ConfigParser

import xmodem

def make_choice(options):
    sel = gtk.combo_box_entry_new_text()

    for o in options:
        sel.append_text(o)

    return sel

class AppConfig:
    def init_config(self):
        def mset(section, option, value):
            if not self.config.has_section(section):
                self.config.add_section(section)

            if not self.config.has_option(section, option):
                self.config.set(section, option, value)

        mset("user", "name", "A. Mateur")
        mset("user", "callsign", "W1AW")

        mset("prefs", "autoid", "True")
        mset("prefs", "autoid_freq", "10")
        mset("prefs", "autoreceive", "False")
        mset("prefs", "download_dir", "")

        mset("settings", "port", self.default_port)
        mset("settings", "rate", "9600")
        mset("settings", "xfer", "YModem")

    id2label = {"name" : "Name",
                "callsign" : "Callsign",
                "autoid" : "Automatic ID",
                "autoid_freq": "Freqency",
                "autoreceive" : "Auto File Receive",
                "download_dir" : "Download directory",
                "port" : "Serial port",
                "rate" : "Baud rate",
                "xfer" : "File transfer protocol"}

    xfers = {"XModem" : xmodem.XModem,
             "XModemCRC" : xmodem.XModemCRC,
             "YModem" : xmodem.YModem}

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
        self.mainapp.refresh_config()

    def refresh_app(self):
        self.mainapp.refresh_config()

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
                                     make_choice(self.port_list())))
        vbox.pack_start(self.make_sb("rate",
                                     make_choice(baud_rates)))

        vbox.pack_start(self.make_sb("autoid", self.make_bool()))
        vbox.pack_start(self.make_sb("autoid_freq", gtk.Entry()))
        vbox.pack_start(self.make_sb("autoreceive", self.make_bool()))
        vbox.pack_start(self.make_sb("download_dir", gtk.Entry()))
        vbox.pack_start(self.make_sb("xfer",
                                     make_choice(self.xfers.keys())))

        vbox.pack_start(self.make_buttons())

        # Disable unsupported functions
        for i in ("autoid", "autoreceive", "autoid_freq", "download_dir"):
            self.fields[i].set_sensitive(False)
        
        self.window.add(vbox)

        vbox.show()

    def show(self):
        self.window.show()
        self.sync_gui(load=True)

    def sync_texts(self, list, load):
        for s, k in list:
            if load:
                self.fields[k].set_text(self.config.get(s, k))
            else:
                self.config.set(s, k, self.fields[k].get_text())

    def sync_booleans(self, list, load):
        for s, k in list:
            if load:
                self.fields[k].set_active(self.config.getboolean(s,k))
            else:
                self.config.set(s, k, str(self.fields[k].get_active()))
        
    def sync_choices(self, list, load):
        for s, k in list:
            if load:
                self.fields[k].child.set_text(self.config.get(s, k))
            else:
                self.config.set(s, k, self.fields[k].child.get_text())
        

    def sync_gui(self, load=True):
        text_v = [("user", "callsign"),
                  ("user", "name"),
                  ("prefs", "download_dir")]

        bool_v = [("prefs", "autoid"),
                  ("prefs", "autoreceive")]

        choice_v = [("settings", "port"),
                    ("settings", "rate"),
                    ("settings", "xfer")]

        self.sync_texts(text_v, load)
        self.sync_booleans(bool_v, load)
        self.sync_choices(choice_v, load)        

    def __init__(self, mainapp, _file=None):
        self.mainapp = mainapp

        if not _file:
            _file = self.default_filename()

        self.config = ConfigParser.ConfigParser()
        self.config.read(_file)
        self.fields = {}

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
    g = UnixAppConfig(None)
    g.show()
    gtk.main()
