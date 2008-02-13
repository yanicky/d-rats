import sys
import time

from xml.dom.ext.reader import Sax2
from xml.dom.ext import Print
from xml import xpath
from xml.dom.NodeFilter import NodeFilter
from xml.dom import Node

import gtk

from config import make_choice

test = """
<xml>
  <form id="testform">
    <title>Test Form</title>
    <field id="foo">
      <caption>Name</caption>
      <entry type="text">Foobar</entry>
    </field>
    <field id="bar">
      <entry type="multiline"/>
    </field>
    <field id="baz">
      <caption>Is this person okay?</caption>
      <entry type="toggle">True</entry>
    </field>
  </form>
</xml>

"""

def tree2string(node, indent=0):
    string = ""
    if node.nodeType == Node.TEXT_NODE:
        if str(node.nodeValue).strip():
            string = "%s%s\n" % (" " * indent, node.nodeValue)
        return string

    attrs = []
    if node.attributes:
        for k in node.attributes.keys():
            (_, name) = k
            attrs.append("%s='%s'" % (name, node.getAttribute(name)))
    
    if attrs:
        openstring = "%s %s" % (node.nodeName," ".join(attrs))
    else:
        openstring = "%s" % node.nodeName

    if node.childNodes:
        string += "%s<%s>\n" % (" " * indent, openstring)
        for c in node.childNodes:
            string += tree2string(c, indent+2)
        string += "%s</%s>\n" % (" " * indent, node.nodeName)
    else:
        string += "%s<%s/>\n" % (" " * indent, openstring)
    
    return string
        

class FieldWidget:
    def __init__(self, node):
        self.node = node
        self.caption = "Untitled Field"

    def set_caption(self, caption):
        self.caption = caption

    def make_container(self):
        hbox = gtk.HBox(True, 2)

        label = gtk.Label(self.caption)
        hbox.pack_start(label, 0,0,0)
        hbox.pack_start(self.widget, 1,1,0)

        label.show()
        hbox.show()

        return hbox

    def get_widget(self):
        return self.make_container()

    def get_value(self):
        pass

    def set_value(self, value):
        pass

    def update_node(self):
        for child in self.node.childNodes:
            self.node.removeChild(child)

        value = self.get_value()
        if value:
            newnode = self.node.ownerDocument.createTextNode(value)
            self.node.appendChild(newnode)

class TextWidget(FieldWidget):
    def __init__(self, node):
        FieldWidget.__init__(self, node)

        if len(node.childNodes) != 0:
            text = node.childNodes[0].nodeValue.strip()
        else:
            text = ""

        self.widget = gtk.Entry()
        self.widget.set_text(text)
        self.widget.show()

    def get_value(self):
        return self.widget.get_text()

class ToggleWidget(FieldWidget):
    def __init__(self, node):
        FieldWidget.__init__(self, node)

        if len(node.childNodes) != 0:
            try:
                status = eval(node.childNodes[0].nodeValue.title())
            except:
                print "Status of `%s' is invalid" % node.childNodes[0].nodeValue
                status = False
        else:
            status = False

        self.widget = gtk.CheckButton("Yes")
        self.widget.set_active(status)
        self.widget.show()

    def get_value(self):
        return str(self.widget.get_active())

class MultilineWidget(FieldWidget):
    def __init__(self, node):
        FieldWidget.__init__(self, node)

        if len(node.childNodes) != 0:
            text = node.childNodes[0].nodeValue.strip()
        else:
            text = ""

        self.buffer = gtk.TextBuffer()
        self.buffer.set_text(text)
        self.widget = gtk.TextView(self.buffer)
        self.widget.show()
        self.widget.set_size_request(175, 200)
        self.widget.set_wrap_mode(gtk.WRAP_WORD)

    def make_container(self):
        vbox = gtk.VBox(False, 2)

        label = gtk.Label(self.caption)
        vbox.pack_start(label, 0,0,0)
        vbox.pack_start(self.widget, 0,0,0)

        label.show()
        vbox.show()

        return vbox

    def get_value(self):
        return self.buffer.get_text(self.buffer.get_start_iter(),
                                    self.buffer.get_end_iter())

