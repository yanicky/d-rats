import sys
import os
import time
import serial
import base64
import struct

from utils import hexprint

FILE_XFER_START = 1
FILE_XFER_BLOCK = 2
FILE_XFER_ACK   = 3
FILE_XFER_DONE  = 4

def detect_frame_type(data):
    frame = DDTEncodedFrame()
    try:
        frame.unpack(data)
    except:
        return None

    type = frame.get_type()

    if type == FILE_XFER_START:
        return DDTXferStartFrame
    elif type == FILE_XFER_BLOCK:
        return DDTEncodedFrame
    elif type == FILE_XFER_ACK:
        return DDTAckFrame
    elif type == FILE_XFER_DONE:
        return DDTEndFrame
    else:
        print "*** Unknown frame type: %i" % type
        return None

class DDTFrame:
    def __init__(self):
        self.data = None
        self.type = None
        self.seq = 0
        self.magic = 0xD5
        self.checksum = 0
        self.format = "!BHHHB"

    def set_data(self, data):
        self.data = data
        self.calc_checksum()
        
    def set_type(self, type):
        self.type = type

    def set_seq(self, seq):
        self.seq = seq
        
    def get_data(self):
        return self.data

    def get_type(self):
        return self.type

    def get_seq(self):
        return self.seq

    def pack(self):
        length = len(self.data)

        val = struct.pack(self.format,
                          self.magic,
                          length,
                          self.seq,
                          self.checksum,
                          self.type)
        val += self.data

        return val

    def unpack(self, value):
        header = value[0:8]
        data = value[8:]

        (magic,
         length,
         seq,
         checksum,
         self.type) = struct.unpack(self.format, header)

        if magic != self.magic:
            print "Failed magic: %0x != %0x" % (magic, self.magic)
            hexprint(header)
            hexprint(data)
            return False

        self.seq = seq

        if len(data) != length:
            print "Length %i != %i" % (len(data), length)
            return False

        self.data = data
        self.calc_checksum()

        if self.checksum != checksum:
            print "Checksum failed:"
            hexprint(self.checksum)
            hexprint(checksum)
        
        return True

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

    def calc_checksum(self):
        self.checksum = 0
        for i in self.data:
            self.checksum = self.update_crc(ord(i), self.checksum)

        self.checksum = self.update_crc(0, self.checksum)
        self.checksum = self.update_crc(0, self.checksum)

class DDTEncodedFrame(DDTFrame):

    def pack(self):
        raw = DDTFrame.pack(self)

        return base64.encodestring(raw)

    def unpack(self, value):
        raw = base64.decodestring(value)

        return DDTFrame.unpack(self, raw)

class DDTXferStartFrame(DDTEncodedFrame):
    def xfer_start_data(self):
        return struct.pack("I", self.file_size) + self.file_name

    def __init__(self, filename=None):
        DDTFrame.__init__(self)

        if filename:
            stat = os.stat(filename)
            self.file_size = stat.st_size
            self.file_name = os.path.basename(filename)
            DDTFrame.set_data(self, self.xfer_start_data())
            self.set_type(FILE_XFER_START)

    def set_data(self):
        raise Exception("File transfer start blocks have no user data")

    def get_data(self):
        raise Exception("File transfer start blocks have no user data")

    def xfer_parse(self):
        size = self.data[0:4]
        name = self.data[4:]

        size = struct.unpack("I", size)[0]

        return (size, name)

    def get_filename(self):
        s, n = self.xfer_parse()
        return n

    def get_size(self):
        s, n = self.xfer_parse()
        return s

class DDTAckFrame(DDTEncodedFrame):
    length = 3

    def ack_data(self, seq, ack):
        if ack:
            char = ord('A')
        else:
            char = ord('N')

        return struct.pack("!BH", char, seq)

    def __init__(self):
        DDTFrame.__init__(self)
        self.set_type(FILE_XFER_ACK)
        DDTFrame.set_data(self, 'I' + "\x00" + "\x00")

    def set_ack(self, seq, ack=True):
        DDTFrame.set_data(self, self.ack_data(seq, ack))

    def set_data(self):
        raise Exception("File transfer start blocks have no user data")

    def get_data(self):
        raise Exception("File transfer start blocks have no user data")

    def ack_parse(self):
        (char, block) = struct.unpack("!BH", self.data)

        return (chr(char), block)

    def is_ack(self):
        c, b = self.ack_parse()
        return c == 'A'

    def get_block(self):
        c, b = self.ack_parse()
        return b

class DDTEndFrame(DDTEncodedFrame):
    def __init__(self):
        DDTFrame.__init__(self)
        self.set_type(FILE_XFER_DONE)
        self.set_data("")

