#!/usr/bin/python

import ConfigParser

class AppConfig:
    def init_config(self):
        self.config.add_section("user")
        self.config.set("user", "name", "A. Mateur")
        self.config.set("user", "callsign", "W1AW")

        self.config.add_section("prefs")
        self.config.set("prefs", "autoid", "True")
        self.config.set("prefs", "autoid_freq", "10")
        self.config.set("prefs", "autoreceive", "False")
        self.config.set("prefs", "download_dir", "")

        self.config.add_section("settings")
        self.config.set("settings", "port", "0")
        self.config.set("settings", "rate", "9600")

    def default_filename(self):
        return "drats.config"

    def __init__(self, _file=None):
        if not _file:
            _file = self.default_filename()

        self.config = ConfigParser.ConfigParser()
        self.config.read(_file)

        if not self.config.has_section("user"):
            self.init_config()

    def save(self, _file=None):
        if not _file:
            _file = self.default_filename()

        f = file(_file, "w")
        self.config.write(f)
        f.close()
