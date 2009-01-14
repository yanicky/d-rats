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

import sys
import time
import os
import tempfile

import libxml2
import libxslt

import gtk
import gobject

from miscwidgets import make_choice
import mainapp
import platform

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

xml_escapes = [("<", "&lt;"),
               (">", "&gt;"),
               ("&", "&amp;"),
               ('"', "&quot;"),
               ("'", "&apos;")]

def xml_escape(string):
    d = {}
    for char, esc in xml_escapes:
        d[char] = esc

    out = ""
    for i in string:
        out += d.get(i, i)

    return out

def xml_unescape(string):
    d = {}
    for char, esc in xml_escapes:
        d[esc] = char

    out = ""
    i = 0
    while i < len(string):
        if string[i] != "&":
            out += string[i]
            i += 1
        else:
            try:
                semi = string[i:].index(";") + i + 1
            except:
                print "XML Error: & with no ;"
                i += 1
                continue

            esc = string[i:semi]

            if not esc:
                print "No escape: %i:%i" % (i, semi)
                i += 1
                continue

            if d.has_key(string[i:semi]):
                out += d[esc]
            else:
                print "XML Error: No such escape: `%s'" % esc
                
            i += len(esc)

    return out

class FormWriter:
    def write(self, formxml, outfile):
        doc = libxml2.parseMemory(formxml, len(formxml))
        doc.saveFile(outfile)
        doc.freeDoc()

class HTMLFormWriter(FormWriter):
    def __init__(self, type):
        config = mainapp.get_mainapp().config
        dir = config.form_source_dir()

        self.xslpath = os.path.join(dir, "%s.xsl" % type)
        if not os.path.exists(self.xslpath):
            self.xslpath = os.path.join(dir, "default.xsl")
        
    def writeDoc(self, doc, outfile):
        print "Writing to %s" % outfile
        styledoc = libxml2.parseFile(self.xslpath)
        style = libxslt.parseStylesheetDoc(styledoc)
        result = style.applyStylesheet(doc, None)
        style.saveResultToFilename(outfile, result, 0)
        #style.freeStylesheet()
        #styledoc.freeDoc()
        #doc.freeDoc()
        #result.freeDoc()

class FieldWidget:
    def __init__(self, node):
        self.node = node
        self.caption = "Untitled Field"
        self.id = "unknown"
        self.type = (self.__class__.__name__.replace("Widget", "")).lower()
        self.widget = None

    def set_caption(self, caption):
        self.caption = caption

    def set_id(self, id):
        self.id = id

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
        child = self.node.children
        while child:
            if child.type == "text":
                child.unlinkNode()

            child = child.next

        value = xml_escape(self.get_value())
        if value:
            self.node.addContent(value)

class TextWidget(FieldWidget):
    def __init__(self, node):
        FieldWidget.__init__(self, node)

        if node.children:
            text = xml_unescape(node.getContent().strip())
        else:
            text = ""

        self.widget = gtk.Entry()
        self.widget.set_text(text)
        self.widget.show()

    def get_value(self):
        return self.widget.get_text()

    def set_value(self, value):
        self.widget.set_text(value)

class ToggleWidget(FieldWidget):
    def __init__(self, node):
        FieldWidget.__init__(self, node)

        if node.children:
            try:
                status = eval(node.getContent().title())
            except:
                print "Status of `%s' is invalid" % node.getContent()
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

        if node.children:
            text = xml_unescape(node.children.getContent().strip())
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

        sw = gtk.ScrolledWindow()
        sw.set_policy(gtk.POLICY_AUTOMATIC, gtk.POLICY_AUTOMATIC)
        sw.add(self.widget)

        label = gtk.Label(self.caption)
        vbox.pack_start(label, 0,0,0)
        vbox.pack_start(sw, 0,0,0)

        label.show()
        vbox.show()
        sw.show()

        return vbox

    def get_value(self):
        return self.buffer.get_text(self.buffer.get_start_iter(),
                                    self.buffer.get_end_iter())

    def set_value(self, value):
        self.buffer.set_text(value)

