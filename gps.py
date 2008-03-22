import re
import time

TEST = "$GPGGA,180718.02,4531.3740,N,12255.4599,W,1,07,1.4,50.6,M,-21.4,M,,*63 KE7JSS  ,440.350+ PL127.3"

class GPSPosition:
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
        self.altitude = "%s %s" % (m.group(9), m.group(10))
        self.station = m.group(13).split(' ', 1)[1].strip()
        self.comment = m.group(14).strip()
        
    def __init__(self, string):
        string = string.replace('\r', ' ')
        string = string.replace('\n', ' ') 
        try:
            self.parse_string(string)
            self.valid = True
        except Exception, e:
            print "Invalid GPS data: %s" % e
            self.valid = False
            return

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

    def to_NMEA_GGA(self, station, comment="D-RATS"):
        date = time.strftime("%H%M%S")
        if self.latitude > 0:
            lat = "%.4f,%s" % (self.latitude, "N")
        else:
            lat = "%.4f,%s" % (self.latitude * -1, "S")

        if self.longitude > 0:
            lon = "%.4f,%s" % (self.longitude, "E")
        else:
            lon = "%.4f,%s" % (self.longitude * -1, "W")

        return "$GPGGA,%s,%s,%s,1,0,0,0,M,0,M,,*00 %s,%s" % ( \
            date, lat, lon, station, comment)

def parse_GPS(string):
    if string.startswith("$GPGGA,"):
        return GPSPosition(string)

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
        print "\n%s" % p.to_NMEA_GGA("KI4IFW")
