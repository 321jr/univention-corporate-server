#!/bin/bash
#
# Copyright 2013-2017 Univention GmbH
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

basic_setup ()
{
	if grep "QEMU Virtual CPU" /proc/cpuinfo ; then
		echo "KVM detected"
		ucr set --force updater/identify="UCS (EC2 Test)"
	elif ip -4 addr show | grep -Fq 'inet 10.210.'
	then
		echo "Assuming Amazon Cloud"
		GW='10.210.216.13' MDS='169.254.169.254'
		echo "supersede routers ${GW};" >> /etc/dhcp/dhclient.conf.local
		echo "supersede rfc3442-classless-static-routes 32,${MDS//./,},0,0,0,0,0,${GW//./,};" >> /etc/dhcp/dhclient.conf.local
		ip route replace default via "$GW"  # VPN gateway
		ip route replace "$MDS" dev eth0  # EC2 meta-data service
		ucr set gateway="$GW"
		sleep 10 # just wait a few seconds to give the amazone cloud some time
		# set dns/forwarder*, this should prevent a later bind restart (Bug #39807)
		i=1; cat /etc/resolv.conf | sed -ne 's|^nameserver ||p' | while read ns; do ucr set dns/forwarder$i=$ns; i="$((i+1))"; done
		ucr set --force updater/identify="UCS (EC2 Test)"
		if grep -F /dev/vda /boot/grub/device.map && [ -b /dev/xvda ] # Bug 36256
		then
			/usr/sbin/grub-mkdevicemap
			echo set grub-pc/install_devices /dev/xvda | debconf-communicate
		fi
	fi
	ucr set update/check/cron/enabled=false update/check/boot/enabled=false
	# wait until Univention System Setup is running and profile file has been moved
	while pgrep -f "/etc/init.d/rc 2" && ! pgrep -f "startxwithfirefox" ; do
		sleep 1s
	done
	sleep 5s
	if [ -f /var/cache/univention-system-setup/profile.bak ] ; then
		mv /var/cache/univention-system-setup/profile.bak /var/cache/univention-system-setup/profile
	fi
}

rotate_logfiles () {
	test -x /usr/sbin/logrotate && logrotate -f /etc/logrotate.conf
}

jenkins_updates () {
	local version_version version_patchlevel version_erratalevel target rc=0
	target="$(echo "${JOB_NAME:-}"|sed -rne 's,.*/UCS-([0-9]+\.[0-9]+-[0-9]+)/.*,\1,p')"
	eval "$(ucr shell '^version/(version|patchlevel|erratalevel)$')"
	echo "Starting from ${version_version}-${version_patchlevel}+${version_erratalevel} to ${target}..."

	case "${release_update:-}" in
	public) upgrade_to_latest --updateto "$target" || rc=$? ;;
	testing) upgrade_to_testing --updateto "$target" || rc=$? ;;
	none|"") ;;
	*) echo "Unknown release_update='$release_update'" >&1 ; exit 1 ;;
	esac

	eval "$(ucr shell '^version/(version|patchlevel|erratalevel)$')"
	echo "Continuing from ${version_version}-${version_patchlevel}+${version_erratalevel} to ${target}..."

	case "${errata_update:-}" in
	testing) upgrade_to_latest_test_errata || rc=$? ;;
	public) upgrade_to_latest_errata || rc=$? ;;
	none|"") ;;
	*) echo "Unknown errata_update='$errata_update'" >&1 ; exit 1 ;;
	esac

	eval "$(ucr shell '^version/(version|patchlevel|erratalevel)$')"
	echo "Finished at ${version_version}-${version_patchlevel}+${version_erratalevel}"
	return $rc
}

upgrade_to_latest_patchlevel ()
{
	local updateto="$(ucr get version/version)-99"
	upgrade_to_latest --updateto "$updateto"
}

upgrade_to_latest_errata () {
	local current="$(ucr get version/version)-$(ucr get version/patchlevel)"
	upgrade_to_latest --updateto "$current"
}

