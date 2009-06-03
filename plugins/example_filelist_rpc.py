#!/usr/bin/python
#
# Copyright 2009 Dan Smith (dsmith@danplanet.com)
#

import xmlrpclib
import sys
import time

# Validate the command line arguments
try:
    dest = sys.argv[1]
except Exception:
    print "Usage: %s STATION" % sys.argv[0]
    sys.exit(1)

# Instantiate the xmlrpc proxy object
s = xmlrpclib.Server("http://localhost:9100")

# Submit the FileList request and get a job identifier
ident = s.submit_rpcjob(dest, "RPCFileListJob")

# Poll for completion of the identifier
result = {}
while not result:
    print "Waiting for result of operation %s..." % ident
    time.sleep(1)
    result = s.get_result(ident)

# Print results
print "File list:\n%s" % "\r\n".join(result.keys())
