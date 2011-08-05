#!/usr/bin/python2.6
# -*- coding: utf-8 -*-
#
# Univention Management Console
#  module: manages UDM modules
#
# Copyright 2011 Univention GmbH
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

import operator
import threading

from univention.management.console import Translation

import univention.admin as udm
import univention.admin.modules as udm_modules
import univention.admin.objects as udm_objects
import univention.admin.uldap as udm_uldap
import univention.admin.syntax as udm_syntax
import univention.admin.uexceptions as udm_errors

from ...config import ucr
from ...log import MODULE

from .syntax import widget, default_value

_ = Translation( 'univention-management-console-modules-udm' ).translate

# global LDAP connection
_ldap_connection = None
_ldap_position = udm_uldap.position( ucr.get( 'ldap/base' ) )

udm_modules.update()

# exceptions
class UDM_Error( Exception ):
	pass

# module cache
class UDM_ModuleCache( dict ):
	lock = threading.Lock()

	def get( self, name, template_object = None ):
		UDM_ModuleCache.lock.acquire()
		if name in self:
			UDM_ModuleCache.lock.release()
			return self[ name ]

		self[ name ] = udm_modules.get( name )
		if self[ name ] is None:
			UDM_ModuleCache.lock.release()
			return None

		lo, po = get_ldap_connection()
		udm_modules.init( lo, po, self[ name ], template_object )
		UDM_ModuleCache.lock.release()

		return self[ name ]

_module_cache = UDM_ModuleCache()


def get_ldap_connection():
	"""Tries to open an LDAP connection. On DC master and DC backup
	systems the cn=admin account is used and on all other system roles
	the machine account.

	return: ( <LDAP connection>, <LDAP position> )
	"""
	global _ldap_connection, _ldap_position

	if _ldap_connection is not None:
		return _ldap_connection, _ldap_position

	if ucr.get( 'server/role' ) in ( 'domaincontroller_master', 'domaincontroller_backup' ):
		_ldap_connection, _ldap_position = udm_uldap.getAdminConnection()
	else:
		_ldap_connection, _ldap_position = udm_uldap.getMachineConnection()

	return _ldap_connection, _ldap_position

