from distutils.core import setup
import py2exe

opts = {
    "py2exe" : {
        "includes" : "pango,atk,gobject,cairo,pangocairo,xml",
        "compressed" : 1,
        "optimize" : 2,
        "bundle_files" : 3,
#        "packages" : ""
        }
    }

setup(
    windows=[{'script' : "d-rats.py",
              'icon_resources': [(0x0004, 'd-rats.ico')]},
             {'script' : 'repeater.py'},
             {'script' : 'mapdownloader.py'}],
    options=opts)
