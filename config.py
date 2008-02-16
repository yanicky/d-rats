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

import gtk
import pygtk

import ConfigParser

import xmodem
import ddt

def color_string(color):
    try:
        return color.to_string()
    except:
        return "#%04x%04x%04x" % (color.red, color.green, color.blue)

def make_choice(options, editable=True, default=None):
    if editable:
        sel = gtk.combo_box_entry_new_text()
    else:
        sel = gtk.combo_box_new_text()

    for o in options:
        sel.append_text(o)

    if default:
        try:
            idx = options.index(default)
            sel.set_active(idx)
        except:
            pass

    return sel

class AppConfig:
    def init_config(self):
        def mset(section, option, value):
            if not self.config.has_section(section):
                self.config.add_section(section)

            if option and not self.config.has_option(section, option):
                self.config.set(section, option, value)

        mset("user", "name", "A. Mateur")
        mset("user", "callsign", "W1AW")

        mset("prefs", "autoreceive", "False")
        mset("prefs", "download_dir", self.default_directory())
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
        mset("prefs", "logenabled", "False")
        mset("prefs", "debuglog", "False")
        mset("prefs", "eolstrip", "True")
        mset("prefs", "font", "Sans 12")

        mset("settings", "port", self.default_port)
        mset("settings", "rate", "9600")
        mset("settings", "xfer", "DDT")
        mset("settings", "write_chunk", "0")
        mset("settings", "chunk_delay", "1.5")
        mset("settings", "ddt_block_size", "1024")
        mset("settings", "swflow", "False")

        mset("quick", None, None)

        mset("state", "main_size_x", "640")
        mset("state", "main_size_y", "400")
        mset("state", "main_advanced", "0")

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
                "logenabled" : "Enable chat logging",
                "debuglog" : "Enable debug logging",
                "eolstrip" : "End-of-line stripping",
                "font" : "Chat font",
                "write_chunk" : "<span foreground='red'>Write chunk size (bytes)</span>",
                "chunk_delay" : "<span foreground='red'>Chunk delay (sec)</span>",
                "ddt_block_size" : "Outgoing block size (KB)",
                "swflow" : "Software Flow Control",
                }

    id2tip = {"write_chunk" : "Stage DDT blocks into small chunks of this many bytes",
              "chunk_delay" : "Delay this many seconds between chunks",
              "ddt_block_size" : "Size (in KB) of data blocks to send with DDT",
              "debuglog" : "Requires D-RATS restart to take effect",
              "swflow" : "Try this if using a USB-to-serial adapter",
              }

    xfers = {"DDT" : ddt.DDTTransfer}

    def xfer(self):
        name = self.config.get("settings", "xfer")

        return self.xfers[name]

    def default_filename(self):
        return "drats.config"

    def default_directory(self):
        return os.path.abspath(".")

    def form_source_dir(self):
        d = os.path.join(self.config.get("prefs", "download_dir"),
                         "Form_Templates")
        if not os.path.isdir(d):
            os.mkdir(d)

        return d

    def form_store_dir(self):
        d = os.path.join(self.config.get("prefs", "download_dir"),
                         "Saved_Forms")
        if not os.path.isdir(d):
            os.mkdir(d)

        return d

    def make_sb(self, id, child):
        hbox = gtk.HBox(True, 0)

        label = gtk.Label()
        label.set_markup(self.id2label[id])
        
        hbox.pack_start(label, 0, 0, 0)
        hbox.pack_end(child, 1, 1, 0)

        self.fields[id] = child

        label.show()
        child.show()
        hbox.show()

        if self.id2tip.has_key(id):
            self.tips.set_tip(label, self.id2tip[id])
            self.tips.set_tip(child, self.id2tip[id])
        
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

    def make_spin(self, incr, min, max):
        if (incr - int(incr)) != 0:
            digits = 1
        else:
            digits = 0
        a = gtk.Adjustment(0, min, max, incr, 0, 0)
        b = gtk.SpinButton(adjustment=a, digits=digits)
        return b

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

    def build_user(self):
        vbox = gtk.VBox(False, 2)

        vbox.pack_start(self.make_sb("callsign", gtk.Entry()), 0,0,0)
        vbox.pack_start(self.make_sb("name", gtk.Entry()), 0,0,0)
        vbox.pack_start(self.make_sb("dosignon", self.make_bool()), 0,0,0)
        vbox.pack_start(self.make_sb("signon", gtk.Entry()), 0,0,0)

        vbox.pack_start(self.make_sb("dosignoff", self.make_bool()), 0,0,0)
        vbox.pack_start(self.make_sb("signoff", gtk.Entry()), 0,0,0)
        vbox.pack_start(self.make_sb("logenabled",
                                     self.make_bool()), 0,0,0)
        vbox.pack_start(self.make_sb("debuglog",
                                     self.make_bool()), 0,0,0)

        vbox.show()
        return vbox

    def build_appearance(self):
        vbox = gtk.VBox(False, 2)

        vbox.pack_start(self.make_sb("noticere", gtk.Entry()), 0,0,0)
        vbox.pack_start(self.make_sb("ignorere", gtk.Entry()), 0,0,0)

        vbox.pack_start(self.make_sb("incomingcolor",
                                     gtk.ColorButton()), 0,0,0)
        vbox.pack_start(self.make_sb("outgoingcolor",
                                     gtk.ColorButton()), 0,0,0)
        vbox.pack_start(self.make_sb("noticecolor",
                                     gtk.ColorButton()), 0,0,0)
        vbox.pack_start(self.make_sb("ignorecolor",
                                     gtk.ColorButton()), 0,0,0)

        vbox.pack_start(self.make_sb("eolstrip",
                                     self.make_bool()), 0,0,0)

        vbox.pack_start(self.make_sb("font",
                                     gtk.FontButton()), 0,0,0)
        
        vbox.show()
        return vbox

    def build_data(self):
        vbox = gtk.VBox(False, 2)

        baud_rates = ["300", "1200", "4800", "9600",
                      "19200", "38400", "115200"]

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
        fcb = gtk.FileChooserButton(dlg)
        vbox.pack_start(self.make_sb("download_dir", fcb,
                                     ), 0,0,0)
        vbox.pack_start(self.make_sb("xfer",
                                     make_choice(self.xfers.keys(), False)), 0,0,0)
        vbox.pack_start(self.make_sb("swflow", self.make_bool()), 0,0,0)

        vbox.show()
        return vbox

    def build_ddt(self):
        vbox = gtk.VBox(False, 2)

        block_sizes = [str(pow(2,x)) for x in range(6, 13)]

        vbox.pack_start(self.make_sb("ddt_block_size",
                                     make_choice(block_sizes, False)), 0,0,0)
        vbox.pack_start(self.make_sb("write_chunk",
                                     self.make_spin(32, 0, 512)), 0,0,0)
        vbox.pack_start(self.make_sb("chunk_delay",
                                     self.make_spin(0.1, 0.1, 3.0)), 0,0,0)

        vbox.show()

        return vbox


    def build_gui(self):
        self.window = gtk.Window(gtk.WINDOW_TOPLEVEL)

        self.window.set_default_size(400, 500)
        self.window.set_title("Main Settings")

        self.window.connect("delete_event", self.delete)
        self.window.connect("destroy", self.destroy)

        nb = gtk.Notebook()

        nb.append_page(self.build_user(), gtk.Label("User"))
        nb.append_page(self.build_appearance(), gtk.Label("Appearance"))
        nb.append_page(self.build_data(), gtk.Label("Data"))
        nb.append_page(self.build_ddt(), gtk.Label("DDT"))

        nb.show()

        # Disable unsupported functions
        for i in ("autoreceive",):
            self.fields[i].set_sensitive(False)

        mainvbox = gtk.VBox(False, 5)
        mainvbox.pack_start(nb, 1,1,1)
        mainvbox.pack_start(self.make_buttons(), 0,0,0)
        mainvbox.show()
        
        self.window.add(mainvbox)

    def show(self):
        self.window.show()
        if self.safe:
            d = gtk.MessageDialog(buttons=gtk.BUTTONS_OK)
            d.set_property("text", "Safe Mode")
            d.set_property("secondary-text",
                           """
D-RATS has been started in safe mode, which means the configuration file has not been loaded until now.  Clicking the 'Save' button in the settings dialog will make those settings active and exit safe mode.""")
            d.run()
            d.destroy()
            self.load_config(self.default_filename())
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
                self.config.set(s, k, color_string(self.fields[k].get_color()))

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
                button.set_current_folder(d)
            else:
                d = button.get_current_folder()
                self.config.set(s, k, d)

    def sync_fonts(self, list, load):
        for s, k in list:
            fb = self.fields[k]

            if load:
                fb.set_font_name(self.config.get(s, k))
            else:
                self.config.set(s, k, fb.get_font_name())

    def sync_spins(self, list, load):
        for s, k in list:
            sb = self.fields[k]

            try:
                if load:
                    val = float(self.config.get(s, k))
                    sb.set_value(val)
                else:
                    self.config.set(s, k, str(sb.get_value()))
            except Exception, e:
                print "Failed to sync %s,%s: %s" % (s,k,e)

    def sync_gui(self, load=True):
        text_v = [("user", "callsign"),
                  ("user", "name"),
                  ("prefs", "noticere"),
                  ("prefs", "ignorere"),
                  ("prefs", "signon"),
                  ("prefs", "signoff")]

        bool_v = [("prefs", "autoreceive"),
                  ("prefs", "dosignon"),
                  ("prefs", "dosignoff"),
                  ("prefs", "eolstrip"),
                  ("prefs", "logenabled"),
                  ("prefs", "debuglog"),
                  ("settings", "swflow")]

        choicetext_v = [("settings", "port")]

        choice_v = [("settings", "rate"),
                    ("settings", "xfer"),
                    ("settings", "ddt_block_size")]

        color_v = [("prefs", "incomingcolor"),
                   ("prefs", "outgoingcolor"),
                   ("prefs", "noticecolor"),
                   ("prefs", "ignorecolor")]

        path_v = [("prefs", "download_dir")]

        font_v = [("prefs", "font")]

        spin_v = [("settings", "write_chunk"),
                  ("settings", "chunk_delay")]

        self.sync_texts(text_v, load)
        self.sync_booleans(bool_v, load)
        self.sync_choicetexts(choicetext_v, load)
        self.sync_choices(choice_v, load)
        self.sync_colors(color_v, load)
        self.sync_paths(path_v, load)
        self.sync_fonts(font_v, load)
        self.sync_spins(spin_v, load)

    def load_config(self, file):
        self.config.read(file)

    def __init__(self, mainapp, _file=None, safe=False):
        self.mainapp = mainapp
        self.safe = safe

        self.tips = gtk.Tooltips()

        if not _file:
            _file = self.default_filename()

        self.config = ConfigParser.ConfigParser()
        if not self.safe:
            self.load_config(_file)
        self.fields = {}

        self.init_config()

        self.build_gui()

    def save(self, _file=None):
        if not _file:
            _file = self.default_filename()

        f = file(_file, "w")
        self.config.write(f)
        f.close()

        self.safe = False

class UnixAppConfig(AppConfig):
    default_port = "/dev/ttyS0"

    def port_list(self):
        return ["/dev/ttyS0", "/dev/ttyS1",
                "/dev/ttyUSB0", "/dev/ttyUSB1"]

class Win32AppConfig(AppConfig):
    default_port = "COM1"

    def migrate_old_config(self, new):
        if os.path.isfile("c:\drats.config"):
            print "Migrating old config to %s" % new
            os.rename("c:\drats.config", new)

    def default_filename(self):
        base = os.path.join(os.getenv("APPDATA"), "D-RATS")
        config = os.path.join(base, "d-rats.config")
        if not os.path.isdir(base):
            print "Creating `%s'" % base
            os.mkdir(base)
            self.migrate_old_config(config)

        return config        

    def port_list(self):
        return ["COM1", "COM2", "COM3", "COM4"]

if __name__ == "__main__":
    g = UnixAppConfig(None)
    g.show()
    gtk.main()
