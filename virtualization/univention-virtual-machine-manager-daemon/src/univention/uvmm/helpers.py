#!/usr/bin/python
# -*- coding: utf-8 -*-
#
# Univention Virtual Machine Manager Daemon
#  python module
#
# Copyright 2010 Univention GmbH
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

__all__ = [
		'_',
		'N_',
		'TranslatableException',
		'LIBVIRT_ERR',
		'ms',
		]

import gettext
N_ = lambda msg: msg
_ = gettext.translation('univention-virtual-machine-manager', fallback=True).ugettext

class TranslatableException(Exception):
	"""Translatable exception (translatable_text, dict, key=value)."""

	def __init__(self, translatable_text, dict={}, **args):
		if isinstance(translatable_text, TranslatableException):
			translatable_text, dict2 = translatable_text.args
			dict2.update(dict)
			dict = dict2
		dict.update(args)
		Exception.__init__(self, translatable_text, dict)

	def __str__(self):
		translatable_text, dict = self.args
		return translatable_text % dict

	@property
	def translatable_text(self):
		return self.args[0]

	@property
	def dict(self):
		return self.args[1]

import libvirt
LIBVIRT_ERR = dict([(getattr(libvirt, err), err) for err in dir(libvirt) if err.startswith('VIR_ERR_')])

def ms(ms):
	"""
	Format milli seconds as readable string.
	>>> ms(((12*60+34)*60+56)*1000+789)
	'12:34:56.789'
	"""

	hm, s = divmod(ms, 60000)
	h, m = divmod(hm, 60)
	return "%d:%02d:%06.3f" % (h, m, s / 1000.0)

if __name__ == '__main__':
	import doctest
	doctest.testmod()
