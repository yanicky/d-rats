#!/usr/bin/python

import os
from math import *
import urllib
import time
import random
import shutil
import tempfile

import gtk
import gobject

import platform
import miscwidgets
import inputdialog

from gps import GPSPosition, distance, value_with_units

CROSSHAIR = "+"

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
            for i in range(10):
                url = self.remote_path()
                try:
                    urllib.urlretrieve(url, self._local_path())
                    return True
                except Exception, e:
                    print "[%i] Failed to fetch `%s': %s" % (i, url, e)

            return False
        else:
            return True

    def local_path(self):
        path = self._local_path()
        self.fetch()

        return path

    def remote_path(self):
        i = chr(ord("a") + random.randint(0,25))
        return "http://%s.tile.openstreetmap.org/%s" % (i, self.path())

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

        lat_match = (lat < lat_max and lat > lat_min)
        lon_match = (lon < lon_max and lon > lon_min)

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
    def draw_text_marker_at(self, x, y, text, color="yellow"):
        gc = self.get_style().black_gc

        if self.zoom < 12:
            size = 'size="x-small"'
        elif self.zoom < 14:
            size = 'size="small"'
        else:
            size = ''

        pl = self.create_pango_layout("")
        markup = '<span %s background="%s">%s</span>' % (size, color, text)
        pl.set_markup(markup)
        self.pixmap.draw_layout(gc, int(x), int(y), pl)

    def draw_cross_marker_at(self, x, y):
        width = 2
        cm = self.window.get_colormap()
        color = cm.alloc_color("red")
        gc = self.window.new_gc(foreground=color,
                                line_width=width)

        x = int(x)
        y = int(y)

        self.pixmap.draw_lines(gc, [(x, y-5), (x, y+5)])
        self.pixmap.draw_lines(gc, [(x-5, y), (x+5, y)])

    def latlon2xy(self, lat, lon):
        y = 1- ((lat - self.lat_min) / (self.lat_max - self.lat_min))
        x = 1- ((lon - self.lon_min) / (self.lon_max - self.lon_min))
        
        x *= (self.tilesize * self.width)
        y *= (self.tilesize * self.height)

        return (x, y)

    def xy2latlon(self, x, y):
        lon = 1 - (float(x) / (self.tilesize * self.width))
        lat = 1 - (float(y) / (self.tilesize * self.height))
        
        lat = (lat * (self.lat_max - self.lat_min)) + self.lat_min
        lon = (lon * (self.lon_max - self.lon_min)) + self.lon_min

        return lat, lon

    def draw_marker(self, id):
        (lat, lon, color) = self.markers[id]

        x, y = self.latlon2xy(lat, lon)

        if id == CROSSHAIR:
            self.draw_cross_marker_at(x, y)
        else:
            self.draw_text_marker_at(x, y, id, color)

    def draw_markers(self):
        for id in self.markers.keys():
            self.draw_marker(id)

    def expose(self, area, event):
        if len(self.map_tiles) == 0:
            self.load_tiles()

        gc = self.get_style().black_gc
        self.window.draw_drawable(gc,
                                  self.pixmap,
                                  0, 0,
                                  0, 0,
                                  -1, -1)

        #self.draw_markers()

    def calculate_bounds(self):
        topleft = self.map_tiles[0]
        botright = self.map_tiles[-1]

        (self.lat_min, _, _, self.lon_min) = botright.tile_edges()
        (_, self.lon_max, self.lat_max, _) = topleft.tile_edges()        

    def broken_tile(self):
        broken = [
            "48 16 3 1",
            "       c #FFFFFFFFFFFF",
            "x      c #FFFF00000000",
            "X      c #000000000000",
            "xx             xx   XX   X   XXX                ",
            " xx           xx    X X  X  X   X               ",
            "  xx         xx     X X  X X     X              ",
            "   xx       xx      X  X X X     X              ",
            "    xx     xx       X  X X X     X              ",
            "     xx   xx        X  X X  X   X               ",
            "      xx xx         X   XX   XXX                ",
            "       xxx                                      ",
            "       xxx                                      ",
            "      xx xx         XXXX     XX   XXXXX   XX    ",
            "     xx   xx        X   X   X  X    X    X  X   ",
            "    xx     xx       X    X X    X   X   X    X  ",
            "   xx       xx      X    X X    X   X   X    X  ",
            "  xx         xx     X    X XXXXXX   X   XXXXXX  ",
            " xx           xx    X   X  X    X   X   X    X  ",
            "xx             xx   XXXX   X    X   X   X    X  "
            ]

        return gtk.gdk.pixbuf_new_from_xpm_data(broken)

    def load_tiles(self):
        prog = miscwidgets.ProgressDialog("Loading map")

        prog.set_text("Getting map center")
        center = MapTile(self.lat, self.lon, self.zoom)

        delta_h = self.height / 2
        delta_w = self.width  / 2

        count = 0
        total = self.width * self.height

        try:
            self.pixmap = gtk.gdk.Pixmap(self.window,
                                         self.width * self.tilesize,
                                         self.height * self.tilesize)
        except Exception, e:
            # Window is not loaded, thus can't load tiles
            return

        gc = self.pixmap.new_gc()

        for i in range(0, self.width):
            for j in range(0, self.height):
                tile = center + (i - delta_w, j - delta_h)
                if not tile.is_local():
                    prog.set_text("Retrieving %i, %i" % (i,j))
                    prog.show()
                else:
                    prog.set_text("Loading %i, %i" % (i, j))
                
                try:
                    if not tile.fetch():
                        pb = self.broken_tile()
                    pb = gtk.gdk.pixbuf_new_from_file(tile.local_path())
                except Exception, e:
                    print "Broken cached file"
                    pb = self.broken_tile()
 
                self.pixmap.draw_pixbuf(gc,
                                        pb,
                                        0, 0,
                                        self.tilesize * i,
                                        self.tilesize * j,
                                        -1, -1)

                self.map_tiles.append(tile)

                count += 1
                prog.set_fraction(float(count) / float(total))

        self.calculate_bounds()

        prog.set_text("Complete")
        prog.hide()

        self.draw_markers()

    def export_to(self, filename, bounds=None):
        if not bounds:
            x = 0
            y = 0
            bounds = (0,0,-1,-1)
            width = self.tilesize * self.width
            height = self.tilesize * self.height
        else:
            x = bounds[0]
            y = bounds[1]
            width = bounds[2] - bounds[0]
            height = bounds[3] - bounds[1]

        pb = gtk.gdk.Pixbuf(gtk.gdk.COLORSPACE_RGB, False, 8, width, height)
        pb.get_from_drawable(self.pixmap, self.pixmap.get_colormap(),
                             x, y, 0, 0, width, height)
        pb.save(filename, "png")

    def __init__(self, width, height, tilesize=256):
        gtk.DrawingArea.__init__(self)

        self.height = height
        self.width = width
        self.tilesize = tilesize

        self.lat = 0
        self.lon = 0
        self.zoom = 1

        self.lat_max = self.lat_min = 0
        self.lon_max = self.lon_min = 0

        self.markers = {}
        self.map_tiles = []

        self.set_size_request(self.tilesize * self.width,
                              self.tilesize * self.height)
        self.connect("expose-event", self.expose)

    def set_center(self, lat, lon):
        self.lat = lat
        self.lon = lon
        self.map_tiles = []
        self.queue_draw()

    def get_center(self):
        return (self.lat, self.lon)

    def set_zoom(self, zoom):
        if zoom > 15 or zoom == 1:
            return

        self.zoom = zoom
        self.map_tiles = []
        self.queue_draw()

    def get_zoom(self):
        return self.zoom

    def set_marker(self, id, lat, lon, color="yellow"):
        self.markers[id] = (lat, lon, color)
        self.load_tiles()
        self.queue_draw()

    def del_marker(self, id):
        del self.markers[id]

    def scale(self, x, y, pixels=128):
        shift = 15
        tick = 5

        #rect = gtk.gdk.Rectangle(x-pixels,y-shift-tick,x,y)
        #self.window.invalidate_rect(rect, True)

        (lat_a, lon_a) = self.xy2latlon(self.tilesize, self.tilesize)
        (lat_b, lon_b) = self.xy2latlon(self.tilesize * 2, self.tilesize)

        # width of one tile
        d = distance(lat_a, lon_a, lat_b, lon_b) * (float(pixels) / self.tilesize)

        dist = value_with_units(d)

        color = self.window.get_colormap().alloc_color("black")
        gc = self.window.new_gc(line_width=1, foreground=color)

        self.window.draw_line(gc, x-pixels, y-shift, x, y-shift)
        self.window.draw_line(gc, x-pixels, y-shift, x-pixels, y-shift-tick)
        self.window.draw_line(gc, x, y-shift, x, y-shift-tick)
        self.window.draw_line(gc, x-(pixels/2), y-shift, x-(pixels/2), y-shift-tick)

        pl = self.create_pango_layout("")
        pl.set_markup("%s" % dist)
        self.window.draw_layout(gc, x-pixels, y-shift, pl)        

