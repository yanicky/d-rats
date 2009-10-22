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
import pluginsrv
import msgrouting

from ui import main_events

from utils import hexprint,filter_to_ascii,NetFile,log_exception,run_gtk_locked
from utils import init_icon_maps

init_icon_maps()

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

class CallList(object):
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

class MainApp(object):
    def setup_autoid(self):
        idtext = "(ID)"

    def stop_comms(self, portid):
        if self.sm.has_key(portid):
            sm, sc = self.sm[portid]
            sm.shutdown(True)
            sm.pipe.disconnect()
            del self.sm[portid]
            return True
        else:
            return False

    def start_comms(self, portid):
        spec = self.config.get("ports", portid)
        try:
            enb, port, rate, sniff, raw, name = spec.split(",")
            enb = (enb == "True")
            sniff = (sniff == "True")
            raw = (raw == "True")                   
        except Exception, e:
            print "Failed to parse portspec %s:" % spec
            log_exception()
            return

        if not enb:
            if self.sm.has_key(name):
                del self.sm[name]
            return

        print "Starting port %s (%s)" % (portid, name)

        call = self.config.get("user", "callsign")

        if port.startswith("tnc:"):
            _port = port.replace("tnc:", "")
            path = comm.TNCDataPath((_port, int(rate)))
        elif port.startswith("dongle:"):
            path = comm.SocketDataPath(("127.0.0.1", 20003, call, None))
        elif ":" in port:
            try:
                (mode, host, port) = port.split(":")
            except ValueError:
                event = main_events.Event(None,
                                          _("Failed to connect to") + \
                                              " %s: " % port + \
                                              _("Invalid port string"))
                self.mainwindow.tabs["event"].event(event)
                return False

            path = comm.SocketDataPath((host, int(port), call, rate))
        else:
            path = comm.SerialDataPath((port, int(rate)))
                                   
        try:
            path.connect()
        except comm.DataPathNotConnectedError, e:
            print "COMM did not connect: %s" % e
            event = main_events.Event(None,
                                      "Failed to connect (%s)" % e)
            self.mainwindow.tabs["event"].event(event)
            return False

        transport_args = {
            "compat" : raw,
            "warmup_length" : self.config.getint("settings", "warmup_length"),
            "warmup_timeout" : self.config.getint("settings", "warmup_timeout"),
            "force_delay" : self.config.getint("settings", "force_delay"),
            }

        if not self.sm.has_key(name):
            sm = sessionmgr.SessionManager(path, call, **transport_args)

            chat_session = sm.start_session("chat",
                                            dest="CQCQCQ",
                                            cls=sessions.ChatSession)
            self.__connect_object(chat_session, name)

            rpcactions = rpcsession.RPCActionSet(self.config, name)
            self.__connect_object(rpcactions)

            rpc_session = sm.start_session("rpc",
                                           dest="CQCQCQ",
                                           cls=rpcsession.RPCSession,
                                           rpcactions=rpcactions)

            def sniff_event(ss, src, dst, msg, port):
                if sniff:
                    event = main_events.Event(None, "Sniffer: %s" % msg)
                    self.mainwindow.tabs["event"].event(event)

                self.mainwindow.tabs["stations"].saw_station(src, port)

            ss = sm.start_session("Sniffer",
                                  dest="CQCQCQ",
                                  cls=sessions.SniffSession)
            sm.set_sniffer_session(ss._id)
            ss.connect("incoming_frame", sniff_event, name)

            sc = session_coordinator.SessionCoordinator(self.config, sm)
            self.__connect_object(sc, name)

            sm.register_session_cb(sc.session_cb, None)

            self.sm[name] = sm, sc

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
            chat_session.set_ping_function(pingfn)

        else:
            sm, sc = self.sm[name]

            sm.set_comm(path, **transport_args)
            sm.set_call(call)



        return True

    def chat_session(self, portname):
        return self.sm[portname][0].get_session(lid=1)

    def rpc_session(self, portname):
        return self.sm[portname][0].get_session(lid=2)

    def sc(self, portname):
        return self.sm[portname][1]

    def _refresh_comms(self):
        delay = False

        for portid in self.sm.keys():
            print "Stopping %s" % portid
            if self.stop_comms(portid):
                if sys.platform == "win32":
                    # Wait for windows to let go of the serial port
                    delay = True

        if delay:
            time.sleep(0.25)

        for portid in self.config.options("ports"):
            self.start_comms(portid)

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
            try:
                sources = stype.enumerate(self.config)
            except Exception, e:
                import utils
                utils.log_exception()
                print "Failed to load source type %s" % stype
                continue

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

        call = self.config.get("user", "callsign")
        gps.set_units(self.config.get("user", "units"))
        mapdisplay.set_base_dir(self.config.get("settings", "mapdir"))
        mapdisplay.set_connected(self.config.getboolean("state",
                                                        "connected_inet"))
        mapdisplay.set_tile_lifetime(self.config.getint("settings",
                                                        "map_tile_ttl") * 3600)
        proxy = self.config.get("settings", "http_proxy") or None
        mapdisplay.set_proxy(proxy)

        self._refresh_comms()
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
            
        self.__map_point.set_icon_from_aprs_sym(fix.APRSIcon)

        self.stations_overlay.add_point(self.__map_point)
        self.map.update_gps_status(self.gps.status_string())

        return True

    def __chat(self, src, dst, data, incoming, port):
        if self.plugsrv:
            self.plugsrv.incoming_chat_message(src, dst, data)

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

        if port:
            portstr = "[%s] " % port
        else:
            portstr = ""

        line = "%s%s%s %s" % (portstr, src, to, data)

        @run_gtk_locked
        def do_incoming():
            self.mainwindow.tabs["chat"].display_line(line, incoming, color)

        gobject.idle_add(do_incoming)

