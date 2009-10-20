#!/usr/bin/python
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

import os
import time
import shutil
import random
from datetime import datetime

import gobject
import gtk

from ConfigParser import ConfigParser
from glob import glob

from d_rats.ui.main_common import MainWindowElement, MainWindowTab
from d_rats.ui.main_common import prompt_for_station, ask_for_confirmation, \
    display_error, prompt_for_string
from d_rats.ui import main_events
from d_rats import inputdialog
from d_rats import formgui
from d_rats import emailgw
from d_rats.utils import log_exception
from d_rats import signals
from d_rats import msgrouting

_FOLDER_CACHE = {}

def mkmsgid(callsign):
    r = random.SystemRandom().randint(0,100000)
    return "%s.%x.%x" % (callsign, int(time.time()) - 1114880400, r)

class MessageFolderInfo(object):
    def __init__(self, folder_path):
        self._path = folder_path

        if _FOLDER_CACHE.has_key(folder_path):
            self._config = _FOLDER_CACHE[folder_path]
        else:
            self._config = ConfigParser()
            regpath = os.path.join(self._path, ".db")
            if os.path.exists(regpath):
                self._config.read(regpath)
            self._save()
            _FOLDER_CACHE[folder_path] = self._config

    def _save(self):
        regpath = os.path.join(self._path, ".db")
        f = file(regpath, "w")
        self._config.write(f)
        f.close()

    def name(self):
        """Return folder name"""
        return os.path.basename(self._path)

    def _setprop(self, filename, prop, value):
        filename = os.path.basename(filename)

        if not self._config.has_section(filename):
            self._config.add_section(filename)

        self._config.set(filename, prop, value)
        self._save()

    def _getprop(self, filename, prop):
        filename = os.path.basename(filename)

        try:
            return self._config.get(filename, prop)
        except Exception:
            return _("Unknown")

    def get_msg_subject(self, filename):
        return self._getprop(filename, "subject")

    def set_msg_subject(self, filename, subject):
        self._setprop(filename, "subject", subject)

    def get_msg_type(self, filename):
        return self._getprop(filename, "type")

    def set_msg_type(self, filename, type):
        self._setprop(filename, "type", type)

    def get_msg_read(self, filename):
        val = self._getprop(filename, "read")
        return val == "True"

    def set_msg_read(self, filename, read):
        self._setprop(filename, "read", str(read == True))

    def get_msg_sender(self, filename):
        return self._getprop(filename, "sender")

    def set_msg_sender(self, filename, sender):
        self._setprop(filename, "sender", sender)

    def get_msg_recip(self, filename):
        return self._getprop(filename, "recip")

    def set_msg_recip(self, filename, recip):
        self._setprop(filename, "recip", recip)

    def subfolders(self):
        """Return a list of MessageFolderInfo objects representing this
        folder's subfolders"""
        info = []

        entries = glob(os.path.join(self._path, "*"))
        for entry in sorted(entries):
            if entry == "." or entry == "..":
                continue
            if os.path.isdir(entry):
                info.append(MessageFolderInfo(entry))

        return info

    def files(self):
        """Return a list of files contained in this folder"""
        l = glob(os.path.join(self._path, "*"))
        return [x for x in l if os.path.isfile(x) and not x.startswith(".")]
    
    def get_subfolder(self, name):
        """Get a MessageFolderInfo object representing a named subfolder"""
        for folder in self.subfolders():
            if folder.name() == name:
                return folder

        return None

    def create_subfolder(self, name):
        """Create a subfolder by name"""
        path = os.path.join(self._path, name)
        os.mkdir(path)
        return MessageFolderInfo(path)

    def create_msg(self, name):
        self._config.add_section(name)
        return os.path.join(self._path, name)

    def delete(self, filename):
        filename = os.path.basename(filename)
        self._config.remove_section(filename)
        os.remove(os.path.join(self._path, filename))

    def __str__(self):
        return self.name()

