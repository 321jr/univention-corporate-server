#!/bin/bash
#
# Copyright (C) 2010-2016 Univention GmbH
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

export DEBIAN_FRONTEND=noninteractive

UPDATER_LOG="/var/log/univention/updater.log"
exec 3>>"$UPDATER_LOG"
UPDATE_NEXT_VERSION="$1"

echo "Running preup.sh script" >&3
date >&3

eval "$(univention-config-registry shell)" >&3 2>&3

conffile_is_unmodified () {
	# conffile_is_unmodified <conffile>
	# returns exitcode 0 if given conffile is unmodified
	if [ ! -f "$1" ]; then
		return 1
	fi
	local chksum="$(md5sum "$1" | awk '{ print $1 }')"
	local fnregex="$(python -c 'import re,sys;print re.escape(sys.argv[1])' "$1")"
	for testchksum in $(dpkg-query -W -f '${Conffiles}\n' | sed -nre "s,^ $fnregex ([0-9a-f]+)( .*)?$,\1,p") ; do
		if [ "$testchksum" = "$chksum" ] ; then
			return 0
		fi
	done
	return 1
}

readcontinue ()
{
    while true ; do
        echo -n "Do you want to continue [Y/n]? "
        read var
        if [ -z "$var" -o "$var" = "y" -o "$var" = 'Y' ]; then
            return 0
        elif [ "$var" = "n" -o "$var" = 'N' ]; then
            return 1
        else
            echo ""
            continue
        fi
    done
}

###########################################################################
# RELEASE NOTES SECTION (Bug #19584)
# Please update URL to release notes and changelog on every release update
###########################################################################
echo
echo "HINT:"
echo "Please check the release notes carefully BEFORE updating to UCS ${UPDATE_NEXT_VERSION}:"
echo " English version: http://docs.univention.de/release-notes-3.3-0-en.html"
echo " German version:  http://docs.univention.de/release-notes-3.3-0-de.html"
echo
echo "Please also consider documents of following release updates and"
echo "3rd party components."
echo
if [ ! "$update_warning_releasenotes" = "no" -a ! "$update_warning_releasenotes" = "false" -a ! "$update_warning_releasenotes_internal" = "no" ] ; then
	if [ "$UCS_FRONTEND" = "noninteractive" ]; then
		echo "Update will wait here for 60 seconds..."
		echo "Press CTRL-c to abort or press ENTER to continue"
		# BUG: 'read -t' is the only bash'ism in this file, therefore she-bang has to be /bin/bash not /bin/sh!
		read -t 60 somevar
	else
		readcontinue || exit 1
	fi
fi

echo ""

# check if user is logged in using ssh
if [ -n "$SSH_CLIENT" ]; then
	if [ "$update33_ignoressh" != "yes" ]; then
		echo "WARNING: You are logged in using SSH -- this may interrupt the update and result in an inconsistent system!"
		echo "Please log in under the console or re-run with \"--ignoressh\" to ignore it."
		exit 1
	fi
fi

if [ "$TERM" = "xterm" ]; then
	if [ "$update33_ignoreterm" != "yes" ]; then
		echo "WARNING: You are logged in under X11 -- this may interrupt the update and result in an inconsistent system!"
		echo "Please log in under the console or re-run with \"--ignoreterm\" to ignore it."
		exit 1
	fi
fi

# save ucr settings
updateLogDir="/var/univention-backup/update-to-$UPDATE_NEXT_VERSION"
if [ ! -d "$updateLogDir" ]; then
	mkdir -p "$updateLogDir"
fi
cp /etc/univention/base*.conf "$updateLogDir/"
ucr dump > "$updateLogDir/ucr.dump"

# call custom preup script if configured
if [ ! -z "$update_custom_preup" ]; then
	if [ -f "$update_custom_preup" ]; then
		if [ -x "$update_custom_preup" ]; then
			echo "Running custom preupdate script $update_custom_preup"
			"$update_custom_preup" "$UPDATE_NEXT_VERSION" >&3 2>&3
			echo "Custom preupdate script $update_custom_preup exited with exitcode: $?" >&3
		else
			echo "Custom preupdate script $update_custom_preup is not executable" >&3
		fi
	else
		echo "Custom preupdate script $update_custom_preup not found" >&3
	fi
