from distutils.core import setup
import py2exe

opts = {
    "py2exe" : {
    "includes" : "pango,atk,gobject,cairo,pangocairo",
    }
    }

setup(windows=["d-rats.py"], options=opts)
