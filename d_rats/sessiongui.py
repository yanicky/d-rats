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
import threading
import os
import time
import socket

import mainapp
import miscwidgets
import sessionmgr
import sessions
import formgui
import emailgw
import rpcsession

from utils import run_safe

def gui_display(gui, *args):
    gobject.idle_add(gui.display_line, *args)

class SessionThread:
    def __init__(self, session, data, gui):
        self.enabled = True
        self.session = session
        self.gui = gui

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

        gobject.idle_add(self.gui.update,
                         self.session._id,
                         msg)

    def completed(self, objname=None):
        gobject.idle_add(self.gui.update,
                         self.session._id,
                         _("Transfer Completed"))

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

        gui_display(self.gui.chatgui,
                    "%s%s %s%s" % (_("Transfer"), msg, _("complete"), exmsg),
                    "italic")

    def failed(self, reason=None):
        s = _("Transfer Failed")
        if reason:
            s += " " + reason

        gobject.idle_add(self.gui.update, self.session._id, s)

        gui_display(self.gui.chatgui, s, "italic")

    def __init__(self, *args):
        SessionThread.__init__(self, *args)

        self.session.status_cb = self.status_cb

class FileRecvThread(FileBaseThread):
    progress_key = "recv_size"
    
    def worker(self, path):
        fn = self.session.recv_file(path)
        if fn:
            self.completed("file %s" % os.path.basename(fn))
        else:
            self.failed()

class FileSendThread(FileBaseThread):
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

        if not self.gui.chatgui.config.getboolean("settings", "smtp_dogw"):
            print "Not configured as a mail gateway"
            return

        if "EMAIL" in form.get_path():
            print "This form has already been through the internet"
            return

        if not emailgw.validate_outgoing(self.gui.chatgui.config,
                                         self.session.get_station(),
                                         form.get_field_value("recipient")):
            msg = "Remote station %s " % self.session.get_station() + \
                "not authorized for automatic outbound email service; " + \
                "Message held for local station operator."
            print msg
            cb(False, msg)
            return

        srv = emailgw.FormEmailService(self.gui.chatgui.config)
        try:
            st, msg = srv.send_email_background(form, cb)
            gui_display(self.gui.chatgui, msg)
        except Exception, e:
            gui_display(self.gui.chatgui, str(e))
        

    def worker(self, path):
        fm = self.gui.chatgui.adv_controls["forms"]
        newfn = time.strftime(os.path.join(fm.form_store_dir,
                                           "form_%m%d%Y_%H%M%S.xml"))
        fn = self.session.recv_file(newfn)

        name = "%s %s %s" % (self.session.name,
                               _("from"),
                               self.session.get_station())

        if fn == newfn:
            form = formgui.FormFile(None, fn)
            form.add_path_element(self.gui.chatgui.config.get("user",
                                                              "callsign"))
            form.save_to(fn)
            if form.id == "email":
                self.maybe_send_form(form)

            fm.reg_form(name,
                        fn,
                        _("Never"),
                        fm.get_stamp())
            fm.list_add_form(0,
                             name,
                             fn,
                             stamp=_("Never"),
                             xfert=fm.get_stamp())

            print "Registering form %s" % fn
            self.completed("form")

        else:
            self.failed()
            print "<--- Form transfer failed -->"

class FormSendThread(FileBaseThread):
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

        gobject.idle_add(self.gui.update,
                         self.session._id,
                         msg)

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
                

