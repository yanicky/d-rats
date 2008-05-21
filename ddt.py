#!/usr/bin/python
#
# Copyright 2008 Dan Smith <dsmith@danplanet.com>
#
# This program is free software: you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation, either version 3 of the License, or
# (at your option) any later version.
#
# This program is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU General Public License for more details.
#
# You should have received a copy of the GNU General Public License
# along with this program.  If not, see <http://www.gnu.org/licenses/>.

import sys
import os
import time
import serial
import base64
import struct
import zlib

from utils import hexprint

import yencode

FILE_XFER_START = 1
FILE_XFER_BLOCK = 2
FILE_XFER_ACK   = 3
FILE_XFER_DONE  = 4
FILE_XFER_MACK  = 5
FILE_XFER_JOIN  = 6
FILE_XFER_TOKEN = 7
FILE_XFER_MSTART = 8

ENCODED_TRAILER = "--(EOB)--"
ENABLE_COMPRESSION = True
ENCODING = "yenc"

ENCODINGS = {
    "yenc"   : (yencode.yencode_buffer, yencode.ydecode_buffer),
    "base64" : (base64.encodestring, base64.decodestring),
}

def set_compression(enabled):
    global ENABLE_COMPRESSION

    ENABLE_COMPRESSION = enabled

def set_encoding(enc):
    global ENCODING

    if ENCODINGS.has_key(enc):
        ENCODING = enc
        return True
    else:
        return False

def detect_frame_type(data):
    frame = DDTEncodedFrame()
    try:
        frame.unpack(data)
    except Exception, e:
        print "Unpack failed: %s" % e
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

def strip_echo(string):
    try:
        trailer = string.rindex(ENCODED_TRAILER)
    except ValueError, e:
        print "No trailer on frame"
        return string

    exposure = string[:20]

    # FIXME: Remove this and other insane debug in here
    print "Checking for echo in `%s...'" % exposure

    for i in range(0, len(ENCODED_TRAILER)):
        sub = ENCODED_TRAILER[i:]
        
        print "Checking for substring: `%s'" % sub

        if exposure.startswith(sub):
            print "Found echo `%s' in `%s...'" % (sub, exposure)
            return string[len(sub):]
    
    if ENCODED_TRAILER not in exposure:
        print "No echo found"
        return string

    idx = exposure.index(ENCODED_TRAILER) + len(ENCODED_TRAILER)

    print "Found echo `%s' in `%s...'" % (string[:idx], exposure)

    return string[idx:]

