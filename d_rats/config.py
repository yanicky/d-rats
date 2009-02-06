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
import gobject
import ConfigParser
import os
import random

import utils
import miscwidgets
import inputdialog
import platform
import geocode_ui
import config_tips

BAUD_RATES = ["1200", "2400", "4800", "9600", "19200", "38400", "115200"]

_DEF_USER = {
    "name" : "A. Mateur",
    "callsign" : "W1AW",
    "latitude" : "41.6970",
    "longitude" : "-72.7312",
    "altitude" : "0",
    "units" : _("Imperial"),
}

_DEF_PREFS = {
    "download_dir" : platform.get_platform().default_dir(),
    "blinkmsg" : "False",
    "noticere" : "",
    "ignorere" : "",
    "signon" : _("Online (D-RATS)"),
    "signoff" : _("Going offline (D-RATS)"),
    "dosignon" : "True",
    "dosignoff" : "True",
    "incomingcolor" : "#00004444FFFF",
    "outgoingcolor": "#DDDD44441111",
    "noticecolor" : "#0000660011DD",
    "ignorecolor" : "#BB88BB88BB88",
    "callsigncolor" : "#FFDD99CC77CC",
    "brokencolor" : "#FFFFFFFF3333",
    "logenabled" : "True",
    "debuglog" : "False",
    "eolstrip" : "True",
    "font" : "Sans 12",
    "callsigns" : "%s" % str([(True , "US")]),
    "logresume" : "True",
    "scrollback" : "1024",
    "restore_stations" : "True",
    "useutc" : "False",
    "language" : "English",
    "allow_remote_forms" : "False",
    "allow_remote_files" : "False",
    "form_default_private" : "False",
}

_DEF_SETTINGS = {
    "port" : "",
    "rate" : "9600",
    "ddt_block_size" : "512",
    "ddt_block_outlimit" : "4",
    "encoding" : "yenc",
    "compression" : "True",
    "gpsport" : "",
    "gpsenabled" : "False",
    "gpsportspeed" : "4800",
    "aprssymtab" : "/",
    "aprssymbol" : ">",
    "compatmode" : "False",
    "inports" : "[]",
    "outports" : "[]",
    "sockflush" : "0.5",
    "pipelinexfers" : "True",
    "mapdir" : os.path.join(platform.get_platform().config_dir(), "maps"),
    "warmup_length" : "8",
    "warmup_timeout" : "3",
    "force_delay" : "0",
    "ping_info" : "",
    "smtp_server" : "",
    "smtp_replyto" : "",
    "smtp_tls" : "False",
    "smtp_username" : "",
    "smtp_password" : "",
    "smtp_port" : "25",
    "smtp_dogw" : "False",
    "sniff_packets" : "False",
}

_DEF_STATE = {
    "main_size_x" : "640",
    "main_size_y" : "400",
    "main_advanced" : "200",
    "filters" : "[]",
    "show_all_filter" : "False",
    "connected_inet" : "True",
    "qsts_enabled" : "True",
}

DEFAULTS = {
    "user" : _DEF_USER,
    "prefs" : _DEF_PREFS,
    "settings" : _DEF_SETTINGS,
    "state" : _DEF_STATE,
    "quick" : {},
    "tcp_in" : {},
    "tcp_out" : {},
    "incoming_email" : {},
}

if __name__ == "__main__":
    import gettext
    gettext.install("D-RATS")

def color_string(color):
    try:
        return color.to_string()
    except:
        return "#%04x%04x%04x" % (color.red, color.green, color.blue)

class AddressLookup(gtk.Button):
    def __init__(self, caption, latw, lonw):
        gtk.Button.__init__(self, caption)
        self.connect("clicked", self.clicked, latw, lonw)

    def clicked(self, me, latw, lonw):
        aa = geocode_ui.AddressAssistant()
        r = aa.run()
        if r == gtk.RESPONSE_OK:
            latw.latlon.set_text("%.5f" % aa.lat)
            lonw.latlon.set_text("%.5f" % aa.lon)

