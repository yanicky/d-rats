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

import socket
import threading
import time
import os

import gobject

import sessions
import formgui
from utils import run_safe

class SessionThread:
    OUTGOING = False

    def __init__(self, coord, session, data):
        self.enabled = True
        self.coord = coord
        self.session = session
        self.arg = data

        self.thread = threading.Thread(target=self.worker, args=(data,))
        self.thread.setDaemon(True)
        self.thread.start()

    def stop(self):
        self.enabled = False
        self.thread.join()

    def worker(self, **args):
        print "**** EMPTY SESSION THREAD ****"

class FileBaseThread(SessionThread):
    progress_key = "recv_size"

    @run_safe
    def status_cb(self, vals):
        #print "GUI Status:"
        #for k,v in vals.items():
        #    print "   -> %s: %s" % (k, v)

        if vals["total_size"]:
            pct = (float(vals[self.progress_key]) / vals["total_size"]) * 100.0
        else:
            pct = 0.0

        if vals["retries"] > 0:
            retries = " (%i retries)" % vals["retries"]
        else:
            retries = ""

        if vals.has_key("start_time"):
            elapsed = time.time() - vals["start_time"]
            kbytes = vals[self.progress_key]
            speed = " %2.2f B/s" % (kbytes / elapsed)
        else:
            speed = ""

        if vals["sent_wire"]:
            amt = vals["sent_wire"]
            if amt > 1024:
                sent = " (%s %.1f KB)" % (_("Total"), amt >> 10)
            else:
                sent = " (%s %i B)" % (_("Total"), amt)
        else:
            sent = ""

        msg = "%s [%02.0f%%]%s%s%s" % (vals["msg"], pct, speed, sent, retries)

        self.pct_complete = pct

        self.coord.session_status(self.session, msg)

    def completed(self, objname=None):
        self.coord.session_status(self.session, _("Transfer Completed"))

        if objname:
            msg = " of %s" % objname
        else:
            msg = ""

        size = self.session.stats["total_size"]
        if size > 1024:
            size >>= 10
            units = "KB"
        else:
            units = "B"

        if self.session.stats.has_key("start_time"):
            start = self.session.stats["start_time"]
            exmsg = " (%i%s @ %2.2f B/s)" % (\
                size, units,
                self.session.stats["total_size"] /
                (time.time() - start))
        else:
            exmsg = ""

    def failed(self, reason=None):
        s = _("Transfer Interrupted") + \
            " (%.0f%% complete)" % self.pct_complete
        if reason:
            s += " " + reason

        self.coord.session_status(self.session, s)

    def __init__(self, *args):
        SessionThread.__init__(self, *args)

        self.pct_complete = 0.0

        self.session.status_cb = self.status_cb

class FileRecvThread(FileBaseThread):
    progress_key = "recv_size"
    
    def worker(self, path):
        fn = self.session.recv_file(path)
        if fn:
            self.completed("file %s" % os.path.basename(fn))
            self.coord.session_newfile(self.session, fn)
        else:
            self.failed()

class FileSendThread(FileBaseThread):
    OUTGOING = True
    progress_key = "sent_size"

    def worker(self, path):
        if self.session.send_file(path):
            self.completed("file %s" % os.path.basename(path))
        else:
            self.failed()

class FormRecvThread(FileBaseThread):
    progress_key = "recv_size"

    def maybe_send_form(self, form):
        print "Received email form"

        def cb(status, msg):
            self.gui.chatgui.tx_msg("[EMAIL GW] %s" % msg)

        if not self.coord.config.getboolean("settings", "smtp_dogw"):
            print "Not configured as a mail gateway"
            return

        if "EMAIL" in form.get_path():
            print "This form has already been through the internet"
            return

        if not emailgw.validate_outgoing(self.coord.config,
                                         self.session.get_station(),
                                         form.get_field_value("recipient")):
            msg = "Remote station %s " % self.session.get_station() + \
                "not authorized for automatic outbound email service; " + \
                "Message held for local station operator."
            print msg
            cb(False, msg)
            return

        srv = emailgw.FormEmailService(self.coord.config)
        try:
            st, msg = srv.send_email_background(form, cb)
            self.coord.session_status(self.session, msg)
        except Exception, e:
            self.coord.session_status(self.session, msg)

    def worker(self, path):
        md = os.path.join(self.coord.config.platform.config_dir(),
                          "messages", _("Inbox"))
        newfn = time.strftime(os.path.join(md, "form_%m%d%Y_%H%M%S.xml"))
        fn = self.session.recv_file(newfn)

        name = "%s %s %s" % (self.session.name,
                               _("from"),
                               self.session.get_station())

        if fn == newfn:
            form = formgui.FormFile(None, fn)
            form.add_path_element(self.coord.config.get("user", "callsign"))
            form.save_to(fn)

            self.coord.session_newform(self.session, fn)

            # FIXME: Handle this elsewhere
            #if form.id == "email":
            #    self.maybe_send_form(form)

            self.completed("form")

        else:
            self.failed()
            print "<--- Form transfer failed -->"

