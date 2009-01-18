#!/usr/bin/python
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

import os
import threading
import poplib
import smtplib
import email
import rfc822
import time
import platform
import gobject
import re

import formbuilder
import formgui

class MailThread(threading.Thread):
    def __init__(self, config, account, chatgui):
        threading.Thread.__init__(self)
        self.setDaemon(True)

        self.event = threading.Event()

        self.enabled = True
        self.config = config
        self.chatgui = chatgui

        settings = config.get("incoming_email", account)

        try:
            self.server, self.username, \
                self.password, poll, \
                ssl, port, action = settings.split(",", 6)
        except ValueError:
            self.server, self.username, \
                self.password, poll, \
                ssl, port = settings.split(",", 6)
            action = "Form"

        actions = {
            "Form" : self.create_form_from_mail,
            "Chat" : self.do_chat_from_mail,
            }

        try:
            self.action = actions[action]
        except KeyError:
            print "Unsupported action `%s' for %s@%s" % (action,
                                                         self.username,
                                                         self.server)
            return

        if not port:
            self.port = self.use_tls and 995 or 110
        else:
            self.port = int(port)

        self.use_ssl = ssl == "True"
        self.poll = int(poll)

    def trigger(self):
        self.event.set()

    def stop(self):
        self.enabled = False
        self.trigger()

    def message(self, message):
        print "[MAIL %s@%s] %s" % (self.username, self.server, message)

    def fetch_mails(self):
        self.message("Querying %s:%i" % (self.server, self.port))

        if self.use_ssl:
            server = poplib.POP3_SSL(self.server, self.port)
        else:
            server = poplib.POP3(self.server, self.port)

        server.user(self.username)
        server.pass_(self.password)
        
        num = len(server.list()[1])

        messages = []

        for i in range(num):
            self.message("Fetching %i/%i" % (i+1, num))
            result = server.retr(i+1)
            server.dele(i+1)
            message = email.message_from_string("\r\n".join(result[1]))
            messages.append(message)

        server.quit()

        return messages

    def maybe_send_form(self, formfn, sender, recip):
        for i in ["'", '"']:
            recip = recip.replace(i, "")
        recip = recip.strip()

        if not validate_incoming(self.config, recip, sender):
            print "Not auto-sending %s -> %s (no access rule)" % (sender, recip)
            return False

        print "Auto-sending form %s -> %s" % (sender, recip)

        sessiongui = self.chatgui.adv_controls["sessions"]
        sessiongui.send_form(recip, formfn, "Email")

    def create_form_from_mail(self, mail):
        manager = self.chatgui.adv_controls["forms"]

        subject = mail.get("Subject", "[no subject]")
        sender = mail.get("From", "Unknown <devnull@nowhere.com>")
        
        if mail.is_multipart():
            body = None
            for part in mail.walk():
                html = None
                if part.get_content_type() == "text/plain":
                    body = str(part)
                    break
                elif part.get_content_type() == "text/html":
                    html = str(part)
            if not body:
                body = html
        else:
            body = mail.get_payload()

        if not body:
            self.message("Unable to find a text/plain part")

        messageid = mail.get("Message-ID", time.strftime("%m%d%Y%H%M%S"))
        recip, addr = rfc822.parseaddr(mail.get("To", "UNKNOWN"))

        self.message("%s: %s" % (sender, subject))

        efn = os.path.join(manager.form_source_dir, "email.xml")
        mid = platform.get_platform().filter_filename(messageid)
        ffn = os.path.join(manager.form_store_dir, "%s.xml" % mid)

        form = formgui.FormFile("", efn)
        form.set_field_value("_auto_sender", sender)
        form.set_field_value("recipient", recip)
        form.set_field_value("subject", subject)
        form.set_field_value("message", body)
        form.add_path_element("EMAIL")
        form.add_path_element(self.config.get("user", "callsign"))
        form.save_to(ffn)

        form_name = "EMAIL: %s" % subject

        manager.reg_form(form_name,
                         ffn,
                         "Never",
                         manager.get_stamp())
        manager.gui.display_line("Email '%s' received from '%s'" % (\
                subject, sender), "italic")

        self.maybe_send_form(ffn, sender, recip)

    def do_chat_from_mail(self, mail):
        if mail.is_multipart():
            body = None
            for part in mail.walk():
                html = None
                if part.get_content_type() == "text/plain":
                    body = str(part)
                    break
                elif part.get_content_type() == "text/html":
                    html = str(part)
            if not body:
                body = html
        else:
            body = mail.get_payload()

        text = "Message from %s (%s):\r\n%s" % (\
            mail.get("From", "Unknown Sender"),
            mail.get("Subject", ""),
            body)
            
        self.chatgui.tx_msg(text)

    def run(self):
        self.message("Thread starting")

        while self.enabled:
            if not self.config.getboolean("state", "connected_inet"):
                self.message("Not connected")
            else:
                mails = []
                try:
                    mails = self.fetch_mails()
                except Exception, e:
                    self.message("Failed to retrieve messages: %s" % e)
                for mail in mails:
                    self.action(mail)

            self.event.wait(self.poll * 60)
            self.event.clear()

        self.message("Thread ending")

