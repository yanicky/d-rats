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
import formgui
import station_status

from ui import main_events

from utils import hexprint,filter_to_ascii,NetFile,log_exception,run_gtk_locked

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

        (foo, p) = self.data.get(call, (0, None))

        self.data[call] = (ts, p)        

    def get_call_pos(self, call):
        (foo, p) = self.data.get(call, (0, None))

        return p

    def get_call_time(self, call):
        (t, foo) = self.data.get(call, (0, None))

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

    def stop_comms(self):
        if self.comm:
            self.comm.disconnect()
            return True
        else:
            return False

    def start_comms(self):
        rate = self.config.get("settings", "rate")
        port = self.config.get("settings", "port")
        pswd = self.config.get("settings", "socket_pw")
        call = self.config.get("user", "callsign")

        if ":" in port:
            try:
                (mode, host, port) = port.split(":")
            except ValueError:
                event = main_events.Event(None,
                                          _("Failed to connect to") + \
                                              " %s: " % port + \
                                              _("Invalid port string"))
                self.mainwindow.tabs["event"].event(event)
                return False

            self.comm = comm.SocketDataPath((host, int(port), call, pswd))
        else:
            self.comm = comm.SerialDataPath((port, int(rate)))
                                   
        try:
            self.comm.connect()
        except comm.DataPathNotConnectedError, e:
            print "COMM did not connect: %s" % e
            event = main_events.Event(None,
                                      "Failed to connect (%s)" % e)
            self.mainwindow.tabs["event"].event(event)
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


            self.chat_session = self.sm.start_session("chat",
                                                      dest="CQCQCQ",
                                                      cls=sessions.ChatSession)
            self.__connect_object(self.chat_session)

            rpcactions = rpcsession.RPCActionSet(self.config)
            self.__connect_object(rpcactions)

            self.rpc_session = self.sm.start_session("rpc",
                                                     dest="CQCQCQ",
                                                     cls=rpcsession.RPCSession,
                                                     rpcactions=rpcactions)

            def sniff_event(ss, src, dst, msg):
                if self.config.getboolean("settings", "sniff_packets"):
                    event = main_events.Event(None, "Sniffer: %s" % msg)
                    self.mainwindow.tabs["event"].event(event)

                self.mainwindow.tabs["stations"].saw_station(src)

            ss = self.sm.start_session("Sniffer",
                                       dest="CQCQCQ",
                                       cls=sessions.SniffSession)
            self.sm.set_sniffer_session(ss._id)
            ss.connect("incoming_frame", sniff_event)

            self.sc = session_coordinator.SessionCoordinator(self.config,
                                                             self.sm)
            self.__connect_object(self.sc)

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
        if self.stop_comms():
            if sys.platform == "win32":
                time.sleep(0.25) # Wait for windows to let go of the serial port
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
        for acct in accts:
            t = emailgw.MailThread(self.config, acct)
            self.__connect_object(t)
            t.start()
            self.mail_threads.append(t)

    def _refresh_lang(self):
        locales = { "English" : "en",
                    "Italiano" : "it",
                    "Dutch" : "nl",
                    }
        locale = locales.get(self.config.get("prefs", "language"), "English")
        print "Loading locale `%s'" % locale

        localedir = os.path.join(platform.get_platform().source_dir(),
                                 "locale")
        print "Locale dir is: %s" % localedir

        if not os.environ.has_key("LANGUAGE"):
            os.environ["LANGUAGE"] = locale

        try:
            lang = gettext.translation("D-RATS",
                                       localedir=localedir,
                                       languages=[locale])
            lang.install()
            gtk.glade.bindtextdomain("D-RATS", localedir)
            gtk.glade.textdomain("D-RATS")
        except LookupError:
            print "Unable to load language `%s'" % locale
            gettext.install("D-RATS")
        except IOError, e:
            print "Unable to load translation for %s: %s" % (locale, e)
            gettext.install("D-RATS")

    def _load_map_overlays(self):
        self.stations_overlay = None

        self.map.clear_map_sources()

        source_types = [map_sources.MapFileSource,
                        map_sources.MapUSGSRiverSource,
                        map_sources.MapNBDCBuoySource]

        for stype in source_types:
            sources = stype.enumerate(self.config)
            for sname in sources:
                try:
                    source = stype.open_source_by_name(self.config, sname)
                    self.map.add_map_source(source)
                except Exception, e:
                    log_exception()
                    print "Failed to load map source %s: %s" % \
                        (source.get_name(), e)

                if sname == _("Stations"):
                    self.stations_overlay = source

        if not self.stations_overlay:
            fn = os.path.join(self.config.platform.config_dir(),
                              "static_locations",
                              _("Stations") + ".csv")
            try:
                os.makedirs(os.path.dirname(fn))
            except:
                pass
            file(fn, "w").close()
            self.stations_overlay = map_sources.MapFileSource(_("Stations"),
                                                              "Static Overlay",
                                                              fn)

    def refresh_config(self):
        print "Refreshing config..."

        rate = self.config.getint("settings", "rate")
        port = self.config.get("settings", "port")
        call = self.config.get("user", "callsign")
        gps.set_units(self.config.get("user", "units"))
        mapdisplay.set_base_dir(self.config.get("settings", "mapdir"))
        mapdisplay.set_connected(self.config.getboolean("state",
                                                        "connected_inet"))
        mapdisplay.set_tile_lifetime(self.config.getint("settings",
                                                        "map_tile_ttl") * 3600)

        self._refresh_comms(port, rate)
        self._refresh_gps()
        self._refresh_mail_threads()

            
    def _refresh_location(self):
        fix = self.get_position()

        if not self.__map_point:
            self.__map_point = map_sources.MapStation(fix.station,
                                                      fix.latitude,
                                                      fix.longitude,
                                                      fix.altitude,
                                                      fix.comment)
        else:
            self.__map_point.set_latitude(fix.latitude)
            self.__map_point.set_longitude(fix.longitude)
            self.__map_point.set_altitude(fix.altitude)
            self.__map_point.set_comment(fix.comment)
            self.__map_point.set_name(fix.station)
            
        self.stations_overlay.add_point(self.__map_point)

        return True

    def __chat(self, src, dst, data, incoming):
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

        @run_gtk_locked
        def do_incoming():
            self.mainwindow.tabs["chat"].display_line(line, incoming, color)

        gobject.idle_add(do_incoming)

