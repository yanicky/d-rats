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
        c = '?'
        xlate = ([c] * 32) + \
                [chr(x) for x in range(32,127)] + \
                ([c] * 129)

        xlate[ord('\n')] = '\n'
        xlate[ord('\r')] = '\r'

        return str(string).translate("".join(xlate))