fi

# shell-univention-lib is proberly not installed, so use a local function
is_ucr_true () {
    local value
    value="$(/usr/sbin/univention-config-registry get "$1")"
    case "$(echo -n "$value" | tr [:upper:] [:lower:])" in
        1|yes|on|true|enable|enabled) return 0 ;;
        0|no|off|false|disable|disabled) return 1 ;;
        *) return 2 ;;
    esac
}

## check for hold packages
hold_packages=$(LC_ALL=C dpkg -l | grep ^h | awk '{print $2}')
if [ -n "$hold_packages" ]; then
	echo "WARNING: Some packages are marked as hold -- this may interrupt the update and result in an inconsistent"
	echo "system!"
	echo "Please check the following packages and unmark them or set the UCR variable update33/ignore_hold to yes"
	for hp in $hold_packages; do
		echo " - $hp"
	done
	if is_ucr_true update33/ignore_hold; then
		echo "WARNING: update33/ignore_hold is set to true. Skipped as requested."
	else
		exit 1
	fi
fi

##

## Check for PostgreSQL-8.3 (Bug #40690)
check_for_postgresql83 () {
	case "$(dpkg-query -W -f '${Status}' postgresql-8.3 2>/dev/null)" in
	install*) ;;
	*) return 0 ;;
	esac
	echo "WARNING: PostgreSQL-8.3 is no longer supported by UCS-4 and must be migrated to"
	echo "         a newer version of PostgreSQL. See http://sdb.univention.de/1249 for"
	echo "         more details."
	exit 1
}
check_for_postgresql83

## Check for PostgreSQL-8.4 (Bug #40690)
check_for_postgresql84 () {
	case "$(dpkg-query -W -f '${Status}' postgresql-8.4 2>/dev/null)" in
	install*) ;;
	*) return 0 ;;
	esac
	echo "WARNING: PostgreSQL-8.4 is no longer supported by UCS 3.3 and must be migrated to"
	echo "         a newer version of PostgreSQL, AFTER the update to UCS 3.3."
	echo "         See http://sdb.univention.de/1292 for more details."
	echo
	echo "         The update can continue, but to get security updates it is important"
	echo "         that you migrate to PostgreSQL 9.1 after the update to UCS 3.3."
	readcontinue || exit 1
}
check_for_postgresql84

## Check errata version (Bug #40704)
check_for_minimum_errata () {
	local minimum_errata=$1
	if ! is_ucr_true update33/ignore_errata_check; then
		if [ $minimum_errata -gt $version_erratalevel ]; then
			echo "WARNING: The erratalevel version of this system is ${version_erratalevel}."
			echo "         In order to install the UCS 3.3 release update please"
			echo "         upgrade the system to at least errata level ${minimum_errata}!"
			exit 1
		fi
	fi
}
check_for_minimum_errata "422" # http://errata.software-univention.de/ucs/3.2/422.html

#################### Bug #22093

list_passive_kernels () {
	kernel_version="$1"
	dpkg-query -W -f '${Package}\n' "linux-image-${kernel_version}-ucs*" 2>/dev/null |
		fgrep -v "linux-image-$(uname -r)"
}

get_latest_kernel_pkg () {
	# returns latest kernel package for given kernel version
	# currently running kernel is NOT included!

	kernel_version="$1"

	latest_dpkg=""
	latest_kver=""
	for kver in $(list_passive_kernels "$kernel_version") ; do
		dpkgver="$(apt-cache show "$kver" 2>/dev/null | sed -nre 's/Version: //p')"
		if dpkg --compare-versions "$dpkgver" gt "$latest_dpkg" ; then
			latest_dpkg="$dpkgver"
			latest_kver="$kver"
		fi
	done
	echo "$latest_kver"
}

