#!/usr/bin/python
#
# Copyright 2009 Dan Smith <dsmith@danplanet.com>
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

import urllib
import time
import threading

import libxml2
import gobject

import utils

class MapItem:
    pass

class MapPoint(gobject.GObject):
    __gsignals__ = {
        "updated" : (gobject.SIGNAL_RUN_LAST,
                     gobject.TYPE_NONE,
                     (gobject.TYPE_STRING,)),
        }

    def _retr_hook(self):
        pass

    def __init__(self):
        gobject.GObject.__init__(self)
        self.__latitude = 0.0
        self.__longitude = 0.0
        self.__altitude = 0.0
        self.__name = ""
        self.__comment = ""
        self.__icon = None
        self.__timestamp = time.time()
        self.__visible = True

    def __getattr__(self, name):
        self._retr_hook()

        _get, name = name.split("_", 1)

        attrname = "_MapPoint__%s" % name

        #print self.__dict__.keys()
        if not hasattr(self, attrname):
            raise ValueError("No such attribute `%s'" % attrname)

        def get():
            return self.__dict__[attrname]

        def set(val):
            self.__dict__[attrname] = val

        if _get == "get":
            return get
        elif _get == "set":
            return set
        else:
            pass

    def __repr__(self):
        msg = "MapPoint:%s@%.4f,%.4f" % (self.get_name(),
                                         self.get_latitude(),
                                         self.get_longitude())
        return ""

    def __str__(self):
        return self.get_name()

class MapStation(MapPoint):
    def __init__(self, call, lat, lon, alt=0.0, comment=""):
        MapPoint.__init__(self)
        self.set_latitude(lat)
        self.set_longitude(lon)
        self.set_altitude(alt)
        self.set_name(call)
        self.set_comment(comment)
        # FIXME: Set icon from DPRS comment

    def set_icon_from_aprs_sym(self, symbol):
        self.set_icon(utils.get_icon(symbol))

def _xdoc_getnodeval(ctx, nodespec):
    items = ctx.xpathEval(nodespec)
    if len(items) != 1:
        raise Exception("Too many nodes")

    return items[0].getContent()

class MapUSGSRiver(MapPoint):
    def _do_update(self):
        print "[River %i] Doing update..." % self.__site
        if  not self.__have_site:
            self.__parse_site()
            self.__have_site = True

        self.__parse_level()

        print "[River %i] Done with update" % self.__site

        gobject.idle_add(self.emit, "updated", "FOO")

    def _do_update_bg(self):
        if self.__thread and self.__thread.isAlive():
            print "[River %i] Still waiting on a thread" % self.__site
            return

        self.__thread = threading.Thread(target=self._do_update)
        self.__thread.setDaemon(True)
        self.__thread.start()

    def __parse_site(self):
        url = "http://waterdata.usgs.gov/nwis/inventory?search_site_no=%i&format=sitefile_output&sitefile_output_format=xml&column_name=agency_cd&column_name=site_no&column_name=station_nm&column_name=dec_lat_va&column_name=dec_long_va&column_name=alt_va" % self.__site

        fn, headers = urllib.urlretrieve(url)
        content = file(fn).read()

        doc = libxml2.parseMemory(content, len(content))

        ctx = doc.xpathNewContext()

        base = "/usgs_nwis/site/"

        self._basename = _xdoc_getnodeval(ctx, base + "station_nm")

        self.set_name(self._basename)
        self.set_latitude(float(_xdoc_getnodeval(ctx, base + "dec_lat_va")))
        self.set_longitude(float(_xdoc_getnodeval(ctx, base + "dec_long_va")))
        self.set_altitude(float(_xdoc_getnodeval(ctx, base + "alt_va")))

    def __parse_level(self):
        url = "http://waterdata.usgs.gov/nwis/uv?format=rdb&period=7&site_no=%i" % self.__site

        fn, headers = urllib.urlretrieve(url)

        line = file(fn).readlines()[-1]
        fields = line.split("\t")

        self._height_ft = float(fields[3])
        self.set_comment("River height: %.1f ft" % self._height_ft)
        self.set_timestamp(time.time())

    def _retr_hook(self):
        if time.time() - self.__ts > 60:
            try:
                self.__ts = time.time()
                self._do_update_bg()
            except Exception, e:
                print "Can't start: %s" % e

    def __init__(self, site):
        MapPoint.__init__(self)
        self.__thread = None
        self.__site = site
        self.__ts = 0

        self.__have_site = False

        self.set_icon(utils.get_icon("/w"))

class MapSourceFailedToConnect(Exception):
    pass

class MapSourcePointError(Exception):
    pass

class MapSource(gobject.GObject):
    __gsignals__ = {
        "point-added" : (gobject.SIGNAL_RUN_LAST,
                         gobject.TYPE_NONE,
                         (gobject.TYPE_PYOBJECT,)),
        "point-deleted" : (gobject.SIGNAL_RUN_LAST,
                           gobject.TYPE_NONE,
                           (gobject.TYPE_PYOBJECT,)),
        "point-updated" : (gobject.SIGNAL_RUN_LAST,
                           gobject.TYPE_NONE,
                           (gobject.TYPE_PYOBJECT,)),
        }

    def __init__(self, name, description, color="red"):
        gobject.GObject.__init__(self)

        self._name = name
        self._description = description
        self._points = {}
        self._color = color
        self._visible = True

    def add_point(self, point):
        had = self._points.has_key(point.get_name())
        self._points[point.get_name()] = point
        if had:
            self.emit("point-updated", point)
        else:
            self.emit("point-added", point)

    def del_point(self, point):
        del self._points[point.get_name()]
        self.emit("point-deleted", point)

    def get_points(self):
        return self._points.values()

    def get_point_by_name(self, name):
        return self._points[name]

    def get_color(self):
        return self._color

    def get_name(self):
        return self._name

    def get_description(self):
        return self._description

    def get_visible(self):
        return self._visible

    def set_visible(self, visible):
        self._visible = visible

class MapFileSource(MapSource):
    def __parse_line(self, line):
        try:
            id, icon, lat, lon, alt, comment, show = line.split(",", 6)
        except Exception, e:
            raise MapSourcePointError(str(e))
        
        if alt:
            alt = float(alt)
        else:
            alt = 0.0

        point = MapStation(id, float(lat), float(lon), float(alt), comment)
        point.set_visible(show.upper().strip() == "TRUE")
        point.set_icon_from_aprs_sym(icon)

        return point

    def __init__(self, name, description, fn):
        MapSource.__init__(self, name, description)

        self._fn = fn

        try:
            input = file(fn)
        except Exception, e:
            msg = "Failed to open %s: %s" % (fn, e)
            print msg
            raise MapsourceFailedToConnect(msg)

        lines = input.readlines()
        for line in lines:
            try:
                point = self.__parse_line(line)
            except Exception, e:
                print "Failed to parse: %s" % e
                continue

            self._points[point.get_name()] = point

class MapUSGSRiverSource(MapSource):
    def _point_updated(self, point, foo):
        if not self._points.has_key(point.get_name()):
            self._points[point.get_name()] = point
            self.emit("point-added", point)
        else:
            self.emit("point-updated", point)

    def __init__(self, name, description, *sites):
        MapSource.__init__(self, name, description)

        for site in sites:
            point = MapUSGSRiver(site)
            point.connect("updated", self._point_updated)