class DratsConfigWidget(gtk.VBox):
    def __init__(self, config, sec, name):
        gtk.VBox.__init__(self, False, 2)

        self.do_not_expand = False

        self.config = config
        self.vsec = sec
        self.vname = name

        self.config.widgets.append(self)

        if not config.has_section(sec):
            config.add_section(sec)


        if name is not None:
            if not config.has_option(sec, name):
                try:
                    self.value = DEFAULTS[sec][name]
                except KeyError:
                    print "DEFAULTS has no %s/%s" % (sec, name)
                    self.value = ""
            else:
                self.value = config.get(sec, name)
        else:
            self.value = None

    def save(self):
        #print "Saving %s/%s: %s" % (self.vsec, self.vname, self.value)
        self.config.set(self.vsec, self.vname, self.value)

    def set_value(self, value):
        pass

    def add_text(self, limit=0):
        def changed(entry):
            self.value = entry.get_text()

        w = gtk.Entry(limit)
        w.connect("changed", changed)
        w.set_text(self.value)
        w.set_size_request(50, -1)
        w.show()

        self.pack_start(w, 1, 1, 1)

    def add_upper_text(self, limit=0):
        def changed(entry):
            self.value = entry.get_text().upper()

        w = gtk.Entry(limit)
        w.connect("changed", changed)
        w.set_text(self.value)
        w.set_size_request(50, -1)
        w.show()

        self.pack_start(w, 1, 1, 1)

    def add_pass(self, limit=0):
        def changed(entry):
            self.value = entry.get_text()

        w = gtk.Entry(limit)
        w.connect("changed", changed)
        w.set_text(self.value)
        w.set_visibility(False)
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

    def add_bool(self, label=None):
        if label is None:
            label = _("Enabled")

        def toggled(but, confwidget):
            confwidget.value = str(but.get_active())
            
        w = gtk.CheckButton(label)
        w.connect("toggled", toggled, self)
        w.set_active(self.value == "True")
        w.show()

        self.do_not_expand = True

        self.pack_start(w, 1, 1, 1)

    def add_coords(self):
        def changed(entry, confwidget):
            try:
                confwidget.value = "%3.6f" % entry.value()
            except Exception, e:
                print "Invalid Coords: %s" % e
                confwidget.value = "0"

        w = miscwidgets.LatLonEntry()
        w.connect("changed", changed, self)
        print "Setting LatLon value: %s" % self.value
        w.set_text(self.value)
        print "LatLon text: %s" % w.get_text()
        w.show()

        # Dirty ugly hack!
        self.latlon = w

        self.pack_start(w, 1, 1, 1)

    def add_numeric(self, min, max, increment, digits=0):
        def value_changed(sb):
            self.value = "%f" % sb.get_value()

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

class DratsListConfigWidget(DratsConfigWidget):
    def __init__(self, config, section):
        try:
            DratsConfigWidget.__init__(self, config, section, None)
        except ConfigParser.NoOptionError:
            pass

    def convert_types(self, coltypes, values):
        newvals = []

        i = 0
        while i < len(values):
            gtype, label = coltypes[i]
            value = values[i]

            try:
                if gtype == gobject.TYPE_INT:
                    value = int(value)
                elif gtype == gobject.TYPE_FLOAT:
                    value = float(value)
                elif gtype == gobject.TYPE_BOOLEAN:
                    value = eval(value)
            except ValueError, e:
                print "Failed to convert %s for %s: %s" % (value, label, e)
                return []

            i += 1
            newvals.append(value)

        return newvals

    def add_list(self, cols, make_key=None):
        def item_set(lw, key):
            pass

        w = miscwidgets.KeyedListWidget(cols)

        options = self.config.options(self.vsec)
        for option in options:
            vals = self.config.get(self.vsec, option).split(",", len(cols))
            vals = self.convert_types(cols[1:], vals)
            if not vals:
                continue

            try:
                if make_key:
                    key = make_key(vals)
                else:
                    key = vals[0]
                w.set_item(key, *tuple(vals))
            except Exception, e:
                print "Failed to set item '%s': %s" % (str(vals), e)
        
        w.connect("item-set", item_set)
        w.show()

        self.pack_start(w, 1, 1, 1)

        self.listw = w

        return w

    def save(self):
        for opt in self.config.options(self.vsec):
            self.config.remove_option(self.vsec, opt)

        count = 0

        for key in self.listw.get_keys():
            vals = self.listw.get_item(key)
            vals = [str(x) for x in vals]
            value = ",".join(vals[1:])
            label = "%s_%i" % (self.vsec, count)
            print "Setting %s: %s" % (label, value)
            self.config.set(self.vsec, label, value)
            count += 1

