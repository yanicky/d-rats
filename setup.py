import sys

def win32_build():
    from distutils.core import setup
    import py2exe

    try:
        # if this doesn't work, try import modulefinder
        import py2exe.mf as modulefinder
        import win32com
        for p in win32com.__path__[1:]:
            modulefinder.AddPackagePath("win32com", p)
        for extra in ["win32com.shell"]: #,"win32com.mapi"
            __import__(extra)
            m = sys.modules[extra]
            for p in m.__path__[1:]:
                modulefinder.AddPackagePath(extra, p)
    except ImportError:
        # no build path setup, no worries.
        pass


    opts = {
        "py2exe" : {
            "includes" : "pango,atk,gobject,cairo,pangocairo,win32gui,win32com,win32com.shell,email.iterators,email.generator",
            "compressed" : 1,
            "optimize" : 2,
            "bundle_files" : 3,
            #        "packages" : ""
            }
        }

    setup(
        windows=[{'script' : "d-rats",
                  'icon_resources': [(0x0004, 'd-rats2.ico')]},
                 {'script' : 'repeater'},
                 {'script' : 'mapdownloader'}],
        data_files=["C:\\GTK\\bin\\jpeg62.dll"],
        options=opts)

def macos_build():
    from setuptools import setup

    APP = ['d-rats.py']
    DATA_FILES = [('../Frameworks',
                   ['/opt/local/lib/libpangox-1.0.0.2002.3.dylib']),
                  ('../Resources/pango/1.6.0/modules', ['/opt/local/lib/pango/1.6.0/modules/pango-basic-atsui.so']),
                  ('../Resources',
                   ['images']),
                  ]
    OPTIONS = {'argv_emulation': True, "includes" : "gtk,atk,pangocairo,cairo"}

    setup(
        app=APP,
        data_files=DATA_FILES,
        options={'py2app': OPTIONS},
        setup_requires=['py2app'],
        )

def default_build():
    from distutils.core import setup
    from d_rats.mainapp import DRATS_VERSION

    setup(
        name="d-rats",
        packages=["d_rats", "d_rats.geopy"],
        version=DRATS_VERSION,
        scripts=["d-rats", "d-rats_mapdownloader", "d-rats_repeater"],
        data_files=[('/usr/share/applications',
                     ["share/d-rats.desktop",
                      "share/d-rats_mapdownloader.desktop",
                      "share/d-rats_repeater.desktop"])])

if sys.platform == "darwin":
    macos_build()
elif sys.platform == "win32":
    win32_build()
else:
    default_build()


