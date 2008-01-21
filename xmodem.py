#!/usr/bin/python

import os
import time
import sys

from utils import hexprint

EOF = chr(26)
NAK = chr(21)
SOH = chr(1)
ACK = chr(6)
EOT = chr(4)
CAN = chr(24)
STX = chr(2)

class FatalError(Exception):
    pass

class BlockReadError(Exception):
    pass

class GenericError(Exception):
    pass

class CancelledError(Exception):
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
    start_xfer = NAK
    SOH = SOH
    block_size = 128

    def cancel(self):
        self.debug("Cancelling...")
        self.running = False
    
    def __init__(self, debug=None, status_fn=None):
        self.retries = 10
        self.tstart_to = 60
        self.total_errors = 0
        self.total_bytes = 0
        self.running = True
        self.data = ""
        if debug:
            if debug == "stdout":
                self._debug = sys.stdout
            else:
                self._debug = file(debug, "w")
        else:
            self._debug = None

        if not status_fn:
            self.status_fn = self.swallow_status
        else:
            self.status_fn = status_fn

        self.checksums = {"C" : XModemCRCChecksum,
                          NAK : XModemChecksum}

    def swallow_status(self, status, bytecount, errors):
        self.debug("Status: [%s] %i bytes, %i errors" % (status,
                                                         bytecount,
                                                         errors))

    def debug(self, str):
        if not self._debug:
            return

        self._debug.write(str + "\n")

    def read_header(self, pipe, recovery=False):
        next = None

        if recovery:
            valid_next = [SOH, STX]
        else:
            valid_next = [SOH, EOT, CAN, STX]
        
        while next not in valid_next:
            if not self.running:
                raise CancelledError("User cancelled transfer")
            
            if next:
                self.debug("Syncing... 0x%02x '%s'" % (ord(next), next))
            next = pipe.read(1)
            
        self.debug("Next header: 0x%02x (%s)" % (ord(next), next))
        if next == EOT:
            self.debug("End of transfer")
            return -1, 0
        elif next == CAN:
            raise CancelledError("Remote cancelled transfer")
        elif next == STX:
            block_size = 1024
        else:
            block_size = 128

        self.debug("Reading header")
        data = pipe.read(2)
        data = next + data

        #hexprint(data + " " * 20)

        if len(data) != 3:
            raise GenericError("Bad header: short")
        if ord(data[1]) != (255 - ord(data[2])):
            raise GenericError("Bad header: Invalid block")

        return ord(data[1]), block_size

    def write_header(self, pipe, num):
        self.debug("Writing header %i" % num)
        hdr = ""
        hdr += self.SOH
        hdr += chr(num)
        hdr += chr(255 - num)

        hexprint(hdr + " " * 20)
        pipe.write(hdr)

    def _recv_block(self, pipe, error_on_last=False):
        csum = self.checksum()
        
        # Failure to read header bubbles up
        block_num, block_size = self.read_header(pipe, error_on_last)

        if block_num == -1:
            pipe.write(ACK)
            return 0, None

        self.debug("Reading block %i (%i bytes)" % (block_num, block_size))
        data = pipe.read(block_size)

        csum.process_block(data)
        csum.read(pipe)

        if not csum.validate():
            raise GenericError("Block %i checksum mismatch" % block_num)
        else:
            pipe.write(ACK)
            self.debug("Recevied block %i" % block_num)

        return (block_num, data)        

    def recv_block(self, pipe):
        last_error = False
        for i in range(0, self.retries):
            if not self.running:
                raise CancelledError("Cancelled by user")
                
            try:
                n, data = self._recv_block(pipe, last_error)
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
                self.total_errors += 1

        raise FatalError("Transfer failed (too many retries)")

    def _send_block(self, pipe, block, num):
        self.write_header(pipe, num % 256)

        self.debug("Sending block %i (%i bytes)" % (num, len(block)))

        pipe.write(block)
        csum = self.checksum()
        csum.process_block(block)
        csum.write(pipe)

        self.debug("Checksum: %s" % csum)

        ack_start = time.time()
        ack = ''
        while (len(ack) != 1) and (time.time() - ack_start) < 10:
            ack = pipe.read(1)
            
        if ack == ACK:
            self.debug("ACK for block %i" % num)
        elif ack == CAN:
            self.debug("Remote cancelled transfer")
            raise CancelledError("Remote cancelled transfer")
        elif len(ack) == 0:
            raise GenericError("Timeout waiting for ACK of %i" % num)
        else:
            
            raise GenericError("NAK on block %i (`%s':%i:%i)" % (num, ack, ord(ack), len(ack)))

    def send_block(self, pipe, block, num):
        for i in range(0, self.retries):
            if not self.running:
                raise CancelledError("Cancelled by user")
            try:
                r = self._send_block(pipe, block, num)
                return r
            except GenericError, e:
                self.debug("NAK on block %i (%s)" % (num, e))
                self.total_errors += 1

        pipe.write(CAN)
        raise FatalError("Transfer failed (too many retries)")

    def trim_eof(self, data):
        trimmed = data.rstrip(EOF)
        self.total_bytes -= (len(data) - len(trimmed))
        print "Trimmed %i EOF, adjusted total: %i" % (len(data) - len(trimmed),
                                                      self.total_bytes)

        return trimmed                                                      

    def recv_xfer(self, pipe, dest):
        blocks = []
        self.checksum = self.checksums[self.start_xfer]
        pipe.write(self.start_xfer)
        self.debug("Sent start: 0x%02x" % ord(self.start_xfer))
        self.status_fn("Starting...", 0, 0)

        last_data = None
        last = 0
        while self.running:
            n, data = self.recv_block(pipe)
            if data is None:
                dest.write(self.trim_eof(last_data))
                break
            elif last_data:
                dest.write(last_data)

            if (n != last) and (n != last + 1):
                self.debug("Received OOB: %i -> %i" % (last, n))
                raise FatalError("Out of order block")
            if n == last:
                self.debug("Received duplicate block %i" % n)
            elif n == 255:
                last = -1
            else:
                last = n
                last_data = data
                self.total_bytes += len(data)
                self.status_fn("Receiving",
                               self.total_bytes,
                               self.total_errors)

        if not self.running:
            pipe.write(CAN)
            self.debug("Cancelled by user")
            raise CancelledError("Cancelled by user")
        else:
            self.debug("Transfer complete (%i bytes)" % self.total_bytes)
            self.status_fn("Completed",
                           self.total_bytes,
                           self.total_errors,
                           running=False)

    def detect_start(self, pipe):
        starttime = time.time()

        while (time.time() - starttime) < self.tstart_to:
            if not self.running:
                raise CancelledError("User cancelled transfer")

            try:
                start = pipe.read(1)
            except Exception, e:
                self.debug("IO Error while waiting for start")
                return False

            if start not in self.checksums.keys():
                self.debug("Waiting for transfer to start...")
                self.status_fn("Waiting for remote...", 0, 0)
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
                raise FatalError("Transfer start timed out")

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
        pipe.write("Start receive now...\n")
        self.detect_start(pipe)
        
        data = "aa"
        blockno = 1

        while self.running:
            try:
                data = source.read(self.block_size)
                if len(data) == 0:
                    break
            except:
                raise GenericError("IO error reading input file")

            self.send_block(pipe, self.pad_data(data), blockno)
            self.total_bytes += len(data)
            blockno += 1

            self.status_fn("Sending",
                           self.total_bytes,
                           self.total_errors)

        if not self.running:
            pipe.write(CAN)
            raise CancelledError("Cancelled by user")
        else:
            self.debug("Transfer finished (%i bytes)" % self.total_bytes)
            self.status_fn("Completed",
                           self.total_bytes,
                           self.total_errors,
                           running=False)
            self.send_eot(pipe)