class DratsPanel(gtk.Table):
    INITIAL_ROWS = 13
    INITIAL_COLS = 2

    def __init__(self, config):
        gtk.Table.__init__(self, self.INITIAL_ROWS, self.INITIAL_COLS)
        self.config = config
        self.vals = []

        self.row = 0
        self.rows = self.INITIAL_ROWS

    def mv(self, title, *args):
        if self.row+1 == self.rows:
            self.rows += 1
            print "Resizing box to %i" % self.rows
            self.resize(self.rows, 2)

        hbox = gtk.HBox(False, 2)

        lab = gtk.Label(title)
        lab.show()
        self.attach(lab, 0, 1, self.row, self.row+1, gtk.SHRINK, gtk.SHRINK, 5)

        for i in args:
            i.show()
            if isinstance(i, DratsConfigWidget):
                if i.do_not_expand:
                    hbox.pack_start(i, 0, 0, 0)
                else:
                    hbox.pack_start(i, 1, 1, 0)
                self.vals.append(i)
            else:
                hbox.pack_start(i, 0, 0, 0)

        hbox.show()
        self.attach(hbox, 1, 2, self.row, self.row+1, yoptions=gtk.SHRINK)

        self.row += 1

class DratsPrefsPanel(DratsPanel):
    def __init__(self, config):
        DratsPanel.__init__(self, config)

        val = DratsConfigWidget(config, "user", "callsign")
        val.add_upper_text(8)
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

        val = DratsConfigWidget(config, "prefs", "useutc")
        val.add_bool()
        self.mv(_("Show time in UTC"), val)

        val = DratsConfigWidget(config, "settings", "ping_info")
        val.add_text()
        self.mv(_("Ping reply"), val)

        val = DratsConfigWidget(config, "prefs", "language")
        val.add_combo(["English", "Italiano"])
        self.mv(_("Language"), val)

        val = DratsConfigWidget(config, "prefs", "form_default_private")
        val.add_bool()
        self.mv(_("Private default"), val)

class DratsPathsPanel(DratsPanel):
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

        geo = AddressLookup("Lookup", lat, lon)
        self.mv(_("Lookup by address"), geo)

        alt = DratsConfigWidget(config, "user", "altitude")
        alt.add_numeric(0, 29028, 1)
        self.mv(_("Altitude"), alt)

        ports = platform.get_platform().list_serial_ports()

        port = DratsConfigWidget(config, "settings", "gpsport")
        port.add_combo(ports, True, 120)
        rate = DratsConfigWidget(config, "settings", "gpsportspeed")
        rate.add_combo(BAUD_RATES, False)
        self.mv(_("External GPS"), port, rate)

        val = DratsConfigWidget(config, "settings", "gpsenabled")
        val.add_bool()
        self.mv(_("Use External GPS"), val)

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

        val = DratsConfigWidget(config, "prefs", "allow_remote_forms")
        val.add_bool()
        self.mv(_("Remote form transfers"), val)

        val = DratsConfigWidget(config, "prefs", "allow_remote_files")
        val.add_bool()
        self.mv(_("Remote file transfers"), val)

class DratsTuningPanel(DratsPanel):
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

class DratsNetworkPanel(DratsPanel):
    pass

class DratsTCPPanel(DratsPanel):
    INITIAL_ROWS = 2

    def mv(self, title, *widgets):
        self.attach(widgets[0], 0, 2, 0, 1)
        widgets[0].show()

        if len(widgets) > 1:
            box = gtk.HBox(True, 2)

            for i in widgets[1:]:
                box.pack_start(i, 0, 0, 0)
                i.show()

            box.show()
            self.attach(box, 0, 2, 1, 2, yoptions=gtk.SHRINK)

    def but_rem(self, button, lw):
        lw.del_item(lw.get_selected())

    def prompt_for(self, fields):
        d = inputdialog.FieldDialog()
        for n, t in fields:
            d.add_field(n, gtk.Entry())

        ret = {}

        done = False
        while not done and d.run() == gtk.RESPONSE_OK:
            done = True
            for n, t in fields:
                try:
                    s = d.get_field(n).get_text()
                    if not s:
                        raise ValueError("empty")
                    ret[n] = t(s)
                except ValueError, e:
                    ed = gtk.MessageDialog(buttons=gtk.BUTTONS_OK)
                    ed.set_property("text",
                                    _("Invalid value for") + " %s: %s" % (n, e))
                    ed.run()
                    ed.destroy()
                    done = False
                    break

        d.destroy()

        if done:
            return ret
        else:
            return None                    