class FormSendThread(FileBaseThread):
    OUTGOING = True
    progress_key = "sent_size"

    def worker(self, path):
        if self.session.send_file(path):
            self.completed()
        else:
            self.failed()

class SocketThread(SessionThread):
    def status(self):
        vals = self.session.stats

        if vals["retries"] > 0:
            retries = " (%i %s)" % (vals["retries"], _("retries"))
        else:
            retries = ""


        msg = "%i %s %s %i %s %s%s" % (vals["sent_size"],
                                       _("bytes"), _("sent"),
                                       vals["recv_size"],
                                       _("bytes"), _("received"),
                                       retries)
        self.coord.session_status(self.session, msg)

    def socket_read(self, sock, length, to=5):
        data = ""
        t = time.time()

        while (time.time() - t) < to :
            d = ""

            try:
                d = sock.recv(length - len(d))
            except socket.timeout:
                continue

            if not d and not data:
                raise Exception("Socket is closed")

            data += d

        return data

    def worker(self, data):
        (sock, timeout) = data

        print "*** Socket thread alive (%i timeout)" % timeout

        sock.settimeout(timeout)

        while self.enabled:
            t = time.time()
            try:
                sd = self.socket_read(sock, 512, timeout)
            except Exception, e:
                print str(e)
                break
            print "Waited %f sec for socket" % (time.time() - t)

            try:
                rd = self.session.read(512)
            except sessionmgr.SessionClosedError, e:
                print "Session closed"
                self.enabled = False
                break

            self.status()

            if sd:
                print "Sending socket data (%i)" % len(sd)
                self.session.write(sd)

            if rd:
                print "Sending radio data (%i)" % len(rd)
                sock.sendall(rd)
        
        print "Closing session"

        self.session.close()
        try:
            sock.close()
        except:
            pass

        print "*** Socket thread exiting"
                




