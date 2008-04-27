import re
import time
import tempfile
import platform

import threading
import serial

from math import pi,cos,acos,sin,atan2

TEST = "$GPGGA,180718.02,4531.3740,N,12255.4599,W,1,07,1.4,50.6,M,-21.4,M,,*63 KE7JSS  ,440.350+ PL127.3"

EARTH_RADIUS = 3963.1
EARTH_UNITS = "mi"

DEGREE = u"\u00b0"

def parse_dms(string):
    string = string.replace(u"\u00b0", " ")
    string = string.replace('"', ' ')
    string = string.replace("'", ' ')
    string = string.replace('  ', ' ')
    string = string.strip()
    
    (d, m, s) = string.split(' ', 3)
    
    deg = int(d)
    min = int(m)
    sec = float(s)

    if deg < 0:
        mul = -1
    else:
        mul = 1

    deg = abs(deg)
   
    return (deg + (min / 60.0) + (sec / 3600.0)) * mul

def set_units(units):
    global EARTH_RADIUS
    global EARTH_UNITS

    if units == "Imperial":
        EARTH_RADIUS = 3963.1
        EARTH_UNITS = "mi"
    elif units == "Metric":
        EARTH_RADIUS = 6380.0
        EARTH_UNITS = "km"

    print "Set GPS units to %s" % units

def value_with_units(value):
    if value < 0.5:
        if EARTH_UNITS == "km":
            scale = 1000
            units = "m"
        elif EARTH_UNITS == "mi":
            scale = 5280
            units = "ft"
        else:
            scale = 1
            units = EARTH_UNITS
    else:
        scale = 1
        units = EARTH_UNITS

    return "%.2f %s" % (value * scale, units)

def NMEA_checksum(string):
    checksum = 0
    for i in string:
        checksum ^= ord(i)

    return "*%02x" % checksum

def GPSA_checksum(string):
    def calc(buf):
        icomcrc = 0xffff

        for _char in buf:
            char = ord(_char)
            for i in range(0, 8):
                xorflag = (((icomcrc ^ char) & 0x01) == 0x01)
                icomcrc = (icomcrc >> 1) & 0x7fff
                if xorflag:
                    icomcrc ^= 0x8408
                char = (char >> 1) & 0x7f
        return (~icomcrc) & 0xffff

    return calc(string)

def deg2rad(deg):
    return deg * (pi / 180)

def rad2deg(rad):
    return rad / (pi / 180)

def dm2deg(deg, min):
    return deg + (min / 60.0)

def deg2dm(decdeg):
    deg = int(decdeg)
    min = (decdeg - deg) * 60.0

    return deg, min

def nmea2deg(nmea, dir="N"):
    deg = int(nmea) / 100
    try:
        min = nmea % (deg * 100)
    except ZeroDivisionError, e:
        min = int(nmea)

    if dir == "S" or dir == "W":
        m = -1
    else:
        m = 1

    return dm2deg(deg, min) * m

def deg2nmea(deg):
    deg, min = deg2dm(deg)

    return (deg * 100) + min

def distance(lat_a, lon_a, lat_b, lon_b):
    lat_a = deg2rad(lat_a)
    lon_a = deg2rad(lon_a)
    
    lat_b = deg2rad(lat_b)
    lon_b = deg2rad(lon_b)
    
    earth_radius = EARTH_RADIUS
    
    #print "cos(La)=%f cos(la)=%f" % (cos(lat_a), cos(lon_a))
    #print "cos(Lb)=%f cos(lb)=%f" % (cos(lat_b), cos(lon_b))
    #print "sin(la)=%f" % sin(lon_a)
    #print "sin(lb)=%f" % sin(lon_b)
    #print "sin(La)=%f sin(Lb)=%f" % (sin(lat_a), sin(lat_b))
    #print "cos(lat_a) * cos(lon_a) * cos(lat_b) * cos(lon_b) = %f" % (\
    #    cos(lat_a) * cos(lon_a) * cos(lat_b) * cos(lon_b))
    #print "cos(lat_a) * sin(lon_a) * cos(lat_b) * sin(lon_b) = %f" % (\
    #    cos(lat_a) * sin(lon_a) * cos(lat_b) * sin(lon_b))
    #print "sin(lat_a) * sin(lat_b) = %f" % (sin(lat_a) * sin(lat_b))

    tmp = (cos(lat_a) * cos(lon_a) * \
               cos(lat_b) * cos(lon_b)) + \
               (cos(lat_a) * sin(lon_a) * \
                    cos(lat_b) * sin(lon_b)) + \
                    (sin(lat_a) * sin(lat_b))

    # Correct round-off error (which is just *silly*)
    if tmp > 1:
        tmp = 1
    elif tmp < -1:
        tmp = -1

    distance = acos(tmp)

    return distance * earth_radius