upgrade_to_latest_test_errata () {
	local current prev=DUMMY rc=0
	while current="$(ucr get version/version)-$(ucr get version/patchlevel)" && [ "$current" != "$prev" ]
	do
		if [ -x /root/activate-errata-test-scope.sh ]
		then
			/root/activate-errata-test-scope.sh
		fi
		upgrade_to_latest --updateto "$current"
		rc=$?
		prev="$current"
	done
	return $rc
}

upgrade_to_testing () {

	ucr set repository/online/server=updates-test.software-univention.de
	upgrade_to_latest "$@"
}

upgrade_to_latest () {
	declare -i remain=300 rv delay=30
	while true
	do
		univention-upgrade --noninteractive --ignoreterm --ignoressh "$@"
		rv="$?"
		case "$rv" in
		0) return 0 ;;  # success
		5) delay=30 ;;  # /var/lock/univention-updater exists
		*) delay=$remain ;;  # all other errors
		esac
		echo "ERROR: univention-upgrade failed exitcode $rv"
		ps faxwww
		ucr search --brief --non-empty update/check
		[ $remain -gt 0 ] || return "$rv"
		remain+=-$delay
		sleep "$delay"  # Workaround for Bug #31561
	done
}

run_setup_join ()
{
	local srv rv=0
	/usr/lib/univention-system-setup/scripts/setup-join.sh || rv=$?
	ucr set apache2/startsite='univention/' # Bug #31682
	for srv in univention-management-console-server univention-management-console-web-server apache2
	do
		invoke-rc.d "$srv" restart
	done
	ucr unset --forced update/available
	return $rv
}

run_setup_join_on_non_master ()
{
	local admin_password="${1:-univention}"
	local srv rv=0
	ucr set nameserver1="$(sed -ne 's|^nameserver=||p' /var/cache/univention-system-setup/profile)"
	echo -n "$admin_password" >/tmp/univention
	/usr/lib/univention-system-setup/scripts/setup-join.sh --dcaccount Administrator --password_file /tmp/univention || rv=$?
	ucr set apache2/startsite='univention/' # Bug #31682
	for srv in univention-management-console-server univention-management-console-web-server apache2
	do
		invoke-rc.d "$srv" restart
	done
	ucr unset --forced update/available
	return $rv
}

wait_for_reboot ()
{
	local i=0
	while [ $i -lt 900 ]
	do
		pidof apache2 && break
		sleep 1
		i=$((i + 1))
	done
	if [ $i = 900 ]; then
		echo "WARNING: wait_for_reboot: Did not find running apache after 900 seconds"
	fi
	# Wait a little bit more otherwise other services are not available
	sleep 30
}

wait_for_replication ()
{
	local timeout=${1:-3600}
	local steps=${2:-10}
	local timestamp=$(date +"%s")
	echo "Waiting for replication..."
	while ! /usr/lib/nagios/plugins/check_univention_replication; do
		if [ $((timestamp+timeout)) -lt $(date +"%s") ]; then
			echo "ERROR: replication incomplete."
			return 1
		fi
		sleep $steps
	done
	return 0
}

switch_to_test_app_center ()
{
	ucr set repository/app_center/server=appcenter-test.software-univention.de update/secure_apt=no appcenter/index/verify=no
	if [ -x "$(which univention-app)" ]; then
		univention-install --yes univention-appcenter-dev
		univention-app dev-use-test-appcenter
		for app in $(< /var/cache/appcenter-installed.txt); do 
			if [ -n "$(univention-app get "$app" DockerImage)" ]; then
				univention-app shell "$app" univention-install -y univention-appcenter-dev
				univention-app shell "$app" univention-app dev-use-test-appcenter
			fi
		done
	fi
}

switch_components_to_test_app_center ()
{
	ucr search --brief --value appcenter.software-univention.de | \
		grep 'repository/online/component/.*/server' | \
		awk -F ':' '{print $1}' | \
		xargs -I % ucr set %=appcenter-test.software-univention.de
}

