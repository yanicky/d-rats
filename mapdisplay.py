#!/usr/bin/python

import os
from math import *
import urllib
import time

import gtk
import gobject

import platform
import miscwidgets

from gps import GPSPosition

class MapTile:
    def path_els(self):
        # http://svn.openstreetmap.org/applications/routing/pyroute/tilenames.py
        def numTiles(z):
            return(pow(2,z))
        
        def sec(x):
            return(1/cos(x))

        def latlon2relativeXY(lat,lon):
            x = (lon + 180) / 360
            y = (1 - log(tan(radians(lat)) + sec(radians(lat))) / pi) / 2
            return(x,y)
        
        def latlon2xy(lat,lon,z):
            n = numTiles(z)
            x,y = latlon2relativeXY(lat,lon)
            return(n*x, n*y)
        
        def tileXY(lat, lon, zoom):
            x, y = latlon2xy(lat, lon, zoom)
            return (int(x), int(y))

        x, y = tileXY(self.lat, self.lon, self.zoom)

        return x, y

    def tile_edges(self):
        def numTiles(z):
            return(pow(2,z))

        def mercatorToLat(mercatorY):
            return(degrees(atan(sinh(mercatorY))))

        def latEdges(y,z):
            n = numTiles(z)
            unit = 1 / n
            relY1 = y * unit
            relY2 = relY1 + unit
            lat1 = mercatorToLat(pi * (1 - 2 * relY1))
            lat2 = mercatorToLat(pi * (1 - 2 * relY2))
            return(lat1,lat2)

        def lonEdges(x,z):
            n = numTiles(z)
            unit = 360 / n
            lon1 = -180 + x * unit
            lon2 = lon1 + unit
            return(lon1,lon2)
  
        def tileEdges(x,y,z):
            lat1,lat2 = latEdges(y,z)
            lon1,lon2 = lonEdges(x,z)
            return((lat2, lon1, lat1, lon2)) # S,W,N,E
        
        return tileEdges(self.x, self.y, self.zoom)

    def lat_range(self):
        edges = self.tile_edges()
        return (edges[2], edges[0])

    def lon_range(self):
        edges = self.tile_edges()
        return (edges[1], edges[3])

    def path(self):
        return "%d/%d/%d.png" % (self.zoom, self.x, self.y)

    def _local_path(self):
        path = os.path.join(self.dir, self.path())
        if not os.path.isdir(os.path.dirname(path)):
            os.makedirs(os.path.dirname(path))

        return path

    def is_local(self):
        return os.path.exists(self._local_path())

    def fetch(self):
        if not os.path.exists(self._local_path()):
            urllib.urlretrieve(self.remote_path(), self._local_path())

    def local_path(self):
        path = self._local_path()
        self.fetch()

        return path

    def remote_path(self):
        return "http://dev.openstreetmap.org/~ojw/Tiles/tile.php/%s" % self.path()

    def __add__(self, count):
        (x, y) = count

        def mercatorToLat(mercatorY):
            return(degrees(atan(sinh(mercatorY))))

        def numTiles(z):
            return(pow(2,z))

        def xy2latlon(x,y,z):
            n = numTiles(z)
            relY = y / n
            lat = mercatorToLat(pi * (1 - 2 * relY))
            lon = -180.0 + 360.0 * x / n
            return(lat,lon)

        (lat, lon) = xy2latlon(self.x + x, self.y + y, self.zoom)

        return MapTile(lat, lon, self.zoom)

    def __sub__(self, tile):
        return (self.x - tile.x, self.y - tile.y)

    def __contains__(self, point):
        (lat, lon) = point

        # FIXME for non-western!
        (lat_max, lat_min) = self.lat_range()
        (lon_min, lon_max) = self.lon_range()

        #print "%f < %f < %f" % (lat_min, lat, lat_max)
        #print "%f < %f < %f" % (lon_min, lon, lon_max)

        lat_match = (lat < lat_max and lat > lat_min)
        lon_match = (lon < lon_max and lon > lon_min)

        print "LAT: %s LON: %s" % (lat_match, lon_match)

        return lat_match and lon_match

    def __init__(self, lat, lon, zoom):
        self.lat = lat
        self.lon = lon
        self.zoom = zoom

        self.x, self.y = self.path_els()

        self.platform = platform.get_platform()
        self.dir = os.path.join(self.platform.config_dir(), "maps")
        if not os.path.isdir(self.dir):
            os.mkdir(self.dir)

