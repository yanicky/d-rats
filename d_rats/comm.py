import serial
import socket
import time
import struct
import select

import utils
import agw

class DataPathError(Exception):
    pass

class DataPathNotConnectedError(DataPathError):
    pass

class DataPathIOError(DataPathError):
    pass

ASCII_XON = chr(17)
ASCII_XOFF = chr(19)

FEND  = 0xC0
FESC  = 0xDB
TFEND = 0xDC
TFESC = 0xDD

TNC_DEBUG = True

def kiss_escape_frame(frame):
    escaped = ""

    for char in frame:
        if ord(char) == FEND:
            escaped += chr(FESC)
            escaped += chr(TFEND)
        elif ord(char) == FESC:
            escaped += chr(FESC)
            escaped += chr(TFESC)
        else:
            escaped += char

    return escaped

def kiss_send_frame(frame, port=0):
    cmd = (port & 0x0F) << 4

    frame = kiss_escape_frame(frame)
    buf = struct.pack("BB", FEND, cmd) + frame + struct.pack("B", FEND)

    if TNC_DEBUG:
        print "[TNC] Sending:"
        utils.hexprint(buf)

    return buf

def kiss_buf_has_frame(buf):
    return buf.count(chr(FEND)) >=2

def kiss_recv_frame(buf):
    if not buf:
        return "", ""

    data = ""
    inframe = False

    _buf = ""
    _lst = "0" # Make sure we don't choke trying to ord() this
    for char in buf:
        if ord(char) == FEND:
            if not inframe:
                inframe = True
            else:
                data += _buf[1:]
                _buf = ""
                inframe = False
        elif ord(char) == FESC:
            pass # Ignore this and wait for the next character
        elif ord(_lst) == FESC:
            if ord(char) == TFEND:
                _buf += chr(FEND)
            elif ord(char) == TFESC:
                _buf += chr(FESC)
            else:
                print "[TNC] Bad escape of 0x%x" % ord(char)
                break
        elif inframe:
            _buf += char
        else:
            print "[TNC] Out-of-frame garbage: 0x%x" % ord(char)
        _lst = char

    if TNC_DEBUG:
        print "[TNC] Data:"
        utils.hexprint(data)

    if not inframe and _buf:
        # There was not a partial frame started at the end of the data
        print "[TNC] Dumping non-frame data trailer"
        utils.hexprint(_buf)
        _buf = ""

    return data, _buf

class TNCSerial(serial.Serial):
    def __init__(self, **kwargs):
        if "tncport" in kwargs.keys():
            self.__tncport = kwargs["tncport"]
            del kwargs["tncport"]
        else:
            self.__tncport = 0
        serial.Serial.__init__(self, **kwargs)

        self.__buffer = ""
        self.__tstamp = 0

    def reconnect(self):
        pass

    def write(self, data):
        serial.Serial.write(self, kiss_send_frame(data, self.__tncport))

    def read(self, size):
        if self.__buffer:
            print "Buffer is %i before read" % len(self.__buffer)
        self.__buffer += serial.Serial.read(self, 1024)

        framedata = ""
        if kiss_buf_has_frame(self.__buffer):
            framedata, self.__buffer = kiss_recv_frame(self.__buffer)
        elif len(self.__buffer) > 0:
            print "[TNC] Buffer partially-filled (%i b)" % len(self.__buffer)

        return framedata


class SWFSerial(serial.Serial):
    __swf_debug = False

    def __init__(self, **kwargs):
        print "Software XON/XOFF control initialized"
        try:
            serial.Serial.__init__(self, **kwargs)
        except TypeError:
            if "writeTimeout" in kwargs:
                del kwargs["writeTimeout"]
                serial.Serial.__init__(self, **kwargs)
            else:
                print "Unknown TypeError from Serial.__init__: %s" % e
                raise e

        self.state = True
        self.xoff_limit = 15

    def reconnect(self):
        self.close()
        time.sleep(0.5)
        self.open()

    def is_xon(self):
        time.sleep(0.01)
        if serial.Serial.inWaiting(self) == 0:
            return self.state
        char = serial.Serial.read(self, 1)
        if char == ASCII_XOFF:
            if self.__swf_debug:
                print "************* Got XOFF"
            self.state = False
        elif char == ASCII_XON:
            if self.__swf_debug:
                print "------------- Got XON"
            self.state = True
        elif len(char) == 1:
            print "Aiee! Read a non-XOFF char: 0x%02x `%s`" % (ord(char),
                                                                   char)
            self.state = True
            print "Assuming IXANY behavior"

        return self.state

    def _write(self, data):
        chunk = 8
        pos = 0
        while pos < len(data):
            if self.__swf_debug:
                print "Sending %i-%i of %i" % (pos, pos+chunk, len(data))
            serial.Serial.write(self, data[pos:pos+chunk])
            self.flush()
            pos += chunk
            start = time.time()
            while not self.is_xon():
                if self.__swf_debug:
                    print "We're XOFF, waiting: %s" % self.state
                time.sleep(0.01)
                
                if (time.time() - start) > self.xoff_limit:
                    #print "XOFF for too long, breaking loop!"
                    #raise DataPathIOError("Write error (flow)")
                    print "XOFF for too long, assuming XON"
                    self.state = True

    def write(self, data):
        old_to = self.timeout
        self.timeout = 0.01

        self._write(data)

        self.timeout = old_to

    def read(self, len):
        return serial.Serial.read(self, len)