class MapWindow(gtk.Window):
    def zoom(self, widget, data=None):
        adj = widget.get_adjustment()

        self.map.set_zoom(int(adj.value))

    def make_zoom_controls(self):
        box = gtk.HBox(False, 3)
        box.set_border_width(3)
        box.show()

        l = gtk.Label("Min")
        l.show()
        box.pack_start(l, 0,0,0)

        adj = gtk.Adjustment(value=14,
                             lower=2,
                             upper=15,
                             step_incr=1,
                             page_incr=1)
        sb = gtk.HScrollbar(adj)
        sb.connect("value-changed", self.zoom)
        sb.show()
        box.pack_start(sb, 1,1,1)

        l = gtk.Label("Max")
        l.show()
        box.pack_start(l, 0,0,0)

        frame = gtk.Frame("Zoom")
        frame.set_label_align(0.5, 0.5)
        frame.set_size_request(150, 50)
        frame.show()
        frame.add(box)

        return frame

    def toggle_show(self, group, *vals):
        if self.markers.has_key(group):
            (fix, _, color) = self.markers[group][vals[1]]
            self.markers[group][vals[1]] = (fix, vals[0], color)
            print "Setting %s to %s" % (vals[1], vals[0])
        elif group == None:
            id = vals[1]
            for k,v in self.markers[id].items():
                nv = (v[0], vals[0], v[2])
                self.markers[id][k] = nv

        self.refresh_marker_list()
        self.map.load_tiles()
        self.map.queue_draw()

    def make_marker_list(self):
        cols = [(gobject.TYPE_BOOLEAN, "Show"),
                (gobject.TYPE_STRING, "Station"),
                (gobject.TYPE_FLOAT, "Latitude"),
                (gobject.TYPE_FLOAT, "Longitude"),
                (gobject.TYPE_FLOAT, "Distance"),
                (gobject.TYPE_FLOAT, "Direction"),
                ]
        self.marker_list = miscwidgets.TreeWidget(cols, 1, parent=False)
        self.marker_list.toggle_cb.append(self.toggle_show)

        self.marker_list._view.connect("row-activated", self.recenter_cb)

        def render_coord(col, rend, model, iter, cnum):
            if model.iter_parent(iter):
                rend.set_property('text', "%.4f" % model.get_value(iter, cnum))
            else:
                rend.set_property('text', '')

        for col in [2, 3]:
            c = self.marker_list._view.get_column(col)
            r = c.get_cell_renderers()[0]
            c.set_cell_data_func(r, render_coord, col)

        def render_dist(col, rend, model, iter, cnum):
            if model.iter_parent(iter):
                rend.set_property('text', "%.2f" % model.get_value(iter, cnum))
            else:
                rend.set_property('text', '')

        for col in [4, 5]:
            c = self.marker_list._view.get_column(col)
            r = c.get_cell_renderers()[0]
            c.set_cell_data_func(r, render_dist, col)

        sw = gtk.ScrolledWindow()
        sw.set_policy(gtk.POLICY_AUTOMATIC, gtk.POLICY_AUTOMATIC)
        sw.add(self.marker_list.packable())
        sw.set_size_request(-1, 150)
        sw.show()

        return sw

    def refresh_marker_list(self):
        self.map.markers = {}

        (lat, lon) = self.map.get_center()
        center = GPSPosition(lat=lat, lon=lon)

        for grp, lst in self.markers.items():
            for id, (fix, show, color) in lst.items():
                self.marker_list.set_item(grp,
                                          show,
                                          id,
                                          fix.latitude,
                                          fix.longitude,
                                          center.distance_from(fix),
                                          center.bearing_to(fix))
                if show:
                    self.map.markers[id] = (fix.latitude, fix.longitude, color)

    def make_track(self):
        def toggle(cb, mw):
            mw.tracking_enabled = cb.get_active()

        cb = gtk.CheckButton("Track center")
        cb.connect("toggled", toggle, self)

        cb.show()

        return cb

    def clear_map_cache(self):
        d = gtk.MessageDialog(buttons=gtk.BUTTONS_YES_NO)
        d.set_property("text", "Are you sure you want to clear your map cache?")
        r = d.run()
        d.destroy()

        if r == gtk.RESPONSE_YES:
            dir = os.path.join(platform.get_platform().config_dir(), "maps")
            shutil.rmtree(dir, True)
            self.map.queue_draw()
        
    def printable_map(self, bounds=None):
        p = platform.get_platform()

        f = tempfile.NamedTemporaryFile()
        fn = f.name
        f.close()

        mf = "%s.png" % fn
        hf = "%s.html" % fn

        ts = time.strftime("%H:%M:%S %d-%b-%Y")

        html = """
<html>
<body>
<h2>D-RATS Station map</h2>
<h5>Generated at %s</h5>
<img src="file://%s"/>
</body>
</html>
""" % (ts, mf)

        self.map.export_to(mf, bounds)

        f = file(hf, "w")
        f.write(html)
        f.close()

        p.open_html_file(hf)        

    def save_map(self, bounds=None):
        p = platform.get_platform()
        f = p.gui_save_file(default_name="map_%s.png" % \
                                time.strftime("%m%d%Y%_H%M%S"))
        if not f:
            return

        if not f.endswith(".png"):
            f += ".png"
        self.map.export_to(f, bounds)

    def get_visible_bounds(self):
        ha = self.sw.get_hadjustment()
        va = self.sw.get_vadjustment()

        return (int(ha.value), int(va.value),
                int(ha.value + ha.page_size), int(va.value + va.page_size))

    def mh(self, _action):
        action = _action.get_name()

        if action == "refresh":
            self.map_tiles = []
            self.map.queue_draw()
        elif action == "clearcache":
            self.clear_map_cache()
        elif action == "loadstatic":
            p = platform.get_platform()
            f = p.gui_open_file()
            if not f:
                return

            if self.load_static_points(f):
                dir = platform.get_platform().config_dir()
                shutil.copy(f, os.path.join(dir,
                                            "static_locations",
                                            os.path.basename(f)))
                return

            d = gtk.MessageDialog(buttons=gtk.BUTTONS_OK)
            d.set_property("text", "Failed to load overlay file")
        elif action == "remstatic":
            self.remove_current_static()
        elif action == "save":
            self.save_map()
        elif action == "savevis":
            self.save_map(self.get_visible_bounds())
        elif action == "printable":
            self.printable_map()
        elif action == "printablevis":
            self.printable_map(self.get_visible_bounds())
        elif action == "addmarker":
            self.prompt_to_set_marker()

    def make_menu(self):
        menu_xml = """
<ui>
  <menubar name="MenuBar">
    <menu action="map">
      <menuitem action="addmarker"/>
      <menuitem action="refresh"/>
      <menuitem action="clearcache"/>
      <menuitem action="loadstatic"/>
      <menuitem action="remstatic"/>
      <menu action="export">
        <menuitem action="printable"/>
        <menuitem action="printablevis"/>
        <menuitem action="save"/>
        <menuitem action="savevis"/>
      </menu>
    </menu>
  </menubar>
</ui>
"""

        actions = [('map', None, "_Map", None, None, self.mh),
                   ('addmarker', None, "_Set Marker", None, None, self.mh),
                   ('refresh', None, "_Refresh", None, None, self.mh),
                   ('clearcache', None, "_Clear Cache", None, None, self.mh),
                   ('loadstatic', None, "_Load Static Overlay", None, None, self.mh),
                   ('remstatic', None, "_Remove Static Overlay", None, None, self.mh),
                   ('export', None, "_Export", None, None, self.mh),
                   ('printable', None, "_Printable", "<Control>p", None, self.mh),
                   ('printablevis', None, "Printable (visible area)", "<Control><Alt>P", None, self.mh),
                   ('save', None, "_Save Image", "<Control>s", None, self.mh),
                   ('savevis', None, 'Save Image (visible area)', "<Control><Alt>S", None, self.mh),
                   ]

        uim = gtk.UIManager()
        self.menu_ag = gtk.ActionGroup("MenuBar")

        self.menu_ag.add_actions(actions)
        
        uim.insert_action_group(self.menu_ag, 0)
        menuid = uim.add_ui_from_string(menu_xml)

        self._accel_group = uim.get_accel_group()

        return uim.get_widget("/MenuBar")

    def make_controls(self):
        vbox = gtk.VBox(False, 2)

        vbox.pack_start(self.make_zoom_controls(), 0,0,0)
        vbox.pack_start(self.make_track(), 0,0,0)

        vbox.show()

        return vbox

    def make_bottom_pane(self):
        box = gtk.HBox(False, 2)

        box.pack_start(self.make_marker_list(), 1,1,1)
        box.pack_start(self.make_controls(), 0,0,0)

        box.show()

        return box

    def scroll_to_center(self, widget):
        a = widget.get_vadjustment()
        a.set_value((a.upper - a.page_size) / 2)

        a = widget.get_hadjustment()
        a.set_value((a.upper - a.page_size) / 2)

    def center_on(self, lat, lon):
        ha = self.sw.get_hadjustment()
        va = self.sw.get_vadjustment()

        x, y = self.map.latlon2xy(lat, lon)

        ha.set_value(x - (ha.page_size / 2))
        va.set_value(y - (va.page_size / 2))

    def recenter(self, lat, lon):
        self.map.set_center(lat, lon)
        self.refresh_marker_list()
        self.map.load_tiles()
        self.center_on(lat, lon)

    def prompt_to_set_marker(self, _lat=None, _lon=None):
        d = inputdialog.FieldDialog(title="Add Marker")
        d.add_field("Group", miscwidgets.make_choice(self.markers.keys(), True))
        d.add_field("Name", gtk.Entry())
        d.add_field("Latitude", miscwidgets.LatLonEntry())
        d.add_field("Longitude", miscwidgets.LatLonEntry())
        if _lat:
            d.get_field("Latitude").set_text("%.4f" % _lat)
        if _lon:
            d.get_field("Longitude").set_text("%.4f" % _lon)

        while d.run() == gtk.RESPONSE_OK:
            try:
                grp = d.get_field("Group").get_active_text()
                nme = d.get_field("Name").get_text()
                lat = d.get_field("Latitude").value()
                lon = d.get_field("Longitude").value()
            except Exception, e:
                ed = gtk.MessageDialog(buttons=gtk.BUTTONS_OK,
                                       parent=d)
                ed.set_property("text", "Invalid value %s" % e)
                ed.run()
                ed.destroy()
                continue
                
            fix = GPSPosition(lat=lat, lon=lon, station=nme)
            self.set_marker(fix, "green", grp)
            break
        d.destroy()                    

    def recenter_cb(self, view, path, column, data=None):
        model = view.get_model()
        if model.iter_parent(model.get_iter(path)) == None:
            return

        items = self.marker_list.get_selected()

        self.recenter(items[2], items[3])

        self.center_mark = items[1]
        self.sb_center.pop(self.STATUS_CENTER)
        self.sb_center.push(self.STATUS_CENTER, "Center: %s" % self.center_mark)

    def make_popup(self, pos):
        xml = """
<ui>
  <popup name="menu">
    <menuitem action="center"/>
    <menuitem action="setmark"/>
    <menuitem action="setcurrent"/>
  </popup>
</ui>
"""
        ag = gtk.ActionGroup("menu")

        center = gtk.Action("center", "Center here", None, None)
        center.connect("activate", lambda x: self.recenter(pos[0], pos[1]))
        ag.add_action(center)

        setmark = gtk.Action("setmark", "Set Marker", None, None)
        setmark.connect("activate", lambda x: self.prompt_to_set_marker(pos[0],
                                                                        pos[1]))
        ag.add_action(setmark)

        setcurrent = gtk.Action("setcurrent", "Set Current", None, None)
        ag.add_action(setcurrent)

        uim = gtk.UIManager()
        uim.insert_action_group(ag, 0)
        uim.add_ui_from_string(xml)

        return uim.get_widget("/menu")

    def mouse_click_event(self, widget, event):
        x,y = event.get_coords()

        ha = widget.get_hadjustment()
        va = widget.get_vadjustment()
        mx = x + int(ha.get_value())
        my = y + int(va.get_value())

        lat, lon = self.map.xy2latlon(mx, my)

        print "Button %i at %i,%i" % (event.button, mx, my)
        if event.button == 3:
            menu = self.make_popup((lat, lon))
            if menu:
                menu.popup(None, None, None, event.button, event.time)
        elif event.type == gtk.gdk.BUTTON_PRESS:
            print "Clicked: %.4f,%.4f" % (lat, lon)
            self.set_marker(GPSPosition(station=CROSSHAIR,
                                        lat=lat, lon=lon))
        elif event.type == gtk.gdk._2BUTTON_PRESS:
            print "Recenter on %.4f, %.4f" % (lat,lon)

            self.recenter(lat, lon)

    def mouse_move_event(self, widget, event):
        x, y = event.get_coords()
        lat, lon = self.map.xy2latlon(x, y)

        self.sb_coords.pop(self.STATUS_COORD)
        self.sb_coords.push(self.STATUS_COORD, "%.4f, %.4f" % (lat, lon))

    def ev_destroy(self, widget, data=None):
        self.hide()
        return True

    def ev_delete(self, widget, event, data=None):
        self.hide()
        return True

    def update_gps_status(self, string):
        self.sb_gps.pop(self.STATUS_GPS)
        self.sb_gps.push(self.STATUS_GPS, string)

    def __init__(self, *args):
        gtk.Window.__init__(self, *args)

        self.STATUS_COORD = 0
        self.STATUS_CENTER = 1
        self.STATUS_GPS = 2

        self.center_mark = None
        self.tracking_enabled = False

        tiles = 5

        self.map = MapWidget(tiles, tiles)
        self.map.show()

        box = gtk.VBox(False, 2)

        self.menubar = self.make_menu()
        self.menubar.show()
        box.pack_start(self.menubar, 0,0,0)
        self.add_accel_group(self._accel_group)

        self.sw = gtk.ScrolledWindow()
        self.sw.add_with_viewport(self.map)
        self.sw.show()

        def pre_scale(sw, event, mw):
            ha = mw.sw.get_hadjustment()
            va = mw.sw.get_vadjustment()

            px = ha.get_value() + ha.page_size
            py = va.get_value() + va.page_size

            rect = gtk.gdk.Rectangle(int(ha.get_value()), int(va.get_value()),
                                     int(py), int(py))
            mw.map.window.invalidate_rect(rect, True)

        def _scale(sw, event, mw):
            ha = mw.sw.get_hadjustment()
            va = mw.sw.get_vadjustment()

            px = ha.get_value() + ha.page_size
            py = va.get_value() + va.page_size

            pm = mw.map.scale(int(px) - 5, int(py))

        def scale(sw, event, mw):
            gobject.idle_add(_scale, sw, event, mw)

        self.sw.connect("expose-event", pre_scale, self)
        self.sw.connect_after("expose-event", scale, self)

        self.map.add_events(gtk.gdk.POINTER_MOTION_MASK)
        self.map.connect("motion-notify-event", self.mouse_move_event)
        self.sw.connect("button-press-event", self.mouse_click_event)

        self.sw.connect('realize', self.scroll_to_center)

        hbox = gtk.HBox(False, 2)

        self.sb_coords = gtk.Statusbar()
        self.sb_coords.show()
        self.sb_coords.set_has_resize_grip(False)

        self.sb_center = gtk.Statusbar()
        self.sb_center.show()
        self.sb_center.set_has_resize_grip(False)

        self.sb_gps = gtk.Statusbar()
        self.sb_gps.show()

        hbox.pack_start(self.sb_coords, 1,1,1)
        hbox.pack_start(self.sb_center, 1,1,1)
        hbox.pack_start(self.sb_gps, 1,1,1)
        hbox.show()

        box.pack_start(self.sw, 1,1,1)
        box.pack_start(self.make_bottom_pane(), 0,0,0)
        box.pack_start(hbox, 0,0,0)
        box.show()

        self.set_default_size(600,600)
        self.set_geometry_hints(max_width=tiles*256,
                                max_height=tiles*256)

        self.markers = {}

        self.add(box)

        self.connect("destroy", self.ev_destroy)
        self.connect("delete_event", self.ev_delete)

    def get_markers(self):
        return self.markers

    def set_marker(self, fix, color="yellow", group="Misc"):
        if not self.markers.has_key(group):
            self.markers[group] = {}
            print "Adding group %s" % group
            self.marker_list.add_item(None,
                                      True,
                                      group,
                                      0,
                                      0,
                                      0,
                                      0)
        if not self.markers[group].has_key(fix.station):
            self.marker_list.add_item(group,
                                      True,
                                      fix.station,
                                      0,
                                      0,
                                      0,
                                      0)

        self.markers[group][fix.station] = (fix, True, color)
        self.map.set_marker(fix.station, fix.latitude, fix.longitude)

        self.refresh_marker_list()

        if self.center_mark and fix.station == self.center_mark and \
                self.tracking_enabled:
            self.recenter(fix.latitude, fix.longitude)

    def del_marker(self, id, group="Misc"):
        try:
            print "Deleting marker %s" % id
            print self.markers.keys()
            del self.markers[group][id]
            print self.markers.keys()
            self.marker_list.del_item(group, id)
            self.refresh_marker_list()
        except Exception, e:
            print "Unable to delete marker `%s': %s" % (id, e)
            return False

        return True

    def set_zoom(self, zoom):
        self.map.set_zoom(zoom)

    def set_center(self, lat, lon):
        self.map.set_center(lat, lon)

    def parse_static_line(self, line, group, add=True):
        if line.startswith("//"):
            return
        elif "#" in line:
            line = line[:line.index("//")]
            
        (id, lat, lon, alt) = line.split(",", 4)
            
        if add:
            pos = GPSPosition(station=id.strip(),
                              lat=float(lat),
                              lon=float(lon))

            self.set_marker(pos, "orange", group)
        else:
            self.del_marker(id.strip(), group)

    def load_static_points(self, filename, group=None):
        if not group:
            group = os.path.splitext(os.path.basename(filename))[0]

        try:
            f = file(filename)
        except Exception, e:
            print "Failed to open static points `%s': %s" % (filename, e)
            return False

        lines = f.read().split("\n")
        for line in lines:
            try:
                self.parse_static_line(line, group)
            except Exception, e:
                print "Failed to parse line `%s': %s" % (line, e)

        f.close()

        return True

    def remove_static_points(self, group):
        p = platform.get_platform()
        filename = os.path.join(p.config_dir(),
                                "static_locations",
                                group + ".csv")

        try:
            f = file(filename)
        except Exception, e:
            print "Failed to open static points `%s': %s" % (filename, e)
            return False

        lines = f.read().split("\n")
        for line in lines:
            try:
                self.parse_static_line(line, group, add=False)
            except Exception, e:
                print "Failed to parse line `%s': %s" % (line, e)

        f.close()
        os.remove(filename)

        try:
            print "Deleting marker group `%s'" % group
            del self.markers[group]
            self.marker_list.del_item(None, group)
        except Exception, e:
            print "Failed to remove group `%s': %s" % (group, e)

        return True

    def remove_current_static(self):
        try:
            items = self.marker_list.get_selected()
        except Exception, e:
            return
        
        group = items[1]

        if not self.markers.has_key(group):
            d = gtk.MessageDialog(buttons=gtk.BUTTONS_OK, parent=self)
            d.set_property("text", "Please select a top-level overlay group")
            d.run()
            d.destroy()
            return

        d = miscwidgets.YesNoDialog(title="Confirm Delete",
                                    parent=self,
                                    buttons=(gtk.STOCK_YES, gtk.RESPONSE_YES,
                                             gtk.STOCK_NO, gtk.RESPONSE_NO))
        d.set_text("Really delete overlay %s?" % group)
        r = d.run()
        d.destroy()
        if r == gtk.RESPONSE_NO:
            return

        print "Removing group %s" % group
        self.remove_static_points(group)

if __name__ == "__main__":

    import sys
    import gps

    if len(sys.argv) == 3:
        m = MapWindow()
        m.set_center(gps.parse_dms(sys.argv[1]),
                     gps.parse_dms(sys.argv[2]))
        m.set_zoom(15)
    else:
        m = MapWindow()
        m.set_center(45.525012, -122.916434)
        m.set_zoom(14)

        m.set_marker(GPSPosition(station="KI4IFW_H", lat=45.520, lon=-122.916434))
        m.set_marker(GPSPosition(station="KE7FTE", lat=45.5363, lon=-122.9105))
        m.set_marker(GPSPosition(station="KA7VQH", lat=45.4846, lon=-122.8278))
        m.set_marker(GPSPosition(station="N7QQU", lat=45.5625, lon=-122.8645))
        m.del_marker("N7QQU")

        m.load_static_points("/home/dan/.d-rats/static_locations/Washington County ARES.csv")

    m.show()

    try:
        gtk.main()
    except:
        pass


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
