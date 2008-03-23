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

    def open_text_file(self, path):
        pid1 = os.fork()
        if pid1 == 0:
            pid2 = os.fork()
            if pid2 == 0:
                print "calling `gedit %s'" % path
                os.execlp("gedit", "gedit", path)
            else:
                sys.exit(0)
        else:
            os.waitpid(pid1, 0)
            print "Exec child exited"

    def open_html_file(self, path):
        os.system("firefox %s" % path)

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
    