class DratsTCPOutgoingPanel(DratsTCPPanel):
    def but_add(self, button, lw):
        values = self.prompt_for([(_("Local Port"), int),
                                  (_("Remote Port"), int),
                                  (_("Station"), str)])
        if values is None:
            return

        lw.set_item(str(values[_("Local Port")]),
                    values[_("Local Port")],
                    values[_("Remote Port")],
                    values[_("Station")].upper())

    def __init__(self, config):
        DratsTCPPanel.__init__(self, config)

        outcols = [(gobject.TYPE_STRING, "ID"),
                   (gobject.TYPE_INT, _("Local")),
                   (gobject.TYPE_INT, _("Remote")),
                   (gobject.TYPE_STRING, _("Station"))]

        val = DratsListConfigWidget(config, "tcp_out")
        lw = val.add_list(outcols)
        add = gtk.Button(_("Add"), gtk.STOCK_ADD)
        add.connect("clicked", self.but_add, lw)
        rem = gtk.Button(_("Remove"), gtk.STOCK_DELETE)
        rem.connect("clicked", self.but_rem, lw)
        self.mv(_("Outgoing"), val, add, rem)

class DratsTCPIncomingPanel(DratsTCPPanel):
    def but_add(self, button, lw):
        values = self.prompt_for([(_("Port"), int),
                                  (_("Host"), str)])
        if values is None:
            return

        lw.set_item(str(values[_("Port")]),
                    values[_("Port")],
                    values[_("Host")].upper())

    def __init__(self, config):
        DratsTCPPanel.__init__(self, config)

        incols = [(gobject.TYPE_STRING, "ID"),
                  (gobject.TYPE_INT, _("Port")),
                  (gobject.TYPE_STRING, _("Host"))]

        val = DratsListConfigWidget(config, "tcp_in")
        lw = val.add_list(incols)
        add = gtk.Button(_("Add"), gtk.STOCK_ADD)
        add.connect("clicked", self.but_add, lw)
        rem = gtk.Button(_("Remove"), gtk.STOCK_DELETE)
        rem.connect("clicked", self.but_rem, lw)
        self.mv(_("Incoming"), val, add, rem)

class DratsOutEmailPanel(DratsPanel):
    def __init__(self, config):
        DratsPanel.__init__(self, config)

        val = DratsConfigWidget(config, "settings", "smtp_server")
        val.add_text()
        self.mv(_("SMTP Server"), val)

        port = DratsConfigWidget(config, "settings", "smtp_port")
        port.add_numeric(1, 65536, 1)
        mode = DratsConfigWidget(config, "settings", "smtp_tls")
        mode.add_bool("TLS")
        self.mv(_("Port and Mode"), port, mode)

        val = DratsConfigWidget(config, "settings", "smtp_replyto")
        val.add_text()
        self.mv(_("Source Address"), val)
        
        val = DratsConfigWidget(config, "settings", "smtp_username")
        val.add_text()
        self.mv(_("SMTP Username"), val)

        val = DratsConfigWidget(config, "settings", "smtp_password")
        val.add_pass()
        self.mv(_("SMTP Password"), val)

        val = DratsConfigWidget(config, "settings", "smtp_dogw")
        val.add_bool()
        self.mv(_("Gateway"), val)

