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
import email
import rfc822
import time
import platform

import formbuilder
import formgui

class MailThread(threading.Thread):
    def __init__(self, config, manager):
        threading.Thread.__init__(self)

        self.event = threading.Event()

        self.enabled = True
        self.config = config
        self.manager = manager

        self.server = config.get("settings", "pop3_server")
        self.username = config.get("settings", "pop3_username")
        self.password = config.get("settings", "pop3_password")
        
    def trigger(self):
        self.event.set()

    def stop(self):
        self.enabled = False
        self.trigger()

    def message(self, message):
        print "[MAIL] %s" % message

    def fetch_mails(self):
        self.message("Querying %s" % self.server)
        
        server = poplib.POP3(self.server)
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

    def create_form_from_mail(self, mail):
        subject = mail.get("Subject", "[no subject]")
        sender = mail.get("From", "Unknown <devnull@nowhere.com>")
        body = mail.get_payload()
        messageid = mail.get("Message-ID", time.strftime("%m%d%Y%H%M%S"))
        recip, addr = rfc822.parseaddr(mail.get("To", "UNKNOWN"))

        self.message("%s: %s" % (sender, subject))

        efn = os.path.join(self.manager.form_source_dir, "email.xml")
        mid = platform.get_platform().filter_filename(messageid)
        ffn = os.path.join(self.manager.form_store_dir, "%s.xml" % mid)

        form = formgui.FormFile("", efn)
        form.set_field_value("_auto_sender", sender)
        form.set_field_value("recipient", recip)
        form.set_field_value("subject", subject)
        form.set_field_value("message", body)
        form.save_to(ffn)

        form_name = "EMAIL: %s" % subject

        self.manager.reg_form(form_name,
                              ffn,
                              "Never",
                              self.manager.get_stamp())
        self.manager.list_add_form(0,
                                   form_name,
                                   ffn,
                                   stamp="Never",
                                   xfert="Never")

    def run(self):
        self.message("Thread starting")

        while self.enabled:
            try:
                mails = self.fetch_mails()
            except Exception, e:
                self.message("Failed to retrieve messages")
            for mail in mails:
                self.create_form_from_mail(mail)

            self.event.wait(30)
            self.event.clear()

        self.message("Thread ending")

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