class DateWidget(FieldWidget):
    def __init__(self, node):
        FieldWidget.__init__(self, node)

        try:
            text = node.children.getContent().strip()
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
            text = node.children.getContent().strip()
            (h, m, s) = (int(x) for x in text.split(":", 3))
        except:
            config = mainapp.get_mainapp().config
            if config.getboolean("prefs", "useutc"):
                t = time.gmtime()
            else:
                t = time.localtime()

            h = int(time.strftime("%H", t))
            m = int(time.strftime("%M", t))
            s = int(time.strftime("%S", t))

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
        return "%.0f:%02.0f:%02.0f" % (self.hour_a.get_value(),
                                       self.min_a.get_value(),
                                       self.sec_a.get_value())

class NumericWidget(FieldWidget):
    def __init__(self, node):
        FieldWidget.__init__(self, node)

        try:
            min = float(node.prop("min"))
        except:
            min = 0

        try:
            max = float(node.prop("max"))
        except:
            max = 10000.0

        try:
            initial = float(node.children.getContent())
        except:
            initial = 0

        self.adj = gtk.Adjustment(initial, min, max, 1, 10)
        self.widget = gtk.SpinButton(self.adj)
        self.widget.show()

    def get_value(self):
        return "%.0f" % self.adj.get_value()

    def set_value(self, value):
        self.adj.set_value(float(value))

class ChoiceWidget(FieldWidget):
    def parse_choice(self, node):
        if node.name != "choice":
            return

        try:
            content = xml_unescape(node.children.getContent().strip())
            self.choices.append(content)
            if node.prop("set"):
                self.default = content
        except:
            pass

    def __init__(self, node):
        FieldWidget.__init__(self, node)
        
        self.choices = []
        self.default = None

        child = node.children
        while child:
            if child.type == "element":
                self.parse_choice(child)

            child = child.next

        self.widget = make_choice(self.choices, False, self.default)
        self.widget.show()

    def get_value(self):
        return self.widget.get_active_text()

    def update_node(self):
        value = self.get_value()
        if not value:
            return
        
        child = self.node.children
        while child:
            if child.getContent() == value:
                if not child.hasProp("set"):
                    child.newProp("set", "y")
            else:
                child.unsetProp("set")

            child = child.next

class MultiselectWidget(FieldWidget):
    def parse_choice(self, node):
        if node.name != "choice":
            return

        try:
            content = xml_unescape(node.children.getContent().strip())
            print "Got option %s" % content
            self.store.append(row=(node.prop("set") == "y", content))
            self.choices.append((node.prop("set") == "y", content))
        except Exception, e:
            print "Error: %s" % e
            pass

    def toggle(self, rend, path):
        self.store[path][0] = not self.store[path][0]

    def make_selector(self):
        self.store = gtk.ListStore(gobject.TYPE_BOOLEAN,
                                   gobject.TYPE_STRING)
        self.view = gtk.TreeView(self.store)

        rend = gtk.CellRendererToggle()
        rend.connect("toggled", self.toggle)
        col = gtk.TreeViewColumn("", rend, active=0)
        self.view.append_column(col)

        rend = gtk.CellRendererText()
        col = gtk.TreeViewColumn("", rend, text=1)
        self.view.append_column(col)

        self.view.show()
        self.view.set_headers_visible(False)

        return self.view

    def __init__(self, node):
        FieldWidget.__init__(self, node)

        self.choices = []
        self.widget = self.make_selector()
        self.widget.show()

        child = node.children
        while child:
            if child.type == "element":
                self.parse_choice(child)
            child = child.next

    def make_container(self):
        vbox = gtk.VBox(False, 2)

        sw = gtk.ScrolledWindow()
        sw.set_policy(gtk.POLICY_AUTOMATIC, gtk.POLICY_AUTOMATIC)
        sw.add(self.widget)

        if self.caption:
            label = gtk.Label(self.caption)
            vbox.pack_start(label, 0,0,0)
            label.show()
        vbox.pack_start(sw, 0,0,0)

        vbox.show()
        sw.show()

        return vbox

    def get_value(self):
        return ""

    def update_node(self):
        vals = {}
        iter = self.store.get_iter_first()
        while iter:
            setval, name = self.store.get(iter, 0, 1)
            vals[name] = setval
            iter = self.store.iter_next(iter)

        child = self.node.children
        while child:
            choice = child.getContent().strip()
            if choice not in vals.keys():
                vals[choice] = False

            if not child.hasProp("set"):
                child.newProp("set", vals[choice] and "y" or "n")
            else:
                child.setProp("set", vals[choice] and "y" or "n")

            child = child.next