class UDM_Module( object ):
	"""Wraps UDM modules to provie a simple access to the properties and functions"""

	def __init__( self, module ):
		"""Initializes the object"""
		self.load( module )

	def load( self, module, template_object = None ):
		"""Tries to load an UDM module with the given name. Optional a
		template object is passed to the init function of the module. As
		the initialisation of a module is expensive the function uses a
		cache to ensure that each module is just initialized once."""
		global _module_cache

		self.module = _module_cache.get( module )

	def get_default_values( self, property_name ):
		"""Depending on the syntax of the given property a default
		search pattern/value is returned"""
		MODULE.info( 'Searching for property %s' % property_name )
		for key, prop in getattr( self.module, 'property_descriptions', {} ).items():
			if key == property_name:
				return default_value( prop.syntax )

	def create( self, ldap_object, container = None, superordinate = None ):
		"""Creates a LDAP object"""
		lo, po = get_ldap_connection()

		if container is not None:
			try:
				po.setDn( container )
			except udm_errors.noObject, e:
				raise UMC_CommandError( str( e ) )

		if superordinate is not None:
			mod = get_module( self.name, superordinate )
			if mod is not None:
				MODULE.info( 'Found UDM module for superordinate' )
				superordinate = mod.get( superordinate )
			else:
				raise UMC_OptionTypeError( _( 'Could not find an UDM module for the superordinate object %s' ) % superordinate )

		obj = self.module.object( None, lo, po, superordinate = superordinate )
		try:
			obj.open()
			MODULE.info( 'Creating object with properties: %s' % ldap_object )
			for key, value in ldap_object.items():
				obj[ key ] = value
			obj.create()
		except udm_errors.base, e:
			raise UDM_Error( e.message, obj.dn )

		return obj.dn

	def remove( self, ldap_dn ):
		"""Removes a LDAP object"""
		lo, po = get_ldap_connection()

		obj = self.module.object( None, lo, po, dn = ldap_dn )
		try:
			obj.open()
			MODULE.info( 'Removing object with properties: %s' % ldap_dn )
			obj.remove()
		except udm_errors.base, e:
			raise UDM_Error( str( e ) )

	def modify( self, ldap_object ):
		"""Modifies a LDAP object"""
		lo, po = get_ldap_connection()

		obj = self.module.object( None, lo, po, dn = ldap_object.get( 'ldap-dn' ) )
		del ldap_object[ 'ldap-dn' ]
		try:
			obj.open()
			MODULE.info( 'Modifying object with properties: %s' % ldap_object )
			for key, value in ldap_object.items():
				obj[ key ] = value
			obj.modify()
		except udm_errors.base, e:
			raise UDM_Error( e.message )

	def search( self, container = None, attribute = None, value = None, superordinate = None, scope = 'sub' ):
		"""Searches for LDAP objects based on a search pattern"""
		lo, po = get_ldap_connection()
		if container == 'all':
			container = po.getBase()
		elif container is None:
			container = ''
		if attribute is None:
			filter_s = ''
		else:
			filter_s = '%s=%s' % ( attribute, value )

		MODULE.info( 'Searching for LDAP objects: container = %s, filter = %s, superordinate = %s' % ( container, filter_s, superordinate ) )
		try:
			return self.module.lookup( None, lo, filter_s, base = container, superordinate = superordinate, scope = scope )
		except udm_errors.base, e:
			raise UDM_Error( str( e ) )

	def get( self, ldap_dn = None, superordinate = None ):
		"""Retrieves details for a given LDAP object"""
		lo, po = get_ldap_connection()
		if ldap_dn is not None:
			obj = self.module.object( None, lo, None, ldap_dn, superordinate )
			obj.open()
		else:
			obj = self.module.object( None, lo, None, '', superordinate )

		return obj

	def get_property( self, property_name ):
		"""Returns details for a given property"""
		return getattr( self.module, 'property_descriptions', {} ).get( property_name, None )

	@property
	def name( self ):
		"""Internal name of the UDM module"""
		return self.module is not None and self.module.module

	@property
	def title( self ):
		"""Descriptive name of the UDM module"""
		return getattr( self.module, 'short_description', self.module.module )

	@property
	def description( self ):
		"""Descriptive text of the UDM module"""
		return getattr( self.module, 'long_description', '' )

	@property
	def identifies( self ):
		"""Property of the UDM module that identifies objects of this type"""
		for key, prop in getattr( self.module, 'property_descriptions', {} ).items():
			if prop.identifies:
				MODULE.info( 'The property %s identifies to module objects %s' % ( key, self.name ) )
				return key
		return None

	@property
	def childs( self ):
		return bool( getattr( self.module, 'childs', False ) )

	@property
	def child_modules( self ):
		"""List of child modules"""
		if self.module is None:
			return None
		MODULE.info( 'Collecting child modules ...' )
		children = getattr( self.module, 'childmodules', None )
		if children is None:
			MODULE.info( 'No child modules were found' )
			return []
		modules = []
		for child in children:
			mod = udm_modules.get( child )
			if not mod:
				continue
			MODULE.info( 'Found module %s' % str( mod ) )
			modules.append( { 'id' : child, 'label' : getattr( mod, 'short_description', child ) } )
		return modules

	@property
	def layout( self ):
		"""Layout information"""
		layout = getattr( self.module, 'layout', [] )
		if not layout:
			return layout

		if isinstance( layout[ 0 ], udm.tab ):
			return self._parse_old_layout( layout )

		return layout

	def _parse_old_layout( self, layout ):
		"""Parses old layout information"""
		tabs = []
		for tab in layout:
			data = { 'name' : tab.short_description, 'description' : tab.long_description, 'advanced' : tab.advanced, 'layout' : [ { 'name' : 'General', 'description' : 'General settings', 'layout' : [] } ] }
			for item in tab.fields:
				line = []
				for field in item:
					if isinstance( field, ( list, tuple ) ):
						elem = [ x.property for x in field ]
					else:
						elem = field.property
					line.append( elem )
				data[ 'layout' ][ 0 ][ 'layout' ].append( line )
			tabs.append( data )
		return tabs

	@property
	def password_properties( self ):
		"""All properties with the syntax class passwd or userPasswd"""
		passwords = []
		for key, prop in getattr( self.module, 'property_descriptions', {} ).items():
			if prop.syntax in ( udm_syntax.passwd, udm_syntax.userPasswd ):
				passwords.append( key )

		return passwords

	@property
	def properties( self ):
		"""All properties of the UDM module"""
		props = [ { 'id' : 'ldap-dn', 'type' : 'HiddenInput', 'label' : '', 'searchable' : False } ]
		for key, prop in getattr( self.module, 'property_descriptions', {} ).items():
			if key == 'filler': continue
			if hasattr( prop.syntax, '__name__' ):
				syntax_name = prop.syntax.__name__
			elif hasattr( prop.syntax, '__class__' ):
				syntax_name = prop.syntax.__class__.__name__
			else:
				syntax_name = getattr( 'name', prop, None )
			item = { 'id' : key, 'label' : prop.short_description, 'description' : prop.long_description, 'syntax' : syntax_name,
					 'required' : bool( prop.required ), 'editable' : bool( prop.may_change ),
					 'options' : prop.options, 'searchable' : not prop.dontsearch, 'multivalue' : bool( prop.multivalue ) }

			# default value
			if prop.base_default is not None:
				if isinstance( prop.base_default, ( list, tuple ) ):
					if prop.multivalue and prop.base_default and isinstance( prop.base_default[ 0 ], ( list, tuple ) ):
						item[ 'default' ] = prop.base_default
					else:
						item[ 'default' ] = prop.base_default[ 0 ]
				else:
					item[ 'default' ] = str( prop.base_default )

			# read UCR configuration
			item.update( widget( prop.syntax ) )
			props.append( item )
		props.sort( key = operator.itemgetter( 'label' ) )
		return props

	@property
	def options( self ):
		"""List of defined options"""
		opts = []
		for key, option in getattr( self.module, 'options', {} ).items():
			item = { 'id' : key, 'label' : option.short_description, 'default' : option.default }
			opts.append( item )
		opts.sort( key = operator.itemgetter( 'label' ) )
		return opts

	@property
	def operations( self ):
		"""Allowed operations of the UDM module"""
		return self.module is not None and getattr( self.module, 'operations', None )

	@property
	def template( self ):
		"""List of UDM module names of templates"""
		return getattr( self.module, 'template', None )

	@property
	def containers( self ):
		"""List of LDAP DNs of default containers"""
		containers = getattr( self.module, 'default_containers', [] )
		ldap_base = ucr.get( 'ldap/base' )

		return map( lambda x: { 'id' : x + ldap_base, 'label' : ldap_dn2path( x + ldap_base ) }, containers )

	@property
	def superordinate( self ):
		return getattr( self.module, 'superordinate', None )

	@property
	def superordinates( self ):
		"""List of superordinates"""
		modules = getattr( self.module, 'wizardsuperordinates', [] )
		superordinates = []
		for mod in modules:
			if mod == 'None':
				superordinates.append( { 'id' : mod, 'label' : _( 'None' ) } )
			else:
				module = UDM_Module( mod )
				if module:
					for obj in module.search():
						superordinates.append( { 'id' : obj.dn, 'label' : '%s: %s' % ( module.title, obj[ module.identifies ] ) } )

		return superordinates

	@property
	def policies( self ):
		"""Searches in all policy objects for the given object type and
		returns a list of all matching policy types"""

		policies = []
		for policy in udm_modules.policyTypes( self.name ):
			module = UDM_Module( policy )
			policies.append( { 'objectType' : policy, 'label' : module.title, 'description' : module.description } )

		return policies

	def types4superordinate( self, flavor, superordinate ):
		"""List of object types for the given superordinate"""
		types = getattr( self.module, 'wizardtypesforsuper' )
		typelist = []

		if superordinate == 'None':
			module_name = superordinate
		else:
			module = get_module( flavor, superordinate )
			if not module:
				return typelist
			module_name = module.name

		if isinstance( types, dict ) and module_name in types:
			for mod in types[ module_name ]:
				module = UDM_Module( mod )
				if module:
					typelist.append( { 'id' : mod, 'label' : module.title } )

		return typelist

