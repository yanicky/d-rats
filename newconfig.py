#!/usr/bin/python

import gtk
import gobject
import ConfigParser

import utils
import miscwidgets
import platform

BAUD_RATES = ["1200", "2400", "4800", "9600", "19200", "38400", "115200"]

if __name__ == "__main__":
    import gettext
    gettext.install("D-RATS")

def color_string(color):
    try:
        return color.to_string()
    except:
        return "#%04x%04x%04x" % (color.red, color.green, color.blue)

class DratsConfigWidget(gtk.VBox):
    def __init__(self, config, sec, name):
        gtk.VBox.__init__(self, False, 2)

        self.config = config
        self.vsec = sec
        self.vname = name

        self.value = config.get(sec, name)

    def add_text(self, limit=0):
        def changed(entry):
            self.value = entry.get_text()

        w = gtk.Entry(limit)
        w.connect("changed", changed)
        w.set_text(self.value)
        w.set_size_request(50, -1)
        w.show()

        self.pack_start(w, 1, 1, 1)

    def add_combo(self, choices=[], editable=False, size=80):
        def changed(box):
            self.value = box.get_active_text()

        if self.value not in choices:
            choices.append(self.value)

        w = miscwidgets.make_choice(choices, editable, self.value)
        w.connect("changed", changed)
        w.set_size_request(size, -1)
        w.show()

        self.pack_start(w, 1, 1, 1)

    def add_bool(self, label=_("Enabled")):
        def toggled(but):
            self.value = but.get_active()
            
        w = gtk.CheckButton(label)
        w.connect("toggled", toggled)
        w.set_active(bool(self.value))
        w.show()

        self.pack_start(w, 1, 1, 1)

    def add_coords(self):
        def changed(entry):
            try:
                self.value = entry.value()
            except:
                print "Invalid Coords"
                self.value = 0

        w = miscwidgets.LatLonEntry()
        w.connect("changed", changed)
        w.set_text(self.value)
        w.show()

        self.pack_start(w, 1, 1, 1)

    def add_numeric(self, min, max, increment, digits=0):
        def value_changed(sb):
            self.value = sb.get_value()

        adj = gtk.Adjustment(float(self.value), min, max, increment, increment)
        w = gtk.SpinButton(adj, digits)
        w.connect("value-changed", value_changed)
        w.show()

        self.pack_start(w, 1, 1, 1)

    def add_color(self):
        def color_set(but):
            self.value = color_string(but.get_color())

        w = gtk.ColorButton()
        w.set_color(gtk.gdk.color_parse(self.value))
        w.connect("color-set", color_set)
        w.show()

        self.pack_start(w, 1, 1, 1)

    def add_font(self):
        def font_set(but):
            self.value = but.get_font_name()

        w = gtk.FontButton()
        w.set_font_name(self.value)
        w.connect("font-set", font_set)
        w.show()

        self.pack_start(w, 1, 1, 1)

    def add_path(self):
        def filename_changed(box):
            self.value = box.get_filename()

        w = miscwidgets.FilenameBox(find_dir=True)
        w.set_filename(self.value)
        w.connect("filename-changed", filename_changed)
        w.show()

        self.pack_start(w, 1, 1, 1)

class DratsPanel(gtk.VBox):
    LW = 100

    def __init__(self, config):
        gtk.VBox.__init__(self, False, 2)
        self.config = config
        self.vals = []

    def mv(self, title, *args):
        hbox = gtk.HBox(False, 2)

        lab = gtk.Label(title)
        lab.set_size_request(self.LW, -1)
        lab.show()
        hbox.pack_start(lab, 0, 0, 0)

        for i in args:
            i.show()
            if isinstance(i, DratsConfigWidget):
                hbox.pack_start(i, 1, 1, 1)
                self.vals.append(i)
            else:
                hbox.pack_start(i, 0, 0, 0)

        hbox.show()
        self.pack_start(hbox, 0, 0, 0)