# ---------- STANDARD SIGNAL HANDLERS --------------------

    def __status(self, object, status):
        self.mainwindow.set_status(status)

    def __user_stop_session(self, object, sid, force=False):
        print "User did stop session %i (force=%s)" % (sid, force)
        try:
            session = self.sm.sessions[sid]
            session.close(force)
        except Exception, e:
            print "Session `%i' not found: %s" % (sid, e)
    
    def __user_cancel_session(self):
        self.__user_stop_session(object.sid, True)

    def __user_send_form(self, object, station, fname, sname):
        self.sc.send_form(station, fname, sname)

    def __user_send_file(self, object, station, fname, sname):
        self.sc.send_file(station, fname, sname)

    def __user_send_chat(self, object, station, msg, raw):
        self.chat_session.write(msg)

    def __incoming_chat_message(self, object, src, dst, data):
        self.__chat(src, dst, data, True)

    def __outgoing_chat_message(self, object, src, dst, data):
        self.__chat(src, dst, data, False)

    def __get_station_list(self, object):
        return self.sm.get_heard_stations().keys()

    def __get_message_list(self, object, station):
        return self.mainwindow.tabs["messages"].get_shared_messages(station)

    def __submit_rpc_job(self, object, job):
        self.rpc_session.submit(job)

    def __event(self, event):
        self.mainwindow.tabs["event"].event(e),        

    def __config_changed(self, object):
        self.refresh_config()

    def __show_map_station(self, object, station):
        print "Showing map"
        self.map.show()

    def __ping_station(self, object, station):
        self.chat_session.ping_station(station)

    def __ping_station_echo(self, object, station, data, callback, cb_data):
        self.chat_session.ping_echo_station(station, data, callback, cb_data)

    def __ping_request(self, object, src, dst, data):
        msg = "%s pinged %s" % (src, dst)
        if data:
            msg += " (%s)" % data

        event = main_events.PingEvent(None, msg)
        self.mainwindow.tabs["event"].event(event)

    def __ping_response(self, object, src, dst, data):
        msg = "%s replied to ping from %s with: %s" % (src, dst, data)
        event = main_events.PingEvent(None, msg)
        self.mainwindow.tabs["event"].event(event)

    def __incoming_gps_fix(self, object, fix):
        ts = self.mainwindow.tabs["event"].last_event_time(fix.station)
        if (time.time() - ts) > 300:
            self.mainwindow.tabs["event"].finalize_last(fix.station)

        fix.set_relative_to_current(self.get_position())
        event = main_events.PosReportEvent(fix.station, str(fix))
        self.mainwindow.tabs["event"].event(event)

        self.mainwindow.tabs["stations"].saw_station(fix.station)

        point = map_sources.MapStation(fix.station,
                                       fix.latitude,
                                       fix.longitude,
                                       fix.altitude,
                                       fix.comment)
        self.stations_overlay.add_point(point)

    def __station_status(self, object, sta, stat, msg):
        self.mainwindow.tabs["stations"].saw_station(sta, stat, msg)
        status = station_status.STATUS_MSGS[stat]
        event = main_events.Event(None, 
                                  "%s %s %s %s: %s" % (_("Station"),
                                                       sta,
                                                       _("is now"),
                                                       status,
                                                       msg))
        self.mainwindow.tabs["event"].event(event)

    def __get_current_status(self, object):
        return self.mainwindow.tabs["stations"].get_status()

    def __session_started(self, object, id, msg=None):
        if msg is None:
            msg = "Ended"

        print "[SESSION %i]: %s" % (id, msg)

        event = main_events.SessionEvent(id, msg)
        self.mainwindow.tabs["event"].event(event)

    def __session_status_update(self, object, *args):
        self.__session_started(object, *args)

    def __session_ended(self, object, *args):
        self.__session_started(object, *args)

    def __session_failed(self, object, id, msg):
        event = main_events.Event(id, msg)
        self.mainwindow.tabs["event"].event(event)

    def __form_received(self, object, id, fn):
        print "[NEWFORM %i]: %s" % (id, fn)
        f = formgui.FormFile("", fn)
        msg = '%s "%s" %s %s' % (_("Message"),
                                 f.get_subject_string(),
                                 _("received from"),
                                 f.get_sender_string())
        event = main_events.FormEvent(id, msg)
        event.set_as_final()
        self.mainwindow.tabs["messages"].refresh_if_folder("Inbox")
        self.mainwindow.tabs["event"].event(event)

    def __file_received(self, object, id, fn):
        _fn = os.path.basename(fn)
        msg = '%s "%s" %s' % (_("File"), _fn, _("Received"))
        event = main_events.FileEvent(id, msg)
        event.set_as_final()
        self.mainwindow.tabs["files"].refresh_local()
        self.mainwindow.tabs["event"].event(event)
                
    def __form_sent(self, object, id, fn):
        print "[FORMSENT %i]: %s" % (id, fn)
        event = main_events.FormEvent(id, _("Message Sent"))
        event.set_as_final()
        self.mainwindow.tabs["messages"].message_sent(fn)
        self.mainwindow.tabs["event"].event(event)

    def __file_sent(self, object, id, fn):
        print "[FILESENT %i]: %s" % (id, fn)
        _fn = os.path.basename(fn)
        msg = '%s "%s" %s' % (_("File"), _fn, _("Sent"))
        event = main_events.FileEvent(id, msg)
        event.set_as_final()
        self.mainwindow.tabs["files"].file_sent(fn)
        self.mainwindow.tabs["event"].event(event)

