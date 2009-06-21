#!/usr/bin/python
#
# Copyright 2009 Leonardo Lastrucci <iz5fsa@gmail.com>
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
# Example plugin script that contacts a running D-RATS instance and sends
# a chat message on the specified port
#
# This is a DxCluster to D-RATS reflector bridge to reply Dx Spots via
# D-RATS chat channel.
import xmlrpclib
import sys
from socket import *
from d_rats.utils import filter_to_ascii

# Validate the command line arguments
try:
    dx_user = sys.argv[1]
    dx_address = sys.argv[2]
    dx_port = int(sys.argv[3])
    ref_address = sys.argv[4]
    ref_port = int(sys.argv[5])
    ref_chan = sys.argv[6]
except Exception:
    print "D-RATS plugin to link DxCluster to Ratflector"
    print ""
    print "Usage: %s <dx_user> <dx_address> <dx_port> <ref_address> <ref_port> <ref-channel>" % sys.argv[0]
    print "       <dx_user>_____callsign of the user to connect to the dxcluster node"
    print "       <dx_address>__URL address of the dxcluster node"
    print "       <dx_port>_____port of the dxcluster node"
    print "       <ref_address>_URL address of the ratflector"
    print "       <ref_port>____port of the ratflector"
    print "       <ref_chan>____channell (internal port) of the ratflector"
    print ""
    print "       by Leo, IZ5FSA"
    sys.exit(1)

# Start operations
print "D-RATS plugin : DX2DR"
print "Link DxCluster to D-RATSflector"
print "v 0.0.1       by Leo, IZ5FSA"
print "DxCluster userid   ", dx_user
print "DxCluster address  ", dx_address
print "DxCluster port     ", dx_port
print "Ratflector address ", ref_address
print "Ratflector port    ", ref_port
print "Ratflector channel ", ref_chan
# Make DxCluster connection
cluster = socket(AF_INET, SOCK_STREAM)
cluster.connect((dx_address, dx_port))
cluster.recv(1024)
cluster.send(dx_user+"\n")
cluster.recv(1024)
cluster.send("u/h\n")
cluster.recv(1024)
print "\nConnected to dxcluster at %s:%s as %s" % (dx_address, str(dx_port), dx_user)

# Instantiate the xmlrpc proxy object
reflector="http://" + ref_address + ":" + str(ref_port)
s = xmlrpclib.Server(reflector)
print "\nConnected to RatFlector at %s:%s" % (ref_address, ref_port)

# Get a list of valid ports
ports = s.list_ports()
print "Available ports at %s > %s" % (ref_address, ports)
print "Connected to %s" % (ref_chan)

# Make sure the specified port is in the list
if ref_chan not in ports:
    print "ERROR: port `%s' not in server's list of ports: %s" % (
        ref_chan, ",".join(ports))
    sys.exit(1)

# Looping into DxCluster and sending to ratflector
print "\nStarting spotting...\n"
while 1:
	try:
		riga = filter_to_ascii(cluster.recv(1024))
	except Exception:
		print "ERROR: DxCluster socket closed"
		sys.exit(1)

	if (riga[:2] == "DX" or
		 riga[:3] == "To "):
		dx_spot = riga[:(len(riga)-1)]
		print dx_spot

		try:
			s.send_chat(ref_chan, dx_spot)
		except Exception:
			print "ERROR: D-RATSflector socket closed on", ref_chan
			sys.exit(1)

		if (riga[6:7] == 'I' or
			 riga[26:27] == 'I'):
			try:
				s.send_chat('Serial', dx_spot)
			except Exception:
				print 'ERROR: D-RATSflector socket closed on Serial'
				sys.exit(1)