class MessageFolders(MainWindowElement):
    __gsignals__ = {
        "user-selected-folder" : (gobject.SIGNAL_RUN_LAST,
                                  gobject.TYPE_NONE,
                                  (gobject.TYPE_STRING,))
        }

    def _folders_path(self):
        path = os.path.join(self._config.platform.config_dir(), "messages")
        if not os.path.isdir(path):
            os.makedirs(path)
        return path

    def _create_folder(self, root, name):
        info = root
        for el in name.split(os.sep)[:-1]:
            info = info.get_subfolder(el)
            if not info:
                break

        try:
            return info.create_subfolder(os.path.basename(name))
        except Exception, e:
            raise Exception("Intermediate folder of %s does not exist" % name)

    def create_folder(self, name):
        root = MessageFolderInfo(self._folders_path())
        return self._create_folder(root, name)
    
    def get_folders(self):
        return MessageFolderInfo(self._folders_path()).subfolders()

    def get_folder(self, name):
        return MessageFolderInfo(os.path.join(self._folders_path(), name))

    def _get_folder_by_iter(self, store, iter):
        els = []
        while iter:
            els.insert(0, store.get(iter, 0)[0])
            iter = store.iter_parent(iter)

        return os.sep.join(els)

    def select_folder(self, folder):
        """Select a folder by path (i.e. Inbox/Subfolder)
        NB: Subfolders currently not supported :)
        """
        view, = self._getw("folderlist")
        store = view.get_model()

        iter = store.get_iter_first()
        while iter:
            fqname = self._get_folder_by_iter(store, iter)            
            if fqname == folder:
                view.set_cursor(store.get_path(iter))
                self.emit("user-selected-folder", fqname)
                break

            iter = store.iter_next(iter)

    def _ensure_default_folders(self):
        defaults = [_("Inbox"), _("Outbox"), _("Sent"), _("Trash")]
        root = MessageFolderInfo(self._folders_path())

        for folder in defaults:
            try:
                info = self._create_folder(root, folder)
                print info.subfolders()
            except Exception:
                pass

    def _add_folders(self, store, iter, root):
        iter = store.append(iter, (root.name(), self.folder_pixbuf))
        for info in root.subfolders():
            self._add_folders(store, iter, info)

    def _select_folder(self, view, event):
        if event.button != 1:
            return

        if event.window == view.get_bin_window():
            x, y = event.get_coords()
            pathinfo = view.get_path_at_pos(int(x), int(y))
            if pathinfo is None:
                return
            else:
                view.set_cursor_on_cell(pathinfo[0])

        store, iter = view.get_selection().get_selected()
        
        self.emit("user-selected-folder", self._get_folder_by_iter(store, iter))

    def _dragged_to(self, view, ctx, x, y, sel, info, ts):
        (path, place) = view.get_dest_row_at_pos(x, y)

        data = sel.data.split("\x01")
        msgs = data[1:]

        src_folder = data[0]
        dst_folder = view.get_model()[path][0]

        if src_folder == dst_folder:
            return

        dst = MessageFolderInfo(os.path.join(self._folders_path(), dst_folder))
        src = MessageFolderInfo(os.path.join(self._folders_path(), src_folder))
                                
        for record in msgs:
            fn, subj, type, read, send, recp = record.split("\0")
            print "Dragged %s from %s into %s" % (fn, src_folder, dst_folder)
            print "  %s %s %s %s->%s" % (subj, type, read, send, recp)

            try:
                dst.delete(os.path.basename(fn))
            except Exception:
                pass
            newfn = dst.create_msg(os.path.basename(fn))
            shutil.copy(fn, newfn)
            src.delete(fn)

            dst.set_msg_read(fn, read == "True")
            dst.set_msg_subject(fn, subj)
            dst.set_msg_type(fn, type)
            dst.set_msg_sender(fn, send)
            dst.set_msg_recip(fn, recp)

    # MessageFolders
    def __init__(self, wtree, config):
        MainWindowElement.__init__(self, wtree, config, "msg")

        folderlist, = self._getw("folderlist")

        store = gtk.TreeStore(gobject.TYPE_STRING, gobject.TYPE_OBJECT)
        folderlist.set_model(store)
        folderlist.set_headers_visible(False)
        folderlist.enable_model_drag_dest([("text/d-rats_message", 0, 0)],
                                          gtk.gdk.ACTION_DEFAULT)
        folderlist.connect("drag-data-received", self._dragged_to)
        folderlist.connect("button_press_event", self._select_folder)

        col = gtk.TreeViewColumn("", gtk.CellRendererPixbuf(), pixbuf=1)
        folderlist.append_column(col)

        col = gtk.TreeViewColumn("", gtk.CellRendererText(), text=0)
        folderlist.append_column(col)

        self.folder_pixbuf = self._config.ship_img("folder.png")

        self._ensure_default_folders()
        for folder in self.get_folders():
            self._add_folders(store, None, folder)