class GPSPosition:
    """Represents a position on the globe, either from GPS data or a static
    positition"""
    def _from_coords(self, lat, lon, alt=0):
        try:
            self.latitude = float(lat)
        except ValueError:
            self.latitude = parse_dms(lat)

        try:
            self.longitude = float(lon)
        except ValueError:
            self.longitude = parse_dms(lon)

        self.altitude = float(alt)
        self.satellites = 3
        self.valid = True

    def __init__(self, lat=0, lon=0, station="UNKNOWN"):
        self.valid = False
        self.altitude = 0
        self.satellites = 0
        self.station = station
        self.comment = ""
        self.current = None
        self.date = "00:00:00"
        self.speed = None
        self.direction = None

        self._from_coords(lat, lon)

    def __str__(self):
        if self.valid:
            if self.current:
                dist = self.distance_from(self.current)
                bear = self.current.bearing_to(self)
                distance = " - %.1f %s away @ %.1f degrees" % (dist,
                                                               EARTH_UNITS,
                                                               bear)
            else:
                distance = ""

            if self.comment:
                comment = " (%s)" % self.comment
            else:
                comment = ""

            if self.speed and self.direction:
                if EARTH_UNITS == "mi":
                    speed = "%.1f mph" % (float(self.speed) * 1.15077945)
                elif EARTH_UNITS == "m":
                    speed = "%.1f km/h" % (float(self.speed) * 1.852)
                else:
                    speed = "%.2f knots" % float(self.speed)

                dir = " (Heading %.0f at %s)" % (self.direction, speed)
            else:
                dir = ""

            return "GPS: %s reporting %.4f,%.4f@%.1f at %s%s%s%s" % ( \
                self.station,
                self.latitude,
                self.longitude,
                self.altitude,
                self.date,
                comment,
                distance,
                dir)
        else:
            return "GPS: (Invalid GPS data)"

    def to_NMEA_GGA(self):
        """Returns an NMEA-compliant GPGGA sentence"""
        date = time.strftime("%H%M%S")

        if self.latitude > 0:
            lat = "%.3f,%s" % (deg2nmea(self.latitude), "N")
        else:
            lat = "%.3f,%s" % (deg2nmea(self.latitude * -1), "S")



        if self.longitude > 0:
            lon = "%.3f,%s" % (deg2nmea(self.longitude), "E")
        else:
            lon = "%.3f,%s" % (deg2nmea(self.longitude * -1), "W")

        data = "GPGGA,%s,%s,%s,1,%i,0,%.1f,M,0,M,," % ( \
            date,
            lat,
            lon,
            self.satellites,
            self.altitude)

        return "$%s%s\r\n%-8.8s,%-20.20s\r\n" % (data,
                                                 NMEA_checksum(data),
                                                 self.station,
                                                 self.comment)

    def to_APRS(self, dest="APRATS"):
        """Returns a GPS-A (APRS-compliant) string"""
        s = "%s>%s,DSTAR*:!" % (self.station, dest)

        if self.latitude > 0:
            ns = "N"
            Lm = 1
        else:
            ns = "S"
            Lm = -1

        if self.longitude > 0:
            ew = "E"
            lm = 1
        else:
            ew = "W"            
            lm = -1

        s += "%.2f%s/%08.2f%s>" % (deg2nmea(self.latitude * Lm), ns,
                                  deg2nmea(self.longitude * lm), ew)
        if self.speed and self.direction:
            s += "%.1f/%.1f" % (float(self.speed), float(self.direction))

        if self.comment:
            s += " %s" % self.comment
            
        s += "\r"

        return "$$CRC%04X,%s\n" % (GPSA_checksum(s), s)

    def set_station(self, station, comment="D-RATS"):
        self.station = station
        self.comment = comment

    def distance_from(self, pos):
        return distance(self.latitude, self.longitude,
                        pos.latitude, pos.longitude)

    def bearing_to(self, pos):
        lat_me = deg2rad(self.latitude)
        lon_me = deg2rad(self.longitude)

        lat_u = deg2rad(pos.latitude)
        lon_u = deg2rad(pos.longitude)

        lat_d = deg2rad(pos.latitude - self.latitude)
        lon_d = deg2rad(pos.longitude - self.longitude)

        y = sin(lon_d) * cos(lat_u)
        x = cos(lat_me) * sin(lat_u) - \
            sin(lat_me) * cos(lat_u) * cos(lon_d)

        bearing = rad2deg(atan2(y, x))

        return (bearing + 360) % 360

    def set_relative_to_current(self, current):
        self.current = current

    def coordinates(self):
        return "%.4f,%.4f" % (self.latitude, self.longitude)

    def fuzzy_to(self, pos):
        dir = self.bearing_to(pos)

        dirs = ["N", "NNE", "NE", "ENE", "E",
                "ESE", "SE", "SSE", "S",
                "SSW", "SW", "WSW", "W",
                "WNW", "NW", "NNW"]

        delta = 22.5
        angle = 0

        direction = "?"
        for i in dirs:
            if dir > angle and dir < (angle + delta):
                direction = i
            angle += delta

        return "%.1f %s %s" % (self.distance_from(pos),
                               EARTH_UNITS,
                               direction)

