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

    def __init__(self, *args):
        SessionThread.__init__(self, *args)

        self.session.status_cb = self.status_cb

class FileRecvThread(FileBaseThread):
    progress_key = "recv_size"
    
    def worker(self, path):
        self.session.recv_file(path)
        self.completed()

class FileSendThread(FileBaseThread):
    progress_key = "sent_size"

    def worker(self, path):
        self.session.send_file(path)
        self.completed()

class FormRecvThread(FileBaseThread):
    progress_key = "recv_size"

    def worker(self, path):
        self.session.recv_file(path)
        self.completed()

class FormSendThread(FileBaseThread):
    progress_key = "sent_size"

    def worker(self, path):
        self.session.send_file(path)
        self.completed()

class SessionGUI:
    def build_list(self):
        cols = [(gobject.TYPE_INT, "ID"),
                (gobject.TYPE_STRING, "Name"),
                (gobject.TYPE_STRING, "Type"),
                (gobject.TYPE_STRING, "Remote Station"),
                (gobject.TYPE_STRING, "Status")]

        self.list = miscwidgets.ListWidget(cols)
        self.list.show()

        return self.list

    def build_gui(self):
        self.root = gtk.HBox(False, 2)

        self.root.pack_start(self.build_list())

    def show(self):
        self.root.show()

    def hide(self):
        self.root.hide()

    def update(self, sessionid, status):
        vals = self.list.get_values()
        newvals = []

        for id, name, type, sta, stat in vals:
            if id == sessionid:
                stat = status

            newvals.append((id, name, type, sta, stat))

        self.list.set_values(newvals)

    def refresh(self):
        try:
            if not self.registered:
                self.mainapp.sm.register_session_cb(self.session_cb, None)
                print "Registered Session CB"
                self.registered = True
        except Exception, e:
            print "Failed to register session CB: %s" % e

    def new_file_xfer(self, session, direction):
        self.chatgui.display("File transfer started with %s" % session._st,
                             "italic")
        if direction == "in":
            dd = self.mainapp.config.get("prefs", "download_dir")
            self.sthreads[session._id] = FileRecvThread(session, dd, self)
        elif direction == "out":
            of = self.outgoing_files.pop()
            self.sthreads[session._id] = FileSendThread(session, of, self)

    def new_form_xfer(self, session, direction):
        self.chatgui.display("Form transfer started with %s" % session._st,
                             "italic")
        if direction == "in":
            dd = self.mainapp.config.form_store_dir()
            self.sthreads[session._id] = FormRecvThread(session, dd, self)
        elif direction == "out":
            of = self.outgoing_forms.pop()
            self.sthreads[session._id] = FormSendThread(session, of, self)

    def new_session(self, type, session, direction):
        if self.sthreads.has_key(session._id):
            print "Already know about session %s" % id
            return
        print "New session!!!!"

        self.list.add_item(session._id, session.name, type, session._st, "Idle")

        print "New session of type: %s" % session.__class__

        if session.__class__ == sessions.FileTransferSession:
            self.new_file_xfer(session, direction)
        elif session.__class__ == sessions.FormTransferSession:
            self.new_form_xfer(session, direction)

    def session_cb(self, data, reason, session):
        t = str(session.__class__).replace("Session", "")
        if "." in t:
            t = t.split(".")[1]

        if reason.startswith("new,"):
            self.new_session(t, session, reason.split(",", 2)[1])
        elif reason == "end":
            # FIXME
            pass

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