class DataPath(object):
    def __init__(self, pathspec, timeout=0.25):
        self.timeout = timeout
        self.pathspec = pathspec
        self.can_reconnect = True

    def connect(self):
        raise DataPathNotConnectedError("Can't connect base class")

    def disconnect(self):
        raise DataPathNotConnectedError("Can't disconnect base class")

    def read(self, count):
        raise DataPathIOError("Can't read from base class")

    def write(self, buf):
        raise DataPathIOError("Can't write to base class")

    def flush(self, buf):
        raise DataPathIOError("Can't flush the base class")

    def is_connected(self):
        return False

    def __str__(self):
        return "--"

class AGWDataPath(DataPath):
    def __init__(self, pathspec, timeout=0):
        DataPath.__init__(self, pathspec, timeout)

        agw, self._addr, self._port = pathspec.split(":")
        self._agw = None

    def connect(self):
        try:
            self._agw = agw.AGWConnection(self._addr, int(self._port), self.timeout)
            self._agw.enable_raw()
        except Exception, e:
            print "AGWPE exception on connect: %s" % e
            raise DataPathNotConnectedError("Unable to connect to AGWPE")

    def disconnect(self):
        if self._agw:
            self._agw.close()

    def reconnect(self):
        self.disconnect()
        self.connect()

    def read(self, count):
        return agw.receive_data(self._agw)

    def write(self, buf):
        agw.transmit_data(self._agw, "CQ", ["SRC", "RELAY"], buf)

    def is_connected(self):
        return bool(self._agw)

    def __str__(self):
        return "[AGWPE %s:%s]" % (self._addr, self._port)

    def get_agw_connection(self):
        return self._agw

    def read_all_waiting(self):
        return agw.receive_data(self._agw)

class SerialDataPath(DataPath):
    def __init__(self, pathspec, timeout=0.25):
        DataPath.__init__(self, pathspec, timeout)

        (self.port, self.baud) = pathspec
        self._serial = None

    def connect(self):
        try:
            self._serial = SWFSerial(port=self.port,
                                     baudrate=self.baud,
                                     timeout=self.timeout,
                                     writeTimeout=self.timeout,
                                     xonxoff=0)
        except Exception, e:
            print "Serial exception on connect: %s" % e
            raise DataPathNotConnectedError("Unable to open serial port")

    def disconnect(self):
        if self._serial:
            self._serial.close()
        self._serial = None

    def reconnect(self):
        return

    def read(self, count):
        try:
            data = self._serial.read(count)
        except Exception, e:
            print "Serial read exception: %s" % e
            utils.log_exception()
            raise DataPathIOError("Failed to read from serial port")

        return data

    def read_all_waiting(self):
        data = self.read(1)
        data += self.read(self._serial.inWaiting())
        return data

    def write(self, buf):
        try:
            self._serial.write(buf)
        except Exception ,e:
            print "Serial write exception: %s" % e
            utils.log_exception()
            raise DataPathIOError("Failed to write to serial port")

    def is_connected(self):
        return self._serial != None

    def flush(self):
        self._serial.flush()

    def __str__(self):
        return "[SERIAL %s@%s]" % (self.port, self.baud)

