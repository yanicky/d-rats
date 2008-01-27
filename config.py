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

import gtk
import pygtk

import ConfigParser

import xmodem

def make_choice(options, editable=True):
    if editable:
        sel = gtk.combo_box_entry_new_text()
    else:
        sel = gtk.combo_box_new_text()

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

        mset("prefs", "autoreceive", "False")
        mset("prefs", "download_dir", "")
        mset("prefs", "blinkmsg", "False")
        mset("prefs", "noticere", "")
        mset("prefs", "ignorere", "")
        mset("prefs", "signon", "Online (D-RATS)")
        mset("prefs", "signoff", "Going offline (D-RATS)")
        mset("prefs", "dosignon", "True")
        mset("prefs", "dosignoff", "True")
        mset("prefs", "incomingcolor", "#00004444FFFF")
        mset("prefs", "outgoingcolor", "#DDDD44441111")
        mset("prefs", "noticecolor", "#0000660011DD")
        mset("prefs", "ignorecolor", "#BB88BB88BB88")

        mset("settings", "port", self.default_port)
        mset("settings", "rate", "9600")
        mset("settings", "xfer", "YModem")

    id2label = {"name" : "Name",
                "callsign" : "Callsign",
                "autoreceive" : "Auto File Receive",
                "download_dir" : "Download directory",
                "port" : "Serial port",
                "rate" : "Baud rate",
                "xfer" : "File transfer protocol",
                "blinkmsg" : "Blink tray on new message",
                "noticere" : "Notice RegEx",
                "ignorere" : "Ignore RegEx",
                "signon" : "",
                "signoff" : "",
                "dosignon" : "Sign-on message",
                "dosignoff" : "Sign-off message",
                "incomingcolor" : "Color for incoming messages",
                "outgoingcolor" : "Color for outgoing messages",
                "noticecolor" : "Color for notices",
                "ignorecolor" : "Color for ignores",
                }

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

    def make_colorpick(self):
        b = gtk.ColorButton()
        #b.set_color(gtk.gdk.color_parse(self.config.get("prefs", key)))
        #b.connect("color-set", self.pick_color, key)
        return b

    def port_list(self):
        return ["Port1", "Port2"]

    def make_bool(self):
        return gtk.CheckButton("Enabled")

    def make_buttons(self):
        hbox = gtk.HBox(False, 5)

        save = gtk.Button("Save", gtk.STOCK_SAVE)
        save.connect("clicked",
                     self.save_button,
                     None)

        cancel = gtk.Button("Cancel", gtk.STOCK_CANCEL)
        cancel.connect("clicked",
                       self.cancel_button,
                       None)

        hbox.pack_end(cancel, 0, 0, 0)
        hbox.pack_end(save, 0, 0, 0)

        save.set_size_request(100, -1)
        cancel.set_size_request(100, -1)

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

        self.window.set_default_size(400, 500)
        self.window.set_title("Main Settings")

        self.window.connect("delete_event", self.delete)
        self.window.connect("destroy", self.destroy)

        baud_rates = ["300", "1200", "4800", "9600",
                      "19200", "38400", "115200"]

        scroll = gtk.ScrolledWindow()
        scroll.set_policy(gtk.POLICY_NEVER, gtk.POLICY_AUTOMATIC)

        vbox = gtk.VBox(False, 2)

        vbox.pack_start(self.make_sb("callsign", gtk.Entry()), 0,0,0)
        vbox.pack_start(self.make_sb("name", gtk.Entry()), 0,0,0)

        vbox.pack_start(self.make_sb("port",
                                     make_choice(self.port_list())), 0,0,0)
        vbox.pack_start(self.make_sb("rate",
                                     make_choice(baud_rates, False)), 0,0,0)

        vbox.pack_start(self.make_sb("autoreceive", self.make_bool()), 0,0,0)

        dlg = gtk.FileChooserDialog("Choose a location",
                                    None,
                                    gtk.FILE_CHOOSER_ACTION_SELECT_FOLDER,
                                    (gtk.STOCK_CANCEL, gtk.RESPONSE_CANCEL,
                                     gtk.STOCK_OPEN, gtk.RESPONSE_OK))

        vbox.pack_start(self.make_sb("download_dir",
                                     gtk.FileChooserButton(dlg)), 0,0,0)
        vbox.pack_start(self.make_sb("xfer",
                                     make_choice(self.xfers.keys(), False)), 0,0,0)

        # Broken on (at least) win32
        #vbox.pack_start(self.make_sb("blinkmsg", self.make_bool()))

        vbox.pack_start(self.make_sb("noticere", gtk.Entry()), 0,0,0)
        vbox.pack_start(self.make_sb("ignorere", gtk.Entry()), 0,0,0)

        vbox.pack_start(self.make_sb("dosignon", self.make_bool()), 0,0,0)
        vbox.pack_start(self.make_sb("signon", gtk.Entry()), 0,0,0)

        vbox.pack_start(self.make_sb("dosignoff", self.make_bool()), 0,0,0)
        vbox.pack_start(self.make_sb("signoff", gtk.Entry()), 0,0,0)

        vbox.pack_start(self.make_sb("incomingcolor",
                                     gtk.ColorButton()), 0,0,0)
        vbox.pack_start(self.make_sb("outgoingcolor",
                                     gtk.ColorButton()), 0,0,0)
        vbox.pack_start(self.make_sb("noticecolor",
                                     gtk.ColorButton()), 0,0,0)
        vbox.pack_start(self.make_sb("ignorecolor",
                                     gtk.ColorButton()), 0,0,0)
        
        # Disable unsupported functions
        for i in ("autoreceive", "noticere"):
            self.fields[i].set_sensitive(False)

        scroll.show()
        scroll.add_with_viewport(vbox)

        mainvbox = gtk.VBox(False, 5)
        mainvbox.pack_start(scroll, 1,1,1)
        mainvbox.pack_start(self.make_buttons(), 0,0,0)
        mainvbox.show()
        
        self.window.add(mainvbox)

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
        
    def sync_choicetexts(self, list, load):
        for s, k in list:
            if load:
                self.fields[k].child.set_text(self.config.get(s, k))
            else:
                self.config.set(s, k, self.fields[k].child.get_text())
        
    def sync_colors(self, list, load):
        for s, k in list:
            if load:
                self.fields[k].set_color(gtk.gdk.color_parse(self.config.get(s, k)))
            else:
                self.config.set(s, k, self.fields[k].get_color().to_string())

    def set_active_if(self, model, path, iter, data):
        widget, tval = data
        if model.get_value(iter, 0) == tval:
            widget.set_active_iter(iter)

    def sync_choices(self, list, load):
        for s, k in list:
            box = self.fields[k]
            model = box.get_model()

            if load:
                val = self.config.get(s, k)
                model.foreach(self.set_active_if, (box, val))
            else:
                index = box.get_active()
                self.config.set(s, k, model[index][0])

    def sync_paths(self, list, load):
        for s, k in list:
            button = self.fields[k]
            
            if load:
                d = self.config.get(s, k)
                print "Setting value to %s" % d
                # FIXME: This blows up
                # button.set_current_folder(d)
            else:
                d = button.get_current_folder()
                self.config.set(s, k, d)
                
    def sync_gui(self, load=True):
        text_v = [("user", "callsign"),
                  ("user", "name"),
                  ("prefs", "noticere"),
                  ("prefs", "ignorere"),
                  ("prefs", "signon"),
                  ("prefs", "signoff")]

        bool_v = [("prefs", "autoreceive"),
                  ("prefs", "dosignon"),
                  ("prefs", "dosignoff")]

        choicetext_v = [("settings", "port")]

        choice_v = [("settings", "rate"),
                    ("settings", "xfer")]

        color_v = [("prefs", "incomingcolor"),
                   ("prefs", "outgoingcolor"),
                   ("prefs", "noticecolor"),
                   ("prefs", "ignorecolor")]

        path_v =[("prefs", "download_dir")]

        self.sync_texts(text_v, load)
        self.sync_booleans(bool_v, load)
        self.sync_choicetexts(choicetext_v, load)
        self.sync_choices(choice_v, load)
        self.sync_colors(color_v, load)
        self.sync_paths(path_v, load)

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
