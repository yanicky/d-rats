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
import sys

if sys.platform == "darwin":
    os.environ["PANGO_RC_FILE"] = "../Resources/etc/pango/pangorc"

import time
import re
from threading import Thread, Lock
from select import select
import socket
from commands import getstatusoutput

import serial
import gtk
import gobject

import chatgui
import config
import ddt
import gps
import mapdisplay
import comm
import sessionmgr
import sessions
import emailgw

from utils import hexprint,filter_to_ascii,NetFile
import qst

DRATS_VERSION = "0.2.7"
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

    def refresh_qsts(self):
        for i in self.qsts:
            print "Disabling QST %s" % i.text
            i.disable()
            print "Done"

        self.qsts = []

        sections = self.config.config.sections()
        qsts = [x for x in sections if x.startswith("qst_")]

        for i in qsts:
            print "Doing QST %s" % i
            text = self.config.get(i, "content")
            freq = self.config.get(i, "freq")
            qtyp = self.config.get(i, "type")
            enab = self.config.getboolean(i, "enabled")

            if not enab:
                continue
            
            qstclass = qst.get_qst_class(qtyp)
            if not qstclass:
                print "Unknown QST type: %s" % qtyp
                continue
            
            qstinst = qstclass(self.chatgui, self.config,
                               text=text, freq=freq)
            qstinst.enable()

            self.qsts.append(qstinst)

    def connected(self, is_connected):
        self.chatgui.set_connected(is_connected)

    def incoming_chat(self, data, args):
        sender = args["From"]
        if sender != "CQCQCQ":
            self.seen_callsigns.set_call_time(sender, time.time())
            gobject.idle_add(self.chatgui.adv_controls["calls"].refresh)

        if args["To"] != "CQCQCQ":
            to = " -> %s:" % args["To"]
        else:
            to = ":"

        if args["From"] == "CQCQCQ":
            color = "brokencolor"
        else:
            color = "incomingcolor"

        line = "%s%s %s" % (sender, to, args["Msg"])
        gobject.idle_add(self.chatgui.display_line, line, color)

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
                           lambda o,m: self.chatgui.display(m, "italic"))
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

    def refresh_comms(self):
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
            print "Invalid static position: %s" % e

        print "Static position: %s,%s" % (lat,lon)
        return gps.StaticGPSSource(lat, lon, alt)

    def refresh_gps(self):
        port = self.config.get("settings", "gpsport")
        enab = self.config.getboolean("settings", "gpsenabled")

        print "GPS: %s on %s" % (enab, port)

        if enab:
            if self.gps:
                self.gps.stop()

            if port.startswith("net:"):
                self.gps = gps.NetworkGPSSource(port)
            else:
                self.gps = gps.GPSSource(port)
            self.gps.start()
        else:
            if self.gps:
                self.gps.stop()

            self.gps = self._static_gps()

    def refresh_mail_threads(self):
        for i in self.mail_threads:
            i.stop()

        if self.config.get("settings", "pop3_server"):
            t = emailgw.MailThread(self.config,
                                   self.chatgui.adv_controls["forms"])
            t.start()
            self.mail_threads.append(t)

    def refresh_config(self):
        rate = self.config.getint("settings", "rate")
        port = self.config.get("settings", "port")
        call = self.config.get("user", "callsign")
        enc = self.config.get("settings", "encoding")
        com = self.config.getboolean("settings", "compression")
        units = self.config.get("user", "units")

        ddt.set_compression(com)
        ddt.set_encoding(enc)

        gps.set_units(units)
        mapdisplay.set_base_dir(self.config.get("settings", "mapdir"))

        self.refresh_comms()

        self.chatgui.display("My Call: %s\n" % call, "blue", "italic")

        self.refresh_qsts()
        self.refresh_gps()
        self.chatgui.refresh_config()
        self.refresh_mail_threads()

    def maybe_redirect_stdout(self):
        try:
            if self.config.getboolean("prefs", "debuglog"):
                dir = self.config.get("prefs", "download_dir")
                logfile = os.path.join(dir, "debug.log")
                sys.stdout = file(logfile, "w", 0)
                sys.stderr = sys.stdout
            elif os.name == "nt":
                class Blackhole(object):
                    softspace=0
                    def write(self, text):
                        pass

                sys.stdout = Blackhole()
                sys.stderr = Blackhole()
                del Blackhole

        except Exception, e:
            print "Unable to open debug log: %s" % e

    def TEMP_migrate_config(self):
        import platform

        if os.name != "posix":
            return

        p = platform.get_platform()
        fn = p.config_file("drats.config")
        if os.path.exists(fn):
            print "Migrating broken UNIX config filename"
            newfn = p.config_file("d-rats.config")
            os.rename(fn, newfn)            
            
    def __init__(self, **args):
        global MAINAPP
        MAINAPP = self

        self.comm = None
        self.sm = None
        self.chat_session = None
        self.qsts = []
        self.seen_callsigns = CallList()
        self.position = None
        self.mail_threads = []

        # REMOVE ME in 0.1.13
        self.TEMP_migrate_config()

        self.config = config.AppConfig(self, **args)

        self.gps = self._static_gps()

        self.maybe_redirect_stdout()

        self.chatgui = chatgui.MainChatGUI(self.config, self)

        self.chatgui.display("D-RATS v%s " % DRATS_VERSION, "red")
        self.chatgui.display("(Copyright 2008 Dan Smith KK7DS)\n",
                             "blue", "italic")
        
        self.refresh_config()
        
        if self.config.getboolean("prefs", "dosignon"):
            self.chatgui.tx_msg(self.config.get("prefs", "signon"))
            
    def get_position(self):
        p = self.gps.get_position()
        p.set_station(self.config.get("user", "callsign"))
        return p

    def main(self):
        try:
            gtk.main()
        except KeyboardInterrupt:
            pass
        except Exception, e:
            print "Got exception on close: %s" % e

        print "Saving config..."
        self.config.save()
        self.chatgui.save_static_locations()

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