# ---------- STANDARD SIGNAL HANDLERS --------------------

    def __status(self, object, status):
        self.mainwindow.set_status(status)

    def __user_stop_session(self, object, sid, port, force=False):
        print "User did stop session %i (force=%s)" % (sid, force)
        try:
            sm, sc = self.sm[port]
            session = sm.sessions[sid]
            session.close(force)
        except Exception, e:
            print "Session `%i' not found: %s" % (sid, e)
    
    def __user_cancel_session(self, object, sid, port):
        self.__user_stop_session(object, sid, port, True)

    def __user_send_form(self, object, station, port, fname, sname):
        self.sc(port).send_form(station, fname, sname)

    def __user_send_file(self, object, station, port, fname, sname):
        self.sc(port).send_file(station, fname, sname)

    def __user_send_chat(self, object, station, port, msg, raw):
        self.chat_session(port).write(msg)

    def __incoming_chat_message(self, object, src, dst, data, port=None):
        self.__chat(src, dst, data, True, port)

    def __outgoing_chat_message(self, object, src, dst, data, port=None):
        self.__chat(src, dst, data, False, port)

    def __get_station_list(self, object):
        stations = {}
        for port, (sm, sc) in self.sm.items():
            stations[port] = sm.get_heard_stations().keys()

        return stations

    def __get_message_list(self, object, station):
        return self.mainwindow.tabs["messages"].get_shared_messages(station)

    def __submit_rpc_job(self, object, job, port):
        self.rpc_session(port).submit(job)

    def __event(self, object, event):
        self.mainwindow.tabs["event"].event(event)

    def __config_changed(self, object):
        self.refresh_config()

    def __show_map_station(self, object, station):
        print "Showing map"
        self.map.show()

    def __ping_station(self, object, station, port):
        self.chat_session(port).ping_station(station)

    def __ping_station_echo(self, object, station, port,
                            data, callback, cb_data):
        self.chat_session(port).ping_echo_station(station, data,
                                                  callback, cb_data)

    def __ping_request(self, object, src, dst, data, port):
        msg = "%s pinged %s [%s]" % (src, dst, port)
        if data:
            msg += " (%s)" % data

        event = main_events.PingEvent(None, msg)
        self.mainwindow.tabs["event"].event(event)

    def __ping_response(self, object, src, dst, data, port):
        msg = "%s replied to ping from %s with: %s [%s]" % (src, dst,
                                                            data, port)
        event = main_events.PingEvent(None, msg)
        self.mainwindow.tabs["event"].event(event)

    def __incoming_gps_fix(self, object, fix, port):
        ts = self.mainwindow.tabs["event"].last_event_time(fix.station)
        if (time.time() - ts) > 300:
            self.mainwindow.tabs["event"].finalize_last(fix.station)

        fix.set_relative_to_current(self.get_position())
        event = main_events.PosReportEvent(fix.station, str(fix))
        self.mainwindow.tabs["event"].event(event)

        self.mainwindow.tabs["stations"].saw_station(fix.station, port)

        point = map_sources.MapStation(fix.station,
                                       fix.latitude,
                                       fix.longitude,
                                       fix.altitude,
                                       fix.comment)
        point.set_icon_from_aprs_sym(fix.APRSIcon)
        self.stations_overlay.add_point(point)
        self.stations_overlay.save()

    def __station_status(self, object, sta, stat, msg, port):
        self.mainwindow.tabs["stations"].saw_station(sta, port, stat, msg)
        status = station_status.STATUS_MSGS[stat]
        event = main_events.Event(None, 
                                  "%s %s %s %s: %s" % (_("Station"),
                                                       sta,
                                                       _("is now"),
                                                       status,
                                                       msg))
        self.mainwindow.tabs["event"].event(event)

    def __get_current_status(self, object, port):
        return self.mainwindow.tabs["stations"].get_status()

    def __get_current_position(self, object, station):
        if station is None:
            return self.get_position()
        else:
            sources = self.map.get_map_sources()
            for source in sources:
                if source.get_name() == _("Stations"):
                    for point in source.get_points():
                        if point.get_name() == station:
                            fix = gps.GPSPosition(point.get_latitude(),
                                                  point.get_longitude())
                            return fix
                    break
            raise Exception("Station not found")

    def __session_started(self, object, id, msg, port):
        print "[SESSION %i]: %s" % (id, msg)

        event = main_events.SessionEvent(id, port, msg)
        self.mainwindow.tabs["event"].event(event)
        return event

    def __session_status_update(self, object, id, msg, port):
        self.__session_started(object, id, msg, port)

    def __session_ended(self, object, id, msg, restart_info, port):
        event = self.__session_started(object, id, msg, port)
        event.set_restart_info(restart_info)
        event.set_as_final()

        fn = None
        if restart_info:
            fn = restart_info[1]

        self.msgrouter.form_xfer_done(fn, port, True)
        msgrouting.msg_unlock(fn)

    def __form_received(self, object, id, fn, port=None):
        if port:
            id = "%s_%s" % (id, port)

        print "[NEWFORM %s]: %s" % (id, fn)
        f = formgui.FormFile(fn)

        fwd_on = self.config.getboolean("settings", "msg_forward");

        msg = '%s "%s" %s %s' % (_("Message"),
                                 f.get_subject_string(),
                                 _("received from"),
                                 f.get_sender_string())

        dst = f.get_path_dst()
        src = f.get_path_src()

        if fwd_on and \
                "@" not in src and \
                dst != self.config.get("user", "callsign"):
            msg += " (" + _("forwarding to") + " " + dst + ")"
            newfn = os.path.join(self.config.form_store_dir(),
                                 _("Outbox"),
                                 os.path.basename(fn))
            shutil.move(fn, newfn)
            self.mainwindow.tabs["messages"].refresh_if_folder("Outbox")
        else:
            self.mainwindow.tabs["messages"].refresh_if_folder("Inbox")

        event = main_events.FormEvent(id, msg)
        event.set_as_final()
        self.mainwindow.tabs["event"].event(event)

    def __file_received(self, object, id, fn, port=None):
        if port:
            id = "%s_%s" % (id, port)
        _fn = os.path.basename(fn)
        msg = '%s "%s" %s' % (_("File"), _fn, _("Received"))
        event = main_events.FileEvent(id, msg)
        event.set_as_final()
        self.mainwindow.tabs["files"].refresh_local()
        self.mainwindow.tabs["event"].event(event)
                
    def __form_sent(self, object, id, fn, port=None):
        self.msgrouter.form_xfer_done(fn, port, False)
        if port:
            id = "%s_%s" % (id, port)
        print "[FORMSENT %s]: %s" % (id, fn)
        event = main_events.FormEvent(id, _("Message Sent"))
        event.set_as_final()

        self.mainwindow.tabs["messages"].message_sent(fn)
        self.mainwindow.tabs["event"].event(event)

        if not msgrouting.msg_unlock(fn):
            print "ERROR: Failed to unlock form %s" % fn

    def __file_sent(self, object, id, fn, port=None):
        if port:
            id = "%s_%s" % (id, port)
        print "[FILESENT %s]: %s" % (id, fn)
        _fn = os.path.basename(fn)
        msg = '%s "%s" %s' % (_("File"), _fn, _("Sent"))
        event = main_events.FileEvent(id, msg)
        event.set_as_final()
        self.mainwindow.tabs["files"].file_sent(fn)
        self.mainwindow.tabs["event"].event(event)

    def __get_chat_port(self, object):
        return self.mainwindow.tabs["chat"].get_selected_port()

