import gtk
import tempfile
import os

import inputdialog
import miscwidgets
import platform

sizes = [
    "160x120",
    "320x240",
    "640x480",
    "1024x768",
    "Original Size",
    "10%",
    "20%",
    "30%",
    "40%",
    "50%",
    "60%",
    "70%",
    "80%",
    "90%",
    ]

def has_image_support():
    global IMAGE
    try:
        import Image
    except ImportError:
        return False

    IMAGE = Image

    return True

def update_image(filename, dlg):
    reqsize = dlg.size.get_active_text()
    if "x" in reqsize:
        _h, _w = reqsize.split("x")

        h = int(_h)
        w = int(_w)
    elif "%" in reqsize:
        factor = float(reqsize[0:2]) / 100.0
        h, w = dlg.image.size

        w = int(w * factor)
        h = int(h * factor)
    else:
        h, w = dlg.image.size

    resized = dlg.image.resize((h, w))

    dlg.resized = os.path.join(tempfile.gettempdir(),
                               "resized_" + os.path.basename(filename) + ".jpg")
    resized.save(dlg.resized, quality=dlg.quality)
    
    print "Saved to %s" % dlg.resized

    f = file(dlg.resized)
    f.seek(0, 2)
    size = f.tell()
    f.close()

    dlg.sizelabel.set_text("%i KB" % (size >> 10))        
    dlg.preview.set_from_file(dlg.resized)

def set_quality(scale, event, value, dlg):
    dlg.quality = int(value)
    dlg.update()

def build_image_dialog(filename, image, dlgParent=None):
    d = inputdialog.FieldDialog(title="Send Image",
                                parent=dlgParent)

    def update():
        update_image(filename, d)

    d.add_field("Filename", gtk.Label(os.path.basename(filename)))

    d.sizelabel = gtk.Label("--")
    d.add_field("Size", d.sizelabel)

    d.size = miscwidgets.make_choice(sizes, False, sizes[1])
    d.size.connect("changed", lambda x: update())
    d.add_field("Resize to", d.size)

    quality = gtk.HScale(gtk.Adjustment(50, 1, 100, 10, 10))
    quality.connect("format-value",
                    lambda s,v: "%i" % v)
    quality.connect("change-value", set_quality, d)
    d.add_field("Quality", quality)

    d.preview = gtk.Image()
    d.preview.show()
    sw = gtk.ScrolledWindow()
    sw.add_with_viewport(d.preview)
    sw.set_size_request(320,320)
    d.add_field("Preview", sw, full=True)

    d.set_size_request(400, 450)

    d.image = image
    d.resized = None
    d.quality = 50

    d.update = update
    d.update()

    return d

def send_image(dlgParent=None):
    p = platform.get_platform()

    f = p.gui_open_file()
    if not f:
        return

    try:
        img = IMAGE.open(f)
    except IOError:
        d = gtk.MessageDialog(buttons=gtk.BUTTONS_OK, parent=dlgParent)
        d.set_property("text", "Unknown image type")
        d.run()
        d.destroy()
        return

    d = build_image_dialog(f, img, dlgParent)
    r = d.run()
    f = d.resized
    d.destroy()

    if r == gtk.RESPONSE_OK:
        return f
    else:
        return None

if __name__ == "__main__":
    has_image_support()
    print send_image()
    gtk.main()
