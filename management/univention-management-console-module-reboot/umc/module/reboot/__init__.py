#!/usr/bin/python2.6
# -*- coding: utf-8 -*-
#
# Univention Management Console
#  module: system halt/reboot
#
# Copyright 2011 Univention GmbH
#
# http://www.univention.de/
#
# All rights reserved.
#
# The source code of this program is made available
# under the terms of the GNU Affero General Public License version 3
# (GNU AGPL V3) as published by the Free Software Foundation.
#
# Binary versions of this program provided by Univention to you as
# well as other copyrighted, protected or trademarked materials like
# Logos, graphics, fonts, specific documentations and configurations,
# cryptographic keys etc. are subject to a license agreement between
# you and Univention and not subject to the GNU AGPL V3.
#
# In the case you use this program under the terms of the GNU AGPL V3,
# the program is provided in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE. See the
# GNU Affero General Public License for more details.
#
# You should have received a copy of the GNU Affero General Public
# License with the Debian GNU/Linux or Univention distribution in file
# /usr/share/common-licenses/AGPL-3; if not, see
# <http://www.gnu.org/licenses/>.

import subprocess
import univention.info_tools as uit
import univention.management.console as umc
import univention.management.console.modules as umcm

from univention.management.console.log import MODULE
from univention.management.console.protocol.definitions import *

_ = umc.Translation('univention-management-console-modules-reboot').translate

class Instance(umcm.Base):
	def init(self):
		uit.set_language(str(self.locale))

        def reboot(self, request):
                if request.options['action'] == 'halt':
                        do="h"
                        target=_('The system is going down for system halt NOW with following message: ')
                elif request.options['action'] == 'reboot':
                        do = "r"
                        target=_('The system is going down for reboot NOW with following message: ')

                message = target + request.options['message']

                try:
                        subprocess.call(('logger', '-f', '/var/log/syslog', '-t', 'UMC', message))
                        subprocess.call(('shutdown', '-%s' %do, 'now', message))
                        request.status = SUCCESS
                except (OSError, ValueError), e:
                        request.status = MODULE_ERR
                        MODULE.warn(str(e))

		self.finished(request.id, {"message": message})