ML_COL_ICON = 0
ML_COL_SEND = 1
ML_COL_SUBJ = 2
ML_COL_TYPE = 3
ML_COL_DATE = 4
ML_COL_FILE = 5
ML_COL_READ = 6
ML_COL_RECP = 7

class MessageList(MainWindowElement):
    def _folder_path(self, folder):
        path = os.path.join(self._config.platform.config_dir(),
                            "messages",
                            folder)
        if not os.path.isdir(path):
            return None
        else:
            return path

    def open_msg(self, filename):
        if not msgrouting.msg_lock(filename):
            e = _("This message is currently being " +
                  "transferred and cannot be opened")
            display_error(e)
            return gtk.RESPONSE_CANCEL

        parent = self._wtree.get_widget("mainwindow")
        form = formgui.FormDialog(_("Form"), filename, parent=parent)
        form.configure(self._config)
        r = form.run_auto()
        form.destroy()

        self.refresh(filename)

        msgrouting.msg_unlock(filename)

        return r

    def _open_msg(self, view, path, col):
        store = view.get_model()
        iter = store.get_iter(path)
        path, = store.get(iter, ML_COL_FILE)

        self.open_msg(path)
        self.current_info.set_msg_read(path, True)
        iter = self.iter_from_fn(path)
        if iter:
            self._update_message_info(iter)

    def _dragged_from(self, view, ctx, sel, info, ts):
        store, paths = view.get_selection().get_selected_rows()
        msgs = [self.current_info.name()]
        for path in paths:
            data = "%s\0%s\0%s\0%s\0%s\0%s" % (store[path][ML_COL_FILE],
                                               store[path][ML_COL_SUBJ],
                                               store[path][ML_COL_TYPE],
                                               store[path][ML_COL_READ],
                                               store[path][ML_COL_SEND],
                                               store[path][ML_COL_RECP])
            msgs.append(data)

        sel.set("text/d-rats_message", 0, "\x01".join(msgs))
        gobject.idle_add(self.refresh)

    # MessageList
    def __init__(self, wtree, config):
        MainWindowElement.__init__(self, wtree, config, "msg")

        msglist, = self._getw("msglist")

        self.store = gtk.ListStore(gobject.TYPE_OBJECT,
                                   gobject.TYPE_STRING,
                                   gobject.TYPE_STRING,
                                   gobject.TYPE_STRING,
                                   gobject.TYPE_INT,
                                   gobject.TYPE_STRING,
                                   gobject.TYPE_BOOLEAN,
                                   gobject.TYPE_STRING)
        msglist.set_model(self.store)
        msglist.get_selection().set_mode(gtk.SELECTION_MULTIPLE)
        msglist.enable_model_drag_source(gtk.gdk.BUTTON1_MASK,
                                         [("text/d-rats_message", 0, 0)],
                                         gtk.gdk.ACTION_DEFAULT|
                                         gtk.gdk.ACTION_MOVE)
        msglist.connect("drag-data-get", self._dragged_from)

        col = gtk.TreeViewColumn("", gtk.CellRendererPixbuf(), pixbuf=0)
        msglist.append_column(col)

        def bold_if_unread(col, rend, model, iter, cnum):
            val, read, = model.get(iter, cnum, ML_COL_READ)
            if not val:
                val = ""
            if not read:
                val = val.replace("&", "&amp;")
                val = val.replace("<", "&lt;")
                val = val.replace(">", "&gt;")
                rend.set_property("markup", "<b>%s</b>" % val)

        r = gtk.CellRendererText()
        col = gtk.TreeViewColumn(_("Sender"), r, text=ML_COL_SEND)
        col.set_cell_data_func(r, bold_if_unread, ML_COL_SEND)
        col.set_sort_column_id(ML_COL_SEND)
        col.set_sizing(gtk.TREE_VIEW_COLUMN_AUTOSIZE)
        msglist.append_column(col)

        r = gtk.CellRendererText()
        col = gtk.TreeViewColumn(_("Recipient"), r, text=ML_COL_RECP)
        col.set_cell_data_func(r, bold_if_unread, ML_COL_RECP)
        col.set_sort_column_id(ML_COL_RECP)
        col.set_sizing(gtk.TREE_VIEW_COLUMN_AUTOSIZE)
        msglist.append_column(col)

        r = gtk.CellRendererText()
        col = gtk.TreeViewColumn(_("Subject"), r, text=ML_COL_SUBJ)
        col.set_cell_data_func(r, bold_if_unread, ML_COL_SUBJ)
        col.set_expand(True)
        col.set_sort_column_id(ML_COL_SUBJ)
        col.set_sizing(gtk.TREE_VIEW_COLUMN_AUTOSIZE)
        msglist.append_column(col)

        r = gtk.CellRendererText()
        col = gtk.TreeViewColumn(_("Type"), r, text=ML_COL_TYPE)
        col.set_cell_data_func(r, bold_if_unread, ML_COL_TYPE)
        col.set_sort_column_id(ML_COL_TYPE)
        msglist.append_column(col)

        def render_date(col, rend, model, iter):
            ts, read = model.get(iter, ML_COL_DATE, ML_COL_READ)
            stamp = datetime.fromtimestamp(ts).strftime("%H:%M:%S %Y-%m-%d")
            if read:
                rend.set_property("text", stamp)
            else:
                rend.set_property("markup", "<b>%s</b>" % stamp)

        r = gtk.CellRendererText()
        col = gtk.TreeViewColumn(_("Date"), r, text=ML_COL_DATE)
        col.set_cell_data_func(r, render_date)
        col.set_sort_column_id(ML_COL_DATE)
        msglist.append_column(col)

        msglist.connect("row-activated", self._open_msg)
        self.store.set_sort_column_id(ML_COL_DATE, gtk.SORT_DESCENDING)

        self.message_pixbuf = self._config.ship_img("message.png")
        self.unread_pixbuf = self._config.ship_img("msg-markunread.png")
        self.current_info = None


    def _update_message_info(self, iter, force=False):
        fn, = self.store.get(iter, ML_COL_FILE)

        subj = self.current_info.get_msg_subject(fn)
        if subj == _("Unknown") or force:
            # Not registered, so update the registry
            form = formgui.FormFile(fn)
            self.current_info.set_msg_type(fn, form.id)
            self.current_info.set_msg_read(fn, False)
            self.current_info.set_msg_subject(fn, form.get_subject_string())
            self.current_info.set_msg_sender(fn, form.get_sender_string())
            self.current_info.set_msg_recip(fn, form.get_recipient_string())

        ts = os.stat(fn).st_ctime
        read = self.current_info.get_msg_read(fn)
        if read:
            icon = self.message_pixbuf
        else:
            icon = self.unread_pixbuf
        self.store.set(iter,
                       ML_COL_ICON, icon,
                       ML_COL_SEND, self.current_info.get_msg_sender(fn),
                       ML_COL_RECP, self.current_info.get_msg_recip(fn),
                       ML_COL_SUBJ, self.current_info.get_msg_subject(fn),
                       ML_COL_TYPE, self.current_info.get_msg_type(fn),
                       ML_COL_DATE, ts,
                       ML_COL_READ, read)

    def iter_from_fn(self, fn):
        iter = self.store.get_iter_first()
        while iter:
            _fn, = self.store.get(iter, ML_COL_FILE)
            if _fn == fn:
                break
            iter = self.store.iter_next(iter)

        return iter

    def refresh(self, fn=None):
        """Refresh the current folder"""
        if fn is None:
            self.store.clear()
            for msg in self.current_info.files():
                iter = self.store.append()
                self.store.set(iter, ML_COL_FILE, msg)
                self._update_message_info(iter)
        else:
            iter = self.iter_from_fn(fn)
            if not iter:
                iter = self.store.append()
                self.store.set(iter,
                               ML_COL_FILE, fn)

            self._update_message_info(iter, True)

    def open_folder(self, path):
        """Open a folder by path"""
        self.current_info = MessageFolderInfo(self._folder_path(path))
        self.refresh()

    def delete_selected_messages(self):
        msglist, = self._getw("msglist")

        iters = []
        (store, paths) = msglist.get_selection().get_selected_rows()
        for path in paths:
            iters.append(store.get_iter(path))

        for iter in iters:
            fn, = store.get(iter, ML_COL_FILE)
            store.remove(iter)
            self.current_info.delete(fn)

    def move_selected_messages(self, folder):
        dest = MessageFolderInfo(self._folder_path(folder))
        for msg in self.get_selected_messages():
            newfn = dest.create_msg(os.path.basename(msg))
            print "Moving %s -> %s" % (msg, newfn)
            shutil.copy(msg, newfn)
            self.current_info.delete(msg)
            
        self.refresh()

    def get_selected_messages(self):
        msglist, = self._getw("msglist")

        selected = []
        (store, paths) = msglist.get_selection().get_selected_rows()
        for path in paths:
            selected.append(store[path][ML_COL_FILE])
        
        return selected