class UDM_Settings( object ):
	"""Provides access to different kinds of settings regarding UDM"""

	def __init__( self, username ):
		"""Reads the policies for the current user"""
		lo, po = get_ldap_connection()
		self.user_dn = lo.searchDn( 'uid=%s' % username, unique = True )
		if self.user_dn:
			self.user_dn = self.user_dn[ 0 ]
			self.policies = lo.getPolicies( self.user_dn )

		directories = udm_modules.lookup( 'settings/directory', None, lo, scope = 'sub' )
		if not directories:
			self.directory = None
		else:
			self.directory = directories[ 0 ]

	def containers( self, module_name ):
		"""Returns list of default containers for a given UDM module"""
		base, name = split_module_name( module_name )

		return map( lambda x: { 'id' : x, 'label' : ldap_dn2path( x ) }, self.directory.info.get( base, [] ) )

	def resultColumns( self, module_name ):
		pass

def split_module_name( module_name ):
	"""Splits a module name into category and internal name"""

	if module_name.find( '/' ) < 0:
		return []
	parts = module_name.split( '/', 1 )
	if len( parts ) == 2:
		return parts

	return ( None, None )

def ldap_dn2path( ldap_dn ):
	"""Returns a path representation of an LDAP DN"""

	ldap_base = ucr.get( 'ldap/base' )
	if ldap_base is None or not ldap_dn.endswith( ldap_base ):
		return ldap_dn
	rdn = ldap_dn[ : -1 * len( ldap_base ) ]
	path = []
	for item in ldap_base.split( ',' ):
		if not item: continue
		dummy, value = item.split( '=', 1 )
		path.insert( 0, value )
	path = [ '.'.join( path ) + ':', ]
	if rdn:
		for item in rdn.split( ',' )[ : -1 ]:
			if not item: continue
			dummy, value = item.split( '=', 1 )
			path.insert( 1, value )
	else:
		path.append('')
	return '/'.join( path )

