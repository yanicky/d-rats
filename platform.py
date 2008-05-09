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
import glob
from subprocess import Popen

class Platform:
    def config_dir(self):
        return "."

    def log_dir(self):
        dir = os.path.join(self.config_dir(), "logs")
        if not os.path.isdir(dir):
            os.mkdir(dir)

        return dir

    def filter_filename(self, filename):
        return filename

    def log_file(self, filename):
        filename = self.filter_filename(filename + ".txt").replace(" ", "_")
        return os.path.join(self.log_dir(), filename)

    def config_file(self, filename):
        return os.path.join(self.config_dir(),
                            self.filter_filename(filename))

    def open_text_file(self, path):
        raise NotImplementedError("The base class can't do that")

    def open_html_file(self, path):
        raise NotImplementedError("The base class can't do that")

    def list_serial_ports(self):
        return []

    def default_dir(self):
        return "."

    def gui_open_file(self, start_dir=None):
        import gtk

        d = gtk.FileChooserDialog("Select a file to open",
                                  None,
                                  gtk.FILE_CHOOSER_ACTION_OPEN,
                                  (gtk.STOCK_CANCEL, gtk.RESPONSE_CANCEL,
                                   gtk.STOCK_OPEN, gtk.RESPONSE_OK))
        if start_dir and os.path.isdir(start_dir):
            d.set_current_folder(start_dir)

        r = d.run()
        f = d.get_filename()
        d.destroy()

        if r == gtk.RESPONSE_OK:
            return f
        else:
            return None

    def gui_save_file(self, start_dir=None, default_name=None):
        import gtk

        d = gtk.FileChooserDialog("Save file as",
                                  None,
                                  gtk.FILE_CHOOSER_ACTION_SAVE,
                                  (gtk.STOCK_CANCEL, gtk.RESPONSE_CANCEL,
                                   gtk.STOCK_SAVE, gtk.RESPONSE_OK))
        if start_dir and os.path.is_dir(start_dir):
            d.set_current_folder(start_dir)

        if default_name:
            d.set_current_name(default_name)

        r = d.run()
        f = d.get_filename()
        d.destroy()

        if r == gtk.RESPONSE_OK:
            return f
        else:
            return None

class UnixPlatform(Platform):
    def config_dir(self):
        dir = os.path.abspath(os.path.join(os.getenv("HOME"), ".d-rats"))
        if not os.path.isdir(dir):
            os.mkdir(dir)

        return dir

    def default_dir(self):
        return os.path.abspath(os.getenv("HOME"))

    def filter_filename(self, filename):
        return filename.replace("/", "")

    def _editor(self):
        macos_textedit = "/Applications/TextEdit.app/Contents/MacOS/TextEdit"

        if os.path.exists(macos_textedit):
            return macos_textedit
        else:
            return "gedit"

    def open_text_file(self, path):
        pid1 = os.fork()
        if pid1 == 0:
            pid2 = os.fork()
            if pid2 == 0:
                editor = self._editor()
                print "calling `%s %s'" % (editor, path)
                os.execlp(editor, editor, path)
            else:
                sys.exit(0)
        else:
            os.waitpid(pid1, 0)
            print "Exec child exited"

    def open_html_file(self, path):
        os.system("firefox '%s'" % path)

    def list_serial_ports(self):
        return sorted(glob.glob("/dev/ttyS*") + glob.glob("/dev/ttyUSB*"))

class Win32Platform(Platform):
    def config_dir(self):
        dir = os.path.abspath(os.path.join(os.getenv("APPDATA"), "D-RATS"))
        if not os.path.isdir(dir):
            os.mkdir(dir)

        return dir

    def default_dir(self):
        return os.path.abspath(os.path.join(os.getenv("USERPROFILE"),
                                            "Desktop"))

    def filter_filename(self, filename):
        for char in "/\\:*?\"<>|":
            filename = filename.replace(char, "")

        return filename

    def open_text_file(self, path):
        Popen(["notepad", path])
        return

    def open_html_file(self, path):
        os.system("explorer %s" % path)
    
    def list_serial_ports(self):
        return ["COM%i" % x for x in range(1,8)]

    def gui_open_file(self, start_dir=None):
        import win32gui

        try:
            f, _, _ = win32gui.GetOpenFileNameW()
        except Exception, e:
            print "Failed to get filename: %s" % e
            return None

        return f

    def gui_save_file(self, start_dir=None, default_name=None):
        import win32gui

        try:
            f, _, _ = win32gui.GetSaveFileNameW(File=default_name)
        except Exception, e:
            print "Failed to get filename: %s" % e
            return None

        return f

def get_platform():
    if os.name == "nt":
        return Win32Platform()
    else:
        return UnixPlatform()

if __name__ == "__main__":
    p = get_platform()

    print "Config dir: %s" % p.config_dir()
    print "Default dir: %s" % p.default_dir()
    print "Log file (foo): %s" % p.log_file("foo")
    print "Serial ports: %s" % p.list_serial_ports()
    

    p.open_text_file("d-rats.py")

    #print "Open file: %s" % p.gui_open_file()
    print "Save file: %s" % p.gui_save_file(default_name="Foo.txt")
