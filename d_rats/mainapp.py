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
import comm
import sessionmgr
import sessions
import session_coordinator
import emailgw
import rpcsession

from ui import main_events

from utils import hexprint,filter_to_ascii,NetFile

DRATS_VERSION = "0.2.10"
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

    def incoming_chat(self, data, args):
        sender = args["From"]
        if sender != "CQCQCQ":
            self.seen_callsigns.set_call_time(sender, time.time())

        if args["To"] != "CQCQCQ":
            to = " -> %s:" % args["To"]
        else:
            to = ":"

        if args["From"] == "CQCQCQ":
            color = "brokencolor"
        else:
            color = "incomingcolor"

        line = "%s%s %s" % (sender, to, args["Msg"])
        gobject.idle_add(self.mainwindow.tabs["chat"].display_line, line, color)

    def stop_comms(self):
        if self.sm:
            self.sm.shutdown()
            self.sm = None
            self.chat_session = None

        if self.comm:
            self.comm.disconnect()

    def do_rpcjob(self, session, job):
        print "Got job exec: %s" % job.__class__.__name__
        
        result = {"rc" : "Failed: unsupported"}

        allow_forms = self.config.getboolean("prefs", "allow_remote_forms")
        allow_files = self.config.getboolean("prefs", "allow_remote_files")

        if isinstance(job, rpcsession.RPCPositionReport):
            result = rpcsession.RPC_pos_report(job, self)
        elif isinstance(job, rpcsession.RPCFileListJob):
            if allow_files:
                result = rpcsession.RPC_file_list(job, self)
            else:
                result = {"rc" : "Access denied"}
        elif isinstance(job, rpcsession.RPCPullFileJob):
            if allow_files:
                result = rpcsession.RPC_file_pull(job, self)
            else:
                result = {"rc" : "Access denied"}
        elif isinstance(job, rpcsession.RPCFormListJob):
            if allow_forms:
                result = rpcsession.RPC_form_list(job, self)
            else:
                result = {"rc" : "Access denied"}
        elif isinstance(job, rpcsession.RPCPullFormJob):
            if allow_forms:
                result = rpcsession.RPC_form_pull(job, self)
            else:
                result = {"rc" : "Access denied"}

        job.set_state("complete", result)

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
            self.mainwindow.set_status("Failed to connect %s: %s", (port, e))
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
            self.chat_session.register_cb(self.incoming_chat)

            if self.config.getboolean("settings", "sniff_packets"):
                ss = self.sm.start_session("Sniffer",
                                           dest="CQCQCQ",
                                           cls=sessions.SniffSession)
                self.sm.set_sniffer_session(ss._id)
                ss.connect("incoming_frame",
                           lambda o,m: self.mainwindow.tabs["chat"].display_line(m, "italic"))

            self.rpc_session = self.sm.start_session("rpc",
                                                     dest="CQCQCQ",
                                                     cls=rpcsession.RPCSession)
            self.rpc_session.connect("exec-job", self.do_rpcjob)


            self.sc = session_coordinator.SessionCoordinator(self.config,
                                                             self.sm)

            def TEMP_LOG(sc, id, msg):
                print "[SESSION %i]: %s" % (id, msg)

            def log_session_info(sc, id, msg=None):
                if msg is None:
                    msg = "Ended"

                print "[SESSION %i]: %s" % (id, msg)

                event = main_events.Event(id, msg)
                self.mainwindow.tabs["event"].event(event)

            self.sc.connect("session-started", log_session_info)
            self.sc.connect("session-status-update", log_session_info)
            self.sc.connect("session-ended", log_session_info)

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
                # notify file tab
                self.mainwindow.tabs["event"].event(event)
            self.sc.connect("file-received", new_file)
                
            def form_sent(sc, id, fn):
                print "[FORMSENT %i]: %s" % (id, fn)
                event = main_events.FormEvent(id, "Form Sent")
                event.set_as_final()
                self.mainwindow.tabs["messages"].message_sent(fn)
                self.mainwindow.tabs["event"].event(event)
            self.sc.connect("form-sent", form_sent)

            self.sm.register_session_cb(self.sc.session_cb, None)


            def send_form(msgs, sta, fn, name):
                self.sc.send_form(sta, fn, name)
            self.mainwindow.tabs["messages"].connect("user-send-form",
                                                     send_form)

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
        if self.comm and (self.comm.port != port or self.comm.baud != rate):
            self.stop_comms()
            return self.start_comms()
        elif not self.comm:
            return self.start_comms()
        else:
            print "No comm change from %s@%s" % (port, rate)

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

    def refresh_config(self):
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

        self.mainwindow = mainwindow.MainWindow(self.config)
        self.mainwindow.tabs["chat"].connect("user-sent-message",
                                             self.send_chat)
        
        self.refresh_config()
        
        if self.config.getboolean("prefs", "dosignon"):
            msg = self.config.get("prefs", "signon")
            self.mainwindow.tabs["chat"].display_line(msg)
            self.chat_session.write(msg)

    def get_position(self):
        p = self.gps.get_position()
        p.set_station(self.config.get("user", "callsign"))
        return p

    def main(self):
        # Copy default forms before we start

        distdir = platform.get_platform().source_dir()
        userdir = self.config.form_source_dir()
        dist_forms = glob.glob(os.path.join(distdir, "forms", "*.x?l"))
        print "FORMS: %s (%s)" % (str(dist_forms), distdir)
        for form in dist_forms:
            fname = os.path.basename(form)
            user_fname = os.path.join(userdir, fname)
            
            if not os.path.exists(user_fname):
                print "Installing dist form %s -> %s" % (fname, user_fname)
                try:
                    shutil.copyfile(form, user_fname)
                except Exception, e:
                    print "FAILED: %s" % e
            else:
                print "User has form %s" % fname

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