class XModemCRC(XModem):
    start_xfer = "C"

class XModem1K(XModemCRC):
    SOH = STX
    block_size = 1024

class YModem(XModem1K):
    def tx_ymodem_header(self, pipe, source):
        s = os.fstat(source.fileno())

        data = "%s\x00%i " % (os.path.basename(source.name), s.st_size)
        self.debug("YMODEM Data block:")
        hexprint(self.pad_data(data))

        self.send_block(pipe, self.pad_data(data), 0)

    def rx_ymodem_header(self, pipe):
        pipe.write(self.start_xfer)
        self.debug("Started YMODEM")

        self.checksum = self.checksums[self.start_xfer]

        n, data = self.recv_block(pipe)
        if n != 0:
            self.debug("Invalid first block number: %i (%s)" % (n, data))
            raise FatalError("YMODEM negotiation failed")

        name, info = data.split("\x00", 1)
        info_bits = info.split(" ")

        self.debug("Name: %s  Size: %s" % (name, info_bits[0]))

        return name, int(info_bits[0])
        
    def send_xfer(self, pipe, source):
        pipe.write("Start YMODEM receive now...\n")
        self.detect_start(pipe)

        self.tx_ymodem_header(pipe, source)

        self.debug("YModem header sent, starting XMODEM")
        XModem1K.send_xfer(self, pipe, source)

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
    import ptyhelper
 
    x = XModemCRC(debug="stdout")

    if True:
        test_receive(x)
    else:
        test_send(x)
