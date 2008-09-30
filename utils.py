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

import re
import gtk
import os
import tempfile
import urllib

def hexprint(data):
    col = 0

    line_sz = 8
    csum = 0

    lines = len(data) / line_sz
    
    if (len(data) % line_sz) != 0:
        lines += 1
        data += "\x00" * ((lines * line_sz) - len(data))
        
    for i in range(0, (len(data)/line_sz)):


        print "%03i: " % (i * line_sz),

        left = len(data) - (i * line_sz)
        if left < line_sz:
            limit = left
        else:
            limit = line_sz
            
        for j in range(0,limit):
            print "%02x " % ord(data[(i * line_sz) + j]),
            csum += ord(data[(i * line_sz) + j])
            csum = csum & 0xFF

        print "  ",

        for j in range(0,limit):
            char = data[(i * line_sz) + j]

            if ord(char) > 0x20 and ord(char) < 0x7E:
                print "%s" % char,
            else:
                print ".",

        print ""

    return csum

def filter_to_ascii(string):
        c = '\x00'
        xlate = ([c] * 32) + \
                [chr(x) for x in range(32,127)] + \
                ([c] * 129)

        xlate[ord('\n')] = '\n'
        xlate[ord('\r')] = '\r'

        return str(string).translate("".join(xlate)).replace("\x00", "")

def run_safe(f):
    def runner(*args, **kwargs):
        try:
            return f(*args, **kwargs)
        except Exception, e:
            print "<<<%s>>> %s" % (f, e)
            return None

    return runner

def get_sub_image(iconmap, i, j, size=20):
    
    # Account for division lines (1px per icon)
    x = (i * size) + i + 1
    y = (j * size) + j + 1

    icon = gtk.gdk.Pixbuf(gtk.gdk.COLORSPACE_RGB, 1, 8, size, size)
    iconmap.copy_area(x, y, size, size, icon, 0, 0)
    
    return icon

def get_icon_from_map(iconmap, symbol):
    index = ord(symbol) - ord("!")

    i = index % 16
    j = index / 16

    #print "Symbol `%s' is %i,%i" % (symbol, i, j)

    return get_sub_image(iconmap, i, j)

def get_icon(sets, key):
    if not key:
        return None

    if len(key) == 2:
        if key[0] == "/":
            set = "/"
        elif key[0] == "\\":
            set = "\\"
        else:
            print "Unknown APRS symbol table: %s" % key[0]
            return None

        key = key[1]
    elif len(key) == 1:
        set = "/"
    else:
        print "Unknown APRS symbol: `%s'" % key
        return None

    try:
        return get_icon_from_map(sets[set], key)
    except Exception, e:
        print "Error cutting icon %s: %s" % (key, e)
        return None

def open_icon_map(iconfn):
    if not os.path.exists(iconfn):
        print "Icon file %s not found" % iconfn
        return None
    
    try:
        return gtk.gdk.pixbuf_new_from_file(iconfn)
    except Exception, e:
        print "Error opening icon map %s: %s" % (iconfn, e)
        return None

class NetFile(file):
    def __init__(self, uri, mode="r", buffering=1):
        self.__fn = uri
        self.is_temp = False

        methods = ["http", "https", "ftp"]
        for method in methods:
            if uri.startswith("%s://" % method):
                self.is_temp = True
                tmpf = tempfile.NamedTemporaryFile()
                self.__fn = tmpf.name
                tmpf.close()

                print "Retrieving %s -> %s" % (uri, self.__fn)
                urllib.urlretrieve(uri, self.__fn)
                break
        
        file.__init__(self, self.__fn, mode, buffering)

    def close(self):
        file.close(self)

        if self.is_temp:
            os.remove(self.__fn)
