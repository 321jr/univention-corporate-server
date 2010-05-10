# -*- coding: utf-8 -*-
#
# Univention mail Postfix Kolab2
#  listener module: creates mailboxes
#
# Copyright (C) 2005-2010 Univention GmbH
#
# http://www.univention.de/
#
# All rights reserved.
#
# This program is free software; you can redistribute it and/or modify
# it under the terms of the GNU General Public License version 2 as
# published by the Free Software Foundation.
#
# Binary versions of this file provided by Univention to you as
# well as other copyrighted, protected or trademarked materials like
# Logos, graphics, fonts, specific documentations and configurations,
# cryptographic keys etc. are subject to a license agreement between
# you and Univention.
#
# This program is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU General Public License for more details.
#
# You should have received a copy of the GNU General Public License
# along with this program; if not, write to the Free Software
# Foundation, Inc., 51 Franklin St, Fifth Floor, Boston, MA  02110-1301  USA

import os

var = 'mail/archivefolder'
cmd = '/usr/sbin/univention-cyrus-mkdir'

def handler(baseConfig, changes):
	folder = baseConfig.get(var)
	if folder:
		print '', folder
		os.system('%s %s' % (cmd, folder))