class LabelWidget(FieldWidget):
    def __init__(self, node):
        FieldWidget.__init__(self, node)

    def update_node(self):
        pass

    def make_container(self):
        widget = gtk.Label()
        widget.set_markup("<b><span color='blue'>%s</span></b>" % self.caption)
        color = gtk.gdk.color_parse("blue")
        #widget.modify_fg(gtk.STATE_NORMAL, color)
        widget.show()

        return widget

class FormField:
    widget_types = {
    "text" : TextWidget,
    "multiline" : MultilineWidget,
    "toggle" : ToggleWidget,
    "date" : DateWidget,
    "time" : TimeWidget,
    "numeric" : NumericWidget,
    "choice" : ChoiceWidget,
    "multiselect" : MultiselectWidget,
    "label" : LabelWidget,
    }

    def get_caption_string(self, node):
        return node.getContent().strip()

    def build_entry(self, node, caption):
        type = node.prop("type")

        wtype = self.widget_types[type]

        field = wtype(node)
        field.set_caption(caption)
        field.set_id(self.id)

        return field        

    def build_gui(self, node):
        self.caption = None
        self.entry = None
        
        child = node.children

        while child:
            if child.name == "caption":
                cap_node = child
            elif child.name == "entry":
                ent_node = child

            child = child.next

        self.caption = self.get_caption_string(cap_node)
        self.entry = self.build_entry(ent_node, self.caption)
        self.widget = self.entry.get_widget()
        self.widget.show()

    def __init__(self, field):
        self.node = field
        self.id = field.prop("id")
        self.build_gui(field)

    def get_widget(self):
        return self.widget

    def update_node(self):
        self.entry.update_node()

