# -*- coding: utf-8 -*-
#
# Univention Configuration Registry
#  config registry module for the network interfaces
#
# Copyright (C) 2004-2010 Univention GmbH
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

def interface(var):
	if var.startswith('interfaces/') and not var.endswith( 'handler' ):
		return var.split('/')[1].replace('_', ':')
	return None

def stop_iface(iface):
	if iface:
		os.system('ifdown %s >/dev/null 2>&1' % iface)

def start_iface(iface):
	if iface:
		os.system('ifup %s' % iface)

def point2point(old, new, netmask):
	if netmask == "255.255.255.255":
		os.system('ip route del %s' % old)
		if new:
			os.system('ip route add %s/32 dev eth0 ' % new)

def restore_gateway(gateway, netmask):
	if type ( gateway ) == type ( () ):
		old, new = gateway
		if new:
			point2point(old, new, netmask)
			os.system('route del default >/dev/null 2>&1')
			os.system('route add default gw %s' % new)
   		else:
			point2point(old, False, netmask)
			os.system('route del default >/dev/null 2>&1')
	else:
		if gateway:
			point2point(gateway, gateway, netmask)
			os.system('route del default >/dev/null 2>&1')
			os.system('route add default gw %s' % gateway)

def preinst(baseConfig, changes):
	for iface in set(changes):
		if baseConfig.has_key(iface):
			stop_iface(interface(iface))

def postinst(baseConfig, changes):
	for iface in set(changes):
		if baseConfig.has_key(iface):
			start_iface(interface(iface))
	if 'gateway' in set(changes) or 'interfaces/eth0/netmask' in set(changes):
		if 'gateway' in set(changes):
			restore_gateway(changes['gateway'], baseConfig.get("interfaces/eth0/netmask", False))
		else:
			restore_gateway(baseConfig.get("gateway", False), baseConfig.get("interfaces/eth0/netmask", False))