class NMEAGPSPosition(GPSPosition):
    """A GPSPosition initialized from a NMEA sentence"""
    def _test_checksum(self, string, csum):
        try:
            idx = string.index("*")
        except:
            print "String does not contain '*XY' checksum"
            return False

        segment = string[1:idx]

        csum = csum.upper()
        _csum = NMEA_checksum(segment).upper()

        return csum == _csum

    def _parse_GPGGA(self, string):
        csvel = "[^,]+"
        expr = \
            "\$GPGGA,(%s),(%s),([NS]),(%s),([EW]),([0-9]),(%s),(%s),(%s),([A-Z]),(%s),([A-Z]),,(%s),?(%s)?" % \
        (csvel, csvel, csvel, csvel, csvel, csvel, csvel, csvel, csvel)

        m = re.match(expr, string)
        if not m:
            raise Exception("Unable to parse GPGGA")

        t = m.group(1)
        self.date = "%02i:%02i:%02i" % (int(t[0:2]),
                                        int(t[2:4]),
                                        int(t[4:6]))

        self.latitude = nmea2deg(float(m.group(2)), m.group(3))
        self.longitude = nmea2deg(float(m.group(4)), m.group(5))

        print "%f,%f" % (self.latitude, self.longitude)

        self.satellites = int(m.group(7))
        self.altitude = float(m.group(9))
        if " "in m.group(13):
            (csum, self.station) = m.group(13).split(' ', 1)
            self.station = self.station.strip()
            self.comment = m.group(14).strip()
        else:
            csum = m.group(13)
            self.station = ""
            self.comment = ""
        
        self.valid = self._test_checksum(string, csum)

    def _parse_GPRMC(self, string):
        csvel = "[^,]+"
        expr = "\$GPRMC," \
            "(%s),(%s),"  \
            "(%s),(%s),"  \
            "(%s),(%s),"  \
            "(%s),(%s),"  \
            "(%s),(%s),"  \
            "([EW])(.*)" % (csvel, csvel, csvel, csvel,
                            csvel, csvel, csvel, csvel,
                            csvel, csvel)
        
        m = re.search(expr, string)
        if not m:
            raise Exception("Unable to parse GPMRC")

        if m.group(2) != "A":
            self.valid = False
            print "GPRMC marked invalid by GPS"
            return

        t = m.group(1)
        d = m.group(9)

        self.date = "%02i:%02i:%02i %02i-%02i-%02i" % (
            int(t[0:2]), int(t[2:4]), int(t[4:6]),
            int(d[0:2]), int(t[2:4]), int(t[4:6]))

        self.latitude = nmea2deg(float(m.group(3)), m.group(4))
        self.longitude = nmea2deg(float(m.group(5)), m.group(6))

        self.speed = float(m.group(7))
        self.direction = float(m.group(8))

        csum = m.group(12)

        self.valid = self._test_checksum(string, csum)

    def _from_NMEA_GPGGA(self, string):
        string = string.replace('\r', ' ')
        string = string.replace('\n', ' ') 
        try:
            self._parse_GPGGA(string)
        except Exception, e:
            print "Invalid GPS data: %s" % e
            self.valid = False

    def _from_NMEA_GPRMC(self, string):
        try:
            self._parse_GPRMC(string)
        except Exception, e:
            print "Invalid GPS data: %s" % e
            self.valid = False

    def __init__(self, sentence, station="UNKNOWN"):
        GPSPosition.__init__(self)

        if sentence.startswith("$GPGGA"):
            self._from_NMEA_GPGGA(sentence)
        elif sentence.startswith("$GPRMC"):
            self._from_NMEA_GPRMC(sentence)
        else:
            print "Unsupported GPS sentence type: %s" % sentence    