class Form(gtk.Dialog):
    def but_save(self, widget, data=None):
        p = platform.get_platform()
        f = p.gui_save_file(default_name="%s.html" % self.id)
        if not f:
            return

        try:
            self.export(f)
        except Exception, e:
            ed = gtk.MessageDialog(buttons=gtk.BUTTONS_OK,
                                   parent=self)
            ed.text = "Unable to open file"
            ed.format_secondary_text("Unable to open %s (%s)" % (f, e))
            ed.run()
            ed.destroy()

    def but_printable(self, widget, data=None):
        f = tempfile.NamedTemporaryFile(suffix=".html")
        name = f.name
        f.close()
        self.export(name)

        print "Exported to temporary file: %s" % name
        platform.get_platform().open_html_file(name)

    def calc_check(self, buffer, checkwidget):
        message = buffer.get_text(buffer.get_start_iter(),
                                  buffer.get_end_iter())
        checkwidget.set_text("%i" % len(message.split()))

    def build_path_widget(self):
        pathels = self.get_path()

        pathbox = gtk.Entry()
        pathbox.set_text(";".join(pathels))
        pathbox.set_property("editable", False)
        pathbox.show()

        expander = gtk.Expander("Path")
        expander.add(pathbox)
        expander.show()

        return expander

    def build_gui(self, allow_export=True):
        tlabel = gtk.Label()
        tlabel.set_markup("<big><b>%s</b></big>" % self.title_text)
        tlabel.show()

        if self.logo_path:
            image = gtk.Image()
            try:
                image.set_from_file(self.logo_path)
                self.vbox.pack_start(image, 0,0,0)
                image.show()
            except Exception, e:
                print "Unable to load or display logo %s: %s" % (self.logo_path,
                                                                 e)
        self.vbox.pack_start(tlabel, 0,0,0)

        field_box = gtk.VBox(False, 2)

        sw = gtk.ScrolledWindow()
        sw.set_policy(gtk.POLICY_NEVER,
                      gtk.POLICY_AUTOMATIC)
        sw.add_with_viewport(field_box)
        field_box.show()
        sw.show()
        self.vbox.pack_start(sw, 1,1,1)


        msg_field = None
        chk_field = None

        for f in self.fields:
            if f.id == "_auto_check":
                chk_field = f
            elif f.id == "_auto_message":
                msg_field = f
            elif f.id == "_auto_sender":
                config = mainapp.get_mainapp().config
                if not f.entry.widget.get_text():
                    f.entry.widget.set_text(config.get("user", "callsign"))
                f.entry.widget.set_property("editable", False)
            
            field_box.pack_start(f.get_widget(), 0,0,0)

        self.vbox.pack_start(self.build_path_widget(), 0, 0, 0)

        if msg_field and chk_field:
            mw = msg_field.entry.buffer
            cw = chk_field.entry.widget

            mw.connect("changed", self.calc_check, cw)

        if allow_export:
            save = gtk.Button("Export")
            save.connect("clicked", self.but_save, None)
            save.show()
            self.action_area.pack_start(save, 0,0,0)

        printable = gtk.Button("Printable")
        printable.connect("clicked", self.but_printable, None)
        printable.show()
        self.action_area.pack_start(printable, 0,0,0)

    def process_fields(self, doc):
        ctx = doc.xpathNewContext()
        fields = ctx.xpathEval("//form/field")
        for f in fields:
            try:
                self.fields.append(FormField(f))
            except Exception, e:
                raise
                print e

    def process_form(self, doc):
        ctx = doc.xpathNewContext()
        forms = ctx.xpathEval("//form")
        if len(forms) != 1:
            raise Exception("%i forms in document" % len(forms))

        form = forms[0]
        
        self.id = form.prop("id")

        titles = ctx.xpathEval("//form/title")
        if len(titles) != 1:
            raise Exception("%i titles in document" % len(titles))

        title = titles[0]

        self.title_text = title.children.getContent().strip()

        logos = ctx.xpathEval("//form/logo")
        if len(logos) > 1:
            raise Exception("%i logos in document" % len(logos))
        elif len(logos) == 1:
            logo = logos[0]
            self.logo_path = logo.children.getContent().strip()
        else:
            self.logo_path = None

    def get_xml(self):
        for f in self.fields:
            f.update_node()

        return self.doc.serialize()

    def export(self, outfile):
        for f in self.fields:
            f.update_node()

        w = HTMLFormWriter(self.id)
        w.writeDoc(self.doc, outfile)

    def __init__(self, title, xmlstr, buttons=None, parent=None):
        _buttons = (gtk.STOCK_CANCEL, gtk.RESPONSE_CANCEL,
                   gtk.STOCK_SAVE, gtk.RESPONSE_OK)
        if buttons:
            _buttons += buttons

        gtk.Dialog.__init__(self, title=title, buttons=_buttons, parent=parent)

        self.vbox.set_spacing(5)

        self.fields = []

        self.doc = libxml2.parseMemory(xmlstr, len(xmlstr))

        self.process_form(self.doc)
        self.process_fields(self.doc)

        self.set_default_size(300,500)

        print "Form ID: %s" % self.id

        self.build_gui(gtk.RESPONSE_CANCEL in _buttons)
        
    def get_field_value(self, id):
        for field in self.fields:
            print "Checking %s for %s" % (field.id, id)
            if field.id == id:
                return field.entry.get_value()

        return None

    def set_field_value(self, id, value):
        for field in self.fields:
            if field.id == id:
                field.entry.set_value(value)
                break

    def get_path(self):
        pathels = []
        ctx = self.doc.xpathNewContext()
        els = ctx.xpathEval("//form/path/e")
        for element in els:
            pathels.append(element.getContent().strip())

        return pathels
    
    def add_path_element(self, element):
        ctx = self.doc.xpathNewContext()
        els = ctx.xpathEval("//form/path")
        if not els:
            form, = ctx.xpathEval("//form")
            path = form.newChild(None, "path", None)
        else:
            path = els[0]

        pathel = path.newChild(None, "e", element)

class FormFile(Form):
    def __init__(self, title, filename, buttons=None, parent=None):
        self._filename = filename
        f = file(self._filename)
        data = f.read()
        f.close()

        Form.__init__(self, title, data, buttons=buttons, parent=parent)

    def save_to(self, filename):
        f = file(filename, "w")
        print >>f, self.get_xml()
        f.close()
        
    def run_auto(self, save_file=None):
        if not save_file:
            save_file = self._filename

        r = Form.run(self)
        if r != gtk.RESPONSE_CANCEL:
            self.save_to(save_file)

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

    print form.get_text()