class SessionCoordinator(gobject.GObject):
    __gsignals__ = {
        "session-status-update" : (gobject.SIGNAL_RUN_LAST,
                                   gobject.TYPE_NONE,
                                   (gobject.TYPE_INT, gobject.TYPE_STRING)),
        "session-started" : (gobject.SIGNAL_RUN_LAST,
                             gobject.TYPE_NONE,
                             (gobject.TYPE_INT, gobject.TYPE_STRING)),
        "session-ended" : (gobject.SIGNAL_RUN_LAST,
                           gobject.TYPE_NONE,
                           (gobject.TYPE_INT,)),
        "file-received" : (gobject.SIGNAL_RUN_LAST,
                           gobject.TYPE_NONE,
                           (gobject.TYPE_INT, gobject.TYPE_STRING)),
        "form-received" : (gobject.SIGNAL_RUN_LAST,
                           gobject.TYPE_NONE,
                           (gobject.TYPE_INT, gobject.TYPE_STRING)),

        }

    def session_status(self, session, msg):
        self.emit("session-status-update", session._id, msg)

    def session_newform(self, session, path):
        self.emit("form-received", session._id, path)

    def session_newfile(self, session, path):
        self.emit("file-received", session._id, path)

    def cancel_session(self, id, force=False):
        if id < 2:
            # Don't let them cancel Control or Chat
            return

        try:
            session = self.sm.sessions[id]
        except Exception, e:
            print "Session `%i' not found: %s" % (id, e)
            return        

        if self.sthreads.has_key(id):
            del self.sthreads[id]
        session.close(force)

    def create_socket_listener(self, sport, dport, dest):
        if dport not in self.socket_listeners.keys():
            print "Starting a listener for port %i->%s:%i" % (sport,
                                                              dest,
                                                              dport)
            self.socket_listeners[dport] = \
                sessions.SocketListener(self.sm, dest, sport, dport)
            print "Started"
        else:
            raise Exception("Listener for %i already active" % dport)

    def new_file_xfer(self, session, direction):
        msg = _("File transfer of %s started with %s") % (session.name,
                                                          session._st)
        self.emit("session-status-update", session._id, msg)

        if direction == "in":
            dd = self.config.get("prefs", "download_dir")
            self.sthreads[session._id] = FileRecvThread(self, session, dd)
        elif direction == "out":
            of = self.outgoing_files.pop()
            self.sthreads[session._id] = FileSendThread(self, session, of)

    def new_form_xfer(self, session, direction):
        msg = _("Message transfer of %s started with %s") % (session.name,
                                                             session._st)
        self.emit("session-status-update", session._id, msg)

        if direction == "in":
            dd = self.config.form_store_dir()
            self.sthreads[session._id] = FormRecvThread(self, session, dd)
        elif direction == "out":
            of = self.outgoing_forms.pop()
            self.sthreads[session._id] = FormSendThread(self, session, of)

    def new_socket(self, session, direction):
        msg = _("Socket session %s started with %s") % (session.name,
                                                        session._st)
        self.emit("session-status-update", session._id, msg)

        to = float(self.config.get("settings", "sockflush"))

        try:
            foo, port = session.name.split(":", 2)
            port = int(port)
        except Exception, e:
            print "Invalid socket session name %s: %s" % (session.name, e)
            session.close()
            return

        if direction == "in":
            try:
                ports = self.config.options("tcp_in")
                for _portspec in ports:
                    portspec = self.config.get("tcp_in", _portspec)
                    p, h = portspec.split(",")
                    p = int(p)
                    if p == port:
                        sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
                        sock.connect((h, port))
                        self.sthreads[session._id] = SocketThread(self,
                                                                  session,
                                                                  (sock, to))
                        return

                raise Exception("Port %i not configured" % port)
            except Exception, e:
                msg = _("Error starting socket session: %s") % e
                self.emit("session-status-update", session._id, msg)
                session.close()

        elif direction == "out":
            sock = self.socket_listeners[port].dsock
            self.sthreads[session._id] = SocketThread(self, session, (sock, to))

    def new_session(self, type, session, direction):
        print "New session (%s) of type: %s" % (direction, session.__class__)
        self.emit("session-started", session._id, type)

        if isinstance(session, sessions.BaseFormTransferSession):
            self.new_form_xfer(session, direction)
        elif isinstance(session, sessions.BaseFileTransferSession):
            self.new_file_xfer(session, direction)
        elif isinstance(session, sessions.SocketSession):
            self.new_socket(session, direction)
        else:
            print "*** Unknown session type: %s" % session.__class__.__name__

    def end_session(self, id):
        self.emit("session-ended", id)

        if self.sthreads.has_key(id):
            sthread = self.sthreads[id]
            session = sthread.session
            del self.sthreads[id]

    def session_cb(self, data, reason, session):
        t = str(session.__class__.__name__).replace("Session", "")
        if "." in t:
            t = t.split(".")[2]

        print "Session GUI callback: %s %s" % (reason, session._id)
            
        if reason.startswith("new,"):
            self.new_session(t, session, reason.split(",", 2)[1])
        elif reason == "end":
            self.end_session(session._id)

    def send_file(self, dest, filename, name=None):
        if name is None:
            name = os.path.basename(filename)

        self.outgoing_files.insert(0, filename)
        print "Outgoing files: %s" % self.outgoing_files

        if self.config.getboolean("settings", "pipelinexfers"):
            xfer = sessions.PipelinedFileTransfer
        else:
            xfer = sessions.FileTransferSession

        bs = self.config.getint("settings", "ddt_block_size")
        ol = self.config.getint("settings", "ddt_block_outlimit")

        t = threading.Thread(target=self.sm.start_session,
                             kwargs={"name"      : name,
                                     "dest"      : dest,
                                     "cls"       : xfer,
                                     "blocksize" : bs,
                                     "outlimit"  : ol})
        t.start()
        print "Started Session"
        
    def send_form(self, dest, filename, name="Form"):
        self.outgoing_forms.insert(0, filename)
        print "Outgoing forms: %s" % self.outgoing_forms

        if self.config.getboolean("settings", "pipelinexfers"):
            xfer = sessions.PipelinedFormTransfer
        else:
            xfer = sessions.FormTransferSession

        t = threading.Thread(target=self.sm.start_session,
                             kwargs={"name" : name,
                                     "dest" : dest,
                                     "cls"  : xfer})
        t.start()
        print "Started form session"

    def __init__(self, config, sm):
        gobject.GObject.__init__(self)

        self.sm = sm
        self.config = config

        self.sthreads = {}

        self.outgoing_files = []
        self.outgoing_forms = []

        self.socket_listeners = {}
