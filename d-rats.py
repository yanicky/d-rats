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

import sys
import mainapp

from optparse import OptionParser

if __name__ == "__main__":
    o = OptionParser()
    o.add_option("-s", "--safe",
                 dest="safe",
                 action="store_true",
                 help="Safe mode (ignore configuration)")
    (opts, args) = o.parse_args()
    app = mainapp.MainApp(opts.safe)
    sys.exit(app.main())