class TNCDataPath(SerialDataPath):
    def connect(self):
        if ":" in self.port:
            self.port, tncport = self.port.split(":", 1)
            tncport = int(tncport)
        else:
            tncport = 0

        try:
            self._serial = TNCSerial(port=self.port,
                                     tncport=tncport,
                                     baudrate=self.baud,
                                     timeout=self.timeout,
                                     writeTimeout=self.timeout*10,
                                     xonxoff=0)
        except Exception, e:
            print "TNC exception on connect: %s" % e
            utils.log_exception()
            raise DataPathNotConnectedError("Unable to open serial port")

    def __str__(self):
        return "[TNC %s@%s]" % (self.port, self.baud)

class SocketDataPath(DataPath):
    def __init__(self, pathspec, timeout=0.25):
        DataPath.__init__(self, pathspec, timeout)

        self._socket = None

        if isinstance(pathspec, socket.socket):
            self._socket = pathspec
            self._socket.settimeout(self.timeout)
            self.can_reconnect = False
            self.host = "(incoming)"
            self.port = 0
        elif len(pathspec) == 2:
            (self.host, self.port) = pathspec
            self.call = self.passwd = "UNKNOWN"
        else:
            (self.host, self.port, self.call, self.passwd) = pathspec

    def reconnect(self):
        if not self.can_reconnect:
            return
        self.disconnect()
        time.sleep(0.5)
        self.connect()

    def do_auth(self):
        def readline(_s, to=30):
            t = time.time()

            line = ""
            while ("\n" not in line) and ((time.time() - t) < to):
                try:
                    _d = _s.recv(32)
                    if not _d:
                        break
                except socket.timeout:
                    continue

                line += _d
                
            return line.strip()

        def getline(_s, to=30):
            line = readline(_s, to)

            try:
                code, string = line.split(" ", 1)
                code = int(code)
            except Exception, e:
                print "Error parsing line %s: %s" % (line, e)
                raise DataPathNotConnectedError("Conversation error")

            return code, string

        try:
            c, l = getline(self._socket)
        except DataPathNotConnectedError:
            print "Assuming an old-school ratflector for now"
            return

        if c == 100:
            print "Host does not require authentication"
            return
        elif c != 101:
            raise DataPathNotConnectedError("Unknown response code %i" % c)

        print "Doing authentication"
        print "Sending username: %s" % self.call
        self._socket.send("USER %s\r\n" % self.call)

        c, l = getline(self._socket)
        if c == 200:
            print "Host did not require a password"
        elif c != 102:
            raise DataPathNotConnectedError("User rejected username")

        print "Sending password: %s" % ("*" * len(self.passwd))
        self._socket.send("PASS %s\r\n" % self.passwd)

        c, l = getline(self._socket)
        print "Host responded: %i %s" % (c, l)
        if c != 200:
            raise DataPathNotConnectedError("Authentication failed: %s" % l)

    def connect(self):
        try:
            self._socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            self._socket.connect((self.host, self.port))
            self._socket.settimeout(self.timeout)
        except Exception, e:
            print "Socket connect failed: %s" % e
            self._socket = None
            raise DataPathNotConnectedError("Unable to connect (%s)" % e)

        if self.passwd is not None:
            self.do_auth()

    def disconnect(self):
        if self._socket:
            self._socket.close()
        self._socket = None

    def read(self, count):
        data = ""
        end = time.time() + self.timeout

        if not self._socket:
            raise DataPathIOError("Socket closed")

        self._socket.setblocking(True)
        self._socket.settimeout(self.timeout)

        while len(data) < count:

            try:
                x = time.time()
                inp = self._socket.recv(count - len(data))
            except socket.timeout:
                if time.time() > end:
                    break
                else:
                    continue
            except Exception, e:
                raise DataPathIOError("Socket error: %s" % e)

            if inp == "":
                raise DataPathIOError("Socket disconnected")

            end = time.time() + self.timeout
            data += inp


        return data

    def read_all_waiting(self):
        if not self._socket:
            raise DataPathIOError("Socket disconnected")

        self._socket.setblocking(False)

        r, w, x = select.select([self._socket], [], [], self.timeout)
        if not r:
            return ""

        data = ""
        while True:
            try:
                d = self._socket.recv(4096)
            except Exception, e:
                break
            if not d:
                raise DataPathIOError("Socket disconnected")
            data += d

        return data

    def write(self, buf):
        try:
            self._socket.sendall(buf)
        except Exception, e:
            print "Socket write failed: %s" % e
            raise DataPathIOError("Socket write failed")

        return
            
    def is_connected(self):
        return self._socket != None

    def flush(self):
        pass

    def __str__(self):
        try:
            addr, port = self._socket.getpeername()
            return "[NET %s:%i]" % (addr, port)
        except:
            return "[NET closed]"