class MessagesTab(MainWindowTab):
    __gsignals__ = {
        "event" : signals.EVENT,
        "notice" : signals.NOTICE,
        "user-send-form" : signals.USER_SEND_FORM,
        "get-station-list" : signals.GET_STATION_LIST,
        }

    _signals = __gsignals__

    def _new_msg(self, button):
        types = glob(os.path.join(self._config.form_source_dir(), "*.xml"))

        forms = {}
        for fn in types:
            forms[os.path.basename(fn).replace(".xml", "")] = fn

        parent = self._wtree.get_widget("mainwindow")
        d = inputdialog.ChoiceDialog(forms.keys(),
                                     title=_("Choose a form"),
                                     parent=parent)
        r = d.run()
        selection = d.choice.get_active_text()
        d.destroy()
        if r != gtk.RESPONSE_OK:
            return

        current = self._messages.current_info.name()
        self._folders.select_folder(_("Outbox"))

        tstamp = time.strftime("form_%m%d%Y_%H%M%S.xml")
        newfn = self._messages.current_info.create_msg(tstamp)


        form = formgui.FormFile(forms[selection])
        call = self._config.get("user", "callsign")
        form.add_path_element(call)
        form.set_path_src(call)
        form.set_path_mid(mkmsgid(call))
        form.save_to(newfn)

        if self._messages.open_msg(newfn) != gtk.RESPONSE_CANCEL:
            self._messages.refresh(newfn)
        else:
            self._messages.current_info.delete(newfn)
            self._folders.select_folder(current)

    def _rpl_msg(self, button):
        save_fields = [
            ("_auto_number", "_auto_number", lambda x: str(int(x)+1)),
            ("_auto_subject", "_auto_subject", lambda x: "RE: %s" % x),
            ("subject", "subject", lambda x: "RE: %s" % x),
            ("_auto_sender", "_auto_recip", None)
            ]

        try:
            sel = self._messages.get_selected_messages()
        except TypeError:
            return

        if len(sel) > 1:
            print "FIXME: Warn about multiple reply"
            return

        current = self._messages.current_info.name()
        self._folders.select_folder(_("Outbox"))

        fn = sel[0]
        oform = formgui.FormFile(fn)
        tmpl = os.path.join(self._config.form_source_dir(), "%s.xml" % oform.id)
                            
        nform = formgui.FormFile(tmpl)
        nform.add_path_element(self._config.get("user", "callsign"))
        
        try:
            for sf, df, xf in save_fields:
                oldval = oform.get_field_value(sf)
                if not oldval:
                    continue

                if xf:
                    nform.set_field_value(df, xf(oldval))
                else:
                    nform.set_field_value(df, oldval)
        except Exception, e:
            log_exception()
            print "Failed to do reply: %s" % e
            return

        call = self._config.get("user", "callsign")
        nform.add_path_element(call)
        nform.set_path_dst(oform.get_path_src())
        nform.set_path_src(call)
        nform.set_path_mid(mkmsgid(call))

        tstamp = time.strftime("form_%m%d%Y_%H%M%S.xml")
        newfn = self._messages.current_info.create_msg(tstamp)
        nform.save_to(newfn)

        if self._messages.open_msg(newfn) != gtk.RESPONSE_CANCEL:
            self._messages.refresh(newfn)
        else:
            self._messages.current_info.delete(newfn)
            self._folders.select_folder(current)

    def _del_msg(self, button):
        if self._messages.current_info.name() == _("Trash"):
            self._messages.delete_selected_messages()
        else:
            self._messages.move_selected_messages(_("Trash"))

    def _snd_msg(self, button):
        try:
            sel = self._messages.get_selected_messages()
        except TypeError:
            return

        if len(sel) > 1:
            print "FIXME: Warn about multiple send"
            return

        fn = sel[0]
        recip = self._messages.current_info.get_msg_recip(fn)

        stations = []
        ports = self.emit("get-station-list")
        for slist in ports.values():
            stations += slist

        if recip in stations:
            stations.remove(recip)
        stations.insert(0, recip)

        station, port = prompt_for_station(stations, self._config)
        if not station:
            return

        self.emit("user-send-form", station, port, fn, "foo")

    def _mrk_msg(self, button, read):
        try:
            sel = self._messages.get_selected_messages()
        except TypeError:
            return

        for fn in sel:
            self._messages.current_info.set_msg_read(fn, read)

        self._messages.refresh()

    def _importmsg(self, button):
        dir = self._config.get("prefs", "download_dir")
        fn = self._config.platform.gui_open_file(dir)
        if not fn:
            return

        dst = os.path.join(self._config.form_store_dir(),
                           _("Inbox"),
                           time.strftime("form_%m%d%Y_%H%M%S.xml"))

        shutil.copy(fn, dst)
        self.refresh_if_folder(_("Inbox"))
    
    def _exportmsg(self, button):
        try:
            sel = self._messages.get_selected_messages()
        except TypeError:
            return

        if len(sel) > 1:
            print "FIXME: Warn about multiple send"
            return

        fn = sel[0]

        dir = self._config.get("prefs", "download_dir")
        nfn = self._config.platform.gui_save_file(dir, "msg.xml")
        if not nfn:
            return

        shutil.copy(fn, nfn)

    def _init_toolbar(self):
        tb, = self._getw("toolbar")

        read = lambda b: self._mrk_msg(b, True)
        unread = lambda b: self._mrk_msg(b, False)

        buttons = [("msg-new.png", _("New"), self._new_msg),
                   ("msg-send.png", _("Send"), self._snd_msg),
                   ("msg-reply.png", _("Reply"), self._rpl_msg),
                   ("msg-delete.png", _("Delete"), self._del_msg),
                   ("msg-markread.png", _("Mark Read"), read),
                   ("msg-markunread.png", _("Mark Unread"), unread),
                   ]

        c = 0
        for i, l, f in buttons:
            icon = gtk.Image()
            icon.set_from_pixbuf(self._config.ship_img(i))
            icon.show()
            item = gtk.ToolButton(icon, l)
            item.show()
            item.connect("clicked", f)
            tb.insert(item, c)
            c += 1

    def __init__(self, wtree, config):
        MainWindowTab.__init__(self, wtree, config, "msg")

        self._init_toolbar()
        self._folders = MessageFolders(wtree, config)
        self._messages = MessageList(wtree, config)

        self._folders.connect("user-selected-folder",
                              lambda x, y: self._messages.open_folder(y))
        self._folders.select_folder(_("Inbox"))

        iport = self._wtree.get_widget("main_menu_importmsg")
        iport.connect("activate", self._importmsg)

        eport = self._wtree.get_widget("main_menu_exportmsg")
        eport.connect("activate", self._exportmsg);

    def refresh_if_folder(self, folder):
        self._notice()
        if self._messages.current_info.name() == folder:
            self._messages.refresh()

    def message_sent(self, fn):
        outbox = self._folders.get_folder(_("Outbox"))
        files = outbox.files()
        if fn in files:
            sent = self._folders.get_folder(_("Sent"))
            newfn = sent.create_msg(os.path.basename(fn))
            print "Moving %s -> %s" % (fn, newfn)
            shutil.copy(fn, newfn)
            outbox.delete(fn)
            self.refresh_if_folder(_("Outbox"))
            self.refresh_if_folder(_("Sent"))
        else:
            print "Form %s sent but not in outbox" % os.path.basename(fn)

    def get_shared_messages(self, for_station):
        """Return a list of (title, stamp, filename) forms destined
        for station @for_station"""
        shared = _("Inbox")
        path = os.path.join(self._config.platform.config_dir(), "messages")
        if not os.path.isdir(path):
            os.makedirs(path)
        info = MessageFolderInfo(os.path.join(path, shared))

        ret = []
        for fn in info.files():
            stamp = os.stat(fn).st_mtime
            ffn = "%s/%s" % (shared, os.path.basename(fn))
            form = formgui.FormFile(fn)
            ret.append((form.get_subject_string(), stamp, ffn))

        return ret

    def selected(self):
        MainWindowTab.selected(self)

        make_visible = ["main_menu_importmsg", "main_menu_exportmsg"]

        for name in make_visible:
            item = self._wtree.get_widget(name)
            item.set_property("visible", True)

    def deselected(self):
        MainWindowTab.deselected(self)

        make_invisible = ["main_menu_importmsg", "main_menu_exportmsg"]

        for name in make_invisible:
            item = self._wtree.get_widget(name)
            item.set_property("visible", False)
