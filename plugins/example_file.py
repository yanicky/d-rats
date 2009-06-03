#!/usr/bin/python
#
# Copyright 2009 Dan Smith (dsmith@danplanet.com)
#

import xmlrpclib
import sys
import os

# Validate the command line arguments
try:
    dest = sys.argv[1]
    file = sys.argv[2]
except Exception:
    print "Usage: %s STATION FILENAME" % sys.argv[0]
    sys.exit(1)

# Make sure the file exists
if not os.path.exists(file):
    print "ERROR: File `%s' not found" % file
    sys.exit(1)

# Instantiate the xmlrpc proxy object
s = xmlrpclib.Server("http://localhost:9100")

# Send the file
s.send_file(dest, file)
