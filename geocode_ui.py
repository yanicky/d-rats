import gtk
import gobject

import miscwidgets
from geopy import geocoders

YID = "eHRO5K_V34FXWnljF5BJYvTc.lXh.kQ0MaJpnq3BhgaX.IJrvtd6cvGgtWEPNAb7"

class AddressAssistant(gtk.Assistant):
    def make_address_entry_page(self):
        def complete_cb(label, page):
            self.set_page_complete(page, len(label.get_text()) > 1)

        vbox = gtk.VBox(False, 0)

        lab = gtk.Label("Enter an address, postal code, or intersection:")
        lab.show()
        vbox.pack_start(lab, 1, 1, 1)

        ent = gtk.Entry()
        ent.connect("changed", complete_cb, vbox)
        ent.show()
        vbox.pack_start(ent, 0, 0, 0)

        self.vals["_address"] = ent

        vbox.show()
        return vbox

    def make_address_selection(self):
        cols = [ (gobject.TYPE_STRING, "Address"),
                 (gobject.TYPE_FLOAT, "Latitude"),
                 (gobject.TYPE_FLOAT, "Longitude") ]
        listbox = miscwidgets.ListWidget(cols)

        self.vals["AddressList"] = listbox

        listbox.show()
        return listbox

    def make_address_confirm_page(self):
        vbox = gtk.VBox(False, 0)

        def make_kv(key, value):
            hbox = gtk.HBox(False, 2)
            
            lab = gtk.Label(key)
            lab.set_size_request(100, -1)
            lab.show()
            hbox.pack_start(lab, 0, 0, 0)

            lab = gtk.Label(value)
            lab.show()
            hbox.pack_start(lab, 0, 0, 0)

            self.vals[key] = lab

            hbox.show()
            return hbox

        vbox.pack_start(make_kv("Address", ""), 0, 0, 0)
        vbox.pack_start(make_kv("Latitude", ""), 0, 0, 0)
        vbox.pack_start(make_kv("Longitude", ""), 0, 0, 0)

        vbox.show()
        return vbox

    def prepare_sel(self, assistant, page):
        address = self.vals["_address"].get_text()
        if not address:
            return

        try:
            g = geocoders.Yahoo(YID)
            places = g.geocode(address, exactly_one=False)
            self.set_page_complete(page, True)
        except Exception, e:
            print "Did not find `%s': %s" % (address, e)
            places = []
            lat = lon = 0
            self.set_page_complete(page, False)
        
        i = 0
        self.vals["AddressList"].set_values([])
        for place, (lat, lon) in places:
            i += 1
            self.vals["AddressList"].add_item(place, lat, lon)

        if i == -1:
            page.hide()
            self.set_current_page(self.get_current_page() + 1)
        
    def prepare_conf(self, assistant, page):
        self.place, self.lat, self.lon = self.vals["AddressList"].get_selected(True)

        self.vals["Address"].set_text(self.place)
        self.vals["Latitude"].set_text("%.5f" % self.lat)
        self.vals["Longitude"].set_text("%.5f" % self.lon)

        self.set_page_complete(page, True)

    def prepare_page(self, assistant, page):
        if page == self.sel_page:
            print "Sel"
            return self.prepare_sel(assistant, page)
        elif page == self.conf_page:
            print "Conf"
            return self.prepare_conf(assistant, page)
        elif page == self.entry_page:
            print "Ent"
            self.sel_page.show()
        else:
            print "I dunno"

    def exit(self, _, response):
        self.response = response
        gtk.main_quit()

    def run(self):
        self.show()
        self.set_modal(True)
        self.set_type_hint(gtk.gdk.WINDOW_TYPE_HINT_DIALOG)
        gtk.main()
        self.hide()

        return self.response

    def __init__(self):
        gtk.Assistant.__init__(self)

        self.response = None

        self.vals = {}

        self.place = self.lat = self.lon = None

        self.entry_page = self.make_address_entry_page()
        self.append_page(self.entry_page)
        self.set_page_title(self.entry_page, "Locate an address")
        self.set_page_type(self.entry_page, gtk.ASSISTANT_PAGE_CONTENT)

        self.sel_page = self.make_address_selection()
        self.append_page(self.sel_page)
        self.set_page_title(self.sel_page, "Locations found")
        self.set_page_type(self.sel_page, gtk.ASSISTANT_PAGE_CONTENT)

        self.conf_page = self.make_address_confirm_page()
        self.append_page(self.conf_page)
        self.set_page_title(self.conf_page, "Confirm address")
        self.set_page_type(self.conf_page, gtk.ASSISTANT_PAGE_CONFIRM)

        self.connect("prepare", self.prepare_page)
        self.set_size_request(500, 300)

        self.connect("cancel", self.exit, gtk.RESPONSE_CANCEL)
        self.connect("apply", self.exit, gtk.RESPONSE_OK)

if __name__ == "__main__":
    a = AddressAssistant()
    a.show()
    gtk.main()