class MapWidget(gtk.DrawingArea):
    def draw_marker_at(self, x, y, text):
        gc = self.get_style().black_gc

        pl = self.create_pango_layout("")
        markup = '<span background="yellow">%s</span>' % text
        pl.set_markup(markup)
        self.window.draw_layout(gc, x, y, pl)

    def draw_marker(self, id):
        (lat, lon, comment) = self.markers[id]

        y = 1- ((lat - self.lat_min) / (self.lat_max - self.lat_min))
        x = 1- ((lon - self.lon_min) / (self.lon_max - self.lon_min))

        print "%f, %f" % (x,y)
        print "%f %f %f" % (self.lat_min, lat, self.lat_max)
        print "%ix%i" % ((self.tilesize * self.width),
                         (self.tilesize * self.height))

        x *= (self.tilesize * self.width)
        y *= (self.tilesize * self.height)

        print "%s label is %i,%i" % (id, x,y)

        self.draw_marker_at(x, y, id)

    def draw_markers(self):
        for id in self.markers.keys():
            self.draw_marker(id)

    def expose(self, area, event):

        if len(self.map_bufs) == 0:
            self.load_tiles()

        gc = self.get_style().black_gc

        for i in range(0, self.width):
            for j in range(0, self.height):
                index = (i * self.height) + j
                try:
                    (pb, _) = self.map_bufs[index]
                except:
                    print "Index %i out of range (%i)" % (index,
                                                          len(self.map_bufs))
                    return

                self.window.draw_pixbuf(gc,
                                        pb,
                                        0, 0,
                                        self.tilesize * i,
                                        self.tilesize * j,
                                        -1, -1)
                
        self.draw_markers()

    def calculate_bounds(self):
        (_, topleft) = self.map_bufs[0]
        (_, botright) = self.map_bufs[-1]

        (self.lat_min, _, _, self.lon_min) = botright.tile_edges()
        (_, self.lon_max, self.lat_max, _) = topleft.tile_edges()        

    def load_tiles(self):
        prog = miscwidgets.ProgressDialog("Loading map")
        prog.show()

        prog.set_text("Getting map center")
        center = MapTile(self.lat, self.lon, self.zoom)

        delta_h = self.height / 2
        delta_w = self.width  / 2

        count = 0
        total = self.width * self.height

        for i in range(0, self.width):
            for j in range(0, self.height):
                tile = center + (i - delta_w, j - delta_h)
                if not tile.is_local():
                    prog.set_text("Retrieving %i, %i" % (i,j))
                else:
                    prog.set_text("Loading %i, %i" % (i, j))
                
                try:
                    pb = gtk.gdk.pixbuf_new_from_file(tile.local_path())
                except Exception, e:
                    print "Broken cached file: %s" % tile.local_path()
                    continue
 
                self.map_bufs.append((pb, tile))

                count += 1
                prog.set_fraction(float(count) / float(total))

        self.calculate_bounds()

        prog.set_text("Complete")
        prog.hide()

    def __init__(self, width, height, tilesize=256):
        gtk.DrawingArea.__init__(self)

        self.height = height
        self.width = width
        self.tilesize = tilesize

        self.lat = 0
        self.lon = 0
        self.zoom = 1

        self.markers = {}
        self.map_bufs = []

        self.set_size_request(self.tilesize * self.width,
                              self.tilesize * self.height)
        self.connect("expose-event", self.expose)

    def set_center(self, lat, lon):
        self.lat = lat
        self.lon = lon
        self.map_bufs = []
        self.queue_draw()

    def get_center(self):
        return (self.lat, self.lon)

    def set_zoom(self, zoom):
        if zoom > 15 or zoom == 1:
            return

        self.zoom = zoom
        self.map_bufs = []
        self.queue_draw()

    def get_zoom(self):
        return self.zoom

    def set_marker(self, id, lat, lon, comment=None):
        self.markers[id] = (lat, lon, comment)
        self.queue_draw()

    def del_marker(self, id):
        del self.markers[id]

