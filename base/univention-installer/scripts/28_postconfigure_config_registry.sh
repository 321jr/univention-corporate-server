#!/bin/sh
#
# Univention Installer
#  Configure Univention Config Registry
#
# Copyright 2004-2011 Univention GmbH
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

. /tmp/installation_profile

architecture=`/bin/uname -m`

acpi_off=`grep "acpi=off" /proc/cmdline`
pci_acpi_off=`grep "pci=noacpi" /proc/cmdline`
pci_acpi_on=`grep "pci=acpi" /proc/cmdline`
grub_append=`cat /proc/cmdline | sed -e 's|.* profile||;s|.* usb||;s|.* floppy||;s|.* text||'`
version_version=`cat /instmnt/sourcedevice/.univention_install | grep VERSION | sed -e 's|VERSION=||'`
version_patchlevel=`cat /instmnt/sourcedevice/.univention_install | grep PATCHLEVEL | sed -e 's|PATCHLEVEL=||'`

if [ -n "$system_role" ]; then
	export server_role="$system_role"
fi
cat >>/instmnt/hostname.sh <<__EOT__
if [ -n "$to_scan" ] || [ -n "$scan" ]; then
	for ts in $to_scan $scan; do
		if [ "\$ts" = "hostname" ]; then
			ipcmd=\`cat /proc/cmdline | grep ip | sed -e 's/.*ip=//g'\`
			myip=\`echo \$ipcmd | awk -F ':' '{print \$1}'\`
			if [ -n "$nameserver1" ]; then
				host=\`host \$myip $nameserver1 |tail -1 | awk '{print \$5}' | awk -F '.' '{print \$1}'\`
			elif [ -n "$nameserver_1" ]; then
				host=\`host \$myip $nameserver_1 |tail -1 | awk '{print \$5}' | awk -F '.' '{print \$1}'\`
			fi
		fi
	done
fi
if [ -n "\$host" ]; then
	univention-config-registry set hostname=\$host
elif [ -n "$hostname" ]; then
	univention-config-registry set hostname=$hostname
fi
hostname \`univention-config-registry get hostname\`		# finally
__EOT__

chmod +x /instmnt/hostname.sh
chroot /instmnt ./hostname.sh

cat >>/instmnt/postconfigure_config_registry.sh <<__EOT__

univention-config-registry set domainname=$domainname
univention-config-registry set windows/domain=$windows_domain

if [ -n "$eth0_type" -a "$eth0_type" = "dynamic" ]; then
	univention-config-registry set interfaces/eth0/type=dhcp
fi
if [ -n "$eth1_type" -a "$eth1_type" = "dynamic" ]; then
	univention-config-registry set interfaces/eth1/type=dhcp
fi
if [ -n "$eth2_type" -a "$eth2_type" = "dynamic" ]; then
	univention-config-registry set interfaces/eth2/type=dhcp
fi
if [ -n "$eth3_type" -a "$eth3_type" = "dynamic" ]; then
	univention-config-registry set interfaces/eth3/type=dhcp
fi

__EOT__

for i in 0 1 2 3; do 
	for j in 0 1 2 3; do
		nettmpxzy=$(eval echo  \$eth${i}_${j}_type)
cat >>/instmnt/postconfigure_config_registry.sh <<__EOT__
if [ -n "$nettmpxzy" -a "$nettmpxzy" = "dynamic" ]; then
	univention-config-registry set interfaces/eth${i}_${j}/type=dhcp
fi
__EOT__
	done
done

cat >>/instmnt/postconfigure_config_registry.sh <<__EOT__

if [ -n "$use_external_nameserver" -a "$use_external_nameserver" = "true" ]; then
	univention-config-registry set nameserver/external=true
else
	univention-config-registry set nameserver/external=false
fi

if [ -n "$dns_forwarder_1" ]; then
	univention-config-registry set dns/forwarder1=$dns_forwarder_1
fi
if [ -n "$dns_forwarder_2" ]; then
	univention-config-registry set dns/forwarder2=$dns_forwarder_2
fi
if [ -n "$dns_forwarder_3" ]; then
	univention-config-registry set dns/forwarder3=$dns_forwarder_3
fi

if [ -n "$create_home_share" -a "$create_home_share" = "true" ]; then
	univention-config-registry set create/home/share=true
fi

# Available services in security service defs:
# smtp pop3 imap sieve kerberos krsh nfs nagios dhcp dns ftp http https ldap postgres
# samba ssh telnet tftp

if [ -n "$security_profile" -a "$security_profile" = "strict" ]; then

  univention-config-registry set security/profile="strict"

  if [ "$server_role" = "domaincontroller_master" -o "$server_role" = "domaincontroller_backup" ]; then
    univention-config-registry set security/services/smtp="disabled" security/services/pop3="disabled"
    univention-config-registry set security/services/kerberos="disabled" security/services/krsh="disabled" security/services/nfs="disabled" security/services/x11="disabled"
    univention-config-registry set security/services/imap="disabled" security/services/sieve="disabled" security/services/nagios="disabled" security/services/dhcp="disabled" 
    univention-config-registry set security/services/dns="disabled" security/services/ftp="disabled" security/services/http="disabled"
    univention-config-registry set security/services/postgres="disabled" security/services/samba="disabled"
    univention-config-registry set security/services/telnet="disabled" security/services/tftp="disabled" security/services/ipp="disabled" security/services/time="disabled" security/services/umc="disabled"
  fi


  # Right now the selection is identical to DC M/B, eventually merge later
  if [ "$server_role" = "managed_client" -o "$server_role" = "mobile_client" -o "$server_role" = "domaincontroller_slave" -o "$server_role" = "memberserver" -o "$server_role" = "basesystem" ]; then
    univention-config-registry set security/services/smtp="disabled" security/services/pop3="disabled" security/services/notifier="disabled" security/services/x11="disabled"
    univention-config-registry set security/services/kerberos="disabled" security/services/krsh="disabled" security/services/nfs="disabled" 
    univention-config-registry set security/services/imap="disabled" security/services/sieve="disabled" security/services/nagios="disabled" security/services/dhcp="disabled" 
    univention-config-registry set security/services/dns="disabled" security/services/ftp="disabled" security/services/http="disabled"
    univention-config-registry set security/services/postgres="disabled" security/services/samba="disabled"
    univention-config-registry set security/services/telnet="disabled" security/services/tftp="disabled" security/services/ipp="disabled" security/services/time="disabled" security/services/umc="disabled"
  fi

fi




if [ -n "$security_profile" -a "$security_profile" = "normal" ]; then

  univention-config-registry set security/profile="normal"

  if [ "$server_role" = "domaincontroller_master" -o "$server_role" = "domaincontroller_backup" ]; then
    univention-config-registry set security/services/telnet="disabled" security/services/ftp="disabled"
  fi

  if [ "$server_role" = "domaincontroller_slave" -o "$server_role" = "memberserver" ]; then
    univention-config-registry set security/services/telnet="disabled" security/services/ftp="disabled"
  fi

  if [ "$server_role" = "managed_client" -o "$server_role" = "mobile_client" -o "$server_role" = "basesystem" ]; then
    univention-config-registry set security/services/smtp="disabled" security/services/pop3="disabled" security/services/notifier="disabled"
    univention-config-registry set security/services/kerberos="disabled" security/services/krsh="disabled"
    univention-config-registry set security/services/imap="disabled" security/services/sieve="disabled" security/services/nagios="disabled" security/services/dhcp="disabled" 
    univention-config-registry set security/services/dns="disabled" security/services/ftp="disabled"
    univention-config-registry set security/services/ldap="disabled" security/services/postgres="disabled" security/services/samba="disabled"
    univention-config-registry set security/services/telnet="disabled" security/services/tftp="disabled"
  fi
fi   

if [ -n "$security_profile" -a "$security_profile" = "open" ]; then

  univention-config-registry set security/profile="open"
  univention-config-registry set security/packetfilter/disabled="true"

fi


if [ -n "$ldap_position" ]; then
	univention-config-registry set ldap/position="$ldap_position"
fi

if [ "$server_role" = "domaincontroller_master" ]; then
	if [ -n "$ldap_base" ]; then
		univention-config-registry set ldap/base="$ldap_base"
	fi
	univention-config-registry set ldap/server/ip=$eth0_ip \
								ldap/server/port=7389
	univention-config-registry set ldap/server/name=$hostname.$domainname
	univention-config-registry set ldap/master=$hostname.$domainname
	univention-config-registry set ldap/master/port=7389
	univention-config-registry set kerberos/adminserver=$hostname.$domainname
	univention-config-registry set server/role=domaincontroller_master
	univention-config-registry set ldap/server/type=master
else
	if [ -n "$ldap_base" ]; then
		univention-config-registry set ldap/base="$ldap_base"
	fi
	if [ -n "$domain_controller_ip" ]; then
		univention-config-registry set ldap/master/ip=$domain_controller_ip
		univention-config-registry set ldap/master/port=7389
	fi

	univention-config-registry set ldap/server/type=slave

	if [ $server_role = "domaincontroller_slave" ]; then
		univention-config-registry set server/role=domaincontroller_slave
	elif [ $server_role = "memberserver" ]; then
		univention-config-registry set server/role=memberserver
	elif [ $server_role = "managed_client" ]; then
		univention-config-registry set server/role=fatclient
	elif [ $server_role = "mobile_client" ]; then
		univention-config-registry set server/role=mobileclient
	elif [ $server_role = "domaincontroller_backup" ]; then
		univention-config-registry set server/role=domaincontroller_backup
	elif [ $server_role = "basesystem" ]; then
		univention-config-registry set server/role=basesystem
	fi
fi

# get all profile variables with leading "ssl_" and set them as UCR variables with leading "ssl/"
set | grep ^ssl_ | while read ; do 
    ucr set "$(echo $REPLY | sed -e 's,^ssl_,ssl/,')"
done

if [ -n "$acpi_off" ]; then
	univention-config-registry set "\$(univention-config-registry get grub/append) acpi=off"
fi

if [ -n "$pci_acpi_off" ]; then
	univention-config-registry set "\$(univention-config-registry get grub/append) pci=noacpi"
fi

if [ -n "$grub_append" ]; then
	univention-config-registry set grub/append="$grub_append"
fi

univention-config-registry set locale="$locales"

if [ -n "$locale_default" ]; then
	short_form=`echo $locale_default | awk -F ':' '{print $1}'`

	univention-config-registry set "locale/default"="$locale_default"

	univention-config-registry set admin/web/language="$short_form"
	univention-config-registry set console/web/language="$short_form"
	univention-config-registry set gdm/language="$locale_default"
fi

echo "$timezone" >/etc/timezone
ln -sf /usr/share/zoneinfo/$timezone /etc/localtime

mkdir -p /etc/console

univention-config-registry set locale/keymap="$keymap"
univention-config-registry set xorg/keyboard/options/XkbLayout=$(echo $keymap | sed -e 's|-.*||')

if [ -n "$ox_primary_maildomain" ] ; then
	univention-config-registry set ox/mail/domain/primary=$ox_primary_maildomain
fi

univention-config-registry set version/version=$version_version
univention-config-registry set version/patchlevel=$version_patchlevel

univention-config-registry commit

# Start syslogd
/etc/init.d/sysklogd start


__EOT__

chmod +x /instmnt/postconfigure_config_registry.sh
chroot /instmnt ./postconfigure_config_registry.sh
