TIPS_USER = {
    "latitude" : u"Your current latitude.  " + \
        u"Use decimal degrees (DD.DDDDD)\n" + \
        u"or D\u00b0M'S\".  Use a space for special characters",
    "longitude" : u"Your current longitude.  " + \
        u"Use decimal degrees (DD.DDDDD)\n" + \
        u"or D\u00b0M'S\".  Use a space for special characters",
    "altitude" : "Your current altitude",
}

TIPS_PREFS = {
    "useutc" : "When enabled, form time fields will default to current " + \
        "time in UTC.  When disabled, default to local time",
    "language" : "Requires a D-RATS restart",
    }

TIPS_SETTINGS = {
    "port" : "On Windows, use something like 'COM12'\n" + \
        "On UNIX, use something like '/dev/ttyUSB0'\n" + \
        "For a network connection, use something like 'net:host:9000'",
    "rate" : "9600 for mobile radios, 38400 for handhelds",
    "gpsport" : "Serial port for an NMEA-compliant external GPS",
    "gpsenabled" : "If enabled, take current position from the external GPS",
    "gpsportspeed" : "The NMEA standard is 4800",
    "aprssymtab" : "The symbol table character for GPS-A beacons",
    "aprssymbol" : "The symbol character for GPS-A beacons",
    "compatmode" : "Treat incoming raw text (and garbage) as chat data " + \
        "and display it on-screen",
    "mapdir" : "Alternate location to store cached map images",
    "warmup_length" : "Amount of fake data to send during a warmup cycle",
    "warmup_timeout" : "Length of time between transmissions that must " + \
        "pass before we send a warmup block to open the power-save " + \
        "circuits on handhelds",
    "force_delay" : "Amount of time to wait between transmissions",
    "ping_info" : "Text string to return in response to a ping.\n" + \
        "If prefixed by a > character, interpret as a path to a text file\n" + \
        "If prefixed by a ! character, interpret as a path to a script",
    "smtp_server" : "Hostname of outgoing SMTP server.  If this is " + \
        "specified, this station will be a gateway for email forms.  " + \
        "If left blank, this feature is disabled",
    "smtp_replyto" : "Email address to set on outgoing form email messages",
    "smtp_tls" : "If enabled, attempt to negotiate TLS/SSL with SMTP server",
    "smtp_username" : "Username for SMTP authentication.  Disabled if blank",
    "smtp_password" : "Password for SMTP authentication",
    "smtp_port" : "Default is 25.  Set to the value given by your ISP",
    "sniff_packets" : "Display information about packets seen that are " + \
        "destined for other stations",
    }

CONFIG_TIPS = {
    "user" : TIPS_USER,
    "prefs" : TIPS_PREFS,
    "settings" : TIPS_SETTINGS,
}
    
def get_tip(section, value):
    try:
        tip = CONFIG_TIPS[section][value]
    except KeyError:
        tip = None

    return tip
