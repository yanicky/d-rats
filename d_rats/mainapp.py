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

import sys
import platform
import os

debug_path = platform.get_platform().config_file("debug.log")
if sys.platform == "win32" or not os.isatty(0):
    sys.stdout = file(debug_path, "w", 0)
    sys.stderr = sys.stdout
    print "Enabled debug log"
else:
    try:
        os.unlink(debug_path)
    except OSError:
        pass

import gettext
gettext.install("D-RATS")

import time
import re
from threading import Thread, Lock
from select import select
import socket
from commands import getstatusoutput
import glob
import shutil
import datetime

import serial
import gtk
import gobject

import mainwindow
import config
import gps
import mapdisplay
import map_sources
import comm
import sessionmgr
import sessions
import session_coordinator
import emailgw
import rpcsession

from ui import main_events

from utils import hexprint,filter_to_ascii,NetFile

LOGTF = "%m-%d-%Y_%H:%M:%S"

MAINAPP = None

gobject.threads_init()

def ping_file(filename):
    try:
        f = NetFile(filename, "r")
    except IOError, e:
        raise Exception("Unable to open file %s: %s" % (filename, e))
        return None

    data = f.read()
    f.close()

    return data

def ping_exec(command):
    s, o = getstatusoutput(command)
    if s:
        raise Exception("Failed to run command: %s" % command)
        return None

    return o    

class CallList:
    def __init__(self):
        self.clear()

    def clear(self):
        self.data = {}

    def set_call_pos(self, call, pos):
        (t, _) = self.data.get(call, (0, None))

        self.data[call] = (t, pos)

    def set_call_time(self, call, ts=None):
        if ts is None:
            ts = time.time()

        (_, p) = self.data.get(call, (0, None))

        self.data[call] = (ts, p)        

    def get_call_pos(self, call):
        (_, p) = self.data.get(call, (0, None))

        return p

    def get_call_time(self, call):
        (t, _) = self.data.get(call, (0, None))

        return t

    def list(self):
        return self.data.keys()

    def is_known(self, call):
        return self.data.has_key(call)

    def remove(self, call):
        try:
            del self.data[call]
        except:
            pass

