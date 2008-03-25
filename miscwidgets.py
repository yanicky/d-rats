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

    def __init__(self, columns):
        gtk.HBox.__init__(self)

        col_types = tuple([x for x,y in columns])
        self._ncols = len(col_types)

        self._store = gtk.ListStore(*col_types)
        self._view = gtk.TreeView(self._store)

        for t,c in columns:
            index = columns.index((t,c))
            if t == gobject.TYPE_STRING or t == gobject.TYPE_INT:
                r = gtk.CellRendererText()
                c = gtk.TreeViewColumn(c, r, text=index)
            elif t == gobject.TYPE_BOOLEAN:
                r = gtk.CellRendererToggle()
                r.connect("toggled", self._toggle, index)
                c = gtk.TreeViewColumn(c, r, active=index)
            else:
                raise Exception("Unknown column type (%i)" % index)

            self._view.append_column(c)

        self._view.show()
        self.pack_start(self._view, 1,1,1)

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

    try:
        gtk.main()
    except KeyboardInterrupt, e:
        pass

    print l.get_values()