class DratsPrefsPanel(DratsPanel):
    def __init__(self, config):
        DratsPanel.__init__(self, config)

        val = DratsConfigWidget(config, "user", "callsign")
        val.add_text()
        self.mv(_("Callsign"), val)

        val = DratsConfigWidget(config, "user", "name")
        val.add_text()
        self.mv(_("Name"), val)

        val1 = DratsConfigWidget(config, "prefs", "dosignon")
        val1.add_bool()
        val2 = DratsConfigWidget(config, "prefs", "signon")
        val2.add_text()
        self.mv(_("Sign-on Message"), val1, val2)

        val1 = DratsConfigWidget(config, "prefs", "dosignoff")
        val1.add_bool()
        val2 = DratsConfigWidget(config, "prefs", "signoff")
        val2.add_text()
        self.mv(_("Sign-off Message"), val1, val2)
        
        val = DratsConfigWidget(config, "user", "units")
        val.add_combo([_("Imperial"), _("Metric")])
        self.mv(_("Units"), val)

class DratsPathsPanel(DratsPanel):
    LW = 150

    def __init__(self, config):
        DratsPanel.__init__(self, config)

        val = DratsConfigWidget(config, "prefs", "download_dir")
        val.add_path()
        self.mv(_("Download Directory"), val)

        val = DratsConfigWidget(config, "settings", "mapdir")
        val.add_path()
        self.mv(_("Map Storage Directory"), val)

class DratsGPSPanel(DratsPanel):
    def __init__(self, config):
        DratsPanel.__init__(self, config)

        lat = DratsConfigWidget(config, "user", "latitude")
        lat.add_coords()
        self.mv(_("Latitude"), lat)
        
        lon = DratsConfigWidget(config, "user", "longitude")
        lon.add_coords()
        self.mv(_("Longitude"), lon)

        alt = DratsConfigWidget(config, "user", "altitude")
        alt.add_numeric(0, 29028, 1)
        self.mv(_("Altitude"), alt)

        ports = platform.get_platform().list_serial_ports()

        port = DratsConfigWidget(config, "settings", "gpsport")
        port.add_combo(ports, True, 120)
        rate = DratsConfigWidget(config, "settings", "gpsportspeed")
        rate.add_combo(BAUD_RATES, False)
        val = DratsConfigWidget(config, "settings", "gpsenabled")
        val.add_bool()
        self.mv(_("External GPS"), port, rate, val)

        val1 = DratsConfigWidget(config, "settings", "aprssymtab")
        val1.add_text(1)
        val2 = DratsConfigWidget(config, "settings", "aprssymbol")
        val2.add_text(1)
        self.mv(_("GPS-A Symbol"),
                gtk.Label(_("Table:")), val1,
                gtk.Label(_("Symbol:")), val2)
           
class DratsAppearancePanel(DratsPanel):
    def __init__(self, config):
        DratsPanel.__init__(self, config)

        val = DratsConfigWidget(config, "prefs", "noticere")
        val.add_text()
        self.mv(_("Notice RegEx"), val)

        val = DratsConfigWidget(config, "prefs", "ignorere")
        val.add_text()
        self.mv(_("Ignore RegEx"), val)

        colors = ["Incoming", "Outgoing", "Notice",
                  "Ignore", "Callsign", "Broken"]

        for i in colors:
            low = i.lower()
            print "Doing %scolor" % low
            val = DratsConfigWidget(config, "prefs", "%scolor" % low)
            val.add_color()
            self.mv("%s Color" % i, val)

class DratsChatPanel(DratsPanel):
    def __init__(self, config):
        DratsPanel.__init__(self, config)

        val = DratsConfigWidget(config, "prefs", "logenabled")
        val.add_bool()
        self.mv(_("Log chat traffic"), val)

        val = DratsConfigWidget(config, "prefs", "logresume")
        val.add_bool()
        self.mv(_("Load log tail"), val)

        val = DratsConfigWidget(config, "prefs", "font")
        val.add_font()
        self.mv(_("Chat font"), val)

        val = DratsConfigWidget(config, "prefs", "scrollback")
        val.add_numeric(0, 9999, 1)
        self.mv(_("Scrollback Lines"), val)

class DratsRadioPanel(DratsPanel):
    def __init__(self, config):
        DratsPanel.__init__(self, config)

        ports = platform.get_platform().list_serial_ports()

        port = DratsConfigWidget(config, "settings", "port")
        port.add_combo(ports, True, 120)
        rate = DratsConfigWidget(config, "settings", "rate")
        rate.add_combo(BAUD_RATES, False)
        self.mv(_("Serial Port"), port, rate)

        val = DratsConfigWidget(config, "settings", "compatmode")
        val.add_bool()
        self.mv(_("Receive raw text"), val)

        val = DratsConfigWidget(config, "settings", "sniff_packets")
        val.add_bool()
        self.mv(_("Sniff packets"), val)

