wait_for_LDAP_replication_of_domain_sambaSid () {
	local username t0 t sambaSID
	username="${1:?username}"
	t0=$(date +%Y%m%d%H%M%S)
	t=t0
	sambaSID=$(univention-ldapsearch -xLLL uid="$username" sambaSID | sed -n 's/^sambaSID: //p')
	if [ -z "${sambaSID%S-1-4*}" ]; then
		echo -n "Waiting for S4-Connector and LDAP replication of domain sambaSID for user $username (current: $sambaSID)."
		while [ -z "${sambaSID%S-1-4*}" ]; do
			if [ "$(($t-$t0))" -gt 30 ]; then
				fail_fast 1 "TIMEOUT: No domain sambaSID replicated to local LDAP after $(($t-$t0)) seconds"
			fi
			sleep 1
			echo -n "."
			sambaSID=$(univention-ldapsearch -xLLL uid="$username" sambaSID | sed -n 's/^sambaSID: //p')
			t=$(date +%Y%m%d%H%M%S)
		done
		echo
	fi
	echo "S4-Connector and LDAP replication of domain sambaSID took $(($t-$t0)) seconds"
}

wait_for_drs_replication () {
	local option ldap_filter attr t0 t output value i
	local -a opts
	OPTIND=0
	while getopts "b:s:" option; do
		case "${option}" in
			b) opts+=("-b" "${OPTARG}"); shift 2; break;;
			s) opts+=("-s" "${OPTARG}"); shift 2; break;;
			*) echo "wait_for_drs_replication [-b <base] [-s <scope>] <ldap_filter>"; return 1; break;;
		esac
	done

	ldap_filter="${1:?ldap_filter}"
	attr="${2:-dn}"
	t0=$(date +%Y%m%d%H%M%S)
	t=t0
	output=$(ldbsearch -H /var/lib/samba/private/sam.ldb "${opts[@]}" "$ldap_filter" "$attr")
	if [ $? != 0 ]; then
		fail_fast 1 "ldbsearch failed: $output"
		return 1
	fi
	value=$(sed -n "s/^$attr: //p" <<<"$output")

	i=0
	if [ -z "$value" ]; then
		echo -n "Waiting for DRS replication, filter: $ldap_filter"
		while [ -z "$value" ]; do
			if [ "$(($t-$t0))" -gt 360 ]; then
				fail_fast 1 "TIMEOUT: Replication timout to local sam.ldb after $(($t-$t0)) seconds"
			fi
			sleep 1
			echo -n "."
			output=$(ldbsearch -H /var/lib/samba/private/sam.ldb "${opts[@]}" "$ldap_filter" "$attr")
			if [ $? != 0 ]; then
				fail_fast 1 "ldbsearch failed: $output"
				return 1
			fi
			value=$(sed -n "s/^$attr: //p" <<<"$output")
			t=$(date +%Y%m%d%H%M%S)
		done
		echo
	fi
	echo "DRS replication took $(($t-$t0)) seconds"
}

force_drs_replication () {
	local direction="in" option source_dc destination_dc partition_dn
	while getopts "o" option; do
		case "${option}" in
			o) direction="out"; shift; break;;
			*) echo "force_drs_replication [-o] [<source>] [<destination>] [<partition_dn>]"; return 1; break;;
		esac
	done

	source_dc="${1:-}"
	if [ -z "$source_dc" ]; then
		s4_connector_hosts=$(univention-ldapsearch -x -b "cn=computers,$ldap_base" univentionService="S4 Connector" uid | sed -nr 's/^uid: (.*)\$$/\1/p')
		if [ "$(wc -w <<<"$s4_connector_hosts")" -eq 1 ]; then
			source_dc="$s4_connector_hosts"
		else
			echo "WARNING: Automatic S4 Connector host detection failed"
		fi
	fi
	destination_dc="${2:-$(ucr get hostname)}"
	partition_dn="${3:-$(ucr get samba4/ldap/base)}"

	hostname=$(ucr get hostname)
	if [ "$direction" = "in" ]; then
		samba-tool drs replicate "$destination_dc" "$source_dc" "$partition_dn"
	else
		samba-tool drs replicate "$source_dc" "$destination_dc" "$partition_dn"
	fi
}

# vim:set filetype=sh ts=4:
