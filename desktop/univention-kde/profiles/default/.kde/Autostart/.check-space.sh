#!/bin/bash
#
# Univention KDE
#  create 1M file in home dir. if an error occurs, home is nearly full
#  (quota) and user will be warned.
#
# Copyright (C) 2004, 2005, 2006 Univention GmbH
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

dd if=/dev/zero of=$HOME/.kde/.spacesaver bs=10k count=25 >/dev/null 2>&1 || {
    case $LANG in
		de*)
			echo -e 'Der ihrem Benutzerkonto zugewiesene Speicherplatz wird knapp.\nSie sollten nicht ben�tigte Dateien l�schen oder den Systemverwalter\num eine Erh�hung der Speicherplatzquote bitten.' \
				| xmessage -center -file -
			;;
		*)
			echo -e 'Your account is running out of disk space.\n You should delete some unused files or ask your administrator\nfor quota increasement.' \
				| xmessage -geometry -file -
			;;
    esac
}