install_apps ()
{
	local app rv=0
	for app in "$@"; do echo "$app" >>/var/cache/appcenter-installed.txt; done
	for app in "$@"
	do
		latestversion="$(python -c "from univention.appcenter.app import AppManager; print AppManager.find('$app', latest=True).version")"
		username="$(ucr get tests/domainadmin/account | sed -e 's/uid=//' -e 's/,.*//')"
		if [ -n "$(univention-app get "$app=$latestversion" DockerImage)" ]; then
			if [ -z "$(ucr get "appcenter/apps/$app/status")" ]; then
				univention-app install "$app" --noninteractive --username="$username" --pwdfile="$(ucr get tests/domainadmin/pwdfile)" || rv=$?
			else
				univention-app upgrade "$app" --noninteractive --username="$username" --pwdfile="$(ucr get tests/domainadmin/pwdfile)" || rv=$?
			fi
		else
			univention-add-app -a --latest "$app" || rv=$?
			univention-run-join-scripts -dcaccount "$username" -dcpwd "$(ucr get tests/domainadmin/pwdfile)"
		fi
	done
	return $rv
}

uninstall_apps ()
{
	local app rv=0
	for app in "$@"; do echo "$app" >>/var/cache/appcenter-uninstalled.txt; done
	for app in "$@"
	do
		if [ -n "$(univention-app get "$app" DockerImage)" ]; then
			username="$(ucr get tests/domainadmin/account | sed -e 's/uid=//' -e 's/,.*//')"
			univention-app remove "$app" --noninteractive --username="$username" --pwdfile="$(ucr get tests/domainadmin/pwdfile)" || rv=$?
		else
			/root/uninstall-app.py -a "$app" || rv=$?
		fi
	done
	return $rv
}

install_apps_master_packages ()
{
	local app rv=0
	for app in "$@"
	do
		if [ -n "$(univention-app get "$app" DockerImage)" ]; then
			continue
		fi
		univention-add-app -m --latest "$app" || rv=$?
	done
	return $rv
}

install_with_unmaintained () {
	local rv=0
	ucr set repository/online/unmaintained=yes
	univention-install --yes "$@" || rv=$?
	ucr set repository/online/unmaintained=no
	return $rv
}

install_ucs_test ()
{
	install_with_unmaintained ucs-test
}

install_additional_packages ()
{
	if [ -n "$1" ]; then
		install_with_unmaintained "$@"
	fi
}

install_apps_test_packages ()
{
	local app rv=0
	ucr set repository/online/unmaintained=yes
	for app in "$@"
	do
		if [ -n "$(univention-app get $app DockerImage)" ]; then
			univention-app shell "$app" apt-get download "ucs-test-$app"
			dpkg -i /var/lib/docker/overlay/$(ucr get appcenter/apps/$app/container)/merged/ucs-test-${app}_*.deb
			univention-install -f --yes
		else
			univention-install --yes "ucs-test-$app" || rv=$?
		fi
	done
	ucr set repository/online/unmaintained=no
	return $rv
}

install_ucs_test_appcenter_uninstall ()
{
	install_with_unmaintained ucs-test-appcenter-uninstall
}

install_ucsschool ()
{
	case "${ucsschool_release:-scope}" in
		appcenter.test)
			switch_to_test_app_center
			install_apps ucsschool
			;;
		public)
			install_apps ucsschool
			;;
		scope|*)
			local component="repository/online/component/ucsschool_DEVEL"
			ucr set "$component"/description="Development version of UCS@school packages" \
				"$component"/version="$(ucr get version/version)" \
				"$component"/server=updates-test.software-univention.de \
				"$component"=enabled
			echo "install_ucsschool - DEBUG1"
			cat /etc/apt/sources.list.d/20_ucs-online-component.list
			univention-install --yes ucs-school-umc-installer
			# Ensure ucsschool is a registered app
			univention-app install ucsschool
			echo "install_ucsschool - DEBUG2"
			cat /etc/apt/sources.list.d/20_ucs-online-component.list
			;;
	esac

}

install_coverage ()
{
	install_with_unmaintained python-pip python-all-dev python-all-dbg python-setuptools python-docutils python-pkg-resources
	pip install coverage
}

remove_s4connector_tests_and_mark_tests_manual_installed ()
{
	univention-remove --yes ucs-test-s4connector
	apt-mark manual $(apt-mark showauto | grep ^ucs-test-)
}

