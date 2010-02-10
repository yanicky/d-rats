import sys
import os
import socket
import tempfile
import subprocess
import shutil
import email
import threading
import gobject
import struct
import time
import re

sys.path.insert(0, "..")

from d_rats import version
from d_rats import platform
from d_rats import formgui
from d_rats import utils
from d_rats.ddt2 import calc_checksum

FBB_BLOCK_HDR = 1
FBB_BLOCK_DAT = 2
FBB_BLOCK_EOF = 4

FBB_BLOCK_TYPES = { FBB_BLOCK_HDR : "header",
                    FBB_BLOCK_DAT : "data",
                    FBB_BLOCK_EOF : "eof",
                    }

def escaped(string):
    return string.replace("\n", r"\n").replace("\r", r"\r")

def run_lzhuf(cmd, data):
    p = platform.get_platform()

    cwd = tempfile.mkdtemp()

    f = file(os.path.join(cwd, "input"), "wb")
    f.write(data)
    f.close()

    kwargs = {}
    if subprocess.mswindows:
        su = subprocess.STARTUPINFO()
        su.dwFlags |= subprocess.STARTF_USESHOWWINDOW
        su.wShowWindow = subprocess.SW_HIDE
        kwargs["startupinfo"] = su

    if os.name == "nt":
        lzhuf = "LZHUF_1.EXE"
    elif os.name == "darwin":
        raise Exception("Not supported on MacOS")
    else:
        lzhuf = "lzhuf"

    lzhuf_path = os.path.abspath(os.path.join(p.source_dir(), "libexec", lzhuf))
    shutil.copy(os.path.abspath(lzhuf_path), cwd)
    run = [lzhuf_path, cmd, "input", "output"]
    
    print "Running %s in %s" % (run, cwd)

    ret = subprocess.call(run, cwd=cwd, **kwargs)
    print "LZHUF returned %s" % ret
    if ret:
        return None

    f = file(os.path.join(cwd, "output"), "rb")
    data = f.read()
    f.close()

    return data

def run_lzhuf_decode(data):
    return run_lzhuf("d", data[2:])

def run_lzhuf_encode(data):
    lzh = run_lzhuf("e", data)
    lzh = struct.pack("<H", calc_checksum(lzh)) + lzh
    return lzh

class WinLinkMessage:
    def __init__(self, header=None):
        self.__name = ""
        self.__content = ""
        self.__usize = self.__csize = 0
        self.__id = ""
        self.__type = "P"

        if header:
            fc, self.__type, self.__id, us, cs, off = header.split()
            self.__usize = int(us)
            self.__csize = int(cs)

            if int(off) != 0:
                raise Exception("Offset support not implemented")

    def __decode_lzhuf(self, data):
        return run_lzhuf_decode(data)

    def __encode_lzhuf(self, data):
        return run_lzhuf_encode(data)

    def read_from_socket(self, s):
        data = ""

        i = 0
        while True:
            print "Reading at %i" % i
            t = ord(s.recv(1))

            if chr(t) == "*":
                msg = s.recv(1024)
                raise Exception("Error getting message: %s" % msg)

            if t not in FBB_BLOCK_TYPES.keys():
                i += 1
                print "Got %x (%c) while reading %i" % (t, chr(t), i)
                continue

            print "Found %s at %i" % (FBB_BLOCK_TYPES.get(t, "unknown"), i)
            size = ord(s.recv(1))
            i += 2 # Account for the type and size

            if t == FBB_BLOCK_HDR:
                header = s.recv(size)
                self.__name, offset, foo = header.split("\0")
                print "Name is `%s' offset %s\n" % (self.__name, offset)
                i += size
            elif t == FBB_BLOCK_DAT:
                print "Reading data block %i bytes" % size
                data += s.recv(size)
                i += size
            elif t == FBB_BLOCK_EOF:
                cs = size
                for i in data:
                    cs += ord(i)
                if (cs % 256) != 0:
                    print "Ack! %i left from cs %i" % (cs, size)
                
                break

        print "Got data: %i bytes" % len(data)
        self.__content = self.__decode_lzhuf(data)
        if self.__content is None:
            raise Exception("Failed to decode compressed message")
        
        if len(data) != self.__csize:
            print "Compressed size %i != %i" % (len(data), self.__csize)
        if len(self.__content) != self.__usize:
            print "Uncompressed size %i != %i" % (len(self.__content),
                                                  self.__usize)

    def send_to_socket(self, s):
        data = self.__lzh_content

        # filename \0 length(0) \0
        header = self.__name + "\x00" + chr(len(data) & 0xFF) + "\x00"
        s.send(struct.pack("BB", FBB_BLOCK_HDR, len(header)) + header)

        sum = 0
        while data:
            chunk = data[:128]
            data = data[128:]

            for i in chunk:
                sum += ord(i)

            s.send(struct.pack("BB", FBB_BLOCK_DAT, len(chunk)) + chunk)

        # Checksum, mod 256, two's complement
        sum = (~sum & 0xFF) + 1
        s.send(struct.pack("BB", FBB_BLOCK_EOF, sum))

    def get_content(self):
        return self.__content

    def set_content(self, content, name="message"):
        self.__name = name
        self.__content = content
        self.__lzh_content = self.__encode_lzhuf(content)
        self.__usize = len(self.__content)
        self.__csize = len(self.__lzh_content)

    def get_id(self):
        return self.__id

    def set_id(self, id):
        self.__id = id

    def get_proposal(self):
        return "FC %s %s %i %i 0" % (self.__type, self.__id,
                                     self.__usize, self.__csize)

