#!/usr/bin/python

import ptyhelper
import os
import time

EOF = chr(26)
NAK = chr(21)
SOH = chr(1)
ACK = chr(6)

debug = None

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

class XModem:
    def __init__(self):
        self.block_size = 128
        self.checksum_size = 1
        self.start_xfer = NAK
        self.data = ""

    def read_header(self, pipe):
        print "Reading header"
        data = pipe.read(3)

        hexprint(data + " " * 20)

        if data[0] != SOH:
            raise Exception("Bad header: Missing SOH")

        if ord(data[1]) != (255 - ord(data[2])):
            raise Exception("Bad header: Invalid block")

        return ord(data[1])

    def write_header(self, pipe, num):
        if debug:
            debug.write("Writing header %i\n" % num)
        hdr = ""
        hdr += SOH
        hdr += chr(num)
        hdr += chr(255 - num)

        pipe.write(hdr)

    def checksum(self, data):
        csum = 0
        for i in data:
            csum += ord(i)
            csum = (csum & 0xFF)

        return csum

    def compare_checksum(self, r, c):
        return ord(r) == c

    def recv_block(self, pipe):
        block_num = self.read_header(pipe)

        print "Reading block %i" % block_num
        data = pipe.read(self.block_size)
        r_csum = pipe.read(self.checksum_size)
        c_csum = self.checksum(data)

        if not self.compare_checksum(r_csum, c_csum):
            pipe.write(NAK)
            #print "Checksum: 0x%x Received: 0x%x" % (c_csum, ord(r_csum))
            raise Exception("Block %i checksum mismatch" % block_num)
        else:
            pipe.write(ACK)

        return (block_num, data)        

    def send_block(self, pipe, block, num):
        self.write_header(pipe, num)

        if debug:
            debug.write("Sending block %i\n" % num)
        #print block
        pipe.write(block)
        csum = self.checksum(block)
        pipe.write(chr((csum & 0xFF00) >> 8) + chr(csum & 0xFF))
        if debug:
            debug.write("Checksum: %s\n" % chr((csum & 0xFF00) >> 8) + chr(csum & 0xFF))


        ack = pipe.read(1)
        if ack == ack:
            if debug:
                debug.write("Got ack for block %i\n" % num)
        else:
            raise Exception("NAK on block" % block)

    def recv_xfer(self, pipe):
        pipe.write(self.start_xfer)
        print "Sent start"

        data = "aa"

        while data[-1] != EOF:
            n, data = self.recv_block(pipe)
            print "Received block %i" % n
            self.data += data

        print "Transfer completed"

    def send_xfer(self, pipe, source):
        global debug
        #pipe.write("Start receive now...\n")
        debug = file("xmodem.debug", "w", 0)

        for i in range(0,10):
            debug.write("Waiting for start %i\n" % time.time())

            try:
                start = pipe.read(1)
            except Exception, e:
                debug.write("Didn't get start %i\n" % time.time())
                debug.write(str(e))
                return

            debug.write("Got start: `%s'\n" % start)

            if start != NAK and start != "C":
                debug.write("Waiting again...")
                time.sleep(1)
            else:
                break
        
        if start != NAK and start != "C":
            if debug:
                debug.write("Got !NAK for start\n")
            raise Exception("Received 0x%02x instead of NAK" % ord(start))
        else:
            if debug:
                debug.write("Got '%s' for start\n" % start)

        data = "aa"
        blockno = 0


        blocks = len(data) / self.block_size

        if debug:
            debug.write("Sending %i blocks\n" % blocks)
        for blockno in range(0, 10):
            try:
                data = source.read(self.block_size)
                if len(data) < 128:
                    data += (128 - len(data)) * " "
            except Exception, e:
                if debug:
                    debug.write("Got exception on source read: %s\n" % e)
            self.send_block(pipe, data, blockno)
            debug.write("sent blockno %i\n" % blockno)
            self.crc = 0

        if debug:
            debug.write("Transfer finished\n")
        

class XModemCRC(XModem):
    def __init__(self):
        self.block_size = 128
        self.checksum_size = 2
        self.start_xfer = "C"
        self.crc = 0
        self.data = ""

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

    def checksum(self, data):
        for i in data:
            self.crc = self.update_crc(ord(i) & 0377, self.crc)

        self.crc = self.update_crc(0, self.crc)
        self.crc = self.update_crc(0, self.crc)

        return self.crc

    def compare_checksum(self, r, c):
        rcsum = (ord(r[0]) << 8) | ord(r[1])

        self.crc = 0

        return rcsum == c

if __name__ == "__main__":
    p = ptyhelper.PtyHelper("python sx.py xmodem.py")
    #p = ptyhelper.PtyHelper("python test.py")
    #p = ptyhelper.PtyHelper("rx -v outputfile")
    #p = ptyhelper.PtyHelper("sx xmodem.py")
    
    x = XModemCRC()

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
