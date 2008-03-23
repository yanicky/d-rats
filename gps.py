import re
import time

from math import pi,cos,acos,sin

TEST = "$GPGGA,180718.02,4531.3740,N,12255.4599,W,1,07,1.4,50.6,M,-21.4,M,,*63 KE7JSS  ,440.350+ PL127.3"

def NMEA_checksum(string):
    checksum = 0
    for i in string:
        checksum ^= ord(i)

    return "*%02x" % checksum

def deg2rad(deg):
    return deg * (pi / 180)

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

class GPSPosition:
    def __init__(self):
        self.valid = False
        self.latitude = 0
        self.longitude = 0
        self.altitude = 0
        self.satellites = 0
        self.station = "UNKNOWN"
        self.comment = ""
        self.current = None

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
        self.station = m.group(13).split(' ', 1)[1].strip()
        self.comment = m.group(14).strip()
        
    def __str__(self):
        if self.valid:
            if self.current:
                dist = self.distance_from(self.current)
                distance = " [%.1f miles away]" % dist
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

        return "$%s%s %s,%s" % (data,
                               NMEA_checksum(data),
                               self.station,
                               self.comment)

    def from_NMEA_GGA(self, string):
        string = string.replace('\r', ' ')
        string = string.replace('\n', ' ') 
        try:
            self.parse_string(string)
            self.valid = True
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
        lat_me = deg2rad(self.latitude)
        lon_me = deg2rad(self.longitude)

        lat_u = deg2rad(pos.latitude)
        lon_u = deg2rad(pos.longitude)

        earth_radius = 3963.1 # miles

        distance = acos((cos(lat_me) * cos(lon_me) * \
                             cos(lat_u) * cos(lon_u)) + \
                            (cos(lat_me) * sin(lon_me) * \
                                 cos(lat_u) * sin(lon_u)) + \
                            (sin(lat_me) * sin(lat_u)))
        
        return distance * earth_radius

    def set_relative_to_current(self, current):
        self.current = current

def parse_GPS(string):
    if string.startswith("$GPGGA,"):
        p = GPSPosition()
        p.from_NMEA_GGA(string)
        return p
    else:
        return None

if __name__ == "__main__":

    p = parse_GPS(TEST)
    P = GPSPosition()
    P.from_coords(45.535156, -122.956260)
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
        print "\n%s" % p.to_NMEA_GGA()

        print "Checksum of TEST: %s" % NMEA_checksum("GPGGA,180718.02,4531.3740,N,12255.4599,W,1,07,1.4,50.6,M,-21.4,M,,")

        print "Distance: %s" % P.distance_from(p)
