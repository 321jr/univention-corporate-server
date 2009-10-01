# -*- coding: utf-8 -*-
#
# Univention Directory Reports
#  write an interpreted token structure to a file
#
# Copyright (C) 2007 Univention GmbH
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

import univention.admin.uldap as ua_ldap
import univention.admin.objects as ua_objects
import univention.admin.modules as ua_modules
import univention.admin.mapping as ua_mapping
import univention.admin.syntax as ua_syntax
import univention.admin.config as ua_config

import univention_baseconfig as ub

import univention.debug as ud

import re
from locales import *
from filter import *

__all__ = [ 'connect', 'get_object', 'cache_object', 'connected', 'identify', 'set_format' ]

_admin = None

class AdminConnection( object ):
	def __init__( self, userdn = None, password = None, host = 'localhost', base = None, start_tls = 2, access = None, format = True ):
		self._cached = {}
		self._modules = {}
		self._policies = {}
		self._format = format
		self._bc = ub.baseConfig()
		self._bc.load()
		if not base:
			self._base = self._bc[ 'ldap/base' ]
		else:
			self._base = base
		self._position = ua_ldap.position( self._base )
		if access:
			self._access = access
		else:
			self._access = ua_ldap.access(  host = host, base = self._base,
											binddn = userdn, bindpw = password, start_tls = start_tls )
		self._config = ua_config.config( host = host )

	def cache_object( self, obj ):
		return self.get_object( ua_objects.module( obj ), obj.dn )

	def clear_cache( self ):
		del self._cached
		self._cached = {}

	def get_object( self, module, dn ):
		if self._cached.has_key( dn ):
			return self._cached[ dn ]
		if isinstance( module, basestring ):
			if self._modules.has_key( module ):
				module = self._modules[ module ]
			else:
				name = module
				module = ua_modules.get( name )
				ua_modules.init( self._access, self._position, module )
				self._modules[ name ] = module
		elif module == None:
			module = self.identify( dn )
			if not module:
				return None
			ua_modules.init( self._access, self._position, module )
		new = ua_objects.get( module, self._config, self._access, position = self._position, dn = dn )
		# if the object is not valid it should be displayed as an empty object
		try:
			new.open()
		except Exception, e:
			# write the traceback in the logfile
			import traceback
			
			ud.debug( ud.ADMIN, ud.ERROR, 'The object %s could not be opened' % dn )
			try:
				tb = traceback.format_exc().encode( 'ascii', 'replace' ).replace( '%', '?' )
				# this might fail because of problems with univention.debug
				ud.debug( ud.ADMIN, ud.ERROR, 'Traceback: %s' % tb )
			except:
				pass
		for key, value in new.items():
			if self._format:
				i, j = self.format_property( new.descriptions, key, value )
				new.info[ i ] = j
			else:
				new.info[ key ] = value

		self._get_policies( new )
		self._cached[ dn ] = new

		return new

	def identify( self, dn ):
		res = self._access.search( base = dn, scope = 'base' )
		if res:
			mods = ua_modules.identify( dn, res[ 0 ][ 1 ] )
			if mods:
				return mods[ 0 ]
		return None

	def format_property( self, props, key, value ):
		prop = props.get( key, None )

		def texClean(string):
			string = string.replace('€', "EUR")
			string = string.replace('"', "''")
			string = string.replace('\\', '$\\backslash$')
			for c in '&%#_{}':
				string = string.replace(c, '\\%s' % c)
			string = string.replace('~', '\\textasciitilde{}')
			string = string.replace('^', '\\^{\,}')

			# following regular expression replaces $ with \$ if and only if
			# - no leading $\backslash exists and    ==> prevents replacement of the second $ character
			# - it does not match $\backslash$       ==> prevents replacement of the first $ character
			string = re.sub(r'(?<![$]\\backslash)(?![$]\\backslash[$])[$]', '\\$', string)

			string = string.replace('°', '$^{\\circ}$')

			return string

		if not prop:
			return ( key, value )
		else:
			if isinstance( value, ( list, tuple ) ):
				result = []
				for v in value:
					if type(v) == type([]) or type(v) == type(()):
						for i in v:
							result.append(texClean(str(i)))
					else:
						result.append(texClean(str(v)))
				value = result
			elif value:
				value = texClean(value)
			filter = filter_get( prop.syntax )
			if filter:
				return filter( prop, key, value )

		return ( key, value )

	def _get_policies( self, obj ):
		dict={}
		policies = self._access.getPolicies( obj.dn )
		for policy_oc, attrs in policies.items():
			module_name = ua_objects.ocToType( policy_oc )
			module = ua_modules.get( module_name )
			if not module:
				continue
			for attr_name, value_dict in attrs.items():
				dict[attr_name]=value_dict[ 'value' ]

			for key, value in ua_mapping.mapDict( module.mapping, dict ).items():
				if self._format:
					i, j = self.format_property( module.property_descriptions, key, value )
					obj.info[ i ] = j
				else:
					obj.info[ key ] = value



def connect( userdn = None, password = None, host = 'localhost', base = None, start_tls = 2, access = None ):
	global _admin
	if _admin:
		return
	_admin = AdminConnection( userdn, password, host, base, start_tls, access )

def cache_object( obj ):
	global _admin
	if not _admin:
		return None
	return _admin.cache_object( obj )

def clear_cache():
	global _admin
	if not _admin:
		return
	_admin.clear_cache()

def get_object( module, dn ):
	global _admin
	if not _admin:
		return None
	return _admin.get_object( module, dn )

def set_format( format ):
	global _admin
	if _admin:
		_admin._format = format

def identify( dn ):
	global _admin
	return _admin.identfy( dn )

def connected():
	global _admin
	return _admin != None
