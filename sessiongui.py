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

import mainapp
import miscwidgets
import sessionmgr
import sessions

class SessionThread:
    def __init__(self, session, data, gui):
        self.enabled = True
        self.session = session
        self.gui = gui

        self.thread = threading.Thread(target=self.worker, args=(data,))
        self.thread.start()

    def stop(self):
        self.enabled = False
        self.thread.join()

    def worker(self, **args):
        print "**** EMPTY SESSION THREAD ****"

class FileBaseThread(SessionThread):
    progress_key = "recv_size"

    def status_cb(self, vals):
        print "GUI Status:"
        for k,v in vals.items():
            print "   -> %s: %s" % (k, v)

        if vals["total_size"]:
            pct = (float(vals[self.progress_key]) / vals["total_size"]) * 100.0
        else:
            pct = 0.0

        gobject.idle_add(self.gui.update,
                         self.session._id,
                         "%s (%02.0f%%, %i retries)" % (vals["msg"],
                                                        pct,
                                                        vals["retries"]))

    def completed(self):
        gobject.idle_add(self.gui.update,
                         self.session._id,
                         "Transfer Completed")

    def failed(self, reason=None):
        s = "Transfer Failed"
        if reason:
            s += " " + reason

        gobject.idle_add(self.gui.update, self.session._id, s)

    def __init__(self, *args):
        SessionThread.__init__(self, *args)

        self.session.status_cb = self.status_cb

class FileRecvThread(FileBaseThread):
    progress_key = "recv_size"
    
    def worker(self, path):
        if self.session.recv_file(path):
            self.completed()
        else:
            self.failed()

class FileSendThread(FileBaseThread):
    progress_key = "sent_size"

    def worker(self, path):
        if self.session.send_file(path):
            self.completed()
        else:
            self.failed()

class FormRecvThread(FileBaseThread):
    progress_key = "recv_size"

    def worker(self, path):
        fm = self.gui.chatgui.adv_controls["forms"]
        newfn = time.strftime(os.path.join(fm.form_store_dir,
                                           "form_%m%d%Y_%H%M%S.xml"))
        fn = self.session.recv_file(newfn)

        if fn == newfn:
            fm.reg_form("Received from %s" % self.session.get_station(),
                        fn,
                        "Never",
                        fm.get_stamp())
            fm.list_add_form(0,
                             "Received from %s" % self.session.get_station(),
                             fn,
                             stamp="Never",
                             xfert=fm.get_stamp())

            print "Registering form %s" % fn
            self.completed()

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

class SessionGUI:
    def cancel_selected_session(self):
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

        session.close()

    def mh(self, _action):
        action = _action.get_name()

        if action == "cancel":
            self.cancel_selected_session()

    def make_menu(self):
        a = [("cancel", None, "Cancel session", None, None, self.mh)]

        xml = """
<ui>
  <popup name="menu">
    <menuitem action="cancel"/>
  </popup>
</ui>
"""
        ag = gtk.ActionGroup("menu")
        ag.add_actions(a)

        uim = gtk.UIManager()
        uim.insert_action_group(ag, 0)
        uim.add_ui_from_string(xml)

        return uim.get_widget("/menu")

    def mouse_cb(self, view, event, data=None):
        if event.button != 3:
            return

        menu = self.make_menu()
        menu.popup(None, None, None, event.button, event.time)

    def build_list(self):
        cols = [(gobject.TYPE_INT,    gtk.CellRendererText, "ID"),
                (gobject.TYPE_STRING, gtk.CellRendererText, "Name"),
                (gobject.TYPE_STRING, gtk.CellRendererText, "Type"),
                (gobject.TYPE_STRING, gtk.CellRendererText, "Remote Station"),
                (gobject.TYPE_STRING, gtk.CellRendererText, "Status")]

        types = tuple([x for x, y, z in cols])
        self.store = gtk.ListStore(*types)

        self.view = gtk.TreeView(self.store)
        self.view.connect("button_press_event", self.mouse_cb)

        i = 0
        for typ, renderer, caption in cols:
            r = renderer()
            c = gtk.TreeViewColumn(caption, r, text=i)
            c.set_sort_column_id(i)

            self.view.append_column(c)

            i += 1

        self.view.show()

        return self.view

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

    def new_file_xfer(self, session, direction):
        self.chatgui.display_line("File transfer started with %s" % session._st,
                                  "italic")
        if direction == "in":
            dd = self.mainapp.config.get("prefs", "download_dir")
            self.sthreads[session._id] = FileRecvThread(session, dd, self)
        elif direction == "out":
            of = self.outgoing_files.pop()
            self.sthreads[session._id] = FileSendThread(session, of, self)

    def new_form_xfer(self, session, direction):
        self.chatgui.display_line("Form transfer started with %s" % session._st,
                                  "italic")
        if direction == "in":
            dd = self.mainapp.config.form_store_dir()
            self.sthreads[session._id] = FormRecvThread(session, dd, self)
        elif direction == "out":
            of = self.outgoing_forms.pop()
            self.sthreads[session._id] = FormSendThread(session, of, self)

    def new_session(self, type, session, direction):
        iter = self.iter_of(0, session._id)
        if iter:
            self.store.remove(iter)

        iter = self.store.append()
        self.store.set(iter,
                       0, session._id,
                       1, session.name,
                       2, type,
                       3, session._st,
                       4, "Idle")

        print "New session of type: %s" % session.__class__

        if session.__class__ == sessions.FileTransferSession:
            self.new_file_xfer(session, direction)
        elif session.__class__ == sessions.FormTransferSession:
            self.new_form_xfer(session, direction)

    def end_session(self, id):
        iter = self.iter_of(0, id)
        if iter:
            self.store.set(iter,
                           0, -1,
                           4, "Closed")

    def session_cb(self, data, reason, session):
        t = str(session.__class__).replace("Session", "")
        if "." in t:
            t = t.split(".")[1]

        if reason.startswith("new,"):
            self.new_session(t, session, reason.split(",", 2)[1])
        elif reason == "end":
            self.end_session(session._id)

    def send_file(self, dest, filename):
        self.outgoing_files.insert(0, filename)
        print "Outgoing files: %s" % self.outgoing_files

        t = threading.Thread(target=self.mainapp.sm.start_session,
                             kwargs={"name" : os.path.basename(filename),
                                     "dest" : dest,
                                     "cls"  : sessions.FileTransferSession})
        t.start()
        print "Started Session"
        
    def send_form(self, dest, filename):
        self.outgoing_forms.insert(0, filename)
        print "Outgoing forms: %s" % self.outgoing_forms

        t = threading.Thread(target=self.mainapp.sm.start_session,
                             kwargs={"name" : "form",
                                     "dest" : dest,
                                     "cls"  : sessions.FormTransferSession})
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