class MainApp:
    def setup_autoid(self):
        idtext = "(ID)"

    def incoming_chat(self, cs, src, dst, data, incoming):
        if src != "CQCQCQ":
            self.seen_callsigns.set_call_time(src, time.time())

        if dst != "CQCQCQ":
            to = " -> %s:" % dst
        else:
            to = ":"

        if src == "CQCQCQ":
            color = "brokencolor"
        elif incoming:
            color = "incomingcolor"
        else:
            color = "outgoingcolor"

        line = "%s%s %s" % (src, to, data)
        gobject.idle_add(self.mainwindow.tabs["chat"].display_line,
                         line, incoming, color)

    def stop_comms(self):
        if self.sm:
            self.sm.shutdown()
            self.sm = None
            self.chat_session = None

        if self.comm:
            self.comm.disconnect()

    def start_comms(self):
        rate = self.config.get("settings", "rate")
        port = self.config.get("settings", "port")

        if ":" in port:
            (_, host, port) = port.split(":")
            self.comm = comm.SocketDataPath((host, int(port)))
        else:
            self.comm = comm.SerialDataPath((port, int(rate)))
                                   
        try:
            self.comm.connect()
        except comm.DataPathNotConnectedError, e:
            print "COMM did not connect: %s" % e
            self.mainwindow.set_status("Failed to connect %s: %s" % (port, e))
            return False

        transport_args = {
            "compat" : self.config.getboolean("settings", "compatmode"),
            "warmup_length" : self.config.getint("settings", "warmup_length"),
            "warmup_timeout" : self.config.getint("settings", "warmup_timeout"),
            "force_delay" : self.config.getint("settings", "force_delay"),
            }

        callsign = self.config.get("user", "callsign")
        if not self.sm:
            self.sm = sessionmgr.SessionManager(self.comm,
                                                callsign,
                                                **transport_args)

            def in_ping(cs, src, dst, data):
                msg = "%s pinged %s" % (src, dst)
                print msg
                event = main_events.PingEvent(-1, msg)
                self.mainwindow.tabs["event"].event(event)

            def out_ping(cs, src, dst, data):
                msg = "%s replied to ping from %s with: %s" % (src, dst, data)
                print msg
                event = main_events.PingEvent(-1, msg)
                self.mainwindow.tabs["event"].event(event)

            def in_gps(cs, fix):
                fix.set_relative_to_current(self.get_position())
                event = main_events.PosReportEvent(-1, str(fix))
                event.set_as_final()
                self.mainwindow.tabs["event"].event(event)

                point = map_sources.MapStation(fix.station,
                                               fix.latitude,
                                               fix.longitude,
                                               fix.altitude,
                                               fix.comment)
                self.stations_overlay.add_point(point)

            self.chat_session = self.sm.start_session("chat",
                                                      dest="CQCQCQ",
                                                      cls=sessions.ChatSession)
            self.chat_session.connect("incoming-chat-message",
                                      self.incoming_chat, True)
            self.chat_session.connect("outgoing-chat-message",
                                      self.incoming_chat, False)
            self.chat_session.connect("ping-request", in_ping)
            self.chat_session.connect("ping-response", out_ping)
            self.chat_session.connect("incoming-gps-fix", in_gps)

            if self.config.getboolean("settings", "sniff_packets"):
                ss = self.sm.start_session("Sniffer",
                                           dest="CQCQCQ",
                                           cls=sessions.SniffSession)
                self.sm.set_sniffer_session(ss._id)
                ss.connect("incoming_frame",
                           lambda o,m: self.mainwindow.tabs["chat"].display_line(m, "italic"))

            def send_file(ft, sta, fn, name):
                self.sc.send_file(sta, fn, name)
            def send_form(msgs, sta, fn, name):
                self.sc.send_form(sta, fn, name)
            def get_messages(obj, sta):
                return self.mainwindow.tabs["messages"].get_shared_messages(sta)

            rpcactions = rpcsession.RPCActionSet(self.config)
            rpcactions.connect("rpc-send-file", send_file)
            rpcactions.connect("rpc-send-msg", send_form)
            rpcactions.connect("rpc-get-msgs", get_messages)
            self.rpc_session = self.sm.start_session("rpc",
                                                     dest="CQCQCQ",
                                                     cls=rpcsession.RPCSession,
                                                     rpcactions=rpcactions)

            def do_rpc(files, job):
                self.rpc_session.submit(job)

            self.mainwindow.tabs["files"].connect("submit-rpc-job", do_rpc)

            def do_stop_session(events, sid, force):
                print "User did stop session %i (force=%s)" % (sid, force)
                try:
                    session = self.sm.sessions[sid]
                    session.close(force)
                except Exception, e:
                    print "Session `%i' not found: %s" % (sid, e)

            self.mainwindow.tabs["event"].connect("user-stop-session",
                                                  do_stop_session,
                                                  False)
            self.mainwindow.tabs["event"].connect("user-cancel-session",
                                                  do_stop_session,
                                                  True)

            self.sc = session_coordinator.SessionCoordinator(self.config,
                                                             self.sm)

            def log_session_info(sc, id, msg=None):
                if msg is None:
                    msg = "Ended"

                print "[SESSION %i]: %s" % (id, msg)

                event = main_events.SessionEvent(id, msg)
                self.mainwindow.tabs["event"].event(event)

            def failed_session(sc, id, msg):
                event = main_events.Event(id, msg)
                self.mainwindow.tabs["event"].event(event)

            self.sc.connect("session-started", log_session_info)
            self.sc.connect("session-status-update", log_session_info)
            self.sc.connect("session-ended", log_session_info)
            self.sc.connect("session-failed", failed_session)

            def new_form(sc, id, fn):
                print "[NEWFORM %i]: %s" % (id, fn)
                event = main_events.FormEvent(id, "Form Received")
                event.set_as_final()
                self.mainwindow.tabs["messages"].refresh_if_folder("Inbox")
                self.mainwindow.tabs["event"].event(event)
            self.sc.connect("form-received", new_form)

            def new_file(sc, id, fn):
                _fn = os.path.basename(fn)
                event = main_events.FileEvent(id, "File %s Received" % _fn)
                event.set_as_final()
                self.mainwindow.tabs["files"].refresh_local()
                self.mainwindow.tabs["event"].event(event)
            self.sc.connect("file-received", new_file)
                
            def form_sent(sc, id, fn):
                print "[FORMSENT %i]: %s" % (id, fn)
                event = main_events.FormEvent(id, "Form Sent")
                event.set_as_final()
                self.mainwindow.tabs["messages"].message_sent(fn)
                self.mainwindow.tabs["event"].event(event)
            self.sc.connect("form-sent", form_sent)

            def file_sent(sc, id, fn):
                print "[FILESENT %i]: %s" % (id, fn)
                _fn = os.path.basename(fn)
                event = main_events.FileEvent(id, "File %s Sent" % _fn)
                event.set_as_final()
                self.mainwindow.tabs["files"].file_sent(fn)
                self.mainwindow.tabs["event"].event(event)
            self.sc.connect("file-sent", file_sent)

            self.mainwindow.tabs["files"].connect("user-send-file",
                                                  send_file)

            self.mainwindow.tabs["messages"].connect("user-send-form",
                                                     send_form)

            self.sm.register_session_cb(self.sc.session_cb, None)


        else:
            self.sm.set_comm(self.comm, **transport_args)
            self.sm.set_call(callsign)

        pingdata = self.config.get("settings", "ping_info")
        if pingdata.startswith("!"):
            def pingfn():
                return ping_exec(pingdata[1:])
        elif pingdata.startswith(">"):
            def pingfn():
                return ping_file(pingdata[1:])
        elif pingdata:
            def pingfn():
                return pingdata
        else:
            pingfn = None

        self.chat_session.set_ping_function(pingfn)

        return True

    def _refresh_comms(self, port, rate):
        self.stop_comms()
        return self.start_comms()

    def _static_gps(self):
        lat = 0.0
        lon = 0.0
        alt = 0.0

        try:
            lat = self.config.get("user", "latitude")
            lon = self.config.get("user", "longitude")
            alt = self.config.get("user", "altitude")
        except Exception, e:
            import traceback
            traceback.print_exc(file=sys.stdout)
            print "Invalid static position: %s" % e

        print "Static position: %s,%s" % (lat,lon)
        return gps.StaticGPSSource(lat, lon, alt)

    def _refresh_gps(self):
        port = self.config.get("settings", "gpsport")
        rate = self.config.getint("settings", "gpsportspeed")
        enab = self.config.getboolean("settings", "gpsenabled")

        print "GPS: %s on %s@%i" % (enab, port, rate)

        if enab:
            if self.gps:
                self.gps.stop()

            if port.startswith("net:"):
                self.gps = gps.NetworkGPSSource(port)
            else:
                self.gps = gps.GPSSource(port, rate)
            self.gps.start()
        else:
            if self.gps:
                self.gps.stop()

            self.gps = self._static_gps()

    def _refresh_mail_threads(self):
        for i in self.mail_threads:
            i.stop()

        accts = self.config.options("incoming_email")
        accts = [] # FIXME
        for acct in accts:
            t = emailgw.MailThread(self.config, acct, self.chatgui)
            t.start()
            self.mail_threads.append(t)

    def _refresh_lang(self):
        locales = { "English" : "en",
                    "Italiano" : "it",
                    }
        locale = locales.get(self.config.get("prefs", "language"), "English")
        print "Loading locale `%s'" % locale

        localedir = os.path.join(platform.get_platform().source_dir(),
                                 "locale")
        print "Locale dir is: %s" % localedir

        try:
            lang = gettext.translation("D-RATS",
                                       localedir=localedir,
                                       languages=[locale])
            lang.install()
        except LookupError:
            print "Unable to load language `%s'" % locale
            gettext.install("D-RATS")
        except IOError, e:
            print "Unable to load translation for %s: %s" % (locale, e)
            gettext.install("D-RATS")

    def _load_map_overlays(self):
        dir = os.path.join(self.config.platform.config_dir(),
                           "static_locations")
        overlays = glob.glob(os.path.join(dir, "*.csv"))

        self.stations_overlay = None

        self.map.clear_map_sources()
        for overlay in overlays:
            name = os.path.basename(overlay).replace(".csv", "")
            source = map_sources.MapFileSource(name, "Static Overlay", overlay)
            self.map.add_map_source(source)
            if name == _("Stations"):
                self.stations_overlay = source

        if not self.stations_overlay:
            fn = os.path.join(dir, _("Stations") + ".csv")
            os.makedirs(os.path.dirname(fn))
            file(fn, "w").close()
            self.stations_overlay = map_sources.MapFileSource(_("Stations"),
                                                              "Static Overlay",
                                                              fn)

        rivers = [14299800]
        for river in rivers:
            self.map.add_map_source(map_sources.MapUSGSRiverSource("USGS NWIS",
                                                                   "Rivers",
                                                                   river))
            
    def refresh_config(self):
        print "Refreshing config..."

        rate = self.config.getint("settings", "rate")
        port = self.config.get("settings", "port")
        call = self.config.get("user", "callsign")
        gps.set_units(self.config.get("user", "units"))
        mapdisplay.set_base_dir(self.config.get("settings", "mapdir"))
        mapdisplay.set_connected(self.config.getboolean("state",
                                                        "connected_inet"))

        self._refresh_comms(port, rate)
        self._refresh_gps()
        self._refresh_mail_threads()

    def send_chat(self, chattab, station, msg, raw):
        self.chat_session.write(msg)
            
    def _refresh_location(self):
        fix = self.get_position()

        point = map_sources.MapStation(fix.station,
                                       fix.latitude,
                                       fix.longitude,
                                       fix.altitude,
                                       fix.comment)
        self.stations_overlay.add_point(point)

        return True

    def __init__(self, **args):
        global MAINAPP
        MAINAPP = self

        self.comm = None
        self.sm = None
        self.chat_session = None
        self.seen_callsigns = CallList()
        self.position = None
        self.mail_threads = []

        self.config = config.DratsConfig(self)
        self._refresh_lang()

        self.gps = self._static_gps()

        self.map = mapdisplay.MapWindow()
        self.map.set_title("D-RATS Map Window")
        pos = self.get_position()
        self.map.set_center(pos.latitude, pos.longitude)
        self.map.set_zoom(14)
                                                              
        #self.map.add_popup_handler(_("Set as current location"),
        #                           self.set_loc_from_map)

        self.mainwindow = mainwindow.MainWindow(self.config)
        self.mainwindow.tabs["chat"].connect("user-sent-message",
                                             self.send_chat)
        self.mainwindow.connect("config-changed",
                                lambda w: self.refresh_config())
        self.mainwindow.connect("show-map-station",
                                lambda w, s: self.map.show())
        self.mainwindow.connect("ping-station",
                                lambda w, s: self.chat_session.ping_station(s))
        self.mainwindow.connect("get-station-list",
                                lambda m, f:
                                    self.sm.get_heard_stations().keys())
        self.mainwindow.tabs["files"].connect("get-station-list",
                                              lambda m, f:
                                                  self.sm.get_heard_stations().keys())
        self.refresh_config()
        self._load_map_overlays()
        
        if self.config.getboolean("prefs", "dosignon") and self.chat_session:
            msg = self.config.get("prefs", "signon")
            self.chat_session.write(msg)

        gobject.timeout_add(3000, self._refresh_location)

    def get_position(self):
        p = self.gps.get_position()
        p.set_station(self.config.get("user", "callsign"))
        return p

    def main(self):
        # Copy default forms before we start

        distdir = platform.get_platform().source_dir()
        userdir = self.config.form_source_dir()
        dist_forms = glob.glob(os.path.join(distdir, "forms", "*.x?l"))
        for form in dist_forms:
            fname = os.path.basename(form)
            user_fname = os.path.join(userdir, fname)
            
            if not os.path.exists(user_fname):
                print "Installing dist form %s -> %s" % (fname, user_fname)
                try:
                    shutil.copyfile(form, user_fname)
                except Exception, e:
                    print "FAILED: %s" % e
        try:
            gtk.main()
        except KeyboardInterrupt:
            pass
        except Exception, e:
            print "Got exception on close: %s" % e

        print "Saving config..."
        self.config.save()
        #self.chatgui.save_static_locations()

        #if self.sm:
        #    print "Stopping session manager..."
        #    self.sm.shutdown(True)
        #
        #print "Closing serial..."
        #self.comm.disconnect()
        #
        #if self.gps:
        #    print "Stopping GPS..."
        #    self.gps.stop()
        #
        #for i in self.mail_threads:
        #    i.stop()
        #    i.join()
        #
        #print "Done.  Exit."

def get_mainapp():
    return MAINAPP
