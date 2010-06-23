# -*- coding: utf-8 -*-
#
# Univention Directory Listener
#  listener script for setting ldap server
#
# Copyright 2004-2010 Univention GmbH
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

import listener
import grp, string
import univention_baseconfig

import univention.debug
import univention.misc

name='ldap_server'
description='Update ldap server master list'
filter='(&(objectClass=univentionDomainController)(|(univentionServerRole=master)(univentionServerRole=backup)))'
attributes=[]

def handler(dn, new, old):

	baseConfig = univention_baseconfig.baseConfig()
	baseConfig.load()

	if baseConfig['server/role'] == 'domaincontroller_master':
		return

	listener.setuid(0)
	try:
		if new.has_key('univentionServerRole'):
			if new.has_key('associatedDomain'):
				domain=new['associatedDomain'][0]
			else:
				 domain=baseConfig['domainname']
			add_ldap_server(baseConfig, new['cn'][0], domain, new['univentionServerRole'][0])
		elif old.has_key('univentionServerRole') and not new:
			if old.has_key('associatedDomain'):
				domain=old['associatedDomain'][0]
			else:
				 domain=baseConfig['domainname']
			remove_ldap_server(baseConfig,old['cn'][0], domain, old['univentionServerRole'][0])
	finally:
		listener.unsetuid()

def add_ldap_server(baseConfig, name, domain, role):

	univention.debug.debug(univention.debug.LISTENER, univention.debug.INFO, 'LDAP_SERVER: Add ldap_server %s' % name)

	server_name="%s.%s" % (name, domain)

	if role == 'master':
		old_master=baseConfig.get('ldap/master')

		univention_baseconfig.handler_set(['ldap/master=%s' % server_name])

		if baseConfig.has_key('kerberos/adminserver') and baseConfig['kerberos/adminserver'] == old_master:
			univention_baseconfig.handler_set(['kerberos/adminserver=%s' % server_name])

		if baseConfig.has_key('ldap/server/name') and baseConfig['ldap/server/name'] == old_master:
			univention_baseconfig.handler_set(['ldap/server/name=%s' % server_name])


	if role == 'backup':
		backup_list = []
		if baseConfig.get('ldap/backup'):
			backup_list = baseConfig.get('ldap/backup','').split(' ')
		if not server_name in backup_list:
			backup_list.append(server_name)
			univention_baseconfig.handler_set(['ldap/backup=%s' % (string.join(backup_list, ' '))])

def remove_ldap_server(baseConfig, name, domain, role):

	univention.debug.debug(univention.debug.LISTENER, univention.debug.INFO, 'LDAP_SERVER: Remove ldap_server %s' % name)

	server_name="%s.%s" % (name, domain)

	if role == 'backup':
		univention_baseconfig.handler_set(['ldap/backup=%s' % string.replace(baseConfig['ldap/backup'],server_name,'').replace('  ',' ')])