class DDTFrame:
    def __init__(self):
        self.data = None
        self.type = None
        self.seq = 0
        self.magic_reg = 0xD5
        self.magic_com = 0xCC
        self.magic = self.magic_reg
        self.checksum = 0
        self.format = "!BHHHB"

    def set_data(self, data):
        if ENABLE_COMPRESSION:
            self.magic = self.magic_com

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
        if self.magic == self.magic_com:
            data = zlib.compress(self.data, 9)
        else:
            data = self.data

        length = len(data)

        val = struct.pack(self.format,
                          self.magic,
                          length,
                          self.seq,
                          self.checksum,
                          self.type)

        val += data

        return val

    def unpack(self, value):
        header = value[0:8]
        data = value[8:]

        (magic,
         length,
         seq,
         checksum,
         self.type) = struct.unpack(self.format, header)

        if magic not in [self.magic_com, self.magic_reg]:
            print "Failed magic: %0x != %0x" % (magic, self.magic)
            hexprint(header)
            hexprint(data)
            return False

        self.seq = seq

        if len(data) != length:
            print "Length %i != %i" % (len(data), length)
            hexprint(value)
            return False

        if magic == self.magic_com:
            self.data = zlib.decompress(data)
        else:
            self.data = data

        self.calc_checksum()

        if self.checksum != checksum:
            print "Checksum failed:"
            hexprint(self.checksum)
            hexprint(checksum)
            return False

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

        func = ENCODINGS[ENCODING][0]

        return func(raw) + ENCODED_TRAILER

    def unpack(self, value):
        func = ENCODINGS[ENCODING][1]

        try:
            ri = value.rindex(ENCODED_TRAILER)
        except:
            ri = len(value)

        raw = func(value[0:ri])

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
    def __init__(self, pipe, status_fn=None):
        self.pipe = pipe
        self.enabled = True
        self.filename = "--"

        # Limits
        self.limit_tries = 20
        self.limit_timeout = 4

        # Stats
        self.total_errors = 0
        self.total_size = 0
        self.transfer_size = 0
        self.wire_size = 0

        # Tuning parameters
        self.write_chunk = 0
        self.chunk_delay = 1.5 
        self.block_size = 1024

        if status_fn is None:
            self.status_cb = self.status_to_stdout
        else:
            self.status_cb = status_fn

    def status_to_stdout(self, msg, stats):
        print ">> %s" % msg
        
        for k, v in stats.items():
            print "  %s: %s" % (k, v)

    def status(self, msg):
        vals = {
            "transferred" : self.transfer_size,
            "wiresize" : self.wire_size,
            "errors" : self.total_errors,
            "totalsize" : self.total_size,
            "filename" : self.filename,
            }

        self.status_cb(msg, vals)

    def cancel(self):
        self.enabled = False

    def _send_block(self, data):
        print "Sending %i-byte block" % len(data)

        if self.write_chunk == 0 or \
                self.write_chunk > len(data):
            self.pipe.write(data)
            self.pipe.flush()
        else:
            pos = 0
            while pos < len(data):
                print "  Chunk %i-%i" % (pos, pos+self.write_chunk)
                self.pipe.write(data[pos:pos+self.write_chunk])
                self.pipe.flush()
                time.sleep(self.chunk_delay)
                pos += self.write_chunk

        self.wire_size += len(data)

        ack = DDTAckFrame()

        result = ""
        to = Timeout(self.limit_timeout)
        while self.enabled and \
                not result.endswith(ENCODED_TRAILER) and \
                not to.expired():
            result += self.pipe.read(128)

        try:
            result = strip_echo(result)
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
            if not self.enabled:
                break

            result = self._send_block(packed)
            print "Sent data, waiting for ack"
            if result.is_ack():
                print "Sent block %i" % num
                return True
            else:
                self.total_errors += 1
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
        while self.enabled and \
                not data.endswith(ENCODED_TRAILER) and \
                not to.expired():
            _data = self.pipe.read(512)
            if len(_data) > 0:
                to = Timeout(self.limit_timeout)
            #print "Read.. data: \n%s\n" % _data
            data += _data

        if not data.endswith(ENCODED_TRAILER):
            print "Block doesn't have proper trailer"
            hexprint(data)
            return None

        print "Got frame"
        self.wire_size += len(data)

        data = strip_echo(data)

        type = detect_frame_type(data)
        if type is None:
            print "Unknown frame type"
            self.send_ack(0, False)
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
            #print "RAW FRAME: |%s|" % data
            self.send_ack(frame.get_seq(), False)
            return None

    def recv_block(self):
        for i in range(1, self.limit_tries):
            if not self.enabled:
                break

            print "Reading block..."
            result = self._recv_block()
            if result is not None:
                break
            else:
                self.total_errors += 1
                print "Failed to receive block"
        
        print "Got block"
        return result

    def send_start_file(self, filename):
        frame = DDTXferStartFrame(str(filename))

        self.filename = frame.get_filename()
        self.total_size = frame.get_size()

        for i in range(1, self.limit_tries):
            if not self.enabled:
                break

            self.status("Waiting for remote to acknowledge start")

            print "Sending XferStart"
            ack = self._send_block(frame.pack())
            if ack.is_ack():
                return True

        return False

    def recv_start_file(self):
        for i in range(1, self.limit_tries):
            if not self.enabled:
                break

            self.status("Waiting for transfer to start")

            frame = self._recv_block()
            if frame:
                break

        if not frame:
            return (None, None)

        print "Got file: %s (%i bytes)" % (frame.get_filename(),
                                           frame.get_size())
        
        self.total_size = frame.get_size()
        self.filename = frame.get_filename()

        return (frame.get_filename(), frame.get_size())

    def send_eof(self):
        frame = DDTEndFrame()
        frame.set_data("EOF")

        for i in range(1, self.limit_tries):
            self.status("Waiting for remote to acknowledge finish")
            if not self.enabled:
                break
            if self._send_block(frame.pack()):
                return True

        return False

    def send_cancel(self):
        frame = DDTEndFrame()
        frame.set_data("CAN")

        self.status("Sending Cancel")
        time.sleep(2)

        print "Sending cancel notice"
        self._send_block(frame.pack())

    def send_file(self, filename):
        if not self.send_start_file(filename):
            if self.enabled:
                self.status("Timed out waiting for transfer start")
            else:
                self.status("Cancelled")
            return False

        self.status("Negotiation Complete")

        f = file(filename, "rb")

        i = 0
        while self.enabled:
            block = f.read(self.block_size)
            if len(block) <= 0:
                print "EOF"
                if not self.send_eof():
                    print "Transfer failed (EOT not ACKed)"
                    self.status("Failed: Remote did not acknowledge EOT")
                    return False

                break
            if not self.send_block(i, block):
                self.send_cancel()
                if not self.enabled:
                    self.status("Cancelled")
                else:
                    self.status("Failed: Too many retries")
                return False

            self.transfer_size += len(block)
            i += 1
            self.status("Sending")

        self.status("Transfer complete")

        return True

    def recv_file(self, filename):
        (name, size) = self.recv_start_file()

        if not name or not size:
            if self.enabled:
                self.status("Timed out waiting for transfer start")
            else:
                self.status("Cancelled")
            return False

        self.status("Negotiation Complete")

        if os.path.isdir(filename):
            filename = "%s%s%s" % (filename, os.path.sep, name)

        print "Output file is: %s" % filename
        f = file(filename, "wb")
        
        last_block = -1
        while self.enabled:
            frame = self.recv_block()
            if frame is None:
                continue

            if frame.__class__ == DDTEndFrame:
                end_data = frame.get_data()
                if end_data == "EOF":
                    print "Got >0.1.6 EOT"
                    self.status("Transfer complete")
                    return True
                elif end_data == "CAN":
                    self.status("Transfer cancelled by remote")
                    return False
                else:
                    self.status("Transfer complete")
                    print "Got <0.1.6 EOT"
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
                self.transfer_size += len(frame.get_data())
                self.status("Receiving")
            else:
                print "Failed, bad frame type: %s" % frame.__class__
                self.status("ERROR: Bad frame type returned from recv_block()")
                return False

        if not self.enabled:
            self.status("Cancelled")
        else:
            self.status("ERROR: Invalid state in recv_file()")

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

    print "Sent: %i bytes" % x.transfer_size
    print "Wire: %i bytes" % x.wire_size
    print "Errors: %i" % x.total_errors
