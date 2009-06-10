#!/usr/bin/python
#
# Copyright 2009 Dan Smith (dsmith@danplanet.com)
#
# Example plugin script that contacts a running D-RATS instance and waits
# for a chat message

import xmlrpclib
import sys

# Instantiate the xmlrpc proxy object
s = xmlrpclib.Server("http://localhost:9100")

# Wait 10 seconds for a chat message from anyone
sta, txt = s.wait_for_chat(10)
if sta:
    print "%s said: `%s'" % (sta, txt)
else:
    print "Nothing received"
