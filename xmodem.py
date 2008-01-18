#!/usr/bin/python

import ptyhelper
import os
import time
import sys

EOF = chr(26)
NAK = chr(21)
SOH = chr(1)
ACK = chr(6)

def hexprint(data):
    col = 0

    line_sz = 8
    csum = 0

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

            if ord(char) > ord('A') and ord(char) < ord('z'):
                print "%s" % char,
            else:
                print ".",

        print ""

    return csum

class XModemChecksum:
    def __init__(self):
        self.c = 0
        self.r = 0
        self.title = "XModem"

    def process_block(self, data):
        for i in data:
            self.c += ord(i)
            self.c &= 0xFF

    def read(self, pipe):
        data = pipe.read(1)
        self.r = ord(data)

    def write(self, pipe):
        data = chr(self.c)
        pipe.write(data)

    def validate(self):
        return self.c == self.r

    def __str__(self):
        return "%s Checksum: 0x%02x,0x%02x" % (self.title, self.c, self.r)

class XModemCRCChecksum(XModemChecksum):
    def __init__(self):
        XModemChecksum.__init__(self)
        self.title = "XModemCRC"
    
    def update_crc(self, c, crc):
        for _ in range(0,8):
            c <<= 1

            if (c & 0400) != 0:
                v = 1
            else:
                v = 0
                
            if (crc & 0x8000):
                crc <<= 1
                crc += v
                crc ^= 0x1021
            else:
                crc <<= 1
                crc += v

        return crc & 0xFFFF

    def process_block(self, data):
        for i in data:
            self.c = self.update_crc(ord(i), self.c)

        self.c = self.update_crc(0, self.c)
        self.c = self.update_crc(0, self.c)

    def read(self, pipe):
        data = pipe.read(2)
        if len(data) != 2:
            raise Exception("Short CRC read")

        self.r = (ord(data[0]) << 8) | (ord(data[1]))

    def write(self, pipe):
        data = chr((self.c >> 8) & 0xFF) + chr(self.c & 0xFF)
        pipe.write(data)

class XModem:
    def __init__(self, debug=None):
        self.block_size = 128
        self.start_xfer = NAK
        self.data = ""
        if debug:
            if debug == "stdout":
                self._debug = sys.stdout
            else:
                self._debug = file(debug, "w")
        else:
            self._debug = None

        self.checksums = {"C" : XModemCRCChecksum,
                          NAK : XModemChecksum}

    def debug(self, str):
        if not self._debug:
            return

        self._debug.write(str + "\n")

    def read_header(self, pipe):
        self.debug("Reading header")
        data = pipe.read(3)

        hexprint(data + " " * 20)

        if data[0] != SOH:
            raise Exception("Bad header: Missing SOH")

        if ord(data[1]) != (255 - ord(data[2])):
            raise Exception("Bad header: Invalid block")

        return ord(data[1])

    def write_header(self, pipe, num):
        self.debug("Writing header %i" % num)
        hdr = ""
        hdr += SOH
        hdr += chr(num)
        hdr += chr(255 - num)

        pipe.write(hdr)

    def recv_block(self, pipe):
        csum = self.checksum()
        
        try:
            block_num = self.read_header(pipe)
        except:
            return 0, None

        self.debug("Reading block %i" % block_num)
        data = pipe.read(self.block_size)

        csum.process_block(data)
        csum.read(pipe)

        if not csum.validate():
            pipe.write(NAK)
            #print "Checksum: 0x%x Received: 0x%x" % (c_csum, ord(r_csum))
            raise Exception("Block %i checksum mismatch" % block_num)
        else:
            self.debug("Recevied block %i" % block_num)
            pipe.write(ACK)

        return (block_num, data)        

    def send_block(self, pipe, block, num):
        self.write_header(pipe, num)

        self.debug("Sending block %i (%i bytes)" % (num, len(block)))

        pipe.write(block)
        csum = self.checksum()
        csum.process_block(block)
        csum.write(pipe)

        self.debug("Checksum: %s" % csum)

        ack = pipe.read(1)
        if ack == ACK:
            self.debug("ACK for block %i" % num)
        else:
            
            raise Exception("NAK on block %i (`%s':%i)" % (num, ack, len(ack)))

    def recv_xfer(self, pipe):
        self.checksum = self.checksums[self.start_xfer]
        pipe.write(self.start_xfer)
        self.debug("Sent start: 0x%02x" % ord(self.start_xfer))

        data = "aa"

        while data[-1] != EOF:
            n, data = self.recv_block(pipe)
            if data is None:
                break
            
            self.data += data

        self.debug("Transfer complete (%i bytes)" % len(self.data))

    def send_xfer(self, pipe, source):
        pipe.write("Start receive now...\n")

        for i in range(0,10):
            self.debug("Waiting for start %i" % time.time())

            try:
                start = pipe.read(1)
            except Exception, e:
                self.debug("Didn't get start %i" % time.time())
                self.debug("Exception: %" % str(e))
                return

            self.debug("Got start: `%s'" % start)

            if start != NAK and start != "C":
                self.debug("Waiting again...")
                time.sleep(1)
            else:
                break
        
        if start != NAK and start != "C":
            self.debug("Got !NAK for start")
            raise Exception("Received 0x%02x instead of NAK" % ord(start))
        else:
            self.debug("Got '%s' for start" % start)

        data = "aa"
        blockno = 0

        self.checksum = self.checksums[start]

        blocks = len(data) / self.block_size

        for blockno in range(0, 10):
            try:
                data = source.read(self.block_size)
                if len(data) < 128:
                    data += (128 - len(data)) * " "
            except Exception, e:
                if debug:
                    debug.write("Got exception on source read: %s" % e)
            self.send_block(pipe, data, blockno)
            self.debug("Sent block %i" % blockno)
            self.crc = 0

        self.debug("Transfer finished")

class XModemCRC(XModem):
    def __init__(self, debug=None):
        XModem.__init__(self, debug)
        self.start_xfer = "C"
        self.debug("XMODEMCRC")

if __name__ == "__main__":
    p = ptyhelper.PtyHelper("python sx.py xmodem.py")
    #p = ptyhelper.PtyHelper("python test.py")
    #p = ptyhelper.PtyHelper("rx -v outputfile")
    #p = ptyhelper.PtyHelper("sx xmodem.py")
    
    x = XModemCRC(debug="stdout")

    try:
        # Eat up the buffer
        #p.write(NAK)
        foo = p.read(200)
        print "Skipped %i bytes in buffer" % len(foo)
        print foo
    except:
        pass

    x.recv_xfer(p)
    print x.data
    #f = file("testfile")
    #x.send_xfer(p, f)