pruneOldKernel () {
	# removes all kernel packages of given kernel version
	# EXCEPT currently running kernel and latest kernel package
	# ==> at least one and at most two kernel should remain for given kernel version
	kernel_version="$1"

	list_passive_kernels "$kernel_version" |
		fgrep -v "$(get_latest_kernel_pkg "$kernel_version")" |
		DEBIAN_FRONTEND=noninteractive xargs -r apt-get -o DPkg::Options::=--force-confold -y --force-yes purge
}

if [ "$update33_pruneoldkernel" = "yes" ]; then
	echo "Purging old kernel..." | tee -a /var/log/univention/updater.log
	pruneOldKernel "2.6.*"
	pruneOldKernel "3.2.0"
	pruneOldKernel "3.10.0"
	echo "done" | tee -a /var/log/univention/updater.log
fi

#####################

check_space(){
	partition=$1
	size=$2
	usersize=$3
	echo -n "Checking for space on $partition: "
	if [ `df -P "$partition" | tail -n1 | awk '{print $4}'` -gt "$size" ]; then
		echo "OK"
	else
		echo "failed"
		echo "ERROR:   Not enough space in $partition, need at least $usersize."
		echo "         This may interrupt the update and result in an inconsistent system!"
		echo "         If neccessary you can skip this check by setting the value of the"
		echo "         config registry variable update33/checkfilesystems to \"no\"."
		echo "         But be aware that this is not recommended!"
		if [ "$partition" = "/boot" -a ! "$update33_pruneoldkernel" = "yes" ] ; then
			echo "         Old kernel versions on /boot can be pruned automatically during"
			echo "         next update attempt by setting config registry variable"
			echo "         update33/pruneoldkernel to \"yes\"."
		fi
		echo ""
		# kill the running univention-updater process
		exit 1
	fi
}


# move old initrd files in /boot
initrd_backup=/var/backups/univention-initrd.bak/
if [ ! -d "$initrd_backup" ]; then
	mkdir "$initrd_backup"