class SessionGUI:
    def cancel_selected_session(self, force=False):
        (list, iter) = self.view.get_selection().get_selected()

        id = int(list.get(iter, 0)[0])

        print "Cancel ID: %s" % id

        if id < 2:
            # Don't let them cancel Control or Chat
            return

        try:
            session = self.mainapp.sm.sessions[id]
        except Exception, e:
            print "Session `%i' not found: %s" % (id, e)
            return        

        session.close(force)

    def clear_selected_session(self):
        (list, iter) = self.view.get_selection().get_selected()
        list.remove(iter)

    def clear_all_finished_sessions(self):
        iter = self.store.get_iter_first()

        while iter is not None:
            tmp = self.store.iter_next(iter)

            (id,) = self.store.get(iter, 0)
            if id == -1:
                self.store.remove(iter)
            iter = tmp

    def mh(self, _action):
        action = _action.get_name()

        if action == "cancel":
            self.cancel_selected_session()
        elif action == "forcecancel":
            self.cancel_selected_session(force=True)
        elif action == "clear":
            self.clear_selected_session()
        elif action == "clearall":
            self.clear_all_finished_sessions()

    def make_menu(self):
        (list, iter) = self.view.get_selection().get_selected()

        xml = """
<ui>
  <popup name="menu">
    <menuitem action="cancel"/>
    <menuitem action="forcecancel"/>
    <menuitem action="clear"/>
    <menuitem action="clearall"/>
  </popup>
</ui>
"""

        ag = gtk.ActionGroup("menu")

        cancel = gtk.Action("cancel", _("Cancel"), None, None)
        cancel.connect("activate", self.mh)
        ag.add_action(cancel)

        fcancel = gtk.Action("forcecancel", _("Cancel (without ACK)"), None, None)
        fcancel.connect("activate", self.mh)
        ag.add_action(fcancel)

        clear = gtk.Action("clear", _("Clear"), None, None)
        clear.connect("activate", self.mh)
        ag.add_action(clear)

        clearall = gtk.Action("clearall", _("Clear all finished"), None, None)
        clearall.connect("activate", self.mh)
        ag.add_action(clearall)

        if iter:
            id = list.get(iter, 0)[0]
        else:
            id = None

        if id is None:
            cancel.set_sensitive(False)
            fcancel.set_sensitive(False)
            clear.set_sensitive(False)

        if id == -1:
            cancel.set_sensitive(False)
            fcancel.set_sensitive(False)
        else:
            clear.set_sensitive(False)

        if id is not None and id < 2:
            cancel.set_sensitive(False)
            fcancel.set_sensitive(False)

        uim = gtk.UIManager()
        uim.insert_action_group(ag, 0)
        uim.add_ui_from_string(xml)

        return uim.get_widget("/menu")

    def mouse_cb(self, view, event, data=None):
        if event.button != 3:
            return

        if event.window == view.get_bin_window():
            x, y = event.get_coords()
            pathinfo = view.get_path_at_pos(int(x), int(y))
            if pathinfo is None:
                return
            else:
                view.set_cursor_on_cell(pathinfo[0])
                
        menu = self.make_menu()
        if menu:
            menu.popup(None, None, None, event.button, event.time)

    def build_list(self):
        cols = [(gobject.TYPE_INT,    gtk.CellRendererText, _("ID")),
                (gobject.TYPE_STRING, gtk.CellRendererText, _("Name")),
                (gobject.TYPE_STRING, gtk.CellRendererText, _("Type")),
                (gobject.TYPE_STRING, gtk.CellRendererText, _("Remote Station")),
                (gobject.TYPE_STRING, gtk.CellRendererText, _("Status"))]

        types = tuple([x for x, y, z in cols])
        self.store = gtk.ListStore(*types)

        self.view = gtk.TreeView(self.store)
        self.view.connect("button_press_event", self.mouse_cb)

        sw = gtk.ScrolledWindow()
        sw.set_policy(gtk.POLICY_AUTOMATIC, gtk.POLICY_AUTOMATIC)
        sw.add(self.view)

        i = 0
        for typ, renderer, caption in cols:
            r = renderer()
            c = gtk.TreeViewColumn(caption, r, text=i)
            c.set_sort_column_id(i)

            self.view.append_column(c)

            i += 1

        def render_id(col, rend, model, iter, colnum):
            v = model.get_value(iter, colnum)
            if v < 3:
                rend.set_property("text", "")
            else:
                rend.set_property("text", "%i" % v)
            
        idc = self.view.get_column(0)
        idr = idc.get_cell_renderers()[0]
        idc.set_cell_data_func(idr, render_id, 0)

        self.view.show()
        sw.show()

        return sw

    def build_gui(self):
        self.root = gtk.HBox(False, 2)

        self.root.pack_start(self.build_list())

    def show(self):
        self.root.show()

    def hide(self):
        self.root.hide()

    def iter_of(self, col, match):
        iter = self.store.get_iter_first()

        while iter is not None:
            val = self.store.get(iter, col)[0]
            if val == match:
                return iter

            iter = self.store.iter_next(iter)

        return None

    def update(self, sessionid, status):
        iter = self.iter_of(0, sessionid)
        if iter:
            self.store.set(iter, 4, status)

    def refresh(self):
        try:
            self.store.clear()
            self.mainapp.sm.register_session_cb(self.session_cb, None)
            print "Registered Session CB"
            self.registered = True
        except Exception, e:
            print "Failed to register session CB: %s" % e

        try:
            ports = self.mainapp.config.options("tcp_out")

            for l in self.socket_listeners.values():
                l.stop()
                del self.socket_listeners[l.dport]

            print "Refresh listeners: %s" % self.socket_listeners

            for _port in ports:
                port = self.mainapp.config.get("tcp_out", _port)
                sport, dport, dest = port.split(",")
                sport = int(sport)
                dport = int(dport)
                if dport not in self.socket_listeners.keys():
                    print "Starting a listener for port %i->%s:%i" % (sport,
                                                                      dest,
                                                                      dport)
                    self.socket_listeners[dport] = \
                        sessions.SocketListener(self.mainapp.sm,
                                                dest,
                                                sport,
                                                dport)
                    print "Started"

        except Exception, e:
            print "Failed to start listeners: %s" % e

        print "Done with sessiongui refresh"

    def new_file_xfer(self, session, direction):
        gui_display(self.chatgui,
                    _("File transfer started with") + " %s (%s)" % (session._st,
                                                                    session.name),
                    "italic")

        if direction == "in":
            dd = self.mainapp.config.get("prefs", "download_dir")
            self.sthreads[session._id] = FileRecvThread(session, dd, self)
        elif direction == "out":
            of = self.outgoing_files.pop()
            self.sthreads[session._id] = FileSendThread(session, of, self)

    def new_form_xfer(self, session, direction):
        gui_display(self.chatgui,
                    _("Form transfer started with") + " %s (%s)" % (session._st,
                                                                    session.name),
                    "italic")

        if direction == "in":
            dd = self.mainapp.config.form_store_dir()
            self.sthreads[session._id] = FormRecvThread(session, dd, self)
        elif direction == "out":
            of = self.outgoing_forms.pop()
            self.sthreads[session._id] = FormSendThread(session, of, self)

    def new_socket(self, session, direction):
        gui_display(self.chatgui,
                    _("Socket session started with") + " %s (%s)" % (session._st,
                                                                     session.name),
                    "italic")

        to = float(self.mainapp.config.get("settings", "sockflush"))

        try:
            foo, port = session.name.split(":", 2)
            port = int(port)
        except Exception, e:
            print "Invalid socket session name %s: %s" % (session.name, e)
            session.close()
            return

        if direction == "in":
            try:
                ports = self.mainapp.config.options("tcp_in")
                for _portspec in ports:
                    portspec = self.mainapp.config.get("tcp_in", _portspec)
                    p, h = portspec.split(",")
                    p = int(p)
                    if p == port:
                        sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
                        sock.connect((h, port))
                        self.sthreads[session._id] = SocketThread(session,
                                                                  (sock, to),
                                                                  self)
                        return

                raise Exception("Port %i not configured" % port)
            except Exception, e:
                gui_display(self.chatgui,
                            _("Error starting socket session") + ": %s" % e,
                            "italic",
                            "red")
                session.close()

        elif direction == "out":
            sock = self.socket_listeners[port].dsock

            self.sthreads[session._id] = SocketThread(session, (sock, to), self)

    def new_session(self, type, session, direction):
        print "New session (%s) of type: %s" % (direction, session.__class__)

        iter = self.iter_of(0, session._id)
        if iter:
            self.store.remove(iter)

        iter = self.store.append()
        self.store.set(iter,
                       0, session._id,
                       1, session.name,
                       2, type,
                       3, session._st,
                       4, _("Idle"))

        if isinstance(session, sessions.BaseFormTransferSession):
            self.new_form_xfer(session, direction)
        elif isinstance(session, sessions.BaseFileTransferSession):
            self.new_file_xfer(session, direction)
        elif isinstance(session, sessions.SocketSession):
            self.new_socket(session, direction)
        else:
            print "*** Unknown session type: %s" % session.__class__.__name__

    def end_session(self, id):
        print "session ended"
        iter = self.iter_of(0, id)
        if iter:
            self.store.remove(iter)
        else:
            print "No iter"

    def session_cb(self, data, reason, session):
        t = str(session.__class__.__name__).replace("Session", "")
        if "." in t:
            t = t.split(".")[2]

        print "Session GUI callback: %s %s" % (reason, session._id)
            
        if reason.startswith("new,"):
            self.new_session(t, session, reason.split(",", 2)[1])
        elif reason == "end":
            self.end_session(session._id)

    def send_file(self, dest, filename):
        self.outgoing_files.insert(0, filename)
        print "Outgoing files: %s" % self.outgoing_files

        if self.mainapp.config.getboolean("settings", "pipelinexfers"):
            xfer = sessions.PipelinedFileTransfer
        else:
            xfer = sessions.FileTransferSession

        bs = self.mainapp.config.getint("settings", "ddt_block_size")
        ol = self.mainapp.config.getint("settings", "ddt_block_outlimit")

        t = threading.Thread(target=self.mainapp.sm.start_session,
                             kwargs={"name"      : os.path.basename(filename),
                                     "dest"      : dest,
                                     "cls"       : xfer,
                                     "blocksize" : bs,
                                     "outlimit"  : ol})
        t.start()
        print "Started Session"
        
    def send_form(self, dest, filename, name="Form"):
        self.outgoing_forms.insert(0, filename)
        print "Outgoing forms: %s" % self.outgoing_forms

        if self.mainapp.config.getboolean("settings", "pipelinexfers"):
            xfer = sessions.PipelinedFormTransfer
        else:
            xfer = sessions.FormTransferSession

        t = threading.Thread(target=self.mainapp.sm.start_session,
                             kwargs={"name" : name,
                                     "dest" : dest,
                                     "cls"  : xfer})
        t.start()
        print "Started form session"

    def __init__(self, chatgui):
        self.chatgui = chatgui
        self.mainapp = mainapp.get_mainapp()
        self.build_gui()

        self.sthreads = {}
        self.registered = False

        self.outgoing_files = []
        self.outgoing_forms = []

        self.socket_listeners = {}