# ------------ END SIGNAL HANDLERS ----------------

    def __connect_object(self, object):
        for signal in object._signals.keys():
            handler = self.handlers.get(signal, None)
            if handler is None:
                raise Exception("Object signal `%s' of object %s not known" % \
                                    (signal, object))
            elif self.handlers.has_key(signal):
                object.connect(signal, handler)

    def __init__(self, **args):
        self.handlers = {
            "status" : self.__status,
            "user-stop-session" : self.__user_stop_session,
            "user-cancel-session" : self.__user_cancel_session,
            "user-send-form" : self.__user_send_form,
            "user-send-file" : self.__user_send_file,
            "rpc-send-form" : self.__user_send_form,
            "rpc-send-file" : self.__user_send_file,
            "user-send-chat" : self.__user_send_chat,
            "incoming-chat-message" : self.__incoming_chat_message,
            "outgoing-chat-message" : self.__outgoing_chat_message,
            "get-station-list" : self.__get_station_list,
            "get-message-list" : self.__get_message_list,
            "submit-rpc-job" : self.__submit_rpc_job,
            "event" : self.__event,
            "notice" : False,
            "config-changed" : self.__config_changed,
            "show-map-station" : self.__show_map_station,
            "ping-station" : self.__ping_station,
            "ping-station-echo" : self.__ping_station_echo,
            "ping-request" : self.__ping_request,
            "ping-response" : self.__ping_response,
            "incoming-gps-fix" : self.__incoming_gps_fix,
            "station-status" : self.__station_status,
            "get-current-status" : self.__get_current_status,
            "session-status-update" : self.__session_status_update,
            "session-started" : self.__session_started,
            "session-ended" : self.__session_ended,
            "session-failed" : self.__session_failed,
            "file-received" : self.__file_received,
            "form-received" : self.__form_received,
            "file-sent" : self.__file_sent,
            "form-sent" : self.__form_sent,
            }

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

        self.map = mapdisplay.MapWindow(self.config)
        self.map.set_title("D-RATS Map Window")
        self.map.connect("reload-sources", lambda m: self._load_map_overlays())
        pos = self.get_position()
        self.map.set_center(pos.latitude, pos.longitude)
        self.map.set_zoom(14)
        self.__map_point = None
                                                              
        self.mainwindow = mainwindow.MainWindow(self.config)
        self.__connect_object(self.mainwindow)

        for tab in self.mainwindow.tabs.values():
            self.__connect_object(tab)

        self.refresh_config()
        self._load_map_overlays()
        
        if self.config.getboolean("prefs", "dosignon") and self.chat_session:
            msg = self.config.get("prefs", "signon")
            self.chat_session.advertise_status(station_status.STATUS_ONLINE,
                                               msg)

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

        if self.config.getboolean("prefs", "dosignoff") and self.sm:
            msg = self.config.get("prefs", "signoff")
            self.chat_session.advertise_status(station_status.STATUS_OFFLINE,
                                               msg)
            time.sleep(0.5) # HACK

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