class DratsTransfersPanel(DratsPanel):
    def __init__(self, config):
        DratsPanel.__init__(self, config)

        val = DratsConfigWidget(config, "settings", "ddt_block_size")
        val.add_numeric(128, 4096, 128)
        self.mv(_("Block size"), val)

        val = DratsConfigWidget(config, "settings", "ddt_block_outlimit")
        val.add_numeric(1, 32, 1)
        self.mv(_("Pipeline blocks"), val)

        val = DratsConfigWidget(config, "settings", "pipelinexfers")
        val.add_bool()
        self.mv(_("Pipeline transfers"), val)

class DratsTuningPanel(DratsPanel):
    LW = 200

    def __init__(self, config):
        DratsPanel.__init__(self, config)

        val = DratsConfigWidget(config, "settings", "warmup_length")
        val.add_numeric(0, 64, 8)
        self.mv(_("Warmup Length"), val)

        val = DratsConfigWidget(config, "settings", "warmup_timeout")
        val.add_numeric(0, 16, 1)
        self.mv(_("Warmup timeout"), val)

        val = DratsConfigWidget(config, "settings", "force_delay")
        val.add_numeric(-32, 32, 1)
        self.mv(_("Force transmission delay"), val)

class DratsConfigUI(gtk.Dialog):

    def mouse_event(self, view, event):
        x, y = event.get_coords()
        path = view.get_path_at_pos(int(x), int(y))
        if path:
            view.set_cursor_on_cell(path[0])

        try:
            (store, iter) = view.get_selection().get_selected()
            selected, = store.get(iter, 0)
        except Exception, e:
            print "Unable to find selected: %s" % e
            return None

        print "Selected: %s" % selected
        for v in self.panels.values():
            v.hide()
        self.panels[selected].show()
        
    def build_ui(self):
        hbox = gtk.HBox(False, 2)

        self.__store = gtk.TreeStore(gobject.TYPE_STRING, gobject.TYPE_STRING)
        self.__tree = gtk.TreeView(self.__store)

        hbox.pack_start(self.__tree, 0, 0, 0)
        self.__tree.set_size_request(150, -1)
        self.__tree.set_headers_visible(False)
        rend = gtk.CellRendererText()
        col = gtk.TreeViewColumn(None, rend, text=1)
        self.__tree.append_column(col)
        self.__tree.show()
        self.__tree.connect("button_press_event", self.mouse_event)

        def add_panel(c, s, l, par):
            p = c(self.config)
            self.panels[s] = p
            hbox.pack_start(p, 1, 1, 1)
            return self.__store.append(par, row=(s, l))
            
        prefs = add_panel(DratsPrefsPanel, "prefs", _("Preferences"), None)
        add_panel(DratsPathsPanel, "paths", _("Paths"), prefs)
        add_panel(DratsGPSPanel, "gps", _("GPS"), prefs)
        add_panel(DratsAppearancePanel, "appearance", _("Appearance"), prefs)
        add_panel(DratsChatPanel, "chat", _("Chat"), prefs)
        radio = add_panel(DratsRadioPanel, "radio", _("Radio"), None)
        add_panel(DratsTransfersPanel, "transfers", _("Transfers"), radio)
        add_panel(DratsTuningPanel, "tuning", _("Tuning"), radio)

        self.panels["prefs"].show()

        hbox.show()
        self.vbox.pack_start(hbox, 1, 1, 1)

        self.__tree.expand_all()

    def __init__(self, config):
        gtk.Dialog.__init__(self,
                            title=_("Config"),
                            buttons=(gtk.STOCK_SAVE, gtk.RESPONSE_OK,
                                     gtk.STOCK_CANCEL, gtk.RESPONSE_CANCEL))
        self.config = config
        self.panels = {}
        self.build_ui()
        self.set_default_size(320, 240)

class DratsConfig:
    def __init__(self, mainapp, safe=False):
        self.config = ConfigParser.ConfigParser()

        self.panels = {}

        self.ui = DratsConfigUI(self)

if __name__ == "__main__":
    cf = ConfigParser.ConfigParser()
    cf.read("/home/dan/.d-rats/d-rats.config")

    c = DratsConfigUI(cf)
    c.run()
    