class WinLinkTelnet:
    def __init__(self, callsign, server="server.winlink.org", port=8772):
        self.__callsign = callsign
        self.__server = server
        self.__port = port

        self.__socket = None
        self.__messages = []

    def __ssid(self):
        return "[DRATS-%s-B2FHIM$]" % version.DRATS_VERSION

    def __send(self, string):
        print "  -> %s" % string
        self.__socket.send(string + "\r")

    def __recv(self):
        resp = self.__socket.recv(1024).strip()
        print "  <- %s" % escaped(resp)
        return resp

    def __connect(self):
        self.__socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        self.__socket.connect((self.__server, self.__port))

    def __disconnect(self):
        self.__socket.close()

    def __login(self):
        resp = self.__recv()
        if not resp.startswith("Callsign :"):
            raise Exception("Conversation error (never saw login)")

        self.__send(self.__callsign)
        resp = self.__recv()
        if not resp.startswith("Password :"):
            raise Exception("Conversation error (never saw password)")

        self.__send("CMSTELNET")
        resp = self.__recv()
        try:
            sw, ver, caps = resp[1:-1].split("-")
        except Exception:
            raise Exception("Conversation error (unparsable SSID `%s')" % resp)

        self.__send(self.__ssid())
        prompt = self.__recv()
        if not prompt.endswith(">"):
            raise Exception("Conversation error (never got prompt)")

    def __get_list(self):
        self.__send("FF")

        msgs = []
        reading = True
        while reading:
            resp = self.__recv()
            for l in resp.split("\r"):
                if l.startswith("FC"):
                    print "Creating message for %s" % l
                    msgs.append(WinLinkMessage(l))
                elif l.startswith("F>"):
                    reading = False
                    break
                elif l.startswith("FQ"):
                    reading = False
                    break
                else:
                    raise Exception("Conversation error (%s while listing)" % l)

        return msgs

    def get_messages(self):
        self.__connect()
        self.__login()
        self.__messages = self.__get_list()

        if self.__messages:
            self.__send("FS %s" % ("Y" * len(self.__messages)))

            for msg in self.__messages:
                print "Getting message..."
                try:
                    msg.read_from_socket(self.__socket)
                except Exception, e:
                    print e
                    
            self.__send("FQ")

        self.__disconnect()

        return len(self.__messages)

    def get_message(self, index):
        return self.__messages[index]

    def send_messages(self, messages):
        if len(messages) != 1:
            raise Exception("Sorry, batch not implemented yet")

        self.__connect()
        self.__login()

        cs = 0
        for msg in messages:
            p = msg.get_proposal()
            for i in p:
                cs += ord(i)
            cs += ord("\r")
            self.__send(p)

        cs = ((~cs & 0xFF) + 1)
        self.__send("F> %02X" % cs)
        resp = self.__recv()

        if not resp.startswith("FS"):
            raise Exception("Error talking to server: %s" % resp)

        fs, accepts = resp.split()
        if len(accepts) != len(messages):
            raise Exception("Server refused some of my messages?!")

        for msg in messages:
            msg.send_to_socket(self.__socket)

        resp = self.__recv()
        self.__disconnect()

        return 1

