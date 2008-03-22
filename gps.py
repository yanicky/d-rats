import re
import time

TEST = "$GPGGA,180718.02,4531.3740,N,12255.4599,W,1,07,1.4,50.6,M,-21.4,M,,*63 KE7JSS  ,440.350+ PL127.3"

def NMEA_checksum(string):
    checksum = 0
    for i in string:
        checksum ^= ord(i)

    return "*%02x" % checksum

class GPSPosition:
    def __init__(self):
        self.valid = False
        self.latitude = 0
        self.longitude = 0
        self.altitude = 0
        self.satellites = 0
        self.station = "UNKNOWN"
        self.comment = ""

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
        self.latitude = float(m.group(2)) * mult

        if m.group(5) == "W":
            mult = -1
        else:
            mult = 1
        self.longitude = float(m.group(4)) * mult

        self.satellites = int(m.group(7))
        self.altitude = float(m.group(9))
        self.station = m.group(13).split(' ', 1)[1].strip()
        self.comment = m.group(14).strip()
        
    def __str__(self):
        if self.valid:
            return "GPS: %s reporting %s,%s@%s at %s (%s)" % (self.station,
                                                              self.latitude,
                                                              self.longitude,
                                                              self.altitude,
                                                              self.date,
                                                              self.comment)
        else:
            return "GPS: (Invalid GPS data)"

    def to_NMEA_GGA(self):
        date = time.strftime("%H%M%S")
        if self.latitude > 0:
            lat = "%.3f,%s" % (self.latitude, "N")
        else:
            lat = "%.3f,%s" % (self.latitude * -1, "S")

        if self.longitude > 0:
            lon = "%.3f,%s" % (self.longitude, "E")
        else:
            lon = "%.3f,%s" % (self.longitude * -1, "W")

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
        self.latitude = lat * 100
        self.longitude = lon * 100
        self.altitude = alt
        self.satellites = 3
        self.valid = True

    def set_station(self, station, comment="D-RATS"):
        self.station = station
        self.comment = comment

def parse_GPS(string):
    if string.startswith("$GPGGA,"):
        p = GPSPosition()
        p.from_NMEA_GGA(string)
        return p
    else:
        return None

if __name__ == "__main__":
    p = parse_GPS(TEST)
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