class MapWindow(gtk.Window):
    def zoom_in(self, widget, data=None):
        self.map.set_zoom(self.map.get_zoom() + 1)

    def zoom_out(self, widget, data=None):
        self.map.set_zoom(self.map.get_zoom() - 1)
    
    def make_zoom_controls(self):
        box = gtk.HBox(False, 2)

        zi = gtk.Button("+")
        zi.connect("clicked", self.zoom_in)
        zi.set_size_request(75,75)
        zi.show()

        zo = gtk.Button("-")
        zo.connect("clicked", self.zoom_out)
        zo.set_size_request(75,75)
        zo.show()

        box.pack_start(zo, 0,0,0)
        box.pack_start(zi, 0,0,0)

        box.show()

        return box

    def recenter(self, view, path, column, data=None):
        items = self.marker_list.get_selected()

        self.map.set_center(items[2], items[3])
        self.refresh_marker_list()
        self.scroll_to_center(self.sw)

    def make_marker_list(self):
        cols = [(gobject.TYPE_BOOLEAN, "Show"),
                (gobject.TYPE_STRING, "Station"),
                (gobject.TYPE_FLOAT, "Latitude"),
                (gobject.TYPE_FLOAT, "Longitude"),
                (gobject.TYPE_FLOAT, "Distance"),
                (gobject.TYPE_FLOAT, "Direction"),
                ]
        self.marker_list = miscwidgets.ListWidget(cols)
        self.marker_list.set_size_request(-1, 150)

        self.marker_list._view.connect("row-activated", self.recenter)

        self.marker_list.show()

        return self.marker_list

    def refresh_marker_list(self):
        self.marker_list.set_values([])
        self.map.markers = {}

        (lat, lon) = self.map.get_center()
        center = GPSPosition(lat=lat, lon=lon)

        for id, fix in self.markers.items():
            self.marker_list.add_item(True,
                                      id,
                                      fix.latitude,
                                      fix.longitude,
                                      center.distance_from(fix),
                                      center.bearing_to(fix))
            self.map.markers[id] = (fix.latitude, fix.longitude, None)

    def make_bottom_pane(self):
        box = gtk.HBox(False, 2)

        box.pack_start(self.make_marker_list(), 1,1,1)
        box.pack_start(self.make_zoom_controls(), 0,0,0)

        box.show()

        return box

    def scroll_to_center(self, widget):
        a = widget.get_vadjustment()
        print a.upper
        print a.lower
        a.set_value((a.upper - a.page_size) / 2)

        print a.upper
        a = widget.get_hadjustment()
        a.set_value((a.upper - a.page_size) / 2)

    def __init__(self, *args):
        gtk.Window.__init__(self, *args)

        tiles = 5

        self.map = MapWidget(tiles, tiles)
        self.map.show()

        box = gtk.VBox(False, 2)

        self.sw = gtk.ScrolledWindow()
        self.sw.add_with_viewport(self.map)
        self.sw.show()

        self.sw.connect('realize', self.scroll_to_center)

        box.pack_start(self.sw, 1,1,1)
        box.pack_start(self.make_bottom_pane(), 0,0,0)
        box.show()

        self.set_default_size(600,600)
        self.set_geometry_hints(max_width=tiles*256,
                                max_height=tiles*256)

        self.markers = {}

        self.add(box)

    def set_marker(self, fix):
        self.markers[fix.station] = fix
        self.map.set_marker(fix.station, fix.latitude, fix.longitude)
        self.refresh_marker_list()

    def del_marker(self, id):
        self.map.del_marker(id)
        self.refresh_marker_list()

    def set_zoom(self, zoom):
        self.map.set_zoom(zoom)

    def set_center(self, lat, lon):
        self.map.set_center(lat, lon)

if __name__ == "__main__":

    m = MapWindow()
    m.set_center(45.525012, -122.916434)
    m.set_zoom(14)

    m.set_marker(GPSPosition(station="KI4IFW", lat=45.525012, lon=-122.916434))
    m.set_marker(GPSPosition(station="KE7FTE", lat=45.5363, lon=-122.9105))
    m.set_marker(GPSPosition(station="KA7VQH", lat=45.4846, lon=-122.8278))
    m.set_marker(GPSPosition(station="N7QQU", lat=45.5625, lon=-122.8645))

    m.show()

    print m.sw.get_vadjustment().get_value()

    try:
        gtk.main()
    except:
        pass

    print m.sw.get_vadjustment().get_value()


#    area = gtk.DrawingArea()
#    area.set_size_request(768, 768)
#
#    w = gtk.Window(gtk.WINDOW_TOPLEVEL)
#    w.add(area)
#    area.show()
#    w.show()
#
#    def expose(area, event):
#        for i in range(1,4):
#            img = gtk.gdk.pixbuf_new_from_file("/tmp/tile%i.png" % i)
#            area.window.draw_pixbuf(area.get_style().black_gc,
#                                    img,
#                                    0, 0, 256 * (i-1), 0, 256, 256)
#
#    area.connect("expose-event", expose)
#
