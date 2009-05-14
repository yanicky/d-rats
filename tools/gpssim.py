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

# This is a simple app to simulate some GPS activity on a ratflector
# Run it with "-h" to see a help screen

import math
import time
import socket
import sys
from optparse import OptionParser

import gettext
gettext.install("D-RATS")

try:
    from d_rats import gps
except ImportError:
    sys.path.append("..")
    print "Ignore the following icon error messages..."
    from d_rats import gps    

DEFLAT = 41.6970
DEFLON = -72.7312
DEFDIA = 0.0025
DEFDLY = 1

def make_data(pipe, lat, lon, dia, call, mesg, dly):
    start = 0
    while True:
        rads = math.radians(start)

        dx = math.cos(rads)
        dy = math.sin(rads)

        x = (dia * dx) + lon
        y = (dia * dy) + lat

        pos = gps.GPSPosition(y, x, call)
        if mesg:
            pos.comment = mesg
        pipe.send(pos.to_NMEA_GGA())

        start = (start + 5) % 360
        time.sleep(dly)

def connect_net(host, port):
    try:
        soc = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        soc.connect((host, port))
    except Exception, e:
        print "Failed to connect: %s" % e
        return None

    print "Connected to %s:%i" % (host, port)
    return soc


def main():
    op = OptionParser()
    op.add_option("-H", "--host",
                  default="localhost",
                  dest="host",
                  help="Destination host (default: localhost)")
    op.add_option("-p", "--port",
                  default=9000,
                  dest="port",
                  type="int",
                  help="Destination port (default: 9000)")
    op.add_option("-c", "--call",
                  default=None,
                  dest="call",
                  help="Callsign")
    op.add_option("-m", "--message",
                  default=None,
                  dest="mesg",
                  help="GPS Message")
    op.add_option("-i", "--icon",
                  default=None,
                  dest="icon",
                  help="GPS Icon (APRS /X notation)")
    op.add_option("", "--lat",
                  default=DEFLAT,
                  dest="lat",
                  type="float",
                  help="Center Latitude (default: %.4f)" % DEFLAT)
    op.add_option("", "--lon",
                  default=DEFLON,
                  dest="lon",
                  type="float",
                  help="Center Longitude (default: %.4f)" % DEFLON)
    op.add_option("", "--dia",
                  default=DEFDIA,
                  dest="dia",
                  type="float",
                  help="Diameter scale (default: %.4f)" % DEFDIA)
    op.add_option("", "--delay",
                  default=1,
                  dest="dly",
                  type="float",
                  help="Delay (sec) between updates (default: %i)" % DEFDLY)

    opts, args = op.parse_args()

    host = opts.host or "localhost"
    port = opts.port or 9000
    if not opts.call:
        print "A callsign must be specified"
        return

    lat = opts.lat or DEFLAT
    lon = opts.lon or DEFLON
    dia = opts.dia or DEFDIA
    dly = opts.dly or DEFDLY

    pipe = connect_net(host, port)
    if not pipe:
        return

    if opts.icon:
        icon = gps.APRS_TO_DPRS[opts.icon]
        mesg = "%s  %s" % (icon, opts.mesg)
        mesg += gps.DPRS_checksum(opts.call, mesg)
    else:
        mesg = opts.mesg

    make_data(pipe, lat, lon, dia, opts.call, mesg, dly)

if __name__ == "__main__":
    sys.exit(main())
