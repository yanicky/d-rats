#!/usr/bin/python

import os
import pty
import fcntl
import time
import sys
import termios
TERMIOS = termios

from select import select

class PtyHelper:
    def reconf(self, fd):
        iflag, oflag, cflag, lflag, ispeed, ospeed, cc = termios.tcgetattr(fd)

        cflag |= (TERMIOS.CLOCAL | TERMIOS.CREAD)
        lflag &= ~(TERMIOS.ICANON|TERMIOS.ECHO|TERMIOS.ECHOE|TERMIOS.ECHOK|TERMIOS.ECHONL|TERMIOS.ISIG|TERMIOS.IEXTEN)
        oflag &= ~(TERMIOS.OPOST)
        iflag &= ~(TERMIOS.INLCR|TERMIOS.IGNCR|TERMIOS.ICRNL|TERMIOS.IGNBRK)

        cc[TERMIOS.VMIN] = 0
        cc[TERMIOS.VTIME] = 0

        termios.tcsetattr(fd, TERMIOS.TCSANOW, [iflag,oflag,cflag,lflag,ispeed,ospeed,cc])

    def __init__(self, cmd):
        argv = cmd.split()
        (pid, fd) = pty.fork()
        if pid == 0:

            self.reconf(sys.stdin.fileno())
            self.reconf(sys.stdout.fileno())

            os.close(2)
            efd = os.open("stderr", os.O_WRONLY | os.O_CREAT)
            os.execlp(argv[0], *argv)

        # Set non-blocking mode
        flags = fcntl.fcntl(fd, fcntl.F_GETFL)
        flags |= os.O_NONBLOCK
        fcntl.fcntl(fd, fcntl.F_SETFL, flags)

        self.reconf(fd)
        
        self.fd = fd

        self.timeout = 2

    def read(self, size):
        count = 0
        data = ""
        start = 0

        while count < size:
            #print "Going for read (%i/%i)" % (count, size)
            try:
                buf = os.read(self.fd, size - count)
            except:
                buf = ""
                
            if len(buf) == 0:
                if not start:
                    start = time.time()
                elif (time.time() - start) > self.timeout:
                    break
                
            data += buf
            count += len(buf)
            #print "Got %i that cycle" % len(buf)

        print "Returning %i" % count
        #print data
        return data

    def write(self, str):
        os.write(self.fd, str)
        #self.file.flush()

if __name__ == "__main__":
    p = PtyHelper("ls")

    print p.read(2000)
    