class APRSGPSPosition(GPSPosition):
    def _parse_GPSA(self, string):
        elements = string.split(",")

        if not elements[0].startswith("$$CRC"):
            print "Missing $$CRC..."
            return

        crc = re.search("^\$\$CRC([A-Z0-9]{4})", elements[0]).group(1)
        
        self.station, dst = elements[1].split(">")

        path, data = elements[2].split(":")

        latlon, extra = data.split(">")

        lat, lon = latlon[1:].split("/")

        self.latitude = nmea2deg(float(lat[:-1]), lat[-1])
        self.longitude = nmea2deg(float(lon[:-1]), lon[-1])

        self.date = time.strftime("%H:%M:%S")
        
        self.valid = True

    def _from_APRS(self, string):
        self.valid = False
        try:
            self._parse_GPSA(string)
        except Exception, e:
            print "Invalid APRS: %s" % e
            return False

        return self.valid        

    def __init__(self, message):
        GPSPosition.__init__(self)

        self._from_APRS(message)

class MapImage:
    def __init__(self, center):
        self.key = "ABQIAAAAWot3KuWpenfCAGfQ65FdzRTaP0xjRaMPpcw6bBbU2QUEXQBgHBR5Rr2HTGXYVWkcBFNkPvxtqV4VLg"
        self.center = center
        self.markers = [center]

    def add_markers(self, markers):
        self.markers += markers

    def get_image_url(self):
        el = [ "key=%s" % self.key,
               "center=%s" % self.center.coordinates(),
               "size=400x400"]

        mstr = "markers="
        index = ord("a")
        for m in self.markers:
            mstr += "%s,blue%s|" % (m.coordinates(), chr(index))
            index += 1

        el.append(mstr)

        return "http://maps.google.com/staticmap?%s" % ("&".join(el))

    def station_table(self):
        table = ""

        index = ord('A')
        for m in self.markers:
            table += "<tr><td>%s</td><td>%s</td><td>%s</td>\n" % (\
                chr(index),
                m.station,
                m.coordinates())
            index += 1
            
        return table

    def make_html(self):
        return """
<html>
  <head>
    <title>Known stations</title>
  </head>
  <body>
    <h1> Known Stations </h1>
    <img src="%s"/><br/><br/>
    <table border="1">
%s
    </table>
  </body>
</html>
""" % (self.get_image_url(), self.station_table())

    def display_in_browser(self):
        f = tempfile.NamedTemporaryFile(suffix=".html")
        name = f.name
        f.close()
        f = file(name, "w")
        f.write(self.make_html())
        f.flush()
        f.close()
        p = platform.get_platform()
        p.open_html_file(f.name)

