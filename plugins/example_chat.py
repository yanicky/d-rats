#!/usr/bin/python
#
# Copyright 2009 Dan Smith (dsmith@danplanet.com)
#
# Example plugin script that contacts a running D-RATS instance and sends
# a chat message on the specified port

import xmlrpclib
import sys

# Validate the command line arguments
try:
    port = sys.argv[1]
    mesg = sys.argv[2]
except Exception:
    print "Usage: %s PORT 'MESSAGE'" % sys.argv[0]
    sys.exit(1)

# Instantiate the xmlrpc proxy object
s = xmlrpclib.Server("http://localhost:9100")

# Get a list of valid ports
ports = s.list_ports()

# Make sure the specified port is in the list
if port not in ports:
    print "ERROR: port `%s' not in server's list of ports: %s" % (
        port, ",".join(ports))
    sys.exit(1)

# Send the chat message
s.send_chat(port, mesg)