install_ucs_windows_tools ()
{
	install_with_unmaintained ucs-windows-tools
}

run_apptests ()
{

	# some tests create domaincontroller_master objects, the listener ldap_server.py
	# sets these objects as ldap/server/name ldap/master in the docker container
	# until this is fixed, force the variables in the docker container
	for app in $(< /var/cache/appcenter-installed.txt); do
		if [ -n "$(univention-app get "$app" DockerImage)" ]; then
			univention-app shell "$app" bash -c 'eval "$(ucr shell)"; test -n "$ldap_server_name" && ucr set --force ldap/server/name="$ldap_server_name"'
			univention-app shell "$app" bash -c 'eval "$(ucr shell)"; test -n "$ldap_master" && ucr set --force ldap/master="$ldap_master"'
			univention-app shell "$app" bash -c 'eval "$(ucr shell)"; test -n "$kerberos_adminserver" && ucr set --force kerberos/adminserver="$kerberos_adminserver"'
		fi
	done

	run_tests -r apptest "$@"
}

run_minimal_apptests ()
{
	run_apptests -s checks -s appcenter "$@"
}

run_appcenter_uninstall_tests ()
{
	run_tests -s appcenter-uninstall "$@"
}

run_admember_tests ()
{
	run_tests -p skip_admember -p docker "$@"
}

run_adconnector_tests ()
{
	# Test if the failed Jenkins test are timing issues
	sed -i 's|AD_ESTIMATED_MAX_COMPUTATION_TIME=3|AD_ESTIMATED_MAX_COMPUTATION_TIME=16|' /usr/share/ucs-test/55_adconnector/adconnector.sh
	run_tests -s adconnector "$@"
}

run_win_member_gpo_tests ()
{
	run_tests -r windows_gpo_test "$@"
}

run_windows_native_client_tests ()
{
	# tests that require a native windows client in the domain
	run_tests -r native_win_client "$@"
}

run_tests ()
{
	[ ! -e /DONT_START_UCS_TEST ] && LANG=de_DE.UTF-8 ucs-test -E dangerous -F junit -l "ucs-test.log" -p producttest "$@"
}

run_tests_with_parameters() {
	local s="${test_section:-}"
	case "$s" in
	all_sections|all*) s= ;;
	esac
	ucs-test ${s:+-s "$s"} -E dangerous -F junit -l "ucs-test.log" "$@"
}

run_join_scripts ()
{
	local admin_password="${1:-univention}"

	if [ "$(ucr get server/role)" = "domaincontroller_master" ]; then
		univention-run-join-scripts
	else
 		echo -n "$admin_password" >/tmp/univention
		univention-run-join-scripts -dcaccount Administrator -dcpwd /tmp/univention
	fi
}

run_rejoin ()
{
	local admin_password="${1:-univention}"

 	echo -n "$admin_password" >/tmp/univention
	univention-join -dcaccount Administrator -dcpwd /tmp/univention
}

do_reboot () {
	reboot
}

assert_version () {
	local requested_version="$1"
	local version

	eval "$(ucr shell '^version/(version|patchlevel)$')"
	version="$version_version-$version_patchlevel"
	echo "Requested version $requested_version"
	echo "Current version $version"
	if [ "$requested_version" != "$version" ]; then
		echo "Creating /DONT_START_UCS_TEST"
		touch /DONT_START_UCS_TEST
		exit 1
	fi
}

assert_join () {
	if ! univention-check-join-status; then
		echo "Creating /DONT_START_UCS_TEST"
		touch /DONT_START_UCS_TEST
		exit 1
	fi
}

assert_adconnector_configuration () {
	if [ -z "$(ucr get connector/ad/ldap/host)" ]; then
		echo "Creating /DONT_START_UCS_TEST"
		touch /DONT_START_UCS_TEST
		exit 1
	fi
}

assert_packages () {
	local packages="$@"
	for package in $packages; do
		local installed=$(dpkg-query -W -f '${status}' "$package")
    	if [ "$installed" != "install ok installed" ]; then
			echo "Failed: package status of $package is $installed"
			echo "Creating /DONT_START_UCS_TEST"
			touch /DONT_START_UCS_TEST
			exit 1
		fi
	done
}