class DratsInEmailPanel(DratsPanel):
    INITIAL_ROWS = 2

    def mv(self, title, *widgets):
        self.attach(widgets[0], 0, 2, 0, 1)
        widgets[0].show()

        if len(widgets) > 1:
            box = gtk.HBox(True, 2)

            for i in widgets[1:]:
                box.pack_start(i, 0, 0, 0)
                i.show()

            box.show()
            self.attach(box, 0, 2, 1, 2, yoptions=gtk.SHRINK)

    def but_rem(self, button, lw):
        lw.del_item(lw.get_selected())

    def prompt_for_acct(self, fields):
        dlg = inputdialog.FieldDialog()
        for n, t, d in fields:
            if n in self.choices.keys():
                w = miscwidgets.make_choice(self.choices[n], False, d)
            elif t == bool:
                w = gtk.CheckButton(_("Enabled"))
                w.set_active(d)
            else:
                w = gtk.Entry()
                w.set_text(str(d))
            dlg.add_field(n, w)

        ret = {}

        done = False
        while not done and dlg.run() == gtk.RESPONSE_OK:
            done = True
            for n, t, d in fields:
                try:
                    if n in self.choices.keys():
                        v = dlg.get_field(n).get_active_text()
                    elif t == bool:
                        v = dlg.get_field(n).get_active()
                    else:
                        v = dlg.get_field(n).get_text()
                        if not v:
                            raise ValueError("empty")
                    ret[n] = t(v)
                except ValueError, e:
                    ed = gtk.MessageDialog(buttons=gtk.BUTTONS_OK)
                    ed.set_property("text",
                                    _("Invalid value for") + " %s: %s" % (n, e))
                    ed.run()
                    ed.destroy()
                    done = False
                    break

        dlg.destroy()
        if done:
            return ret
        else:
            return None

    def but_add(self, button, lw):
        fields = [(_("Server"), str, ""),
                  (_("Username"), str, ""),
                  (_("Password"), str, ""),
                  (_("Poll Interval"), int, 5),
                  (_("Use SSL"), bool, False),
                  (_("Port"), int, 110),
                  (_("Action"), str, "Form"),
                  ]
        ret = self.prompt_for_acct(fields)
        if ret:
            id ="%s@%s" % (ret[_("Server")], ret[_("Username")])
            lw.set_item(id,
                        ret[_("Server")],
                        ret[_("Username")],
                        ret[_("Password")],
                        ret[_("Poll Interval")],
                        ret[_("Use SSL")],
                        ret[_("Port")],
                        ret[_("Action")])

    def but_edit(self, button, lw):
        vals = lw.get_item(lw.get_selected())
        fields = [(_("Server"), str, vals[1]),
                  (_("Username"), str, vals[2]),
                  (_("Password"), str, vals[3]),
                  (_("Poll Interval"), int, vals[4]),
                  (_("Use SSL"), bool, vals[5]),
                  (_("Port"), int, vals[6]),
                  (_("Action"), str, vals[7]),
                  ]
        id ="%s@%s" % (vals[1], vals[2])
        ret = self.prompt_for_acct(fields)
        if ret:
            lw.del_item(id)
            id ="%s@%s" % (ret[_("Server")], ret[_("Username")])
            lw.set_item(id,
                        ret[_("Server")],
                        ret[_("Username")],
                        ret[_("Password")],
                        ret[_("Poll Interval")],
                        ret[_("Use SSL")],
                        ret[_("Port")],
                        ret[_("Action")])

    def convert_018_values(self, config, section):
        options = config.options(section)
        for opt in options:
            val = config.get(section, opt)
            if len(val.split(",")) != 7:
                val += ",Form"
                config.set(section, opt, val)
                print "Converted %s/%s" % (section, opt)

    def __init__(self, config):
        DratsPanel.__init__(self, config)

        cols = [(gobject.TYPE_STRING, "ID"),
                (gobject.TYPE_STRING, _("Server")),
                (gobject.TYPE_STRING, _("Username")),
                (gobject.TYPE_STRING, _("Password")),
                (gobject.TYPE_INT, _("Poll Interval")),
                (gobject.TYPE_BOOLEAN, _("Use SSL")),
                (gobject.TYPE_INT, _("Port")),
                (gobject.TYPE_STRING, _("Action")),
                ]

        self.choices = {
            _("Action") : [_("Form"), _("Chat")],
            }

        # Remove after 0.1.9
        self.convert_018_values(config, "incoming_email")

        val = DratsListConfigWidget(config, "incoming_email")

        def make_key(vals):
            return "%s@%s" % (vals[0], vals[1])

        lw = val.add_list(cols, make_key)
        add = gtk.Button(_("Add"), gtk.STOCK_ADD)
        add.connect("clicked", self.but_add, lw)
        edit = gtk.Button(_("Edit"), gtk.STOCK_EDIT)
        edit.connect("clicked", self.but_edit, lw)
        rem = gtk.Button(_("Remove"), gtk.STOCK_DELETE)
        rem.connect("clicked", self.but_rem, lw)
        self.mv(_("Incoming Accounts"), val, add, edit, rem)

