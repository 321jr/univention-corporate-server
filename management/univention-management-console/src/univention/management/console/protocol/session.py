#!/usr/bin/python2.6
# -*- coding: utf-8 -*-
#
# Univention Management Console
#  session handling
#
# Copyright 2006-2011 Univention GmbH
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

import ldap
import locale
import os
import string
import sys
import time

import notifier
import notifier.signals as signals
import notifier.popen as popen

from OpenSSL import *

import univention.uldap

from .message import Response, Request
from .client import Client
from .version import VERSION
from .definitions import *

from ..resources import moduleManager, syntaxManager, categoryManager
from ..verify import SyntaxVerificationError
from ..auth import AuthHandler
from ..acl import ConsoleACLs
from ..locales import Translation, LocaleNotFound
from ..log import CORE
from ..config import MODULE_INACTIVITY_TIMER, MODULE_DEBUG_LEVEL, MODULE_COMMAND, ucr

class State( signals.Provider ):
	'''Holds information about the state of an active session'''
	def __init__( self, client, socket ):
		signals.Provider.__init__( self )
		self.__auth = AuthHandler()
		self.__auth.signal_connect( 'authenticated', self._authenticated )
		self.client = client
		self.socket = socket
		self.processor = None
		self.authenticated = False
		self.buffer = ''
		self.requests = {}
		self.authResponse = None
		self.signal_new( 'authenticated' )
		self.resend_queue = []
		self.running = False

	def __del__( self ):
		CORE.info( 'The session is shutting down' )
		del self.processor

	def _authenticated( self, success ):
		self.signal_emit( 'authenticated', success, self )

	def authenticate( self, username, password ):
		self.__auth.authenticate( username, password )

	def credentials( self ):
		return self.__auth.credentials()


class ModuleProcess( Client ):
	def __init__( self, module, debug = '0', locale = None ):
		socket = '/var/run/univention-management-console/%u-%lu.socket' % ( os.getpid(), long( time.time() * 1000 ) )
		# determine locale settings
		args = [ MODULE_COMMAND, '-m', module, '-s', socket, '-d', str( debug ) ]
		if locale:
			args.extend( ( '-l', '%s' % locale ) )
			self.__locale = locale
		else:
			self.__locale = None
		Client.__init__( self, unix = socket, ssl = False, auth = False )
		self.signal_connect( 'response', self._response )
		CORE.process( 'running: %s' % args )
		self.__process = popen.RunIt( args, stdout = False )
		self.__process.signal_connect( 'finished', self._died )
		self.__pid = self.__process.start()
		self._connect_retries = 1
		self.signal_new( 'result' )
		self.signal_new( 'finished' )
		self.name = module
		self.running = False
		self._queued_requests = []
		self._inactivity_timer = None

	def __del__( self ):
		CORE.process( 'ModuleProcess: dying' )
		self.disconnect()
		self.__process.stop()
		CORE.process( 'ModuleProcess: child stopped' )

	def _died( self, pid, status ):
		CORE.process( 'ModuleProcess: child died' )
		self.signal_emit( 'finished', pid, status, self.name )

	def _response( self, msg ):
		# these responses must not be send to the external client as
		# this commands were generated within the server
		if msg.command == 'SET' and 'commands/permitted' in msg.arguments:
			return
		if msg.command == 'exit' and 'internal' in msg.arguments:
			return

		self.signal_emit( 'result', msg )

	def pid( self ):
		return self.__pid

