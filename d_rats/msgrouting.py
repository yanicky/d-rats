#
# Copyright 2009 Dan Smith <dsmith@danplanet.com>
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
import threading
import time
import os
import smtplib
from glob import glob

try:
    from email.mime.multipart import MIMEMultipart
    from email.mime.base import MIMEBase
    from email.mime.text import MIMEText
except ImportError:
    # Python 2.4
    from email import MIMEMultipart
    from email import MIMEBase
    from email import MIMEText 

import gobject

import formgui
import signals
import emailgw
import utils

CALL_TIMEOUT_RETRY = 300

MSG_LOCK_LOCK = threading.Lock()

def __msg_lockfile(fn):
    name = os.path.basename(fn)
    path = os.path.dirname(fn)
    return os.path.join(path, ".lock.%s" % name)

def msg_is_locked(fn):
    return os.path.exists(__msg_lockfile(fn))

def msg_lock(fn):
    MSG_LOCK_LOCK.acquire()
    if not msg_is_locked(fn):
        file(__msg_lockfile(fn), "w").write("foo")
        success = True
    else:
        success = False
    MSG_LOCK_LOCK.release()

    #print "Locked %s: %s" % (fn, success)
    return success

def msg_unlock(fn):
    success = True
    MSG_LOCK_LOCK.acquire()
    try:
        os.remove(__msg_lockfile(fn))
    except OSError:
        utils.log_exception()
        success = False
    MSG_LOCK_LOCK.release()

    #print "Unlocked %s: %s" % (fn, success)
    return success

def gratuitous_next_hop(route, path):
    path_nodes = path[1:]
    route_nodes = route.split(";")

    if len(path_nodes) >= len(route_nodes):
        print "Nothing left in the routes"
        return None

    for i in range(0, len(path_nodes)):
        if path_nodes[i] != route_nodes[i]:
            print "Path element %i (%s) does not match route %s" % \
                (i, path_nodes[i], route_nodes[i])
            return None

    return route_nodes[len(path_nodes)]


class MessageRoute(object):
    def __init__(self, line):
        self.dest, self.gw, self.port = line.split()

