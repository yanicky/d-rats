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

import sessionmgr

class ChatSession(sessionmgr.StatelessSession):
    __cb = None
    __cb_data = None

    def incoming_data(self, frame):
        if not self.__cb:
            return

        args = { "From" : frame.s_station,
                 "To" : frame.d_station,
                 "Msg" : frame.data,
                 }

        print "Calling chat callback with %s" % args

        self.__cb(self.__cb_data, args)

    def register_cb(self, cb, data=None):
        self.__cb = cb
        self.__cb_data = data

        self.handler = self.incoming_data
