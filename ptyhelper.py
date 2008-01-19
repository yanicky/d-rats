#!/usr/bin/python

import os
import pty
import fcntl
import time
import sys
import random
import termios
TERMIOS = termios

from select import select

def safe_read(fd, length, timeout=None):
    count = 0
    data = ""
    start = time.time()

    while count < length:
        if timeout:
            time_left = timeout - (time.time() - start)
            if time_left < 0:
                break
        else:
            time_left = None

        i, _, _ = select([fd], [], [], time_left)
        if fd in i:
            _data = os.read(fd, length - count)
            data += _data
            count += len(_data)

    return data

def safe_write(fd, buffer, timeout=None):
    count = 0
    start = time.time()

    while count < len(buffer):
        if timeout:
            time_left = timeout - (time.time() - start)
            if time_left < 0:
                break
        else:
            time_left = None

        _, o, _ = select([], [fd], [], time_left)
        if fd in o:
            r = os.write(fd, buffer[count:])
            count += r

    return count

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
            os.unlink("stderr")
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
        return safe_read(self.fd, size, self.timeout)

    def write(self, str):
        #return os.write(self.fd, str)
        return safe_write(self.fd, str, self.timeout)

    def close(self):
        os.close(self.fd)

class LossyPtyHelper(PtyHelper):
    def __init__(self, cmd, percentLoss=10, garble=True, missing=True):
        PtyHelper.__init__(self, cmd)
        self.loss = 10
        self.garble = garble
        self.missing = missing

    def read(self, size):
        result = PtyHelper.read(self, size)

        isBroken = (random.randint(0,100) <= self.loss)
        if not isBroken:
            return result
        
        doGarble = (random.randint(0,10) <= 5)
        amount = random.randint(0, size / 2)
        start = random.randint(0, size - amount)

        pos = 0
        broken_result = ""
        for i in result:
            if pos < start:
                broken_result += i
            elif pos > start + amount:
                broken_result += i
            else:
                if doGarble:
                    broken_result += 'A'
            pos += 1

        return broken_result

if __name__ == "__main__":
    #p = PtyHelper("ls")
    #print p.read(20)

    #p = PtyHelper("ssh localhost ls")
    #print p.write("foo" * 500)
    #print p.read(20)
    #os.close(p.fd)

    p = LossyPtyHelper("cat xmodem.py")
    for i in range(0, 20):
        print "\nData: %s\n" % p.read(20)

    