def get_module( flavor, ldap_dn ):
	"""Determines an UDM module handling the LDAP object identified by the given LDAP DN"""
	if flavor is None or flavor == 'navigation':
		base = None
	else:
		base, name = split_module_name( flavor )
	lo, po = get_ldap_connection()
	modules = udm_modules.objectType( None, lo, ldap_dn, module_base = base )

	if not modules:
		return None

	return UDM_Module( modules[ 0 ] )

def list_objects( container ):
	"""Returns a list of UDM objects"""
	lo, po = get_ldap_connection()
	try:
		result = lo.searchDn( base = container, scope = 'one' )
	except udm_errors.base, e:
		raise UDM_Error( str( e ) )
	objects = []
	for dn in result:
		modules = udm_modules.objectType( None, lo, dn )
		if not modules:
			MODULE.warn( 'Could not identify LDAP object %s' % dn )
			continue
		module = UDM_Module( modules[ 0 ] )
		if module.superordinate:
			so_module = UDM_Module( module.superordinate )
			so_obj = so_module.get( container )
			objects.append( ( module, module.get( dn, so_obj ) ) )
		else:
			objects.append( ( module, module.get( dn ) ) )

	return objects

def read_syntax_choices( syntax_name ):
	if syntax_name not in udm_syntax.__dict__:
		return None

	syn = udm_syntax.__dict__[ syntax_name ]

	if hasattr( syn, 'udm_module' ):
		MODULE.info( 'Found syntax class %s with udm_module attribute (= %s)' % ( syntax_name, syn.udm_module ) )
		module = UDM_Module( syn.udm_module )
		if module is None:
			syn.choices = ()
			return
		MODULE.info( 'Found syntax %s with udm_module property' % syntax_name )
		syn.choices = map( lambda obj: ( obj.dn, obj[ module.identifies ] ), module.search() )
		MODULE.info( 'Set choices to %s' % syn.choices )
	elif issubclass( syn, udm_syntax.ldapDn ) and hasattr( syn, 'searchFilter' ):
		lo, po = get_ldap_connection()
		try:
			result = lo.searchDn( filter = syn.searchFilter )
		except udm_errors.base, e:
			MODULE.error( 'Failed to initialize syntax class %s' % syntax_name )
			return
		syn.choices = []
		for dn in result:
			dn_list = lo.explodeDn( dn )
			syn.choices.append( ( dn, dn_list[ 0 ].split( '=', 1 )[ 1 ] ) )

	return getattr( syn, 'choices', [] )

def init_syntax():
	"""Initialize all syntax classes

	Syntax classes based on select: If a property udm_module is
	available the choices attribute of the class is set to a list of all
	available modules of the specified UDM module.
	"""
	MODULE.info( 'Scanning syntax classes ...' )
	for name, syn in udm_syntax.__dict__.items():
		if type( syn ) is not type:
			continue
		read_syntax_choices( name )
