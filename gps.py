import re
import time
import tempfile
import platform

from math import pi,cos,acos,sin,atan2

TEST = "$GPGGA,180718.02,4531.3740,N,12255.4599,W,1,07,1.4,50.6,M,-21.4,M,,*63 KE7JSS  ,440.350+ PL127.3"

EARTH_RADIUS = 3963.1
EARTH_UNITS = "mi"

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

def NMEA_checksum(string):
    checksum = 0
    for i in string:
        checksum ^= ord(i)

    return "*%02x" % checksum

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

def nmea2deg(nmea):
    deg = int(nmea) / 100
    min = nmea % (deg * 100)

    return dm2deg(deg, min)

def deg2nmea(deg):
    deg, min = deg2dm(deg)

    return (deg * 100) + min

def distance(lat_a, lon_a, lat_b, lon_b):
    lat_a = deg2rad(lat_a)
    lon_a = deg2rad(lon_a)
    
    lat_b = deg2rad(lat_b)
    lon_b = deg2rad(lon_b)
    
    earth_radius = EARTH_RADIUS # miles
    
    distance = acos((cos(lat_a) * cos(lon_a) * \
                         cos(lat_b) * cos(lon_b)) + \
                        (cos(lat_a) * sin(lon_a) * \
                             cos(lat_b) * sin(lon_b)) + \
                        (sin(lat_a) * sin(lat_b)))
    
    return distance * earth_radius


class GPSPosition:
    def __init__(self, lat=0, lon=0, station="UNKNOWN"):
        self.valid = False
        self.latitude = lat
        self.longitude = lon
        self.altitude = 0
        self.satellites = 0
        self.station = station
        self.comment = ""
        self.current = None

    def test_checksum(self, string, csum):
        try:
            idx = string.index("*")
        except:
            print "String does not contain '*XY' checksum"
            return False

        segment = string[1:idx]

        print "Checking checksum: |%s|" % segment

        print "Calc'd: %s" % NMEA_checksum(segment)
        print "Recv'd: %s" % csum

        return csum == NMEA_checksum(segment)

    def parse_string(self, string):
        csvel = "[^,]+"
        expr = \
            "\$GPGGA,(%s),(%s),([NS]),(%s),([EW]),([0-9]),(%s),(%s),(%s),([A-Z]),(%s),([A-Z]),,(%s),(%s)" % \
        (csvel, csvel, csvel, csvel, csvel, csvel, csvel, csvel, csvel)

        m = re.match(expr, string)
        if not m:
            raise Exception("Unable to parse sentence")

        t = m.group(1)
        self.date = "%02i:%02i:%02i" % (int(t[0:2]),
                                        int(t[2:4]),
                                        int(t[4:6]))

        if m.group(3) == "S":
            mult = -1
        else:
            mult = 1
        self.latitude = nmea2deg(float(m.group(2))) * mult

        if m.group(5) == "W":
            mult = -1
        else:
            mult = 1
        self.longitude = nmea2deg(float(m.group(4))) * mult

        print "%f,%f" % (self.latitude, self.longitude)

        self.satellites = int(m.group(7))
        self.altitude = float(m.group(9))
        (csum, self.station) = m.group(13).split(' ', 1)
        self.station = self.station.strip()
        self.comment = m.group(14).strip()
        
        self.valid = self.test_checksum(string, csum)

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

            return "GPS: %s reporting %.4f,%.4f@%.1f at %s%s%s" % ( \
                self.station,
                self.latitude,
                self.longitude,
                self.altitude,
                self.date,
                comment,
                distance)
        else:
            return "GPS: (Invalid GPS data)"

    def to_NMEA_GGA(self):
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

    def from_NMEA_GGA(self, string):
        string = string.replace('\r', ' ')
        string = string.replace('\n', ' ') 
        try:
            self.parse_string(string)
        except Exception, e:
            print "Invalid GPS data: %s" % e
            self.valid = False
            return

    def from_coords(self, lat, lon, alt=0):
        self.latitude = lat
        self.longitude = lon
        self.altitude = alt
        self.satellites = 3
        self.valid = True

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
                print "%f : %s" % (dir, angle)
                direction = i
            angle += delta

        return "%.1f %s %s" % (self.distance_from(pos),
                               EARTH_UNITS,
                               direction)

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

def parse_GPS(string):
    if "$GPGGA" in string:
        p = GPSPosition()
        p.from_NMEA_GGA(string[string.index("$GPGGA"):])
        return p
    else:
        return None

if __name__ == "__main__":

    p = parse_GPS("08:44:37: " + TEST)
    P = GPSPosition()
    P.from_coords(45.525012, -122.916434)
    p.set_relative_to_current(P)
    if not p:
        print "Failed"
    else:
        print "Date:       %s" % p.date
        print "Latitude:   %s" % p.latitude
        print "Longitude:  %s" % p.longitude
        print "# Sats:     %s" % p.satellites
        print "Altitude:   %s" % p.altitude
        print "Station:    %s" % p.station
        print "Comment:    %s" % p.comment

        print "\n%s" % str(p)
        print "\n%s" % p.to_NMEA_GGA().replace("\r", "\n")

        print "Checksum of TEST: %s" % NMEA_checksum("GPGGA,180718.02,4531.3740,N,12255.4599,W,1,07,1.4,50.6,M,-21.4,M,,")

        print "Distance: %s" % P.distance_from(p)
        print "Bearing: %s" % P.bearing_to(p)
        
        print P.fuzzy_to(p)

        P.station = "KI4IFW M"
        P.comment = "Dan Mobile"

        print P.to_NMEA_GGA().replace("\r", "\n")
