#
# Copyright 2008 Dan Smith <dsmith@danplanet.com>
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

import gtk
import gobject

class ListWidget(gtk.HBox):
    def _toggle(self, render, path, column):
        self._store[path][column] = not self._store[path][column]
        iter = self._store.get_iter(path)
        vals = tuple(self._store.get(iter, *tuple(range(self._ncols))))
        for cb in self.toggle_cb:
            cb(*vals)

    def __init__(self, columns):
        gtk.HBox.__init__(self)

        col_types = tuple([x for x,y in columns])
        self._ncols = len(col_types)

        self._store = gtk.ListStore(*col_types)
        self._view = gtk.TreeView(self._store)

        for t,c in columns:
            index = columns.index((t,c))
            if t == gobject.TYPE_STRING or \
                    t == gobject.TYPE_INT or \
                    t == gobject.TYPE_FLOAT:
                r = gtk.CellRendererText()
                c = gtk.TreeViewColumn(c, r, text=index)
            elif t == gobject.TYPE_BOOLEAN:
                r = gtk.CellRendererToggle()
                r.connect("toggled", self._toggle, index)
                c = gtk.TreeViewColumn(c, r, active=index)
            else:
                raise Exception("Unknown column type (%i)" % index)

            c.set_sort_column_id(index)
            self._view.append_column(c)

        self._view.show()
        self.pack_start(self._view, 1,1,1)

        self.toggle_cb = []

    def add_item(self, *vals):
        if len(vals) != self._ncols:
            raise Exception("Need %i columns" % self._ncols)

        args = []
        i = 0
        for v in vals:
            args.append(i)
            args.append(v)
            i += 1

        args = tuple(args)

        iter = self._store.append()
        self._store.set(iter, *args)

    def _remove_item(self, model, path, iter, match):
        vals = model.get(iter, *tuple(range(0, self._ncols)))
        if vals == match:
            mode.remove(iter)

    def remove_item(self, *vals):
        if len(vals) != self._ncols:
            raise Exception("Need %i columns" % self._ncols)

    def remove_selected(self):
        try:
            (list, iter) = self._view.get_selection().get_selected()
            list.remove(iter)
        except Exception, e:
            print "Unable to remove selected: %s" % e

    def get_selected(self):
        (list, iter) = self._view.get_selection().get_selected()
        return list.get(iter, *tuple(range(self._ncols)))

    def _get_value(self, model, path, iter, list):
        list.append(model.get(iter, *tuple(range(0, self._ncols))))

    def get_values(self):
        list = []

        self._store.foreach(self._get_value, list)

        return list

    def set_values(self, list):
        self._store.clear()

        for i in list:
            self.add_item(*i)

class ProgressDialog(gtk.Window):
    def __init__(self, title, parent=None):
        gtk.Window.__init__(self, gtk.WINDOW_TOPLEVEL)
        self.set_title(title)
        if parent:
            self.set_transient_for(parent)

        self.set_resizable(False)

        vbox = gtk.VBox(False, 2)

        self.label = gtk.Label("")
        self.label.set_size_request(100, 50)
        self.label.show()

        self.bar = gtk.ProgressBar()
        self.bar.show()
        
        vbox.pack_start(self.label, 0,0,0)
        vbox.pack_start(self.bar, 0,0,0)

        vbox.show()

        self.add(vbox)

    def set_text(self, text):
        self.label.set_text(text)
        self.queue_draw()

        while gtk.events_pending():
            gtk.main_iteration_do(False)

    def set_fraction(self, frac):
        self.bar.set_fraction(frac)
        self.queue_draw()

        while gtk.events_pending():
            gtk.main_iteration_do(False)

class LatLonEntry(gtk.Entry):
    def __init__(self, *args):
        gtk.Entry.__init__(self, *args)

        self.connect("changed", self.format)

    def format(self, editable):
        s = self.get_text()

        d = u"\u00b0"

        while " " in s:
            if "." in s:
                break
            elif d not in s:
                s = s.replace(" ", d)
            elif "'" not in s:
                s = s.replace(" ", "'")
            elif '"' not in s:
                s = s.replace(" ", '"')
            else:
                s = s.replace(" ", "")

        self.set_text(s)

    def parse_dd(self, string):
        return float(string)

    def parse_dm(self, string):
        string = string.strip()
        string = string.replace('  ', ' ')
        
        (d, m) = string.split(' ', 2)

        deg = int(d)
        min = float(m)

        return deg + (min / 60.0)

    def parse_dms(self, string):
        string = string.replace(u"\u00b0", " ")
        string = string.replace('"', ' ')
        string = string.replace("'", ' ')
        string = string.replace('  ', ' ')
        string = string.strip()

        items = string.split(' ')

        if len(items) > 3:
            raise Exception("Invalid format")
        elif len(items) == 3:
            d = items[0]
            m = items[1]
            s = items[2]
        elif len(items) == 2:
            d = items[0]
            m = items[1]
            s = 0
        elif len(items) == 1:
            d = items[0]
            m = 0
            s = 0
        else:
            d = 0
            m = 0
            s = 0

        deg = int(d)
        min = int(m)
        sec = float(s)
        
        return deg + (min / 60.0) + (sec / 3600.0)

    def value(self):
        s = self.get_text()

        try:
            return self.parse_dd(s)
        except:
            try:
                return self.parse_dm(s)
            except:
                try:
                    return self.parse_dms(s)
                except Exception, e:
                    print "DMS: %s" % e
                    pass

        raise Exception("Invalid format")

    def validate(self):
        try:
            self.value()
            return True
        except:
            return False
            

if __name__=="__main__":
    w = gtk.Window(gtk.WINDOW_TOPLEVEL)
    l = ListWidget([(gobject.TYPE_STRING, "Foo"),
                    (gobject.TYPE_BOOLEAN, "Bar")])

    l.add_item("Test1", True)
    l.set_values([("Test2", True), ("Test3", False)])
    
    l.show()
    w.add(l)
    w.show()

    w1 = ProgressDialog("foo")
    w1.show()

    w2 = gtk.Window(gtk.WINDOW_TOPLEVEL)
    lle = LatLonEntry()
    lle.show()
    w2.add(lle)
    w2.show()

    def print_val(entry):
        if entry.validate():
            print "Valid: %s" % entry.value()
        else:
            print "Invalid"
    lle.connect("activate", print_val)

    lle.set_text("45 13 12")

    try:
        gtk.main()
    except KeyboardInterrupt, e:
        pass

    print l.get_values()
