# -*- coding: utf-8 -*-
#
# Univention Directory Manager Modules
#  direcory manager module for LDAP ACL extensions
#
# Copyright 2013-2014 Univention GmbH
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

import os

from univention.admin.layout import Tab, Group
import univention.admin.filter
import univention.admin.handlers
import univention.admin.password
import univention.admin.allocators
import univention.admin.localization

translation=univention.admin.localization.translation('univention.admin.handlers.settings')
_=translation.translate

OC = "univentionLDAPExtensionACL"

module='settings/ldapacl'
childs=0
operations=['add','edit','remove','search','move']
short_description=_('Settings: LDAP ACL Extension')
long_description=''
options={}
property_descriptions={
	'name': univention.admin.property(
	        short_description=_('ACL name'),
			long_description='',
			syntax=univention.admin.syntax.TextArea,
			multivalue=0,
			include_in_default_search=1,
			options=[],
			required=1,
			may_change=1,
			identifies=1
			),
	'filename': univention.admin.property(
			short_description=_('ACL file name'),
			long_description='',
			syntax=univention.admin.syntax.BaseFilename,
			multivalue=0,
			options=[],
			required=1,
			may_change=1,
			default = '',
			identifies=0
			),
	'acl': univention.admin.property(
			short_description=_('ACL data'),
			long_description='',
			syntax=univention.admin.syntax.GzipBase64Upload,
			multivalue=0,
			options=[],
			required=1,
			may_change=1,
			identifies=0
		),
	'active': univention.admin.property(
			short_description=_('Active'),
			long_description='',
			syntax=univention.admin.syntax.TrueFalseUp,
			default = 'FALSE',
			multivalue=0,
			options=[],
			required=0,
			may_change=1,
			identifies=0
		),
	'appidentifier': univention.admin.property(
			short_description=_('App identifier'),
			long_description='',
			syntax=univention.admin.syntax.TextArea,
			multivalue=0,
			options=[],
			required=0,
			may_change=1,
			identifies=0
		),
	'package': univention.admin.property(
			short_description=_('Software package'),
			long_description='',
			syntax=univention.admin.syntax.TextArea,
			multivalue=0,
			options=[],
			required=0,
			may_change=1,
			identifies=0
		),
	'packageversion': univention.admin.property(
			short_description=_('Software package version'),
			long_description='',
			syntax=univention.admin.syntax.TextArea,
			multivalue=0,
			options=[],
			required=0,
			may_change=1,
			identifies=0
		),
	'ucsversionstart': univention.admin.property(
			short_description=_('Minimal UCS version'),
			long_description='',
			syntax=univention.admin.syntax.TextArea,
			multivalue=0,
			options=[],
			required=0,
			may_change=1,
			identifies=0
		),
	'ucsversionend': univention.admin.property(
			short_description=_('Maximal UCS version'),
			long_description='',
			syntax=univention.admin.syntax.TextArea,
			multivalue=0,
			options=[],
			required=0,
			may_change=1,
			identifies=0
		),
	}

layout = [
	Tab(_('General'),_('Basic values'), layout = [
		Group( _( 'General' ), layout = [
			["name"],
			["filename"],
		] ),
		Group(_( 'ACL' ), layout = [
			["acl"]
		] ),
		Group( _( 'Registered by' ), layout = [
			["appidentifier"],
		] ),
		Group( _( 'Package Information' ), layout = [
			["package"],
			["packageversion"],
		] ),
		Group( _( 'UCS Version Dependencies' ), layout = [
			["ucsversionstart"],
			["ucsversionend"],
		] ),
		Group( _( 'Activated' ), layout = [
			["active"],
		] ),
	] ),
]

mapping=univention.admin.mapping.mapping()
mapping.register('name', 'cn', None, univention.admin.mapping.ListToString)
mapping.register('filename', 'univentionLDAPACLFilename', None, univention.admin.mapping.ListToString)
mapping.register('acl', 'univentionLDAPACLData', univention.admin.mapping.mapBase64, univention.admin.mapping.unmapBase64)
mapping.register('package', 'univentionLDAPExtensionPackage', None, univention.admin.mapping.ListToString)
mapping.register('packageversion', 'univentionLDAPExtensionPackageVersion', None, univention.admin.mapping.ListToString)
mapping.register('appidentifier', 'univentionAppIdentifier', None, univention.admin.mapping.ListToString)
mapping.register('active', 'univentionLDAPACLActive', None, univention.admin.mapping.ListToString)
mapping.register('ucsversionstart', 'univentionUCSVersionStart', None, univention.admin.mapping.ListToString)
mapping.register('ucsversionend', 'univentionUCSVersionEnd', None, univention.admin.mapping.ListToString)

class object(univention.admin.handlers.simpleLdap):
	module=module

	def __init__(self, co, lo, position, dn='', superordinate=None, attributes = [] ):
		global mapping
		global property_descriptions

		self.mapping=mapping
		self.descriptions=property_descriptions
 		self.options=[]

		self.alloc=[]

		univention.admin.handlers.simpleLdap.__init__(self, co, lo,  position, dn, superordinate, attributes = attributes )

	def open(self):
		univention.admin.handlers.simpleLdap.open(self)

	def _ldap_pre_create(self):		
		self.dn='cn=%s,%s' % ( mapping.mapValue('name', self.info['name']), self.position.getDn())

	def _ldap_addlist(self):
		ocs=['top', OC]		

		return [
			('objectClass', ocs),
		]

def lookup(co, lo, filter_s, base='', superordinate=None, scope='sub', unique=0, required=0, timeout=-1, sizelimit=0):

	filter=univention.admin.filter.conjunction('&', [
		univention.admin.filter.expression('objectClass', OC),
		])

	if filter_s:
		filter_p=univention.admin.filter.parse(filter_s)
		univention.admin.filter.walk(filter_p, univention.admin.mapping.mapRewrite, arg=mapping)
		filter.expressions.append(filter_p)

	res=[]
	for dn, attrs in lo.search(unicode(filter), base, scope, [], unique, required, timeout, sizelimit):
		res.append( object( co, lo, None, dn, attributes = attrs ) )
	return res

def identify(dn, attr, canonical=0):
	
	return OC in attr.get('objectClass', [])

