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
import ConfigParser
import glob
import shutil
import sys

import gtk
import pygtk
import gobject

import ddt
import miscwidgets
import platform
import callsigns
import inputdialog
import geocode_ui

from miscwidgets import make_choice

def color_string(color):
    try:
        return color.to_string()
    except:
        return "#%04x%04x%04x" % (color.red, color.green, color.blue)

class AppConfig:
    def init_config(self):
        def mset(section, option, value):
            if not self.config.has_section(section):
                self.config.add_section(section)

            if option and not self.config.has_option(section, option):
                self.config.set(section, option, value)

        mset("user", "name", "A. Mateur")
        mset("user", "callsign", "W1AW")
        mset("user", "latitude", "0.0")
        mset("user", "longitude", "0.0")
        mset("user", "altitude", "0")
        mset("user", "units", "Imperial")

        mset("prefs", "autoreceive", "False")
        mset("prefs", "download_dir", self.platform.default_dir())
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
        mset("prefs", "callsigncolor", "#FFDD99CC77CC")
        mset("prefs", "brokencolor", "#FFFFFFFF3333")
        mset("prefs", "logenabled", "True")
        mset("prefs", "debuglog", "False")
        mset("prefs", "eolstrip", "True")
        mset("prefs", "font", "Sans 12")
        mset("prefs", "callsigns", "%s" % str([(True, "US")]))
        mset("prefs", "logresume", "True")
        mset("prefs", "scrollback", "1024")
        mset("prefs", "restore_stations", "True")

        mset("settings", "port", self.default_port)
        mset("settings", "rate", "9600")
        mset("settings", "xfer", "DDT")
        mset("settings", "ddt_block_size", "512")
        mset("settings", "ddt_block_outlimit", "4")
        mset("settings", "encoding", "yenc")
        mset("settings", "compression", "True")
        mset("settings", "gpsport", "")
        mset("settings", "gpsenabled", "False")
        mset("settings", "aprssymtab", "/")
        mset("settings", "aprssymbol", ">")
        mset("settings", "compatmode", "False")
        mset("settings", "inports", "[]")
        mset("settings", "outports", "[]")
        mset("settings", "sockflush", "0.5")
        mset("settings", "pipelinexfers", "True")
        mset("settings", "mapdir",
             os.path.join(self.platform.config_dir(), "maps"))
        mset("settings", "warmup_length", "8")
        mset("settings", "warmup_timeout", "3")
        mset("settings", "force_delay", "0")
        mset("settings", "ping_info", "")
        mset("settings", "smtp_server", "")

        mset("quick", None, None)

        mset("state", "main_size_x", "640")
        mset("state", "main_size_y", "400")
        mset("state", "main_advanced", "200")
        mset("state", "filters", "[]")
        mset("state", "show_all_filter", False)

        if not os.path.isdir(self.get("prefs", "download_dir")):
            d = self.platform.default_dir()
            print "Resetting invalid download_dir to: %s" % d
            self.set("prefs", "download_dir", d)

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
                "callsigncolor" : "Color to highlight callsigns",
                "brokencolor" : "Color for raw data",
                "logenabled" : "Enable chat logging",
                "debuglog" : "Enable debug logging",
                "eolstrip" : "End-of-line stripping",
                "font" : "Chat font",
                "ddt_block_size" : "Outgoing block size (KB)",
                "ddt_block_outlimit" : "Pipeline blocks",
                "callsigns" : "Mark callsigns by these countries",
                "encoding" : "Type of ASCII-armoring to use",
                "compression" : "Compress blocks",
                "logresume" : "Load tail of previous log",
                "scrollback" : "Lines of scrollback to keep",
                "latitude" : "Current Latitude",
                "longitude" : "Current Longitude",
                "altitude" : "Current Altitude",
                "units" : "Units",
                "gpsport" : "External GPS serial port",
                "gpsenabled" : "Update position from external GPS",
                "aprssymtab" : "D/APRS Symbol Table ID",
                "aprssymbol" : "D/APRS Symbol ID",
                "compatmode" : "Receive raw text as chat data",
                "sockflush" : "Socket flush interval",
                "restore_stations" : "Restore callsign list",
                "pipelinexfers" : "Use pipelined transfers",
                "mapdir" : "Map storage location",
                "warmup_length" : "Warm-up length",
                "warmup_timeout" : "Warm-up timeout",
                "force_delay" : "Force delay between transmissions",
                "ping_info" : "Ping Reply",
                "smtp_server" : "SMTP Server",
                }

    id2tip = {"ddt_block_size" : "Size (in KB) of data blocks to send with DDT",
              "ddt_block_outlimit" : "Number of blocks to send per round",
              "debuglog" : "Requires D-RATS restart to take effect",
              "callsigns" : "Mark callsigns by these countries",
              "encoding" : "yenc is fastest, base64 is safest (currently)",
              "compression" : "Compress outgoing blocks",
              "logresume" : "Loads the last bit of the log for context at startup",
              "latitude" : "Current latitude (dd.dddd or dd hh mm)",
              "longitude" : "Current longitude (dd.dddd or dd hh mm)",
              "gpsport" : "Set this to the serial port of your external NMEA GPS",
              "gpsenabled" : "When enabled, update position from GPS data",
              "aprssymtab" : "Default is `/'",
              "aprssymbol" : "Default is `>' (Car)",
              "compatmode" : "Pass through raw text as chat data for use with D-RATS 0.1.x and D-CHAT users",
              "outports" : "TCP ports to forward to remote stations",
              "inports" : "TCP ports to forward for remote stations",
              "sockflush" : "Seconds before sending socket data over radio",
              "restore_stations" : "Restore callsign list from map list of `Stations'",
              "pipelinexfers" : "Increases throughput and resiliency (v0.2.4 and later only)",
              "brokencolor" : "Color text that does not pass checksum",
              "mapdir" : "Alternate location for cached map tiles",
              "warmup_length" : "Number of bytes to send before blocks",
              "warmup_timeout" : "Time between transmissions requiring warmup",
              "force_delay" : "Seconds to wait before starting a new transmission",
              "ping_info" : "Blank for OS info, A static string, !path for executable, or >path for contents of a file",
              "smtp_server" : "SMTP server for form-to-mail relay",
              }

    xfers = {"DDT" : ddt.DDTTransfer}

    def units_of(self, type):
        units = {
            "Imperial" : { "distance" : "miles",
                           "dist" : "mi",
                           "elevation" : "feet",
                           "elev" : "ft" },
            "Metric" : { "distance" : "kilometers",
                         "dist" : "km",
                         "elevation" : "meters",
                         "elev" : "m" }
            }

        return units[self.get("user", "units")][type]

    def xfer(self):
        try:
            name = self.config.get("settings", "xfer")
        except:
            name = "DDT"

        return self.xfers[name]

    def default_filename(self):
        return self.platform.config_file("d-rats.config")

    def copy_template_forms(self, dir):
        if os.path.isdir("forms"):
            files = glob.glob(os.path.join("forms", "*.x[ms]l"))
            for f in files:
                dst = os.path.join(dir, os.path.basename(f))
                print "Copying form template %s to %s" % (f, dst)
                shutil.copyfile(f, dst)

    def form_source_dir(self):
        d = os.path.join(self.platform.config_dir(), "Form_Templates")
        if not os.path.isdir(d):
            os.mkdir(d)
            try:
                self.copy_template_forms(d)
            except:
                raise

        return d

    def form_store_dir(self):
        d = os.path.join(self.platform.config_dir(), "Saved_Forms")
        if not os.path.isdir(d):
            os.mkdir(d)

        return d

    def get(self, sec, key):
        return self.config.get(sec, key)

    def set(self, sec, key, val):
        return self.config.set(sec, key, val)

    def getboolean(self, sec, key):
        try:
            return self.config.getboolean(sec, key)
        except:
            print "Failed to get boolean: %s:%s" % (sec, key)
            return False

    def getint(self, sec, key):
        return int(float(self.config.get(sec, key)))

    def options(self, *args):
        return self.config.options(*args)

    def make_setting(self, id, child):
        self.fields[id] = child
        if self.id2tip.has_key(id):
            self.tips.set_tip(child, self.id2tip[id])

    def make_sb(self, id, child):
        hbox = gtk.HBox(True, 0)

        label = gtk.Label()
        label.set_markup(self.id2label[id])
        
        hbox.pack_start(label, 0, 0, 0)
        hbox.pack_end(child, 1, 1, 0)

        label.show()
        child.show()
        hbox.show()

        self.make_setting(id, child)
        
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

    def make_spin(self, incr, min, max, digits=None):
        if not digits:
            if (incr - int(incr)) != 0:
                digits = 1
            else:
                digits = 0

        a = gtk.Adjustment(0, min, max, incr, 0, 0)
        b = gtk.SpinButton(adjustment=a, digits=digits)
        return b

    def destroy(self, widget, data=None):
        gtk.main_quit()
        return True

    def delete(self, widget, event, data=None):
        gtk.main_quit()
        return True

    def save_button(self, widget, data=None):
        self.sync_gui(load=False)
        self.save()
        self.mainapp.refresh_config()
        gtk.main_quit()

    def refresh_app(self):
        self.mainapp.refresh_config()

    def cancel_button(self, widget, data=None):
        self.sync_gui(load=True)
        gtk.main_quit()

    def address_button(self, widget):
        aa = geocode_ui.AddressAssistant()
        r = aa.run()
        if r == gtk.RESPONSE_OK:
            print "SETTING"
            self.fields["latitude"].set_text("%.5f" % aa.lat)
            self.fields["longitude"].set_text("%.5f" % aa.lon)

    def build_user(self):
        vbox = gtk.VBox(False, 2)

        vbox.pack_start(self.make_sb("callsign", gtk.Entry(8)), 0,0,0)
        vbox.pack_start(self.make_sb("name", gtk.Entry()), 0,0,0)
        vbox.pack_start(self.make_sb("dosignon", self.make_bool()), 0,0,0)
        vbox.pack_start(self.make_sb("signon", gtk.Entry()), 0,0,0)

        vbox.pack_start(self.make_sb("dosignoff", self.make_bool()), 0,0,0)
        vbox.pack_start(self.make_sb("signoff", gtk.Entry()), 0,0,0)
        vbox.pack_start(self.make_sb("logenabled",
                                     self.make_bool()), 0,0,0)
        vbox.pack_start(self.make_sb("debuglog",
                                     self.make_bool()), 0,0,0)
        vbox.pack_start(self.make_sb("logresume",
                                     self.make_bool()), 0,0,0)
        vbox.pack_start(self.make_sb("restore_stations",
                                     self.make_bool()), 0,0,0)

        vbox.pack_start(self.make_sb("latitude",
                                     miscwidgets.LatLonEntry()), 0,0,0)
        vbox.pack_start(self.make_sb("longitude",
                                     miscwidgets.LatLonEntry()), 0,0,0)

        lookupbtn = gtk.Button("Lookup by address")
        lookupbtn.connect("clicked", self.address_button)
        lookupbtn.show()
        vbox.pack_start(lookupbtn, 0, 0, 0)

        vbox.pack_start(self.make_sb("altitude",
                                     self.make_spin(1.0, 0.0, 29028.0, 0)),
                        0,0,0)                                     

        units = ["Imperial", "Metric"]

        vbox.pack_start(self.make_sb("units",
                                     make_choice(units, False)), 0,0,0)

        vbox.pack_start(self.make_sb("ping_info",
                                     gtk.Entry()), 0,0,0)
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
        vbox.pack_start(self.make_sb("callsigncolor",
                                     gtk.ColorButton()), 0,0,0)
        vbox.pack_start(self.make_sb("brokencolor",
                                     gtk.ColorButton()), 0,0,0)

        vbox.pack_start(self.make_sb("eolstrip",
                                     self.make_bool()), 0,0,0)

        vbox.pack_start(self.make_sb("font",
                                     gtk.FontButton()), 0,0,0)
        vbox.pack_start(self.make_sb("scrollback",
                                     self.make_spin(128, 0, 10000)), 0,0,0)

        vbox.show()
        return vbox

    def build_data(self):
        vbox = gtk.VBox(False, 2)

        baud_rates = ["300", "1200", "4800", "9600",
                      "19200", "38400", "115200"]

        vbox.pack_start(self.make_sb("port",
                                     make_choice([])), 0,0,0)
        vbox.pack_start(self.make_sb("rate",
                                     make_choice(baud_rates, False)), 0,0,0)

        vbox.pack_start(self.make_sb("autoreceive", self.make_bool()), 0,0,0)

        fb = miscwidgets.FilenameBox(find_dir=True)
        vbox.pack_start(self.make_sb("download_dir", fb), 0,0,0)

        fb = miscwidgets.FilenameBox(find_dir=True)
        vbox.pack_start(self.make_sb("mapdir", fb), 0,0,0)        

        vbox.pack_start(self.make_sb("ddt_block_size",
                                     self.make_spin(128, 128, 4096, 0)), 0,0,0)
        vbox.pack_start(self.make_sb("ddt_block_outlimit",
                                     self.make_spin(1, 1, 32, 0)), 0,0,0)
        vbox.pack_start(self.make_sb("gpsport",
                                     make_choice([])), 0,0,0)
        vbox.pack_start(self.make_sb("gpsenabled",
                                     self.make_bool()), 0,0,0)
        vbox.pack_start(self.make_sb("aprssymtab",
                                     gtk.Entry(1)), 0,0,0)
        vbox.pack_start(self.make_sb("aprssymbol",
                                     gtk.Entry(1)), 0,0,0)
        vbox.pack_start(self.make_sb("compatmode",
                                     self.make_bool()), 0,0,0)
        vbox.pack_start(self.make_sb("pipelinexfers",
                                     self.make_bool()), 0,0,0)
        vbox.pack_start(self.make_sb("warmup_length",
                                     self.make_spin(8, 0, 128, 0)), 0,0,0)
        vbox.pack_start(self.make_sb("warmup_timeout",
                                     self.make_spin(1, 0, 128, 0)), 0,0,0)
        vbox.pack_start(self.make_sb("force_delay",
                                     self.make_spin(1, 0, 128, 0)), 0,0,0)

        vbox.show()
        return vbox

    def build_ddt(self):
        vbox = gtk.VBox(False, 2)

        block_sizes = [str(pow(2,x)) for x in range(6, 13)]
        encodings = ddt.ENCODINGS.keys()

        vbox.pack_start(self.make_sb("compression",
                                     self.make_bool()), 0,0,0)
        vbox.pack_start(self.make_sb("encoding",
                                     make_choice(encodings, False)), 0,0,0)

        vbox.show()

        return vbox

    def build_callsigns(self):
        list = miscwidgets.ListWidget([(gobject.TYPE_BOOLEAN, "Mark"),
                                       (gobject.TYPE_STRING, "Country")])

        self.make_setting("callsigns", list)

        call_settings = eval(self.get("prefs", "callsigns"))
        known = [y for x,y in call_settings]
        avail = callsigns.callsign_functions.keys()

        for i in avail:
            if i not in known:
                call_settings.append((False, i))

        self.set("prefs", "callsigns", str(call_settings))

        list.show()
        return list

    def add_incoming(self, button, listw):
        d = inputdialog.FieldDialog(parent=self.window)
        d.add_field("Port", gtk.Entry())
        d.add_field("Host", gtk.Entry())
        while d.run() == gtk.RESPONSE_OK:
            vals = []

            for field, func in [("Port", int),
                                ("Host", str)]:
                try:
                    s = d.get_field(field).get_text()
                    if not s:
                        raise Exception("Empty")
                    vals.append(func(s))
                except:
                    ed = gtk.MessageDialog(buttons=gtk.BUTTONS_OK,
                                           parent=d)
                    ed.set_property("text", "Invalid value for '%s'" % field)
                    ed.run()
                    ed.destroy()
                    break

            if len(vals) == 2:
                listw.add_item(*tuple(vals))
                break

        d.destroy()

    def add_outgoing(self, button, listw):
        d = inputdialog.FieldDialog(parent=self.window)
        d.add_field("Local", gtk.Entry())
        d.add_field("Remote", gtk.Entry())
        d.add_field("Station", gtk.Entry())
        while d.run() == gtk.RESPONSE_OK:
            vals = []

            for field, func in [("Local", int),
                                ("Remote", int),
                                ("Station", str)]:
                try:
                    s = d.get_field(field).get_text()
                    if not s:
                        raise Exception("Empty")
                    vals.append(func(s))
                except:
                    ed = gtk.MessageDialog(buttons=gtk.BUTTONS_OK,
                                           parent=d)
                    ed.set_property("text", "Invalid value for '%s'" % field)
                    ed.run()
                    ed.destroy()
                    break

            if len(vals) == 3:
                listw.add_item(*tuple(vals))
                break

        d.destroy()

    def remove_current(self, button, listw):
        listw.remove_selected()

    def build_network(self):
        topvbox = gtk.VBox(False, 2)

        topvbox.pack_start(self.make_sb("smtp_server",
                                        gtk.Entry()), 0,0,0)

        topvbox.pack_start(self.make_sb("sockflush",
                                        self.make_spin(0.2, 0, 30)), 0,0,0)

        oframe = gtk.Frame("Outgoing")

        vbox = gtk.VBox(False, 2)
        
        list = miscwidgets.ListWidget([(gobject.TYPE_INT, "Local"),
                                       (gobject.TYPE_INT, "Remote"),
                                       (gobject.TYPE_STRING, "Station")])
        self.make_setting("outports", list)
        list.show()
        sw = gtk.ScrolledWindow()
        sw.set_policy(gtk.POLICY_AUTOMATIC, gtk.POLICY_AUTOMATIC)
        sw.add_with_viewport(list)
        sw.show()

        removeb = gtk.Button("Remove", gtk.STOCK_REMOVE)
        removeb.connect("clicked", self.remove_current, list)
        removeb.set_size_request(100, 30)
        removeb.show()

        addb = gtk.Button("Add new", gtk.STOCK_ADD)
        addb.connect("clicked", self.add_outgoing, list)
        addb.set_size_request(100, 30)
        addb.show()

        hbox = gtk.HBox(True, 2)
        hbox.pack_start(addb, 0,0,0)
        hbox.pack_start(removeb, 0,0,0)
        hbox.show()

        vbox.pack_start(sw, 1,1,1)
        vbox.pack_start(hbox, 0,0,0)
        vbox.show()        

        oframe.add(vbox)
        oframe.show()

        iframe = gtk.Frame("Incoming")

        vbox = gtk.VBox(False, 2)

        list = miscwidgets.ListWidget([(gobject.TYPE_INT, "Port"),
                                       (gobject.TYPE_STRING, "Host")])
        self.make_setting("inports", list)
        list.show()
        sw = gtk.ScrolledWindow()
        sw.set_policy(gtk.POLICY_AUTOMATIC, gtk.POLICY_AUTOMATIC)
        sw.add_with_viewport(list)
        sw.show()

        removeb = gtk.Button("Remove", gtk.STOCK_REMOVE)
        removeb.connect("clicked", self.remove_current, list)
        removeb.set_size_request(100, 30)
        removeb.show()

        addb = gtk.Button("Add", gtk.STOCK_ADD)
        addb.connect("clicked", self.add_incoming, list)
        addb.set_size_request(100, 30)
        addb.show()

        hbox = gtk.HBox(True, 2)
        hbox.pack_start(addb, 0,0,0)
        hbox.pack_start(removeb, 0,0,0)
        hbox.show()

        vbox.pack_start(sw, 1,1,1)
        vbox.pack_start(hbox, 0,0,0)
        vbox.show()

        iframe.add(vbox)
        iframe.show()

        topvbox.pack_start(oframe, 1,1,1)
        topvbox.pack_start(iframe, 1,1,1)
        topvbox.show()

        return topvbox

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
        #nb.append_page(self.build_ddt(), gtk.Label("DDT"))
        self.build_ddt() # Disabled for now
        nb.append_page(self.build_callsigns(), gtk.Label("Callsigns"))
        nb.append_page(self.build_network(), gtk.Label("Network"))

        nb.show()

        # Disable unsupported functions
        for i in ["autoreceive", "encoding"]:
            self.fields[i].set_sensitive(False)

        mainvbox = gtk.VBox(False, 5)
        mainvbox.pack_start(nb, 1,1,1)
        mainvbox.pack_start(self.make_buttons(), 0,0,0)
        mainvbox.show()
        
        self.window.add(mainvbox)

    def show(self, parent=None):
        # Refresh the ports, in case they have changed since we opened
        # D-RATS
        ports = self.platform.list_serial_ports()
        curport = self.config.get("settings", "port")
        if curport and curport not in ports:
            ports.append(curport)
        curport = self.config.get("settings", "gpsport")
        if curport and curport not in ports:
            ports.append(curport)

        for field in ["port", "gpsport"]:
            store = self.fields[field].get_model()
            store.clear()
            for i in sorted(ports):
                store.append((i,))

        if self.safe:
            d = gtk.MessageDialog(buttons=gtk.BUTTONS_OK, parent=self.window)
            d.set_property("text", "Safe Mode")
            d.set_property("secondary-text",
                           """
D-RATS has been started in safe mode, which means the configuration file has not been loaded until now.  Clicking the 'Save' button in the settings dialog will make those settings active and exit safe mode.""")
            d.run()
            d.destroy()
            self.load_config(self.default_filename())
        self.sync_gui(load=True)

        if parent:
            self.window.set_transient_for(parent)
            self.window.set_modal(True)
            self.window.set_type_hint(gtk.gdk.WINDOW_TYPE_HINT_DIALOG)

        self.window.show()
        gtk.main()
        self.window.hide()

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
                button.set_filename(d)
            else:
                d = button.get_filename()
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

    def sync_lists(self, list, load):
        for s, k in list:
            lw = self.fields[k]

            try:
                if load:
                    lw.set_values(eval(self.config.get(s, k)))
                else:
                    self.config.set(s, k, str(lw.get_values()))
            except Exception, e:
                print "Failed to sync %s,%s list: %s" % (s,k,e)
                self.config.set(s,k,str([]))

    def sync_gui(self, load=True):
        text_v = [("user", "callsign"),
                  ("user", "name"),
                  ("prefs", "noticere"),
                  ("prefs", "ignorere"),
                  ("prefs", "signon"),
                  ("prefs", "signoff"),
                  ("user", "latitude"),
                  ("user", "longitude"),
                  ("settings", "aprssymtab"),
                  ("settings", "aprssymbol"),
                  ("settings", "ping_info"),
                  ("settings", "smtp_server")]

        bool_v = [("prefs", "autoreceive"),
                  ("prefs", "dosignon"),
                  ("prefs", "dosignoff"),
                  ("prefs", "eolstrip"),
                  ("prefs", "logenabled"),
                  ("prefs", "debuglog"),
                  ("settings", "compression"),
                  ("prefs", "logresume"),
                  ("settings", "gpsenabled"),
                  ("settings", "compatmode"),
                  ("prefs", "restore_stations"),
                  ("settings", "pipelinexfers")]

        choicetext_v = [("settings", "port"),
                        ("settings", "gpsport")]

        choice_v = [("settings", "rate"),
                    ("settings", "encoding"),
                    ("user", "units")]

        color_v = [("prefs", "incomingcolor"),
                   ("prefs", "outgoingcolor"),
                   ("prefs", "noticecolor"),
                   ("prefs", "ignorecolor"),
                   ("prefs", "callsigncolor"),
                   ("prefs", "brokencolor")]

        path_v = [("prefs", "download_dir"),
                  ("settings", "mapdir")]

        font_v = [("prefs", "font")]

        spin_v = [("prefs", "scrollback"),
                  ("user", "altitude"),
                  ("settings", "sockflush"),
                  ("settings", "ddt_block_size"),
                  ("settings", "ddt_block_outlimit"),
                  ("settings", "warmup_length"),
                  ("settings", "warmup_timeout"),
                  ("settings", "force_delay")]

        list_v = [("prefs", "callsigns"),
                  ("settings", "inports"),
                  ("settings", "outports")]

        self.sync_texts(text_v, load)
        self.sync_booleans(bool_v, load)
        self.sync_choicetexts(choicetext_v, load)
        self.sync_choices(choice_v, load)
        self.sync_colors(color_v, load)
        self.sync_paths(path_v, load)
        self.sync_fonts(font_v, load)
        self.sync_spins(spin_v, load)
        self.sync_lists(list_v, load)

    def load_config(self, file):
        self.config.read(file)

    def __init__(self, mainapp, safe=False):
        self.mainapp = mainapp
        self.safe = safe

        self.platform = platform.get_platform()
        try:
            self.default_port = self.platform.list_serial_ports()[0]
        except:
            self.default_port = ""

        self.tips = gtk.Tooltips()

        self._file = self.platform.config_file("d-rats.config")

        self.config = ConfigParser.ConfigParser()
        if not self.safe:
            self.load_config(self._file)
        self.fields = {}

        self.init_config()

        self.build_gui()

    def save(self, _file=None):
        if not _file:
            _file = self._file

        f = file(_file, "w")
        self.config.write(f)
        f.close()

        self.safe = False