class GPSSource:
    def __init__(self, port):
        self.port = port
        self.enabled = False

        self.serial = serial.Serial(port=port, baudrate=4800, timeout=1)
        self.thread = None

        self.last_valid = False
        self.position = GPSPosition()

    def start(self):
        self.enabled = True
        self.thread = threading.Thread(target=self.gpsthread)
        self.thread.start()

    def stop(self):
        if self.thread and self.enabled:
            self.enabled = False
            self.thread.join()

    def gpsthread(self):
        while self.enabled:
            data = self.serial.read(1024)
            lines = data.split("\r\n")
            
            for line in lines:
                if line.startswith("$GPGGA") or \
                        line.startswith("$GPRMC"):
                    position = NMEAGPSPosition(line)

                    self.last_valid = position.valid
                    if position.valid:
                        self.position = position
                    else:
                        print "Could not parse: %s" % line
                    
            time.sleep(1)

    def get_position(self):
        return self.position

    def status_string(self):
        if self.last_valid and self.position.satellites >= 3:
            return "GPS Locked (%i sats)" % self.position.satellites
        else:
            return "GPS Not Locked"

class StaticGPSSource(GPSSource):
    def __init__(self, lat, lon):
        self.lat = lat
        self.lon = lon

        self.position = GPSPosition(self.lat, self.lon)

    def start(self):
        pass

    def stop(self):
        pass

    def get_position(self):
        return self.position

    def status_string(self):
        return "Static position"

def parse_GPS(string):
    try:
        if "$GPGGA" in string:
            return NMEAGPSPosition(string[string.index("$GPGGA"):])
        elif "$$CRC" in string:
            return APRSGPSPosition(string[string.index("$$CRC"):])
    except Exception, e:
        print "Exception during GPS parse: %s" % e

    return None

if __name__ == "__main__":

#    p = parse_GPS("08:44:37: " + TEST)
    P = GPSPosition(nmea2deg(3302.39), nmea2deg(9644.66, "W"))
    #P.from_coords(45.525012, -122.916434)
    #P.from_coords(,
    #              )
#    p.set_relative_to_current(P)
#    if not p:
#        print "Failed"
#    else:
#        print "Date:       %s" % p.date
#        print "Latitude:   %s" % p.latitude
#        print "Longitude:  %s" % p.longitude
#        print "# Sats:     %s" % p.satellites
#        print "Altitude:   %s" % p.altitude
#        print "Station:    %s" % p.station
#        print "Comment:    %s" % p.comment
#
#        print "\n%s" % str(p)
#        print "\n%s" % p.to_NMEA_GGA().replace("\r", "\n")
#
#        print "Checksum of TEST: %s" % NMEA_checksum("GPGGA,180718.02,4531.3740,N,12255.4599,W,1,07,1.4,50.6,M,-21.4,M,,")
#
#        print "Distance: %s" % P.distance_from(p)
#        print "Bearing: %s" % P.bearing_to(p)
#        
#        print P.fuzzy_to(p)
#
    P.station = "AE5PL-T"
    #P.comment = "Dan Mobile"
#
#        print P.to_NMEA_GGA().replace("\r", "\n")

    print P.to_APRS(dest="API282")
        
#    gps = GPSSource("/dev/ttyS0")
#    gps.start()
#
#    for i in range(30):
#        time.sleep(1)
#
#    print "Stopping"
#    gps.stop()

    string = "AE5PL-T>API282,DSTAR*:!3302.39N/09644.66W>/\r"

    print "%X" % GPSA_checksum(string)

    string = "$$CRCCE3E,%s" % string

    PP = APRSGPSPosition(string)
    print PP

    string = "$GPRMC,220516,A,5133.82,N,00042.24,W,173.8,231.8,130694,004.2,W*70"

    PPP = NMEAGPSPosition(string)
    print PPP
    print PPP.to_APRS()