class MessageRouter(gobject.GObject):
    __gsignals__ = {
        "get-station-list" : signals.GET_STATION_LIST,
        "user-send-form" : signals.USER_SEND_FORM,
        "form-sent" : signals.FORM_SENT,
        "ping-station" : signals.PING_STATION,
        }
    _signals = __gsignals__

    def _emit(self, signal, *args):
        gobject.idle_add(self.emit, signal, *args)

    def __init__(self, config):
        gobject.GObject.__init__(self)

        self.__config = config

        self.__sent_call = {}
        self.__sent_port = {}
        self.__file_to_call = {}
        self.__failed_stations = {}
        self.__pinged_stations = {}

        self.__thread = None
        self.__enabled = False

    def _get_routes(self):
        rf = self.__config.platform.config_file("routes.txt")
        try:
            f = file(rf)
            lines = f.readlines()
            f.close()
        except IOError:
            return {}

        routes = {}

        for line in lines:
            if not line.strip() or line.startswith("#"):
                continue
            try:
                dest, gw, port = line.split()
                routes[dest] = gw
            except Exception, e:
                print "Error parsing line '%s': %s" % (line, e)

        return routes

    def _sleep(self):
        t = self.__config.getint("settings", "msg_flush")
        time.sleep(t)

    def _p(self, string):
        print "[MR] %s" % string
        import sys
        sys.stdout.flush()

    def _get_queue(self):
        queue = {}

        qd = os.path.join(self.__config.form_store_dir(), _("Outbox"))
        fl = glob(os.path.join(qd, "*.xml"))
        for f in fl:
            if not msg_lock(f):
                print "Message %s is locked, skipping" % f
                continue

            form = formgui.FormFile(f)
            call = form.get_path_dst()
            del form

            if not call:
                msg_unlock(f)
                continue
            elif not queue.has_key(call):
                queue[call] = [f]
            else:
                queue[call].append(f)
        
        return queue

    def _send_form(self, call, port, filename):
        self.__sent_call[call] = time.time()
        self.__sent_port[port] = time.time()
        self.__file_to_call[filename] = call
        self._emit("user-send-form", call, port, filename, "Foo")

    def _sent_recently(self, call):
        if self.__sent_call.has_key(call):
            return (time.time() - self.__sent_call[call]) < CALL_TIMEOUT_RETRY
        return False

    def _port_free(self, port):
        return not self.__sent_port.has_key(port)

    def _route_msg(self, src, dst, path, slist, routes):
        invalid = []

        def old(call):
            station = slist.get(call, None)
            if not station:
                return True
            ttl = self.__config.getint("settings", "station_msg_ttl")
            return (time.time() - station.get_heard()) > ttl

        while True:
            if ";" in dst:
                # Gratuitous routing takes precedence
                route = gratuitous_next_hop(dst, path)
                print "Route for %s: %s (%s)" % (dst, route, path)
                break
            elif "@" in dst and dst not in invalid and\
                    emailgw.validate_incoming(self.__config, src, dst):
                # Out via email
                route = dst
            elif slist.has_key(dst) and dst not in invalid:
                # Direct send
                route = dst
            elif routes.has_key(dst) and routes[dst] not in invalid:
                # Static route present
                route = routes[dst]
            elif routes.has_key("*") and routes["*"] not in invalid:
                # Default route
                route = routes["*"]
            else:
                route = None
                break

            if route != dst and route in path:
                print "Route %s in path" % route
                invalid.append(route)
                route = None # Don't route to the same location twice
            elif self._is_station_failed(route):
                print "Route %s is failed" % route
                invalid.append(route)
                route = None # This one is not responding lately
            elif old(route) and self._station_pinged_out(route):
                print "Route %s for %s is pinged out" % (route, dst)
                invalid.append(route)
                route = None # This one has been pinged and isn't responding
            else:
                break # We have a route to try

        if old(route) and "@" not in route:
            # This station is heard, but a long time ago.  Ping it first
            # and consider it unrouteable for now
            route_station = slist.get(route, None)
            self._station_pinged_incr(route)
            if route_station:
                self._p("Pinging stale route %s" % route)
                self._emit("ping-station", route, route_station.get_port())
            route = None
        elif route:
            self._station_pinged_clear(dst)
            self._p("Routing message for %s to %s" % (dst, route))
        else:
            self._p("No route for station %s" % dst)

        return route

    def _form_to_email(self, msgfn, replyto):
        form = formgui.FormFile(msgfn)

        if not replyto:
            replyto = "DO_NOT_REPLY@d-rats.com"

        sender = form.get_path_src()
        for i in "<>\"'":
            if i in sender:
                sender = sender.replace(i, "")

        msg = MIMEMultipart()
        msg["Subject"] = form.get_subject_string()
        msg["From"] = '"%s" <%s>' % (sender, replyto)
        msg["To"] = form.get_path_dst()
        msg["Reply-To"] = msg["From"]

        if form.id == "email":
            body = form.get_field_value("message")
        else:
            body = "D-RATS form data attached"

        msg.attach(MIMEText(body))
    
        payload = MIMEBase("d-rats", "form_xml")
        payload.set_payload(form.get_xml())
        payload.add_header("Content-Disposition",
                           "attachment",
                           filename="do_not_open_me")
        msg.attach(payload)

        return msg

    def _route_via_email(self, call, msgfn):
        server = self.__config.get("settings", "smtp_server")
        replyto = self.__config.get("settings", "smtp_replyto")
        tls = self.__config.getboolean("settings", "smtp_tls")
        user = self.__config.get("settings", "smtp_username")
        pwrd = self.__config.get("settings", "smtp_password")
        port = self.__config.getint("settings", "smtp_port")

        msg = self._form_to_email(msgfn, replyto)

        mailer = smtplib.SMTP(server, port)
        mailer.set_debuglevel(1)

        mailer.ehlo()
        if tls:
            mailer.starttls()
            mailer.ehlo()
        if user and pwrd:
            mailer.login(user, pwrd)

        mailer.sendmail(replyto, msg["To"], msg.as_string())
        mailer.quit()
        self._emit("form-sent", -1, msgfn)

        return True

    def _route_via_station(self, call, route, slist, msg):
        if self._sent_recently(route):
            self._p("Call %s is busy" % route)
            return False

        print slist
        port = slist[route].get_port()
        if not self._port_free(port):
            self._p("I think port %s is busy" % port)
            return False # likely already a transfer going here so skip it

        self._p("Sending %s to %s (via %s)" % (msg, call, route))
        self._send_form(route, port, msg)

        return True

    def _run_one(self):
        plist = self.emit("get-station-list")
        slist = {}

        routes = self._get_routes()

        for port, stations in plist.items():
            for station in stations:
                slist[str(station)] = station

        call = self.__config.get("user", "callsign")

        queue = self._get_queue()
        for dst, callq in queue.items():
            for msg in callq:
                form = formgui.FormFile(msg)
                path = form.get_path()
                emok = path[-2:] != ["EMAIL", call]
                src = form.get_path_src()
                del form
    
                route = self._route_msg(src, dst, path, slist, routes)
                if not route:
                    routed = False
                elif "@" in src and "@" in dst:
                    # Don't route a message from email to email
                    routed = False
                elif "@" in route:
                    if emok:
                        routed = self._route_via_email(dst, msg)
                    else:
                        # The path indicates that we received this via
                        # email, so don't send it back out via email
                        routed = False
                else:
                    routed = self._route_via_station(dst, route, slist, msg)
    
                if not routed:
                    msg_unlock(msg)
    
    def _run(self):
        while self.__enabled:
            if self.__config.getboolean("settings", "msg_forward"):
                self._run_one()
            self._sleep()

    def start(self):
        self.__enabled = True
        self.__thread = threading.Thread(target=self._run)
        self.__thread.start()

    def stop(self):
        self.__enabled = False
        self.__thread.join()

    def _update_path(self, fn, call):
        form = formgui.FormFile(fn)
        form.add_path_element(call)
        form.save_to(fn)

    def _station_succeeded(self, call):
        self.__failed_stations[call] = 0

    def _station_failed(self, call):
        self.__failed_stations[call] = self.__failed_stations.get(call, 0) + 1
        print "Fail count for %s is %i" % (call, self.__failed_stations[call])

    def _is_station_failed(self, call):
        return self.__failed_stations.get(call, 0) >= 1

    def _station_pinged_incr(self, call):
        self.__pinged_stations[call] = self.__pinged_stations.get(call, 0) + 1
        return self.__pinged_stations[call]

    def _station_pinged_clear(self, call):
        self.__pinged_stations[call] = 0

    def _station_pinged_out(self, call):
        return self.__pinged_stations.get(call, 0) >= 3

    def form_xfer_done(self, fn, port, failed):
        self._p("File %s on %s done" % (fn, port))

        if fn and msg_is_locked(fn):
            msg_unlock(fn)

        call = self.__file_to_call.get(fn, None)
        if call and self.__sent_call.has_key(call):
            # This callsign completed (or failed) a transfer
            if failed:
                self._station_failed(call)
            else:
                self._station_succeeded(call)
                self._update_path(fn, call)

            del self.__sent_call[call]
            del self.__file_to_call[fn]

        if self.__sent_port.has_key(port):
            # This port is now open for another transfer
            del self.__sent_port[port]