install_gpmc_windows ()
{
	local HOST="${1:?Missing host address}"
	local DOMAIN="${2:?Missing domain name}"
	local DOMAIN_ADMIN_ACCOUNT="${3:-administrator}"
	local DOMAIN_ADMIN_PWD=$(ucr get tests/domainadmin/pwd)
	local LOCAL_ADMIN_ACCOUNT="testadmin"
	local LOCAL_ADMIN_PWD="Univention@99"
	
	python -c "
import univention.winexe
win=univention.winexe.WinExe('$DOMAIN', '$DOMAIN_ADMIN_ACCOUNT', '$DOMAIN_ADMIN_PWD', '$LOCAL_ADMIN_ACCOUNT', '$LOCAL_ADMIN_PWD', 445, '$HOST')
win.add_gpo_management_console()
"
}

join_windows_memberserver ()
{
	local HOST="${1:?Missing host address}"
	local DOMAIN="${2:?Missing domain name}"
	local DNS_SERVER="${3:?Missing DNS server address}"
	local DOMAIN_ADMIN_ACCOUNT="${4:-administrator}"
	local DOMAIN_ADMIN_PWD=$(ucr get tests/domainadmin/pwd)
	local LOCAL_ADMIN_ACCOUNT="testadmin"
	local LOCAL_ADMIN_PWD="Univention@99"
	
	python -c "
import univention.winexe
win=univention.winexe.WinExe('$DOMAIN', '$DOMAIN_ADMIN_ACCOUNT', '$DOMAIN_ADMIN_PWD', '$LOCAL_ADMIN_ACCOUNT', '$LOCAL_ADMIN_PWD', 445, '$HOST')
win.domain_join('$DNS_SERVER')
"
}

_promote_ad ()
{
	local HOST="${1:?Missing host address}"
	local DOMAIN="${2:?Missing domain name}"
	local MODE="${3:?Missing mode}"
	local DOMAIN_ADMIN_ACCOUNT="${4:-administrator}"
	local DOMAIN_ADMIN_PWD=$(ucr get tests/domainadmin/pwd)
	local LOCAL_ADMIN_ACCOUNT="testadmin"
	local LOCAL_ADMIN_PWD="Univention@99"
	
	python -c "
import univention.winexe
win=univention.winexe.WinExe('$DOMAIN', '$DOMAIN_ADMIN_ACCOUNT', '$DOMAIN_ADMIN_PWD', '$LOCAL_ADMIN_ACCOUNT', '$LOCAL_ADMIN_PWD', 445, '$HOST')
win.promote_ad('$MODE', '$MODE')
"
}

promote_ad_w2k12r2 ()
{
	_promote_ad "$1" "$2" "Win2012R2" "$3"
}

promote_ad_w2k12 ()
{
	_promote_ad "$1" "$2" "Win2012" "$3"
}

promote_ad_w2k8r2 ()
{
	_promote_ad "$1" "$2" "Win2008R2" "$3"
}

promote_ad_w2k8 ()
{
	_promote_ad "$1" "$2" "Win2008" "$3"
}

promote_ad_w2k3r2 ()
{
	_promote_ad "$1" "$2" "Win2003R2" "$3"
}

reboot_windows_host ()
{
	local HOST="${1:?Missing host address}"
	local DOMAIN_ADMIN_ACCOUNT="${2:-administrator}"
	local DOMAIN_ADMIN_PWD=$(ucr get tests/domainadmin/pwd)
	local LOCAL_ADMIN_ACCOUNT="testadmin"
	local LOCAL_ADMIN_PWD="Univention@99"
	
	python -c "
import univention.winexe
win=univention.winexe.WinExe('dummydomain', '$DOMAIN_ADMIN_ACCOUNT', '$DOMAIN_ADMIN_PWD', '$LOCAL_ADMIN_ACCOUNT', '$LOCAL_ADMIN_PWD', 445, '$HOST')
win.reboot_remote_win_host()
"
}