class FormEmailService:
    def message(self, msg):
        print "[SMTP] %s" % msg

    def __init__(self, config):
        self.config = config

    def _send_email(self, send, recp, subj, mesg):
        server = self.config.get("settings", "smtp_server")
        replyto = self.config.get("settings", "smtp_replyto")
        tls = self.config.getboolean("settings", "smtp_tls")
        user = self.config.get("settings", "smtp_username")
        pwrd = self.config.get("settings", "smtp_password")
        port = self.config.getint("settings", "smtp_port")

        if not replyto:
            replyto = "DO_NOT_REPLY@danplanet.com"

        for i in "<>\"'":
            if i in send:
                send = send.replace(i, "")

        mail = \
            "From: \"%s\" <%s>\r\n" % (send, replyto) + \
            "To: %s\r\n" % recp + \
            "Reply-To: \"%s\" <%s>\r\n" % (send, replyto) + \
            "Subject: %s\r\n" % subj +\
            "\r\n%s\r\n" % mesg

        self.message("Connecting to %s:%i" % (server, port))
        mailer = smtplib.SMTP(server, port)
        self.message("Connected")
        mailer.set_debuglevel(1)

        self.message("Sending EHLO")
        mailer.ehlo()
        self.message("Done")
        if tls:
            self.message("TLS is enabled, sending STARTTLS")
            mailer.starttls()
            self.message("Sending EHLO again")
            mailer.ehlo()
            self.message("Done")
        if user and pwrd:
            self.message("Doing login with %s,%s" % (user, pwrd))
            mailer.login(user, pwrd)
            self.message("Done")

        self.message("Sending mail")
        mailer.sendmail(replyto, recp, mail)
        self.message("Done")
        mailer.quit()
        self.message("Disconnected")

    def send_email(self, form):
        if not self.config.getboolean("state", "connected_inet"):
            raise Exception("Unable to send mail: Not connected to internet")

        send = form.get_field_value("_auto_sender")
        recp = form.get_field_value("recipient")
        subj = form.get_field_value("subject")
        mesg = form.get_field_value("message")

        self.message("Preparing to send `%s' from %s to %s" % (\
                subj, send, recp))

        if not self.config.getboolean("settings", "smtp_dogw"):
            return False, "Email form received but not configured for SMTP"
        
        try:
            self.message("Sending mail...")
            self._send_email(send, recp, subj, mesg)
            self.message("Successfully sent to %s" % recp)
            return True, "Mail sent ('%s' to '%s')" % (subj, recp)
        except Exception, e:
            self.message("Error sending mail: %s" % e)
            return False, "Error sending mail: %s" % e

    def thread_fn(self, form, cb):
        status, msg = self.send_email(form)
        gobject.idle_add(cb, status, msg)

    def send_email_background(self, form, cb):
        if not self.config.getboolean("state", "connected_inet"):
            raise Exception("Unable to send mail: Not connected to internet")

        thread = threading.Thread(target=self.thread_fn,
                                  args=(form,cb))
        thread.start()

def __validate_access(config, callsign, emailaddr, types):
    rules = config.options("email_access")

    for rule in rules:
        rulespec = config.get("email_access", rule)
        call, access, filter = rulespec.split(",", 2)

        if call in [callsign, "*"] and re.search(filter, emailaddr):
            print "%s -> %s matches %s,%s,%s" % (callsign, emailaddr,
                                                 call, access, filter)
            print "Access types allowed: %s" % types
            return access in types
        else:
            print "%s -> %s does not match %s,%s,%s" % (callsign, emailaddr,
                                                        call, access, filter)

    print "No match found"

    return False

def validate_outgoing(config, callsign, emailaddr):
    return __validate_access(config, callsign, emailaddr, ["Both", "Outgoing"])
    
def validate_incoming(config, callsign, emailaddr):
    return __validate_access(config, callsign, emailaddr, ["Both", "Incoming"])

if __name__ == "__main__":
    class fakeout:
        form_source_dir = "forms"
        form_store_dir = "."

        def reg_form(self, *args):
            pass

        def list_add_form(self, *args, **kwargs):
            pass

        def get_stamp(self):
            return "FOO"

    mt = MailThread(None, fakeout())
    mt.run()
