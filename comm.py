import serial
import socket
import time
import mainapp

class DataPathError(Exception):
    pass

class DataPathNotConnectedError(DataPathError):
    pass

class DataPathIOError(DataPathError):
    pass

ASCII_XON = chr(17)
ASCII_XOFF = chr(19)

class SWFSerial(serial.Serial):
    __swf_debug = False

    def __init__(self, **kwargs):
        print "Software XON/XOFF control initialized"
        serial.Serial.__init__(self, **kwargs)

        self.state = True
        self.xoff_limit = 15

    def is_xon(self):
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
                
                if time.time() - start > self.xoff_limit:
                    print "XOFF for too long, breaking loop!"
                    raise DataPathIOError("Write error (flow)")

    def write(self, data):
        old_to = self.timeout
        self.timeout = 0.01

        self._write(data)

        self.timeout = old_to

    def read(self, len):
        return serial.Serial.read(self, len)


class DataPath:
    def __init__(self, pathspec, timeout=0.25):
        self.timeout = timeout
        self.pathspec = pathspec

        print "New data path: %s" % str(self.pathspec)

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
        return "-- DataPath base class --"

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

    def read(self, count):
        try:
            data = self._serial.read(count)
        except Exception, e:
            print "Serial read exception: %s" % e
            raise DataPathIOError("Failed to read from serial port")

        return data

    def write(self, buf):
        try:
            self._serial.write(buf)
        except Exception ,e:
            print "Serial write exception: %s" % e
            raise DataPathIOError("Failed to write to serial port")

    def is_connected(self):
        return self._serial != None

    def flush(self):
        self._serial.flush()

    def __str__(self):
        return "Serial (%s at %s baud)" % (self.port, self.baud)

class SocketDataPath(DataPath):
    def __init__(self, pathspec, timeout=0.25):
        DataPath.__init__(self, pathspec, timeout)

        (self.host, self.port) = pathspec
        self._socket = None

    def connect(self):
        try:
            self._socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            self._socket.connect((self.host, self.port))
            self._socket.settimeout(self.timeout)
        except Exception, e:
            print "Socket connect failed: %s" % e
            self._socket = None
            raise DataPathNotConnectedError("Unable to connect (%s)" % e)

    def disconnect(self):
        if self._socket:
            self._socket.close()
        self._socket = None

    def read(self, count):
        data = ""
        end = time.time() + self.timeout

        while len(data) < count:

            try:
                x = time.time()
                inp = self._socket.recv(count - len(data))
            except Exception, e:
                if time.time() > end:
                    break
                else:
                    continue

            if inp == "":
                raise DataPathNotConnectedError("Socket closed")

            end = time.time() + self.timeout
            data += inp


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
        return "Network (%s:%i)" % (self.host, self.port)