class DateWidget(FieldWidget):
    def __init__(self, node):
        FieldWidget.__init__(self, node)

        try:
            text = node.childNodes[0].nodeValue.strip()
            (d, m, y) = text.split("-", 3)
        except:
            y = time.strftime("%Y")
            m = time.strftime("%b")
            d = time.strftime("%d")

        months = ["Jan", "Feb", "Mar", "Apr", "May", "Jun",
                  "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"]
        days = [str("%02i" % x) for x in range(1,32)]
        
        years = [str(x) for x in range(int(y)-2, int(y)+2)]

        self.monthbox = make_choice(months, False, m)
        self.daybox = make_choice(days, False, d)
        self.yearbox = make_choice(years, False, y)

        self.widget = gtk.HBox(False, 2)
        self.widget.pack_start(self.monthbox, 0,0,0)
        self.widget.pack_start(self.daybox, 0,0,0)
        self.widget.pack_start(self.yearbox, 0,0,0)

        self.monthbox.show()
        self.daybox.show()
        self.yearbox.show()

        self.widget.show()

    def get_value(self):
        return "%s-%s-%s" % (self.daybox.get_active_text(),
                             self.monthbox.get_active_text(),
                             self.yearbox.get_active_text())

class TimeWidget(FieldWidget):
    def __init__(self, node):
        FieldWidget.__init__(self, node)

        try:
            text = node.childNodes[0].nodeValue.strip()
            (h, m, s) = (int(x) for x in text.split(":", 3))
        except:
            h = int(time.strftime("%H"))
            m = int(time.strftime("%M"))
            s = int(time.strftime("%S"))

        self.hour_a = gtk.Adjustment(h, 0, 23, 1)
        self.min_a = gtk.Adjustment(m, 0, 59, 1, 10)
        self.sec_a = gtk.Adjustment(s, 0, 59, 1, 10)

        self.hour = gtk.SpinButton(self.hour_a)
        self.min = gtk.SpinButton(self.min_a)
        self.sec = gtk.SpinButton(self.sec_a)

        self.widget = gtk.HBox(False, 2)
        self.widget.pack_start(self.hour, 0,0,0)
        self.widget.pack_start(self.min, 0,0,0)
        self.widget.pack_start(self.sec, 0,0,0)

        self.hour.show()
        self.min.show()
        self.sec.show()
        self.widget.show()

    def get_value(self):
        return "%.0f:%.0f:%.0f" % (self.hour_a.get_value(),
                                   self.min_a.get_value(),
                                   self.sec_a.get_value())

class NumericWidget(FieldWidget):
    def __init__(self, node):
        FieldWidget.__init__(self, node)

        try:
            min = float(node.getAttribute("min"))
        except:
            min = 0

        try:
            max = float(node.getAttribute("max"))
        except:
            max = 10000.0

        try:
            initial = float(node.childNodes[0].nodeValue)
        except:
            initial = 0

        self.adj = gtk.Adjustment(initial, min, max, 1, 10)
        self.widget = gtk.SpinButton(self.adj)
        self.widget.show()

    def get_value(self):
        return "%.0f" % self.adj.get_value()

class ChoiceWidget(FieldWidget):
    def parse_choice(self, node):
        if node.nodeName != "choice":
            return

        try:
            self.choices.append(node.childNodes[0].nodeValue.strip())
        except:
            pass

    def __init__(self, node):
        FieldWidget.__init__(self, node)
        
        self.choices = []
        value = ""

        for child in node.childNodes:
            if child.nodeType == Node.ELEMENT_NODE:
                self.parse_choice(child)
            elif child.nodeType == Node.TEXT_NODE:
                value += child.nodeValue.strip()

        self.widget = make_choice(self.choices, False, value)
        self.widget.show()

    def get_value(self):
        return self.widget.get_active_text()

