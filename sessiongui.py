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

import mainapp
import miscwidgets
import sessionmgr
import sessions

class SessionThread:
    def __init__(self, session, data):
        self.enabled = True
        self.session = session

        self.thread = threading.Thread(target=self.worker, args=(data,))
        self.thread.start()

    def stop(self):
        self.enabled = False
        self.thread.join()

class FileRecvThread(SessionThread):
    def worker(self, path):
        print "----------> receiving file"
        self.session.recv_file(path)
        print "----------> done receiving file"

class SessionGUI:
    def build_list(self):
        cols = [(gobject.TYPE_STRING, "Name"),
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

    def refresh(self):
        try:
            if not self.registered:
                self.mainapp.sm.register_session_cb(self.session_cb, None)
                print "Registered Session CB"
                self.registered = True
        except Exception, e:
            print "Failed to register session CB: %s" % e

    def new_session(self, type, session):
        self.list.add_item(session.name, type, session._st, "Idle")

        if isinstance(session, sessionmgr.FileTransferSession):
            self.sthreads.append(FileRecvThread(session, "/tmp"))

    def session_cb(self, data, reason, session):
        t = str(session.__class__).replace("Session", "")
        if "." in t:
            t = t.split(".")[1]

        if reason == "new":
            self.new_session(t, session)
        elif reason == "end":
            # FIXME
            pass

    def __init__(self, chatgui):
        self.chatgui = chatgui
        self.mainapp = mainapp.get_mainapp()
        self.build_gui()

        self.sthreads = []
        self.registered = False