class WinLinkThread(threading.Thread, gobject.GObject):
    __gsignals__ = {
        "mail-thread-complete" : (gobject.SIGNAL_RUN_LAST, gobject.TYPE_NONE,
                                  (gobject.TYPE_BOOLEAN, gobject.TYPE_STRING)),
        }
    _signals = __gsignals__

    def _emit(self, *args):
        gobject.idle_add(self.emit, *args)

    def __init__(self, config, callsign, callssid=None, send_msgs=[]):
        threading.Thread.__init__(self)
        gobject.GObject.__init__(self)

        if not callssid:
            callssid = callsign

        self.__config = config
        self.__callsign = callsign
        self.__callssid = callssid
        self.__send_msgs = send_msgs

    def __create_form(self, msg):
        mail = email.message_from_string(msg.get_content())

        sender = mail.get("From", "Unknown")

        if ":" in sender:
            method, sender = sender.split(":", 1)
        
        if self.__callsign == self.__config.get("user", "callsign"):
            box = "Inbox"
        else:
            box = "Outbox"

        template = os.path.join(self.__config.form_source_dir(),
                                "email.xml")
        formfn = os.path.join(self.__config.form_store_dir(),
                              box, "%s.xml" % msg.get_id())

        form = formgui.FormFile(template)
        form.set_field_value("_auto_sender", sender)
        form.set_field_value("recipient", self.__callsign)
        form.set_field_value("subject", mail.get("Subject", "Unknown"))
        form.set_field_value("message", mail.get_payload())
        form.set_path_src(sender.strip())
        form.set_path_dst(self.__callsign)
        form.set_path_mid(msg.get_id())
        form.add_path_element("@WL2K")
        form.add_path_element(self.__config.get("user", "callsign"))
        form.save_to(formfn)

    def _run_incoming(self):
        server = self.__config.get("prefs", "msg_wl2k_server")
        wl = WinLinkTelnet(self.__callssid, server)
        count = wl.get_messages()
        for i in range(0, count):
            msg = wl.get_message(i)
            self.__create_form(msg)        

        if count:
            result = "Queued %i messages" % count
        else:
            result = "No messages"

        return result

    def _run_outgoing(self):
        server = self.__config.get("prefs", "msg_wl2k_server")
        wl = WinLinkTelnet(self.__callssid, server)
        for mt in self.__send_msgs:

            m = re.search("Mid: (.*)\r\nSubject: (.*)\r\n", mt)
            if m:
                mid = m.groups()[0]
                subj = m.groups()[1]
            else:
                mid = time.strftime("%H%M%S%d%m%y_DRATS")
                subj = "Message"

            wlm = WinLinkMessage()
            wlm.set_id(mid)
            wlm.set_content(mt, subj)
            print m
            print mt
            wl.send_messages([wlm])

        return "Complete"

    def run(self):
        if self.__send_msgs:
            result = self._run_outgoing()
        else:
            result = self._run_incoming()

        self._emit("mail-thread-complete", True, result)

if __name__=="__main__":
    if False:
      wl = WinLinkTelnet("KK7DS", "sandiego.winlink.org")
      count = wl.get_messages()
      print "%i messages" % count
      for i in range(0, count):
          print "--Message %i--\n%s\n--End--\n\n" % (i, wl.get_message(i))
    else:
        text = "This is a test!"
        _m = """Mid: 12345_KK7DS\r
From: KK7DS\r
To: dsmith@danplanet.com\r
Subject: This is a test\r
Body: %i\r
\r
%s
""" % (len(text), text)

        m = WinLinkMessage()
        m.set_id("1234_KK7DS")
        m.set_content(_m)
        wl = WinLinkTelnet("KK7DS")
        wl.send_messages([m])