class Timeout:
    def __init__(self, timeout):
        self.expire = time.time() + timeout

    def expired(self):
        return time.time() > self.expire

class DDTTransfer:
    def __init__(self, pipe):
        self.limit_tries = 10
        self.limit_timeout = 10

        self.pipe = pipe

    def _send_block(self, data):
        #print "RAW FRAME: |%s|" % data
        self.pipe.write(data)

        ack = DDTAckFrame()

        result = ""
        to = Timeout(self.limit_timeout)
        while not result.endswith("\n") and not to.expired():
            result += self.pipe.read(32)
            print "Read %i bytes for result so far" % len(result)

        try:
            ack.unpack(result)
        except:
            print "ACK unpack failed"

        return ack

    def send_block(self, num, data):
        frame = DDTEncodedFrame()
        frame.set_type(FILE_XFER_BLOCK)
        frame.set_seq(num)
        frame.set_data(data)

        packed = frame.pack()

        print "Sending block %i" % num

        for i in range(1, self.limit_tries):
            result = self._send_block(packed)
            print "Sent data, waiting for ack"
            if result.is_ack():
                print "Sent block %i" % num
                return True
            else:
                print "Failed to send block %i" % num

        return False

    def send_ack(self, seq, ack):
        frame = DDTAckFrame()
        frame.set_ack(seq, ack)

        raw = frame.pack()

        self.pipe.write(raw)

    def _recv_block(self):
        data = ""

        to = Timeout(self.limit_timeout)
        while not data.endswith("\n") and not to.expired():
            data += self.pipe.read(128)
            #print "Read.. data: %s" % data

        if not data.endswith("\n") and to.expired():
            print "Timeout waiting for block"
            return None

        print "Got frame"

        type = detect_frame_type(data)
        if type is None:
            print "Unknown frame type"
            return None

        frame = type()
        try:
            result = frame.unpack(data)
        except:
            print "Unpack failed"
            result = False

        if result:
            print "ACK on %i" % frame.get_seq()
            self.send_ack(frame.get_seq(), True)
            return frame
        else:
            print "NAK"
            self.send_ack(frame.get_seq(), False)
            return None

    def recv_block(self):
        for i in range(1, self.limit_tries):
            print "Reading block..."
            result = self._recv_block()
            if result is not None:
                break
            else:
                print "Failed to receive block"
        
        print "Got block"
        return result

    def send_start_file(self, filename):
        frame = DDTXferStartFrame(filename)

        for i in range(1, self.limit_tries):
            print "Sending XferStart"
            ack = self._send_block(frame.pack())
            if ack.is_ack():
                return True

        return False

    def recv_start_file(self):
        frame = self._recv_block()

        print "Got file: %s (%i bytes)" % (frame.get_filename(),
                                           frame.get_size())
        
        return (frame.get_filename(), frame.get_size())

    def send_eof(self):
        frame = DDTEndFrame()

        for i in range(1, self.limit_tries):
            if self._send_block(frame.pack()):
                return True

        return False

    def send_file(self, filename):
        if not self.send_start_file(filename):
            print "Transfer start timed out"
            return False

        f = file(filename)

        i = 0
        while True:
            block = f.read(512)
            if len(block) <= 0:
                print "EOF"
                if not self.send_eof():
                    print "Transfer failed (EOT not ACKed)"
                break
            if not self.send_block(i, block):
                print "Failed"
                return False
            i += 1

        return True

    def recv_file(self, filename):
        (name, size) = self.recv_start_file()

        if os.path.isdir(filename):
            filename = "%s%s%s" % (filename, os.path.sep, name)

        print "Output file is: %s" % filename
        f = file(filename, "wb")
        
        last_block = -1
        while True:
            frame = self.recv_block()
            if frame is None:
                continue

            if frame.__class__ == DDTEndFrame:
                print "Transfer complete"
                return True
            elif frame.__class__ == DDTEncodedFrame:
                seq = frame.get_seq()
                if seq == last_block:
                    print "Received duplicate block %i" % seq
                    continue
                elif seq != last_block + 1:
                    print "Fatal Error: Received out-of-order block"
                    return False

                f.write(frame.get_data())
                last_block = seq
            else:
                print "Failed, bad frame type: %s" % frame.__class__
                return False

if __name__ == "__main__":
    time.sleep(2)
    print "Going..."

    if sys.argv[1] == "send":
        s = serial.Serial(port="/dev/ttyUSB0", baudrate=4800, timeout=1)
        x = DDTTransfer(s)
        x.send_file("testfile")
    else:
        s = serial.Serial(port="/dev/ttyUSB1", baudrate=4800, timeout=1)
        x = DDTTransfer(s)
        x.recv_file("tmp")

        