class Processor( signals.Provider ):
	'''Implements a proxy and command handler. It handles all internal
	UMCP commands and passes the commands for a module to the
	subprocess.'''

	def __init__( self, username, password ):
		self.__username = username
		self.__password = password
		signals.Provider.__init__( self )
		self.core_i18n = Translation( 'univention-management-console' )
		self.i18n = I18N_Manager()
		self.i18n[ 'umc-core' ] = I18N()

		# stores the module processes [ modulename ] = <>
		self.__processes = {}
		self.__locale = None
		self.__sessionid = None

		self.__killtimer = {}

		lo = ldap.open( ucr[ 'ldap/server/name' ], int( ucr.get( 'ldap/server/port', 389 ) ) )

		try:
			userdn = lo.search_s( ucr[ 'ldap/base' ], ldap.SCOPE_SUBTREE,
								  '(&(objectClass=person)(uid=%s))' % self.__username )[ 0 ][ 0 ]

			self.lo = univention.uldap.access( host = ucr[ 'ldap/server/name' ],
											   base = ucr[ 'ldap/base' ], binddn = userdn,
											   bindpw = self.__password, start_tls = 2 )
		except:
			self.lo = None

		# read the ACLs
		self.acls = ConsoleACLs( self.lo, self.__username, ucr[ 'ldap/base' ] )
		self.__command_list = moduleManager.permitted_commands( ucr[ 'hostname' ], self.acls )

		self.signal_new( 'response' )


	def __del__( self ):
		CORE.process( 'Processor: dying' )
		for process in self.__processes.values():
			del process

	def get_module_name( self, command ):
		return moduleManager.module_providing( self.__comand_list, command )

	def request( self, msg ):
		CORE.info( 'Incoming request of type: %s' % msg.command )
		if msg.command == 'EXIT':
			self.handle_request_exit( msg )
		elif msg.command == 'GET':
			self.handle_request_get( msg )
		elif msg.command == 'SET':
			self.handle_request_set( msg )
		elif msg.command == 'VERSION':
			self.handle_request_version( msg )
		elif msg.command == 'COMMAND':
			self.handle_request_command( msg )
		elif msg.command in ( 'STATUS', 'CANCEL', 'CLOSE' ):
			self.handle_request_unknown( msg )
		else:
			self.handle_request_unknown( msg )

	def _purge_child(self, module_name):
		if module_name in self.__processes:
			CORE.process( 'module %s is still running - purging module out of memory' % module_name)
			pid = self.__processes[ module_name ].pid()
			os.kill(pid, 9)
		return False

	def handle_request_exit( self, msg ):
		if len( msg.arguments ) < 1:
			return self.handle_request_unknown( msg )

		module_name = msg.arguments[ 0 ]
		if module_name:
			if module_name in self.__processes:
				self.__processes[ module_name ].request( msg )
				CORE.info( 'Ask module %s to shutdown gracefully' % module_name )
				# added timer to kill away module after 3000ms
				cb = notifier.Callback( self._purge_child, module_name )
				self.__killtimer[ module_name ] = notifier.timer_add( 3000, cb )
			else:
				CORE.info( 'Got EXIT request for a non-existing module %s' % module_name )

	def handle_request_version( self, msg ):
		res = Response( msg )
		res.status = SUCCESS # Ok
		res.body[ 'version' ] = VERSION

		self.signal_emit( 'response', res )

	def handle_request_get( self, msg ):
		res = Response( msg )

		if 'modules/list' in msg.arguments:
			modules = []
			for id, module in self.__command_list.items():
				# check for translation
				if module.flavors:
					for flavor in module.flavors:
						modules.append( { 'id' : id, 'flavor' : flavor.id, 'name' : self.i18n._( flavor.name, id ), 'description' : self.i18n._( flavor.description, id ), 'icon' : flavor.icon, 'categories' : module.categories } )
				else:
						modules.append( { 'id' : id, 'name' : self.i18n._( module.name, id ), 'description' : self.i18n._( module.description, id ), 'icon' : module.icon, 'categories' : module.categories } )
			res.body[ 'modules' ] = modules
			res.body[ 'categories' ] = map( lambda x: { 'id' : x[ 'id' ], 'name' : self.i18n._( x[ 'name' ] ) }, categoryManager.all() )
			CORE.info( 'Modules: %s' % modules )
			CORE.info( 'Categories: %s' % str( res.body[ 'categories' ] ) )
			res.status = SUCCESS # Ok

		elif 'categories/list' in msg.arguments:
			res.body[ 'categories' ] = categoryManager.all()
			res.status = SUCCESS # Ok
		elif 'syntax/verification' in msg.arguments:
			syntax_name = msg.options.get( 'syntax' )
			value = msg.options.get( 'value' )
			if not value or not syntax_name:
				res.status = BAD_REQUEST_INVALID_OPTS
			else:
				res.status = SUCCESS
				try:
					syntaxManager.verify( syntax_name, value )
					res.result = True
				except SyntaxVerificationError, e:
					res.result = False
					res.message = str( e )
		else:
			res.status = BAD_REQUEST_INVALID_ARGS

		self.signal_emit( 'response', res )

	def handle_request_set( self, msg ):
		res = Response( msg )
		if len( msg.arguments ):
			res.status = BAD_REQUEST_INVALID_ARGS
			res.message = status_description( res.status )

			self.signal_emit( 'response', res )
			return

		res.status = SUCCESS
		res.message = status_description( res.status )
		for key, value in msg.options.items():
			if key == 'locale':
				self.__locale = value
				try:
					self.core_i18n.set_language( value )
					self.i18n.set_locale( value )
				except I18N_Error, e:
					res.status = BAD_REQUEST_UNAVAILABLE_LOCALE
					res.message = status_description( res.status )
					CORE.warn( 'Setting locale: specified locale is not available (%s)' % self.__locale )
					break
			elif key == 'sessionid':
				self.__sessionid = value
			else:
				res.status = BAD_REQUEST_INVALID_OPTS
				res.message = status_description( res.status )
				break

		self.signal_emit( 'response', res )

	def __is_command_known( self, msg ):
		# only one command?
		command = None
		if len( msg.arguments ) > 0:
			command = msg.arguments[ 0 ]

		module_name = moduleManager.module_providing( self.__command_list, command )
		if not module_name:
			res = Response( msg )
			res.status = BAD_REQUEST_FORBIDDEN
			res.message = status_description( res.status )
			self.signal_emit( 'response', res )
			return None

		return module_name

	def reset_inactivity_timer( self, module ):
		if module._inactivity_timer is not None:
			notifier.timer_remove( module._inactivity_timer )

		module._inactivity_timer = notifier.timer_add( MODULE_INACTIVITY_TIMER, notifier.Callback( self._mod_inactive, module ) )

	def handle_request_command( self, msg ):
		module_name = self.__is_command_known( msg )
		if module_name and msg.arguments:
			if not self.acls.is_command_allowed( msg.arguments[ 0 ], options = msg.options ):
				response = Response( msg )
				response.status = BAD_REQUEST_NOT_ALLOWED
				response.message = status_description( response.status )
				self.signal_emit( 'response', response )
				return
			if not module_name in self.__processes:
				CORE.info( 'Starting new module process and passing new request to module %s: %s' % (module_name, str(msg._id)) )
				mod_proc = ModuleProcess( module_name, debug = MODULE_DEBUG_LEVEL, locale = self.__locale )
				mod_proc.signal_connect( 'result', self._mod_result )
				cb = notifier.Callback( self._socket_died, module_name, msg )
				mod_proc.signal_connect( 'closed', cb )
				cb = notifier.Callback( self._mod_died, msg )
				mod_proc.signal_connect( 'finished', cb )
				self.__processes[ module_name ] = mod_proc
				cb = notifier.Callback( self._mod_connect, mod_proc, msg )
				notifier.timer_add( 50, cb )
			else:
				proc = self.__processes[ module_name ]
				if proc.running:
					CORE.info( 'Passing new request to running module %s' % module_name )
					proc.request( msg )
					self.reset_inactivity_timer( proc )
				else:
					CORE.info( 'Queuing incoming request for module %s that is not yet ready to receive' % module_name )
					proc._queued_requests.append( msg )

	def _mod_connect( self, mod, msg ):
		if not mod.connect():
			CORE.info( 'No connection to module process yet' )
			if mod._connect_retries > 200:
				CORE.info( 'Connection to module %s process failed' % mod.name )
				# inform client
				res = Response( msg )
				res.status = SERVER_ERR_MODULE_FAILED # error connecting to module process
				res.message = status_description( res.status )
				self.signal_emit( 'response', res )
				# cleanup module
				mod.signal_disconnect( 'closed', notifier.Callback( self._socket_died ) )
				mod.signal_disconnect( 'result', notifier.Callback( self._mod_result ) )
				mod.signal_disconnect( 'finished', notifier.Callback( self._mod_died ) )
				if mod.name in self.__processes:
					del self.__processes[ mod.name ]
			else:
				mod._connect_retries += 1
				return True
		else:
			CORE.info( 'Connected to new module process')
			mod.running = True

			# send acls, commands, credentials, locale
			options = {
				'acls' : self.acls.json(),
				'commands' : self.__command_list[ mod.name ].json(),
				'credentials' : { 'username' : self.__username, 'password' : self.__password },
				}
			if self.__locale is not None:
				options[ 'locale' ] = self.__locale

			# WARNING! This debug message contains credentials!!!
			# CORE.info( 'Initialize module process: %s' % options )

			req = Request( 'SET', options = options )
			mod.request( req )

			# send first command
			mod.request( msg )

			# send queued request that were received during start procedure
			for req in mod._queued_requests:
				mod.request( req )
			mod._queued_requests = []

			# watch the module's activity and kill it after X seconds inactivity
			self.reset_inactivity_timer( mod )

		return False

	def _mod_inactive( self, module ):
		CORE.info( 'The module %s is inactive for to long. Sending EXIT request to module' % module.name )
		if module.openRequests:
			CORE.info( 'There are unfinished requests. Waiting ...: %s' % module.openRequests )
			return True

		# mark as internal so the response will not be send to the client
		req = Request( 'EXIT', arguments = [ module.name, 'internal' ] )
		self.handle_request_exit( req )

		return False

	def _mod_result( self, msg ):
		self.signal_emit( 'response', msg )

	def _socket_died( self, module_name, msg):
		CORE.warn( 'Socket died (module=%s)' % module_name )
		res = Response( msg )
		res.status = SERVER_ERR_MODULE_DIED
		if module_name in self.__processes:
			self._mod_died( self.__processes[ module_name ].pid(), 1, module_name, msg )

	def _mod_died( self, pid, status, name, msg ):
		if status:
			CORE.warn( 'Module process died (pid: %d, status: %s)' % ( pid, str( status ) ) )
			res = Response( msg )
			res.status = SERVER_ERR_MODULE_DIED
		else:
			CORE.info( 'Module process died on purpose' )

		if name in self.__processes:
			CORE.warn( 'module process died: cleaning up requests')
			self.__processes[ name ].invalidate_all_requests()
		# if killtimer has been set then remove it
		if name in self.__killtimer:
			CORE.info( 'module process died: stopping killtimer of "%s"' % name )
			notifier.timer_remove( self.__killtimer[ name ] )
			del self.__killtimer[ name ]
		if name in self.__processes:
			del self.__processes[ name ]

	def handle_request_unknown( self, msg ):
		res = Response( msg )
		res.status = BAD_REQUEST_NOT_FOUND
		res.message = status_description( res.status )

		self.signal_emit( 'response', res )

if __name__ == '__main__':
	processor = Processor( 'Administrator', 'univention' )
	processor.handle_request_get ( None )
