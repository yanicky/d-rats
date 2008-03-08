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
            if t == gobject.TYPE_STRING:
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

if __name__=="__main__":
    w = gtk.Window(gtk.WINDOW_TOPLEVEL)
    l = ListWidget([(gobject.TYPE_STRING, "Foo"),
                    (gobject.TYPE_BOOLEAN, "Bar")])

    l.add_item("Test1", True)
    l.set_values([("Test2", True), ("Test3", False)])
    
    l.show()
    w.add(l)
    w.show()

    try:
        gtk.main()
    except KeyboardInterrupt, e:
        pass

    print l.get_values()
