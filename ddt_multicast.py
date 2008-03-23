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

import array
import struct
import time
import os
import random

import serial

import ddt
from ddt import DDTEncodedFrame

from utils import hexprint

GROUP_TRAILER = "--(EG)--"

class TransferEnded(Exception):
    def __init__(self, msg, error=True):
        self._error = error
        Exception.__init__(self, msg)

def read_blocks(f, s, c):
    blocks = []
    for i in range(0,c):
        block = f.read(s)
        if block:
            blocks.append(block)
        else:
            break

    return blocks    

class DDTMultiXferStartFrame(DDTEncodedFrame):
    def xfer_start_data(self):
        return struct.pack("IH", self.file_size, self.block_size) + \
            self.file_name

    def __init__(self, filename=None, block_size=512):
        DDTEncodedFrame.__init__(self)

        self.block_size = block_size

        if filename:
            stat = os.stat(filename)
            self.file_size = stat.st_size
            self.file_name = os.path.basename(filename)
            ddt.DDTEncodedFrame.set_data(self, self.xfer_start_data())
            self.set_type(ddt.FILE_XFER_MSTART)

    def set_data(self):
        raise Exception("File transfer start blocks have no user data")

    def get_data(self):
        raise Exception("File transfer start blocks have no user data")

    def xfer_parse(self):
        size = self.data[0:6]
        name = self.data[6:]

        (size, bsize) = struct.unpack("IH", size)

        return (size, bsize,name)

    def get_filename(self):
        s, bs, n = self.xfer_parse()
        return n

    def get_size(self):
        s, bs, n = self.xfer_parse()
        return s

    def get_block_size(self):
        s, bs, n = self.xfer_parse()
        return bs

class DDTMultiACKFrame(DDTEncodedFrame):
    def ack_blocks(self, blocks, ack=True):
        format = "!BH"

        if ack:
            char = 'A'
        else:
            char = 'N'

        print "Going to MACK blocks: %s" % blocks
        data = struct.pack("=BH", ord(char), len(blocks)) + \
            array.array("H", blocks).tostring()
        self.set_data(data)

    def get_acked_blocks(self):
        format = "=BH"

        (char, count) = struct.unpack(format, self.get_data()[0:3])
        if char == ord("A"):
            self.is_ack = True
        elif char == ord("N"):
            self.is_ack = False
        else:
            print "MACK ack char was '%s' (%02x)" % (chr(char), char)
            return []

        print "MACK of %i blocks" % count

        format += ("H" * count)

        try:
            info = struct.unpack(format, self.get_data())
        except Exception, e:
            print "Failed to unpack MACK data"
            return []

        print "MACK of blocks: %s" % list(info[2:])

        return list(info[2:])

    def is_ack(self):
        blocks = self.get_acked_blocks()
        return self.is_ack

    def __init__(self):
        DDTEncodedFrame.__init__(self)
        self.set_type(ddt.FILE_XFER_MACK)
        DDTEncodedFrame.set_data(self, "I")

class DDTJoinFrame(DDTEncodedFrame):
    def __init__(self, station_id=None):
        DDTEncodedFrame.__init__(self)
        self.set_type(ddt.FILE_XFER_JOIN)
        if station_id:
            self.set_data(station_id)

    def get_station(self):
        return self.get_data()

class DDTTokenFrame(DDTEncodedFrame):
    def __init__(self, station_id=None):
        DDTEncodedFrame.__init__(self)
        self.set_type(ddt.FILE_XFER_TOKEN)
        if station_id:
            self.set_data(station_id)

    def get_station(self):
        return self.get_data()

class DDTMulticastTransfer:
    def __init__(self, pipe, station_id, status_fn=None):
        self.pipe = pipe
        self.station_id = station_id
        self.status_fn = status_fn

        self.block_size = 512

        self.stations = {}
        self.waiting_for_checkins = True

        self.enabled = True

        self.limit_tries = 10

        self.transfer_size = 0
        self.wire_size = 0
        self.total_size = 0
        self.errors = 0
        self.filename = "--"

    def cancel(self):
        self.enabled = False
        self.status("Cancelling...")

    def status(self, msg):
        vals = {
            "transferred" : self.transfer_size,
            "wiresize" : self.wire_size,
            "errors" : self.errors,
            "totalsize" : self.total_size,
            "filename" : os.path.basename(self.filename),
            }