class FormField:
    widget_types = {
    "text" : TextWidget,
    "multiline" : MultilineWidget,
    "toggle" : ToggleWidget,
    "date" : DateWidget,
    "time" : TimeWidget,
    "numeric" : NumericWidget,
    "choice" : ChoiceWidget,
    }

    def get_caption_string(self, node):
        return node.childNodes[0].nodeValue.strip()

    def build_entry(self, node, caption):
        type = node.getAttribute("type")

        wtype = self.widget_types[type]

        field = wtype(node)
        field.set_caption(caption)

        return field        

    def build_gui(self, node):
        self.caption = None
        self.entry = None
        
        for i in node.childNodes:
            if i.nodeName == "caption":
                cap_node = i
            elif i.nodeName == "entry":
                ent_node = i

        caption = self.get_caption_string(cap_node)
        self.entry = self.build_entry(ent_node, caption)
        self.widget = self.entry.get_widget()
        self.widget.show()

    def __init__(self, field):
        self.node = field
        self.id = field.getAttribute("id")
        self.build_gui(field)

    def get_widget(self):
        return self.widget

    def update_node(self):
        self.entry.update_node()

class Form(gtk.Dialog):
    def build_gui(self):
        tlabel = gtk.Label()
        tlabel.set_markup("<big><b>%s</b></big>" % self.title_text)
        tlabel.show()

        self.vbox.pack_start(tlabel, 0,0,0)

        for f in self.fields:
            self.vbox.pack_start(f.get_widget(), 0,0,0)

    def process_fields(self, doc):
        fields = xpath.Evaluate("form/field", doc)
        for f in fields:
            try:
                self.fields.append(FormField(f))
            except Exception, e:
                print e

    def process_form(self, doc):
        forms = xpath.Evaluate("form", doc)
        if len(forms) != 1:
            raise Exception("%i forms in document" % len(forms))

        form = forms[0]
        
        self.id = form.getAttribute("id")

        titles = xpath.Evaluate("form/title", doc)
        if len(titles) != 1:
            raise Exception("%i titles in document" % len(titles))

        title = titles[0]

        self.title_text = title.childNodes[0].nodeValue.strip()

    def get_xml(self):
        for f in self.fields:
            f.update_node()

        return tree2string(self.doc.documentElement)

    def __init__(self, title, xmlstr, buttons=None):
        if not buttons:
            buttons = (gtk.STOCK_CANCEL, gtk.RESPONSE_CANCEL,
                       gtk.STOCK_OK, gtk.RESPONSE_OK)

        gtk.Dialog.__init__(self, title=title, buttons=buttons)

        self.vbox.set_spacing(5)

        self.fields = []

        reader = Sax2.Reader()
        self.doc = reader.fromString(xmlstr)

        self.process_form(self.doc.documentElement)
        self.process_fields(self.doc.documentElement)

        print "Form ID: %s" % self.id

        self.build_gui()
        
class FormFile(Form):
    def __init__(self, title, filename, buttons=None):
        self._filename = filename
        f = file(self._filename)
        data = f.read()
        f.close()

        Form.__init__(self, title, data, buttons)

    def run_auto(self, save_file=None):
        if not save_file:
            save_file = self._filename

        r = Form.run(self)
        if r == gtk.RESPONSE_OK:
            f = file(save_file, "w")
            print >>f, self.get_xml()
            f.close()

        return r

if __name__ == "__main__":
    f = file(sys.argv[1])
    xml = f.read()
    form = Form("Form", xml)
    form.run()
    form.destroy()
    try:
        gtk.main()
    except:
        pass

    out = file("output.xml", "w")
    print >>out, form.get_xml()
    out.close()
