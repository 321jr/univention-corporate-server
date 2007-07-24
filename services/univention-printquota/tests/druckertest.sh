#!/bin/sh
#
# Univention Print Quota
#  test script
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

# Dieses Skript legt die im Wiki beschriebene Testumgebung an:
# - 2 Benutzer, die beide der gleichen Gruppe angeh�ren
# - 8 normale Drucker
# - 16 Drucker, die in 8 Druckergruppen verwendet werden

if [ "$1" = "" -a "$2" = "" ]; then
	echo "usage: $0 [user@]<ip-addr> [user@]<ip-addr>"
	echo "configures one printer on the second ip, and a bunch of printers"
	echo "on the first ip, all using the first printer as their output device."
	exit 1
fi

if [  "$1" != "start" ]; then
	echo "--> Please enter password for 2nd host"
	remotehost=`ssh $2 hostname -f`
	remoteip=`echo $2 | sed "s/.*@//"`
	echo "--> Please enter password for 1st host"
	scp $0 $1:/tmp/druckertest.sh
	echo "--> Please enter password for 1st host"
	ssh $1 /tmp/druckertest.sh start $remotehost $remoteip
else
	eval `univention-baseconfig shell`
	remotehost=$2
	remoteip=$3

	# eine Rundablage

	univention-admin shares/printer create --set name="rundablage" \
	--set uri="file:///tmp/druckoutput" --set spoolHost=$remotehost \
	--set model=None --position="cn=printers,$ldap_base"

	# Benutzer, Benutzergruppen

	for num in `seq 1 2`; do
		univention-admin users/user create --set username="dtestuser$num" --set \
		lastname="dtestuser$num" --set password="univention" --position="cn=users,$ldap_base"
	done
	univention-admin groups/group create --set name="dtestgroup" \
	--position="cn=groups,$ldap_base" --append users="uid=dtestuser1,cn=users,$ldap_base" \
	--append users="uid=dtestuser2,cn=users,$ldap_base"

	# Drucker, Druckergruppen

	for num in `seq 1 8`; do
		univention-admin shares/printer create --set name="dtestprinter$num" \
		--set uri="ipp://$remoteip/printers/rundablage" --set spoolHost=`hostname -f` \
		--set setQuota=1 --set model=None --position="cn=printers,$ldap_base"
	done

	for num in `seq 1 16`; do
		univention-admin shares/printer create --set name="dgruppentestprinter$num" \
		--set uri="ipp://$remoteip/printers/rundablage" --set spoolHost=`hostname -f` \
		--set setQuota=1 --set model=None --position="cn=printers,$ldap_base"
	done

	for num in `seq 1 8`; do
		if [ "$num" = "1" ]; then
			# Drucker 2 geh�rt auch Druckergruppe 1 an
			univention-admin shares/printergroup create --set name="dtestprintergroup$num" \
			--set spoolHost=`hostname -f` --set setQuota=1 --append groupMember="dgruppentestprinter$num" \
			--append groupMember="dgruppentestprinter$(($num+8))" --append groupMember="dgruppentestprinter2"\
			--position="cn=printers,$ldap_base"
		else
			univention-admin shares/printergroup create --set name="dtestprintergroup$num" \
			--set spoolHost=`hostname -f` --set setQuota=1 --append groupMember="dgruppentestprinter$num" \
			--append groupMember="dgruppentestprinter$(($num+8))" --position="cn=printers,$ldap_base"
		fi
	done

	# Quotas f�r Drucker 1-8 und Druckergruppe 1-8 festlegen

	for num in `seq 1 7`; do
		univention-admin policies/print_quota create --position "cn=printquota,cn=shares,cn=policies,$ldap_base" --set name="printerpolicy$num"

		if [ "$(( $num & 1 ))" = "1" ]; then
			univention-admin policies/print_quota modify --dn="cn=printerpolicy$num,cn=printquota,cn=shares,cn=policies,$ldap_base" --set quotaUsers="6 12 dtestuser1"
		fi

		if [ "$(( $num & 2 ))" = "2" ]; then
			univention-admin policies/print_quota modify --dn="cn=printerpolicy$num,cn=printquota,cn=shares,cn=policies,$ldap_base" --set quotaGroupsPerUsers="6 12 dtestgroup"
		fi

		if [ "$(( $num & 4 ))" = "4" ]; then
			univention-admin policies/print_quota modify --dn="cn=printerpolicy$num,cn=printquota,cn=shares,cn=policies,$ldap_base" --set quotaGroups="6 12 dtestgroup"
		fi

		univention-admin shares/printer modify --dn="cn=dtestprinter$num,cn=printers,$ldap_base" --policy-reference "cn=printerpolicy$num,cn=printquota,cn=shares,cn=policies,$ldap_base"
		univention-admin shares/printergroup modify --dn="cn=dtestprintergroup$num,cn=printers,$ldap_base"  --policy-reference "cn=printerpolicy$num,cn=printquota,cn=shares,cn=policies,$ldap_base"
	done

fi