shutdown_windows_host ()
{
	local HOST="${1:?Missing host address}"
	local DOMAIN_MODE="${2:-False}"
	local DOMAIN_ADMIN_ACCOUNT="${3:-administrator}"
	local DOMAIN_ADMIN_PWD=$(ucr get tests/domainadmin/pwd)
	local LOCAL_ADMIN_ACCOUNT="testadmin"
	local LOCAL_ADMIN_PWD="Univention@99"
	
	python -c "
import univention.winexe
win=univention.winexe.WinExe('dummydomain', '$DOMAIN_ADMIN_ACCOUNT', '$DOMAIN_ADMIN_PWD', '$LOCAL_ADMIN_ACCOUNT', '$LOCAL_ADMIN_PWD', 445, '$HOST')
win.shutdown_remote_win_host($DOMAIN_MODE)
"
}

set_windows_gateway ()
{
	local HOST="${1:?Missing host address}"
	local DOMAIN="${2:?Missing domain name}"
	local GATEWAY="${3:?Missing gateway address}"
	local DOMAIN_ADMIN_ACCOUNT="${4:-administrator}"
	local DOMAIN_ADMIN_PWD=$(ucr get tests/domainadmin/pwd)
	local LOCAL_ADMIN_ACCOUNT="testadmin"
	local LOCAL_ADMIN_PWD="Univention@99"
	
	python -c "
import univention.winexe
win=univention.winexe.WinExe('dummydomain', '$DOMAIN_ADMIN_ACCOUNT', '$DOMAIN_ADMIN_PWD', '$LOCAL_ADMIN_ACCOUNT', '$LOCAL_ADMIN_PWD', 445, '$HOST')
win.set_gateway('$GATEWAY')
"
}

create_ad_user_and_add_the_user_to_the_group ()
{
	local HOST="${1:?Missing host address}"
	local DOMAIN="${2:?Missing domain name}"
	local NEW_USERNAME="${3:?Missing user name}"
	local NEW_PASSWORD="${4:?Missing user password}"
	local NEW_GROUP="${5:?Missing group name}"
	local DOMAIN_ADMIN_ACCOUNT="${6:-administrator}"
	local DOMAIN_ADMIN_PWD=$(ucr get tests/domainadmin/pwd)
	local LOCAL_ADMIN_ACCOUNT="testadmin"
	local LOCAL_ADMIN_PWD="Univention@99"
	
	python -c "
import univention.winexe
win=univention.winexe.WinExe('$DOMAIN', '$DOMAIN_ADMIN_ACCOUNT', '$DOMAIN_ADMIN_PWD', '$LOCAL_ADMIN_ACCOUNT', '$LOCAL_ADMIN_PWD', 445, '$HOST')
win.create_user_and_add_to_group('$NEW_USERNAME', '$NEW_PASSWORD', '$NEW_GROUP')
"
}

set_administrator_dn_for_ucs_test ()
{
	local dn="$(univention-ldapsearch sambaSid=*-500 -LLL dn | sed -ne 's|dn: ||p')"
	ucr set tests/domainadmin/account="$dn"
}

set_administrator_password_for_ucs_test ()
{
	local password="$1"

	ucr set tests/domainadmin/pwd="$password"
	mkdir -p /var/lib/ucs-test/
	echo -n "$password" >/var/lib/ucs-test/pwdfile
}

set_windows_localadmin_password_for_ucs_test () {
	local username="$1"
	local password="$2"

	ucr set \
		tests/windows/localadmin/name="$username" \
		tests/windows/localadmin/pwd="$password"
}

monkeypatch () {
	# this function can be used to monkeypatch all UCS@school systems before running the tests

	# Bug #42658: temporary raise the connection timeout which the UMC Server waits the module process to start
	sed -i 's/if mod._connect_retries > 200:/if mod._connect_retries > 1200:/' /usr/share/pyshared/univention/management/console/protocol/session.py
	univention-management-console-server restart

	# Bug #40419: UCS@school Slave reject: LDAP sambaSID != S4 objectSID == SID(Master)
	[ "$(hostname)" = "slave300-s1" ] && /usr/share/univention-s4-connector/remove_ucs_rejected.py "cn=master300,cn=dc,cn=computers,dc=autotest300,dc=local" || true
}

# vim:set filetype=sh ts=4:
