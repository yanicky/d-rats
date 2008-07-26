#!/usr/bin/python

import gtk
import gobject
import threading
import time

try:
    import mapdisplay
    import miscwidgets
except ImportError:
    from d_rats import mapdisplay
    from d_rats import miscwidgets

class MapDownloader(gtk.Window):
    def make_val(self, key, label):
        box = gtk.HBox(True, 2)

        l = gtk.Label(label)
        l.show()

        e = miscwidgets.LatLonEntry()
        e.show()

        box.pack_start(l)
        box.pack_start(e)

        box.show()

        self.vals[key] = e

        return box

    def make_zoom(self, key, label, min, max, default):
        box = gtk.HBox(True, 2)

        l = gtk.Label(label)
        l.show()

        a = gtk.Adjustment(default, min, max, 1, 1)
        e = gtk.SpinButton(a, digits=0)
        e.show()

        box.pack_start(l)
        box.pack_start(e)

        box.show()

        self.vals[key] = e

        return box

    def build_bounds(self):
        frame = gtk.Frame("Bounds")

        box = gtk.VBox(True, 2)

        self.val_keys = { "lat_max" : "Upper Latitude",
                          "lat_min" : "Lower Latitude",
                          "lon_max" : "Max Longitude",
                          "lon_min" : "Min Longitude",
                          "zoom_max" : ("Zoom Upper Limit", 10, 15, 15),
                          "zoom_min" : ("Zoom Lower Limit", 10, 15, 13),
                          }

        for key in sorted(self.val_keys.keys()):
            if "zoom" in key:
                box.pack_start(self.make_zoom(key, *self.val_keys[key]), 0,0,0)
            else:
                box.pack_start(self.make_val(key, self.val_keys[key]), 0,0,0)

        box.show()

        frame.add(box)
        frame.show()

        return frame

    def _update(self, prog, status):
        if prog:
            self.progbar.set_fraction(prog)
        self.status.set_text(status)

        if not self.enabled:
            self.thread.join()
            self.stop_button.set_sensitive(False)
            self.start_button.set_sensitive(True)

    def update(self, prog, status):
        gobject.idle_add(self._update, prog, status)

    def download_zoom(self, zoom, **vals):
        lat = vals["lat_min"]
        lon = vals["lon_min"]

        tile = mapdisplay.MapTile(lat, lon, zoom)
        
        _tile = tile

        y = 0
        while _tile.lat < vals["lat_max"] and self.enabled:
            x = 0
            _tile = tile
            while _tile.lon < vals["lon_max"] and self.enabled:
                print "Delta: %i,%i" % (x,y)
                
                _tile = tile + (x,y)

                pct = ((_tile.lat - tile.lat) / (vals["lat_max"] - tile.lat))
                print "Percent: %f" % pct
                print "%.2f %.2f  -  %.2f %.2f" % (tile.lat,
                                                   tile.lon,
                                                   _tile.lat,
                                                   _tile.lon)

                if not _tile.is_local():
                    self.update(pct,
                                "Fetching %.2f,%.2f at %i zoom" % \
                                    (_tile.lat, _tile.lon, zoom))
                    _tile.fetch()
                x += 1

            y -= 1

    def download_thread(self, **vals):
        print "Download thread: %s" % str(vals)
        self.complete = False
        self.enabled = True

        zooms = range(int(vals["zoom_min"]), int(vals["zoom_max"]) + 1)

        print "Zooms: %s" % zooms

        for zoom in zooms:
            print "Zoom: %i" % zoom
            self.download_zoom(zoom, **vals)
            if not self.enabled:
                break

        if self.enabled:
            self.update(1.0, "Complete")
        else:
            self.update(None, "Stopped")

        self.complete = True
        self.enabled = False

    def show_field_error(self, field):
        d = gtk.MessageDialog(buttons=gtk.BUTTONS_OK, parent=self)
        d.set_property("text", "Invalid value for `%s'" % field)

        d.run()
        d.destroy()

    def show_range_error(self, field):
        d = gtk.MessageDialog(buttons=gtk.BUTTONS_OK, parent=self)
        d.set_property("text", "Invalid range for %s" % field)
        d.run()
        d.destroy()

    def do_start(self, widget, data=None):
        vals = {}

        for k,e in self.vals.items():
            try:
                if "zoom" in k:
                    vals[k] = int(e.get_adjustment().get_value())
                else:
                    vals[k] = e.value()
            except ValueError, e:
                self.show_field_error(self.val_keys[k])
                return

        if vals["lat_min"] >= vals["lat_max"]:
            self.show_range_error("latitude")
            return

        if vals["lon_min"] >= vals["lon_max"]:
            self.show_range_error("longitude")
            return

        if vals["zoom_min"] > vals["zoom_max"]:
            self.show_range_error("zoom")
            return

        self.start_button.set_sensitive(False)
        self.stop_button.set_sensitive(True)

        print "Starting"
        self.thread = threading.Thread(target=self.download_thread, kwargs=vals)
        self.thread.start()        
        print "Started"

    def do_stop(self, widget, data=None):
        self.start_button.set_sensitive(True)
        self.stop_button.set_sensitive(False)

        self.enabled = False
        self.thread.join()

    def make_control_buttons(self):
        box = gtk.HBox(True, 2)

        self.start_button = gtk.Button("Start")
        self.start_button.set_size_request(75, 30)
        self.start_button.connect("clicked", self.do_start)
        self.start_button.show()

        self.stop_button = gtk.Button("Stop")
        self.stop_button.set_size_request(75, 30)
        self.stop_button.set_sensitive(False)
        self.stop_button.connect("clicked", self.do_stop)
        self.stop_button.show()

        box.pack_start(self.start_button, 0,0,0)
        box.pack_start(self.stop_button, 0,0,0)

        box.show()

        return box
    
    def build_controls(self):
        frame = gtk.Frame("Controls")

        box = gtk.VBox(False, 2)

        self.progbar = gtk.ProgressBar()
        self.progbar.show()

        self.status = gtk.Label("")
        self.status.show()

        box.pack_start(self.progbar, 0,0,0)
        box.pack_start(self.status, 0,0,0)
        box.pack_start(self.make_control_buttons(), 0,0,0)

        box.show()

        frame.add(box)
        frame.show()

        return frame

    def build_gui(self):
        box = gtk.VBox(False, 2)

        box.pack_start(self.build_bounds())
        box.pack_start(self.build_controls())

        box.show()

        return box

    def __init__(self, title="Map Download Utility"):
        gtk.Window.__init__(self, gtk.WINDOW_TOPLEVEL)

        self.set_title(title)

        self.vals = {}
        self.enabled = False        
        self.thread = None
        self.completed = False

        self.add(self.build_gui())

if __name__=="__main__":
    gobject.threads_init()

    def stop(*args):
        gtk.main_quit()

    w = MapDownloader()
    w.connect("destroy", stop)
    w.connect("delete_event", stop)

    w.show()

    gtk.main()