#        if msg:
#            print "Status: %s" % msg
#        for k,v in vals.items():
#            print "  %s: %s" % (k,v)

        if self.status_fn:
            self.status_fn(msg, vals)

    def send_raw_frames(self, blocks):
        for num, block in blocks:
            if not self.enabled:
                raise TransferEnded("Cancelled by user")

            frame = DDTEncodedFrame()
            frame.set_type(ddt.FILE_XFER_BLOCK)
            frame.set_seq(num)
            frame.set_data(block)

            self.status("Sending block %i" % num)

            self.pipe.write(frame.pack())
       
        self.pipe.write(GROUP_TRAILER)

    def recv_raw_frames(self, timeout=None, expect_single=False):
        data = ""

        if expect_single:
            def end(data):
                return data.endswith(ddt.ENCODED_TRAILER)
        else:
            def end(data):
                return data.endswith(GROUP_TRAILER)

        if not timeout:
            timeout = 10 # FIXME

        to = ddt.Timeout(timeout)
        while self.enabled and \
                not to.expired() and \
                not end(data):
            _data = self.pipe.read(512)
            if len(_data) > 0:
                to = ddt.Timeout(timeout)
            data += _data
            self.wire_size += len(_data)
            self.status(None)

        if not self.enabled:
            raise TransferEnded("Cancelled by user")

        try:
            eog = data.rindex(GROUP_TRAILER)
            data = data[0:eog]
        except:
            pass

        if ddt.ENCODED_TRAILER in data:
            return data.split(ddt.ENCODED_TRAILER)
        else:
            return data

    def pass_token(self, station):
        frame = DDTTokenFrame(station)
        self.pipe.write(frame.pack())

    def process_checkin(self, raw):
        frame = DDTJoinFrame()
        try:
            if not frame.unpack(raw):
                return
        except:
            print "JoinFrame unpack failed"
            return

        station = frame.get_data()

        self.stations[station] = 0
        self.status("Station `%s' joined" % station)
        self.pipe.write(frame.pack())

        return station

    def join_transfer(self):
        for a in range(10):
            delay = float(random.randint(0,500) / 100.0)

            self.status("Trying to join transfer (attempt %i) (delay %.1f)" \
                            % (a, delay))
            ojframe = DDTJoinFrame(self.station_id)

            time.sleep(delay)
            self.pipe.write(ojframe.pack())

            frames = self.recv_raw_frames(5, True)
            for f in frames:
                ijframe = DDTJoinFrame()
                try:
                    ijframe.unpack(f)
                except:
                    continue
                if ijframe.get_data() == self.station_id:
                    self.status("Joined transfer")
                    return True

        self.status("Failed to join transfer")
        return False

    def wait_for_stations(self, joinf):
        checkins = []

        while self.waiting_for_checkins and self.enabled:
            self.status("Sending advertisement")
            self.send_start_file(self.filename)
            
            self.status("Waiting for checkins...")
            raw = self.recv_raw_frames(5, True)

            for d in raw:
                s = self.process_checkin(d)
                if s and joinf:
                    if s not in checkins:
                        joinf(s)
                        checkins.append(s)

        if not self.enabled:
            raise TransferEnded("Cancelled by user")
                    
    def read_all_frames(self, filename):
        f = file(filename)
        self.blocks = read_blocks(f, self.block_size, 10000)
        f.close()

        if not self.blocks:
            raise TransferEnded("Failed to read from source file")

        self.acks = [False] * len(self.blocks)

    def transmit_marked(self):
        for i in range(len(self.blocks)):
            if not self.enabled:
                raise TransferEnded("Cancelled by user")
            
            if not self.acks[i]:
                self.status("Sending block %i of %i" % (i+1, self.total_blocks))
                frame = DDTEncodedFrame()
                frame.set_type(ddt.FILE_XFER_BLOCK)
                frame.set_seq(i)
                frame.set_data(self.blocks[i])
                data = frame.pack()
                self.pipe.write(data)
                self.wire_size += len(data)
                self.acks[i] = True

        self.pipe.write(GROUP_TRAILER)

    def ask_station(self, station, updatef):
        frame = DDTTokenFrame(station)

        if self.stations[station] > self.limit_tries:
            self.status("Giving up on station `%s'" % station)
            updatef(station, 0, "Too many retries")
            del self.stations[station]

        self.status("Checking with station `%s'" % station)

        self.pipe.write(frame.pack())

        frames = self.recv_raw_frames(10, True)
        for raw in frames:
            frame = DDTMultiACKFrame()
            try:
                if not frame.unpack(raw):
                    continue
            except:
                print "Failed to unpack an ACK frame for %s" % station
                continue

            if frame.is_ack():
                self.status("Station `%s' is complete" % station)
                del self.stations[station]
                if updatef:
                    updatef(station, 100, "Complete")
                return []
            else:
                print "Got NAK from %s" % station
                blocks = frame.get_acked_blocks()

                if updatef:
                    f = float(self.total_blocks - len(blocks)) / \
                        float(self.total_blocks)
                    updatef(station,
                            int(f * 100),
                            "In Progress")

                self.status("Station `%s' needs %i blocks resent" % (station,
                                                                     len(blocks)))
                return blocks

        print "limit: %i" % (self.limit_tries)
        print "station: %s" % (self.stations[station])

        updatef(station, 0,
                "No response (%i attempts remaining)" % (self.limit_tries - \
                    self.stations[station]))
        self.stations[station] += 1

        return []

    def collect_reports(self, updatef):
        time.sleep(2) # FIXME

        for station in self.stations.keys():
            if not self.enabled:
                raise TransferEnded("Cancelled by user")

            _naks = self.ask_station(station, updatef)
            if _naks:
                for i in _naks:
                    try:
                        self.acks[i] = False
                        self.errors += 1
                    except:
                        print "Got high block nak of %i from %s" % (i, station)

    def send_start_file(self, filename):
        frame = DDTMultiXferStartFrame(filename, self.block_size)

        self.filename = filename
        self.total_size = frame.get_size()

        if self.total_size % self.block_size:
            self.total_blocks = (self.total_size / self.block_size) + 1
        else:
            self.total_blocks = self.total_size / self.block_size

        self.pipe.write(frame.pack())            

    def recv_start_file(self):
        for i in range(1, self.limit_tries):
            if not self.enabled:
                raise TransferEnded("Cancelled by user")

            print "Getting start block"
            frames = self.recv_raw_frames(1, True)
            print "Got %i blocks" % len(frames)
            for i in frames:
                frame = DDTMultiXferStartFrame()
                try:
                    if not frame.unpack(i):
                        print "Unable to unpack start frame:"
                        hexprint(i)
                        continue
                except Exception, e:
                    print "MC Start Exception: %s" % e
                    continue
                
                print "Got file: %s (%i/%i bytes)" % (frame.get_filename(),
                                                      frame.get_block_size(),
                                                      frame.get_size())
        
                self.total_size = frame.get_size()
                self.block_size = frame.get_block_size()
                self.filename = frame.get_filename()

                return True

        return False

    def update_all_stations(self, percent, status, updatef):
        for i in self.stations.keys():
            updatef(i, percent, status)

    def start_transfer(self):
        self.waiting_for_checkins = False

    def _send_file(self, filename, joinf=None, updatef=None):
        self.filename = filename

        self.wait_for_stations(joinf)

        print "Stations: %s" % self.stations.keys()
        self.update_all_stations(0, "In Progress", updatef)

        self.read_all_frames(filename)

        while False in self.acks or self.stations.keys():
            self.transmit_marked()
            self.collect_reports(updatef)

        if not self.enabled:
            raise TransferEnded("Cancelled")
        else:
            self.status("Transfer Complete")

        if False in self.acks:
            print "No more stations, but have marked blocks!"

    def send_file(self, filename, joinf=None, updatef=None):
        try:
            self._send_file(filename, joinf, updatef)
        except TransferEnded, e:
            self.status(str(e))
            return e._error

        return True            

    def send_list(self, list):
        frame = DDTMultiACKFrame()

        if list:
            self.status("Requesting resend of %i blocks" % len(list))
            frame.ack_blocks(list, ack=False)
        else:
            self.status("Reporting all blocks complete")
            frame.ack_blocks([], ack=True)

        self.pipe.write(frame.pack())

    def process_blocks(self, flist, raw_frames, f):
        for raw in raw_frames:
            if not self.enabled:
                raise TransferEnded("Cancelled by user")

            if not raw:
                continue # skip empty bits resulting from str.split()

            frame = ddt.DDTEncodedFrame()
            try:
                if not frame.unpack(raw):
                    continue
            except Exception, e:
                print "Got a bad frame"
                continue

            if frame.get_type() == ddt.FILE_XFER_BLOCK:
                self.status("Received block %i" % frame.get_seq())
                num = frame.get_seq()
                data = frame.get_data()
                if num in flist and data:
                    flist.remove(frame.get_seq())
                    self.transfer_size += len(data)
                    f.seek(num * self.block_size)
                    f.write(data)

            elif frame.get_type() == ddt.FILE_XFER_TOKEN:
                frame = DDTJoinFrame()
                frame.unpack(raw)
                station = frame.get_station()

                if station == self.station_id:
                    self.status("Sending report")
                    self.send_list(flist)
                    self.errors += len(flist)
                    return len(flist) == 0
                else:
                    self.status("Control checking with station %s" % station)
            else:
                print "Unexpected frame type %i" % frame.get_type()

        return False

    def _recv_file(self, filename):
        if not self.recv_start_file():
            self.status("Timed out waiting for start")
            return

        if os.path.isdir(filename):
            self.filename = os.path.join(filename, self.filename)
            
        f = file(self.filename, "wb", 0)

        if not self.join_transfer():
            raise TransferEnded("Failed to join transfer")

        if self.total_size % self.block_size:
            extra = 1
        else:
            extra = 0

        flist = range((self.total_size / self.block_size) + extra)

        while self.enabled:
            frames = self.recv_raw_frames(2)
            quit = self.process_blocks(flist, frames, f)
            if quit:
                self.status("Transfer complete")
                return

        raise TransferEnded("Cancelled by user")

    def recv_file(self, filename):
        try:
            self._recv_file(filename)
        except TransferEnded, e:
            self.status(str(e))
            return e._error

        return True

if __name__ == "__main__":
    import sys

    if sys.argv[1] == "s":
        s = serial.Serial(port="/dev/ttyUSB0", timeout=0.25)
        t = DDTMulticastTransfer(s, "Sender")
        t.send_file("mainapp.py")
    else:
        s = serial.Serial(port="COM1", timeout=0.25)
        t = DDTMulticastTransfer(s, "KI4IFW")
        t.recv_file("foo.txt")