# ------------ END SIGNAL HANDLERS ----------------

    def __connect_object(self, object, *args):
        for signal in object._signals.keys():
            handler = self.handlers.get(signal, None)
            if handler is None:
                raise Exception("Object signal `%s' of object %s not known" % \
                                    (signal, object))
            elif self.handlers[signal]:
                try:
                    object.connect(signal, handler, *args)
                except Exception:
                    print "Failed to attach signal %s" % signal
                    raise

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
            "get-current-position" : self.__get_current_position,
            "session-status-update" : self.__session_status_update,
            "session-started" : self.__session_started,
            "session-ended" : self.__session_ended,
            "file-received" : self.__file_received,
            "form-received" : self.__form_received,
            "file-sent" : self.__file_sent,
            "form-sent" : self.__form_sent,
            "get-chat-port" : self.__get_chat_port,
            }

        global MAINAPP
        MAINAPP = self

        self.comm = None
        self.sm = {}
        self.seen_callsigns = CallList()
        self.position = None
        self.mail_threads = []

        self.config = config.DratsConfig(self)
        self._refresh_lang()

        self.gps = self._static_gps()

        self.map = mapdisplay.MapWindow(self.config)
        self.map.set_title("D-RATS Map Window")
        self.map.connect("reload-sources", lambda m: self._load_map_overlays())
        self.__connect_object(self.map)
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
            status = station_status.STATUS_ONLINE
            for port in self.sm.keys():
                self.chat_session(port).advertise_status(status, msg)

        gobject.timeout_add(3000, self._refresh_location)

    def get_position(self):
        p = self.gps.get_position()
        p.set_station(self.config.get("user", "callsign"))
        try:
            p.set_station(self.config.get("user", "callsign"),
                          self.config.get("settings", "default_gps_comment"))
        except Exception:
            pass
        return p

    def load_static_routes(self):
        routes = self.config.platform.config_file("routes.txt")
        if not os.path.exists(routes):
            return

        f = file(routes)
        lines = f.readlines()
        lno = 0
        for line in lines:
            lno += 1
            if not line.strip() or line.startswith("#"):
                continue

            try:
                routeto, station, port = line.split()
            except Exception:
                print "Line %i of %s not valid" % (lno, routes)
                continue

            self.mainwindow.tabs["stations"].saw_station(station.upper(), port)
            if self.sm.has_key(port):
                sm, sc = self.sm[port]
                sm.manual_heard_station(station)

    def clear_all_msg_locks(self):
        path = os.path.join(self.config.platform.config_dir(),
                            "messages",
                            "*",
                            ".lock*")
        for lock in glob.glob(path):
            print "Removing stale message lock %s" % lock
            os.remove(lock)        

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

        self.clear_all_msg_locks()

        if len(self.config.options("ports")) == 0 and \
                self.config.has_option("settings", "port"):
            print "Migrating single-port config to multi-port"

            port = self.config.get("settings", "port")
            rate = self.config.get("settings", "rate")
            snif = self.config.getboolean("settings", "sniff_packets")
            comp = self.config.getboolean("settings", "compatmode")

            self.config.set("ports",
                            "port_0",
                            "%s,%s,%s,%s,%s,%s" % (True,
                                                   port,
                                                   rate,
                                                   snif,
                                                   comp,
                                                   "DEFAULT"))
            for i in ["port", "rate", "sniff_packets", "compatmode"]:
                self.config.remove_option("settings", i)

        try:
            self.plugsrv = pluginsrv.DRatsPluginServer()
            self.__connect_object(self.plugsrv.get_proxy())
            self.plugsrv.serve_background()
        except Exception, e:
            print "Unable to start plugin server: %s" % e
            self.plugsrv = None

        self.load_static_routes()

        try:
            self.msgrouter = msgrouting.MessageRouter(self.config)
            self.__connect_object(self.msgrouter)
            self.msgrouter.start()
        except Exception, e:
            log_exception()
            self.msgrouter = None

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
            status = station_status.STATUS_OFFLINE
            for port in self.sm.keys():
                self.chat_session(port).advertise_status(status, msg)

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