class DratsEmailAccessPanel(DratsPanel):
    INITIAL_ROWS = 2

    def mv(self, title, *widgets):
        self.attach(widgets[0], 0, 2, 0, 1)
        widgets[0].show()

        if len(widgets) > 1:
            box = gtk.HBox(True, 2)

            for i in widgets[1:]:
                box.pack_start(i, 0, 0, 0)
                i.show()

            box.show()
            self.attach(box, 0, 2, 1, 2, yoptions=gtk.SHRINK)

    def but_rem(self, button, lw):
        lw.del_item(lw.get_selected())

    def prompt_for_entry(self, fields):
        dlg = inputdialog.FieldDialog()
        for n, t, d in fields:
            if n in self.choices.keys():
                w = miscwidgets.make_choice(self.choices[n], False, d)
            else:
                w = gtk.Entry()
                w.set_text(str(d))
            dlg.add_field(n, w)

        ret = {}

        done = False
        while not done and dlg.run() == gtk.RESPONSE_OK:
            done = True
            for n, t, d in fields:
                try:
                    if n in self.choices.keys():
                        v = dlg.get_field(n).get_active_text()
                    else:
                        v = dlg.get_field(n).get_text()

                    if n == _("Callsign"):
                        if not v:
                            raise ValueError("empty")
                        else:
                            v = v.upper()
                    ret[n] = t(v)
                except ValueError, e:
                    ed = gtk.MessageDialog(buttons=gtk.BUTTONS_OK)
                    ed.set_property("text",
                                    _("Invalid value for") + "%s: %s" % (n, e))
                    ed.run()
                    ed.destroy()
                    done = False
                    break

        dlg.destroy()
        if done:
            return ret
        else:
            return None

    def but_add(self, button, lw):
        fields = [(_("Callsign"), str, ""),
                  (_("Access"), str, _("Both")),
                  (_("Email Filter"), str, "")]
        ret = self.prompt_for_entry(fields)
        if ret:
            id = "%s/%i" % (ret[_("Callsign")],
                            random.randint(1, 1000))
            lw.set_item(id,
                        ret[_("Callsign")],
                        ret[_("Access")],
                        ret[_("Email Filter")])

    def but_edit(self, button, lw):
        vals = lw.get_item(lw.get_selected())
        fields = [(_("Callsign"), str, vals[1]),
                  (_("Access"), str, vals[2]),
                  (_("Email Filter"), str, vals[3])]
        id = vals[0]
        ret = self.prompt_for_entry(fields)
        if ret:
            lw.del_item(id)
            lw.set_item(id,
                        ret[_("Callsign")],
                        ret[_("Access")],
                        ret[_("Email Filter")])

    def __init__(self, config):
        DratsPanel.__init__(self, config)

        cols = [(gobject.TYPE_STRING, "ID"),
                (gobject.TYPE_STRING, _("Callsign")),
                (gobject.TYPE_STRING, _("Access")),
                (gobject.TYPE_STRING, _("Email Filter"))]

        self.choices = {
            _("Access") : [_("None"), _("Both"), _("Incoming"), _("Outgoing")],
            }

        val = DratsListConfigWidget(config, "email_access")

        def make_key(vals):
            return "%s/%i" % (vals[0], random.randint(0, 1000))

        lw = val.add_list(cols, make_key)
        add = gtk.Button(_("Add"), gtk.STOCK_ADD)
        add.connect("clicked", self.but_add, lw)
        edit = gtk.Button(_("Edit"), gtk.STOCK_EDIT)
        edit.connect("clicked", self.but_edit, lw)
        rem = gtk.Button(_("Remove"), gtk.STOCK_DELETE)
        rem.connect("clicked", self.but_rem, lw)
        self.mv(_("Email Access"), val, add, edit, rem)

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
            p.show()
            sw = gtk.ScrolledWindow()
            sw.set_policy(gtk.POLICY_AUTOMATIC, gtk.POLICY_AUTOMATIC)
            sw.add_with_viewport(p)
            hbox.pack_start(sw, 1, 1, 1)

            self.panels[s] = sw

            for val in p.vals:
                self.tips.set_tip(val,
                                  config_tips.get_tip(val.vsec, val.vname))

            return self.__store.append(par, row=(s, l))
            
        prefs = add_panel(DratsPrefsPanel, "prefs", _("Preferences"), None)
        add_panel(DratsPathsPanel, "paths", _("Paths"), prefs)
        add_panel(DratsGPSPanel, "gps", _("GPS"), prefs)
        add_panel(DratsAppearancePanel, "appearance", _("Appearance"), prefs)
        add_panel(DratsChatPanel, "chat", _("Chat"), prefs)

        radio = add_panel(DratsRadioPanel, "radio", _("Radio"), None)
        add_panel(DratsTransfersPanel, "transfers", _("Transfers"), radio)
        add_panel(DratsTuningPanel, "tuning", _("Tuning"), radio)

        network = add_panel(DratsNetworkPanel, "network", _("Network"), None)
        add_panel(DratsTCPIncomingPanel, "tcpin", _("TCP Gateway"), network)
        add_panel(DratsTCPOutgoingPanel, "tcpout", _("TCP Forwarding"), network)
        add_panel(DratsOutEmailPanel, "smtp", _("Outgoing Email"), network)
        add_panel(DratsInEmailPanel, "email", _("Incoming Email"), network)
        add_panel(DratsEmailAccessPanel, "email_ac", _("Email Access"), network)

        self.panels["prefs"].show()

        hbox.show()
        self.vbox.pack_start(hbox, 1, 1, 1)

        self.__tree.expand_all()

    def save(self):
        for widget in self.config.widgets:
            widget.save()

    def __init__(self, config, parent=None):
        gtk.Dialog.__init__(self,
                            title=_("Config"),
                            buttons=(gtk.STOCK_SAVE, gtk.RESPONSE_OK,
                                     gtk.STOCK_CANCEL, gtk.RESPONSE_CANCEL),
                            parent=parent)
        self.config = config
        self.panels = {}
        self.tips = gtk.Tooltips()
        self.build_ui()
        self.set_default_size(600, 400)

