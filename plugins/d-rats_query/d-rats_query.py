#!/usr/bin/python
#
# Copyright 2010 Leonardo Lastrucci <iz5fsa@gmail.com>
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
# DRATSQuery is a D-RATS-PLUGIN performing DstarQuery utility by AE5PL
#            natively inside D-RATS
#
import xmlrpclib
import sys
from socket import *
from d_rats.utils import filter_to_ascii
import time, datetime, sys, re, commands, os, sys
import ConfigParser

# CONSTANTS
NAME = "d-rats_query"
DESC = "D-RATS Query Manager"
VERS = "0.2"

# Read ini file
fn = "d-rats_query.ini"
cf = ConfigParser.ConfigParser()
cf.read(fn)

try:
    ref_address = cf.get("DRATSQuery","ref_address")
    ref_port = int(cf.get("DRATSQuery","ref_port"))
    ref_chan = cf.get("DRATSQuery","ref_chan")
except Exception:
    print "DRATSQuery plugin"
    print " "
    print "Usage: %s <ref_address> <ref_port> <ref-channel>" % NAME
    print "       <ref_address>_URL address of the D-RATS Server"
    print "       <ref_port>____port of the D-RATS Server"
    print "       <ref_chan>____channell (internal port) of the D-RATS Server"
    print ""
    print "       by Leo, IZ5FSA"
    sys.exit(1)

# Start operations
print "\n\n" + time.ctime()
print "D-RATS plugin...... ", NAME
print "Description........ ", DESC
print "Version............ ", VERS
print "Ratflector address. ", ref_address
print "Ratflector port.... ", ref_port
print "Ratflector channel. ", ref_chan

# Config file parser
SECTION = re.compile('^\s*\[\s*([^\]]*)\s*\]\s*$')
PARAM   = re.compile('^\s*(\w+)\s*=\s*(.*)\s*$')
COMMENT = re.compile('^\s*;.*$')

d = {}
f = open("d-rats_query.ini")
for line in f:
    if COMMENT.match(line): continue
    m = SECTION.match(line) 
    if m:
        section, = m.groups()
        d[section] = {}
    m = PARAM.match(line)
    if m:
        key, val = m.groups()
	if section == 'DRATSQueryCMD':
            d[section][key] = val
    
for k, v  in d.items():
    print "Section: [%s]" % (k)
    for x, y in v.items():
    	print "  %s = %s" % (x, y)

# Instantiate the xmlrpc proxy object
reflector="http://" + ref_address + ":" + str(ref_port)
s = xmlrpclib.Server(reflector)
print "\nConnected to..... %s:%s" % (ref_address, ref_port)

# Get a list of valid ports
ports = s.list_ports()
print "Available ports.... %s>%s" % (ref_address, ports)
print "Connected to....... %s" % (ref_chan)

# Make sure the specified port is in the list
if ref_chan not in ports:
    print "ERROR: port `%s' not in server's list of ports: %s" % (
        ref_chan, ",".join(ports))
    sys.exit(1)

# Looping into ratflector and sending to DxCluster
print "\nStarting listening...\n"

riga = ""
while 1:
    try:
        (sta, txt) = s.wait_for_chat(5)
    except Exception:
        print "ERROR: D-RATS socket closed"
        sys.exit(1)

    if ((sta <> "") and (txt[:2] == "?*")):
    	
    	if ((txt == "?*info") or (txt == "?*help")):
    		text = "\n\nD-RATS plugin...... " + NAME + "\n"
    		text += "Description........ " + DESC + "\n"
    		text += "Version............ " + VERS + "\n"
    		f = open("help.txt", "r")
    		text += f.read() + "\n"

    	else:
    		exe = ''
    		args = txt.split()
    		cmd = args[0][2:]
    		del args[0]
    		print "(%s) %s %s" % (sta, cmd, args)
    		for k, v  in d.items():
    			for x, y in v.items():
    				if (x == cmd):
    					exe = y + ' ' + ''.join(args)
    					print "%s found!! => %s" % (cmd, exe)
    		if (exe == ''):
    			text = "Comando " + cmd + " non disponibile"
    			print "%s non found!!" % (cmd)
    		else:
  				if (os.name in ['nt', 'dos', 'os2']):
  					pipe = os.popen(exe + ' 2>&1', 'r')
  				else:
  					pipe = os.popen('{ ' + exe + '; } 2>&1', 'r')
  		    		text = pipe.read()
  		    		sts = pipe.close()
    		
    	try:
    		print "%s" % (text)
    		s.send_chat(ref_chan, text)
    	except Exception as inst:
    		print "ERROR: D_RATSflector write"
    		print type(inst)
    		print inst.args
    		print inst
    		sys.exit(1)