fi
mv /boot/*.bak /var/backups/univention-initrd.bak/ >/dev/null 2>&1

# check space on filesystems
if [ ! "$update33_checkfilesystems" = "no" ]
then

	check_space "/var/cache/apt/archives" "250000" "250 MB"
	check_space "/boot" "60000" "60 MB"
	check_space "/" "700000" "700 MB"

else
    echo "WARNING: skipped disk-usage-test as requested"
fi


echo -n "Checking for package status: "
dpkg -l 2>&1 | LC_ALL=C grep "^[a-zA-Z][A-Z] " >&3 2>&3
if [ $? = 0 ]; then
	echo "failed"
	echo "ERROR: The package state on this system is inconsistent."
	echo "       Please run 'dpkg --configure -a' manually"
	exit 1
fi
echo "OK"

echo "save packages status:" >&3 2>&3
echo "-> dpkg --get-selections" >&3 2>&3
dpkg --get-selections >&3 2>&3
echo >&3 2>&3
echo >&3 2>&3

echo "save auto installed packages (/var/lib/apt/extended_states):" >&3 2>&3
echo "-> apt-cache showauto" >&3 2>&3
apt-cache showauto >&3 2>&3
echo >&3 2>&3
echo >&3 2>&3

if [ -x /usr/sbin/slapschema ]; then
	echo -n "Checking LDAP schema: "
	if ! /usr/sbin/slapschema >&3 2>&3; then
		echo "failed"
		echo "ERROR: There is a problem with the LDAP schema on this system."
		echo "       Please check $UPDATER_LOG or run 'slapschema' manually."
		exit 1
	fi
	echo "OK"
fi

# check for valid machine account
if [ -f /var/univention-join/joined -a ! -f /etc/machine.secret ]
then
	echo "ERROR: The credentials for the machine account could not be found!"
	echo "       Please contact the support team"
	exit 1
fi

eval "$(ucr shell server/role ldap/base ldap/hostdn ldap/server/name)"
if [ -n "$server_role" -a "$server_role" != "basesystem" -a -n "$ldap_base" -a -n "$ldap_hostdn" ]
then
	ldapsearch -x -D "$ldap_hostdn" -w "$(< /etc/machine.secret)" -b "$ldap_base" -s base &>/dev/null
	if [ $? -eq 49 ]
	then
		echo "ERROR: A LDAP connection to the configured LDAP servers with the machine"
		echo "       account has failed (invalid credentials)!"
		echo "       This MUST be fixed before the update can continue."
		echo
		echo "       This problem can be corrected by setting the content of the file"
		echo "       /etc/machine.secret to the password of the computer object using"
		echo "       Univention Management Console."
		exit 1
	fi
fi

# Bug #41203: Fix broken "disable-apche2-umc" preventing Apache2 from being restarted
dpkg-statoverride --quiet --remove "/usr/sbin/apache2"
chmod a+x "/usr/sbin/apache2"

# Mark all installed apps and components as installed and reinstall them
# in postup.sh if necessary

mark_app_as_installed ()
{
    previous_apps="$(ucr get update/ucs33/installedapps)"
    if [ -z "$previous_apps" ]; then
        /usr/sbin/ucr set update/ucs33/installedapps="$1" >&3 2>&3
    else
        /usr/sbin/ucr set update/ucs33/installedapps="$previous_apps $1"  >&3 2>&3
    fi
}

for app in 7i4ucs-123 7i4ucs-dokuwiki 7i4ucs-svn 7i4ucs-trac 7i4ucs-wordpress \
	agorumcore-pro agorumcore-ucs agorumcore-ucs-schema \
	asterisk4ucs-testasterisk asterisk4ucs-udm asterisk4ucs-udm-schema asterisk4ucs-umc-deploy \
	asterisk4ucs-umc-music asterisk4ucs-umc-user \
	audriga-groupware-migration digitec-sugarcrm-web digitec-sugarcrm-zip-ce \
	drbd-meta-pkg edyou kivitendo kix4otrs-meta-6 kolab-admin kolabsys-kolab2 \
	linotp-ucs noctua owncloud owncloud-meta-5.0 owncloud-meta-6.0 owncloud-schema \
	plucs plucs-schema python-univention-directory-manager-ucc sesam-srv tine20-ucs \
	ucc-management-integration ucc-server ucs-school-umc-installer univention-ad-connector \
	univention-bacula-enterprise univention-bareos univention-bareos-schema \
	univention-corporate-client-schema univention-demoapp univention-fetchmail \
	univention-fetchmail-schema univention-icinga univention-kde univention-klms \
	univention-mail-horde univention-mail-server univention-management-console-module-adtakeover \
	univention-nagios-server univention-openvpn-master univention-openvpn-schema \
	univention-openvpn-server univention-ox-dependencies-master univention-ox-meta-singleserver \
	univention-ox-text univention-pkgdb univention-printserver univention-printquota \
	univention-printserver-pdf ucs-school-ucc-integration ucs-school-umc-printermoderation univention-pulse \
	univention-radius univention-s4-connector univention-samba univention-samba4 \
	univention-saml univention-saml-schema univention-squid univention-virtual-machine-manager-daemon \
	univention-virtual-machine-manager-node-kvm univention-xrdp zarafa4ucs zarafa4ucs-udm z-push
do
	case "$(dpkg-query -W -f '${Status}' $app 2>/dev/null)" in
	install*) mark_app_as_installed "$app";;
	esac
done


# Pre-upgrade
preups=""
$update_commands_update >&3 2>&3
for pkg in $preups; do
	if dpkg -l "$pkg" 2>&3 | grep ^ii  >&3 ; then
		echo -n "Starting pre-upgrade of $pkg: "
		$update_commands_install "$pkg" >&3 2>&3
		if [ ! $? = 0 ]; then
			echo "failed."
			echo "ERROR: Failed to upgrade $pkg."
			exit 1
		fi
		echo "done."
	fi
done

echo "** Starting: apt-get -s -o Debug::pkgProblemResolver=yes dist-upgrade" >&3 2>&3
apt-get -s -o Debug::pkgProblemResolver=yes dist-upgrade >&3 2>&3

echo ""
echo "Starting update process, this may take a while."
echo "Check /var/log/univention/updater.log for more information."
date >&3
trap - EXIT

exit 0