class DratsConfig(ConfigParser.ConfigParser):
    def set_defaults(self):
        for sec, opts in DEFAULTS.items():
            if not self.has_section(sec):
                self.add_section(sec)

            for opt, value in opts.items():
                if not self.has_option(sec, opt):
                    self.set(sec, opt, value)

    def __init__(self, mainapp, safe=False):
        ConfigParser.ConfigParser.__init__(self)

        self.platform = platform.get_platform()        
        self.filename = self.platform.config_file("d-rats.config")
        print "FILE: %s" % self.filename
        self.read(self.filename)
        self.widgets = []

        self.set_defaults()

    def show(self, parent=None):
        ui = DratsConfigUI(self, parent)
        r = ui.run()
        if r == gtk.RESPONSE_OK:
            ui.save()
            self.save()
        ui.destroy()

        return r == gtk.RESPONSE_OK

    def save(self):
        f = file(self.filename, "w")
        self.write(f)
        f.close()

    def getboolean(self, sec, key):
        try:
            return ConfigParser.ConfigParser.getboolean(self, sec, key)
        except:
            print "Failed to get boolean: %s/%s" % (sec, key)
            return False

    def getint(self, sec, key):
        return int(float(ConfigParser.ConfigParser.get(self, sec, key)))

    def form_source_dir(self):
        d = os.path.join(self.platform.config_dir(), "Form_Templates")
        if not os.path.isdir(d):
            os.mkdir(d)

        return d

    def form_store_dir(self):
        d = os.path.join(self.platform.config_dir(), "Saved_Forms")
        if not os.path.isdir(d):
            os.mkdir(d)

        return d

if __name__ == "__main__":
    fn = "/home/dan/.d-rats/d-rats.config"

    cf = ConfigParser.ConfigParser()
    cf.read(fn)
    cf.widgets = []

    c = DratsConfigUI(cf)
    if c.run() == gtk.RESPONSE_OK:
        c.save(fn)
