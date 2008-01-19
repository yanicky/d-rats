#!/usr/bin/python

import ptyhelper
import os
import time
import sys

EOF = chr(26)
NAK = chr(21)
SOH = chr(1)
ACK = chr(6)
EOT = chr(4)
CAN = chr(24)

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

class FatalError(Exception):
    pass

class BlockReadError(Exception):
    pass

class GenericError(Exception):
    pass

class XModemChecksum:
    title = "XModem"
    
    def __init__(self):
        self.c = 0
        self.r = 0

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
    title = "XModemCRC"

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
            raise GenericError("Short CRC read")

        self.r = (ord(data[0]) << 8) | (ord(data[1]))

    def write(self, pipe):
        data = chr((self.c >> 8) & 0xFF) + chr(self.c & 0xFF)
        return pipe.write(data)

class XModem:
    def __init__(self, debug=None):
        self.block_size = 128
        self.start_xfer = NAK
        self.retries = 10
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
        next = None
        while next not in [SOH, EOT, CAN]:
            if next:
                self.debug("Syncing... 0x%02x '%s'" % (ord(next), next))
            next = pipe.read(1)
            
        self.debug("Next header: 0x%02x (%s)" % (ord(next), next))
        if next == EOT:
            self.debug("End of transfer")
            return -1
        elif next == CAN:
            raise FatalError("Sender cancelled transfer")

        self.debug("Reading header")
        data = pipe.read(2)
        data = next + data

        #hexprint(data + " " * 20)

        if len(data) != 3:
            raise GenericError("Bad header: short")
        if ord(data[1]) != (255 - ord(data[2])):
            raise GenericError("Bad header: Invalid block")

        return ord(data[1])

    def write_header(self, pipe, num):
        self.debug("Writing header %i" % num)
        hdr = ""
        hdr += SOH
        hdr += chr(num)
        hdr += chr(255 - num)

        hexprint(hdr + " " * 20)
        pipe.write(hdr)

    def _recv_block(self, pipe):
        csum = self.checksum()
        
        # Failure to read header bubbles up
        block_num = self.read_header(pipe)

        if block_num == -1:
            pipe.write(ACK)
            return 0, None

        self.debug("Reading block %i" % block_num)
        data = pipe.read(self.block_size)

        csum.process_block(data)
        csum.read(pipe)

        if not csum.validate():
            #print "Checksum: 0x%x Received: 0x%x" % (c_csum, ord(r_csum))
            raise GenericError("Block %i checksum mismatch" % block_num)
        else:
            pipe.write(ACK)
            self.debug("Recevied block %i" % block_num)

        return (block_num, data)        

    def recv_block(self, pipe):
        last_error = False
        for i in range(0, self.retries):
            try:
                n, data = self._recv_block(pipe)
                if data is None and n == -1:
                    self.debug("Recevied EOT after bad block, retrying")
                    continue
                return n, data
            except FatalError, e:
                self.debug("Fatal error: %s" % e)
                raise e
            except GenericError, e:
                self.debug("Block read: %s (purging)" % e)
                last_error = True
                _ = pipe.read(self.block_size)
                _ += pipe.read(self.block_size)
                _ += pipe.read(self.block_size)
                self.debug("Purged %i" % len(_))
                self.debug("Failed block (attempt %i/%i)" % (i, self.retries))
                pipe.write(NAK)

        raise FatalError("Transfer failed (too many retries)")

    def _send_block(self, pipe, block, num):
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
        elif len(ack) == 0:
            raise GenericError("Timeout waiting for ACK of %i" % num)
        else:
            
            raise GenericError("NAK on block %i (`%s':%i:%i)" % (num, ack, ord(ack), len(ack)))

    def send_block(self, pipe, block, num):
        for i in range(0, self.retries):
            try:
                return self._send_block(pipe, block, num)
            except GenericError, e:
                self.debug("NAK on block %i" % num)

        pipe.write(CAN)
        raise FatalError("Transfer failed (too many retries)")
                

    def recv_xfer(self, pipe):
        blocks = []
        self.checksum = self.checksums[self.start_xfer]
        pipe.write(self.start_xfer)
        self.debug("Sent start: 0x%02x" % ord(self.start_xfer))

        data = "aa"
        last = 0
        while True:
            n, data = self.recv_block(pipe)
            if data is None:
                break

            if (n != last) and (n != last + 1):
                self.debug("Received OOB: %i -> %i" % (last, n))
                raise FatalError("Out of order block")
            else:
                last = n

            if n in blocks:
                self.debug("Received duplicate block %i" % n)
            else:
                self.data += data
                blocks.append(n)

        self.data = self.data.rstrip(EOF)

        self.debug("Transfer complete (%i bytes)" % len(self.data))

    def detect_start(self, pipe, timeout=10):
        starttime = time.time()

        while (time.time() - starttime) < timeout:
            try:
                start = pipe.read(1)
            except Exception, e:
                self.debug("IO Error while waiting for start")
                return False

            if start not in self.checksums.keys():
                self.debug("Waiting for transfer to start...")
            else:
                self.debug("Start char: %s" % start)
                break

        try:
            self.checksum = self.checksums[start]
            self.debug("Starting transfer (%s)" % self.checksum.title)
        except Exception, e:
            if start:
                self.debug(str(self.checksums.keys()))
                self.debug(str(e))
                raise GenericError("Unknown transfer type: 0x%02x" % ord(start[0]))
            else:
                raise GenericError("Transfer start timed out")

        return True

    def pad_data(self, data):
        pad = self.block_size - len(data)
        return data + (pad * EOF)

    def data_slice(self, data):
        if len(data) > self.block_size:
            return data[:self.block_size], data[self.block_size:]

        return pad_data(data), []

    def send_eot(self, pipe):
        pipe.write(EOT)

        self.debug("Sent EOT")

    def send_xfer(self, pipe, source):
        #pipe.write("Start receive now...\n")
        self.detect_start(pipe)
        
        data = "aa"
        blockno = 1

        while True:
            try:
                data = source.read(self.block_size)
                if len(data) == 0:
                    break
            except:
                raise GenericError("IO error reading input file")

            self.send_block(pipe, self.pad_data(data), blockno)
            blockno += 1

        self.send_eot(pipe)

        self.debug("Transfer finished (%i bytes)" % (blockno * self.block_size))

class XModemCRC(XModem):
    def __init__(self, debug=None):
        XModem.__init__(self, debug)
        self.start_xfer = "C"

def test_receive(x):
    #p = ptyhelper.PtyHelper("sx -vvvv xmodem.py")
    #p = ptyhelper.LossyPtyHelper("sx -vvvv xmodem.py", percentLoss=10, missing=False)
    p = ptyhelper.PtyHelper("python sx.py xmodem.py")

    foo = p.read(200)
    print "Skipped %i bytes in buffer" % len(foo)
    print foo

    x.recv_xfer(p)
    output = file("output", "w")
    output.write(x.data)
    p.close()

def test_send(x):
    p = ptyhelper.PtyHelper("rx -vvvvvvvvvvvvvv rxoutput")

    i = file("xmodem.py")

    x.send_xfer(p, i)

if __name__ == "__main__":
    #p = ptyhelper.PtyHelper("python sx.py xmodem.py")
    #p = ptyhelper.PtyHelper("python test.py")
    #p = ptyhelper.PtyHelper("rx -v outputfile")
    
    x = XModemCRC(debug="stdout")

    if True:
        test_receive(x)
    else:
        test_send(x)
