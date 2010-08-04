#!/usr/bin/python
# -*- coding: utf-8 -*-
#
# Univention Virtual Machine Manager Daemon
#  UVMM commands
#
# Copyright 2010 Univention GmbH
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
"""UVMM commands

This module implements parsing the protocol packets, checking parameters for
validity and invoking the real implementation.
"""
import copy

import protocol
import node
import storage
import logging
from helpers import TranslatableException, N_ as _

logger = logging.getLogger('uvmmd.command')

class CommandError(TranslatableException):
	"""Signal error during command execution."""
	def __init__(self, command, e, **kv):
		kv['command'] = command
		TranslatableException.__init__(self, e, kv)

class _Commands:
	@staticmethod
	def NODE_ADD(server, request):
		"""Add node to watch list."""
		if not isinstance(request.uri, basestring):
			raise CommandError('NODE_ADD', _('uri != string: %(uri)s'), uri=request.uri)
		logger.debug('NODE_ADD %s' % (request.uri,))

		try:
			node.node_add(request.uri)
		except node.NodeError, e:
			raise CommandError('NODE_ADD', e)

	@staticmethod
	def NODE_REMOVE(server, request):
		"""Remove node from watch list."""
		if not isinstance(request.uri, basestring):
			raise CommandError('NODE_REMOVE', _('uri != string: %(uri)s'), uri=request.uri)
		logger.debug('NODE_REMOVE %s' % (request.uri,))

		try:
			node.node_remove(request.uri)
		except node.NodeError, e:
			raise CommandError('NODE_REMOVE', e)

	@staticmethod
	def NODE_QUERY(server, request):
		"""Get domain and storage-pool information from node."""
		if not isinstance(request.uri, basestring):
			raise CommandError('NODE_QUERY', _('uri != string: %(uri)s'), uri=request.uri)
		logger.debug('NODE_QUERY %s' % (request.uri,))

		try:
			local_data = node.node_query(request.uri)
			if local_data is None:
				raise CommandError('NODE_QUERY', _('unknown node %(uri)s'), uri=request.uri)
			if local_data.conn is None:
				raise CommandError('NODE_QUERY', _('Node %(uri)s is not available'), uri=request.uri)

			pkg_data = copy.copy(local_data.pd)
			pkg_data.domains = [d.pd for d in local_data.domains.values()]

			res = protocol.Response_DUMP()
			res.data = pkg_data
			return res
		except node.NodeError, e:
			raise CommandError('NODE_QUERY', e)

	@staticmethod
	def NODE_FREQUENCY(server, request):
		"""Set polling interval for node."""
		try:
			hz = int(request.hz)
		except TypeError:
			raise CommandError('NODE_FREQUENCY', _('hz != int: %(hz)s'), hz=request.hz)
		if request.uri != None and not isinstance(request.uri, basestring):
			raise CommandError('NODE_FREQUENCY', _('uri != string: %(uri)s'), uri=request.uri)
		logger.debug('NODE_FREQUENCY %d %s' % (hz,request.uri))
		try:
			node.node_frequency(hz, request.uri)
		except node.NodeError, e:
			raise CommandError('NODE_FREQUENCY', e)

	@staticmethod
	def NODE_LIST(server, request):
		"""Return list of nodes in group."""
		if not isinstance(request.group, basestring):
			raise CommandError('NODE_LIST', _('group != string: %(group)s'), group=request.group)
		logger.debug('NODE_LIST')
		try:
			res = protocol.Response_DUMP()
			res.data = node.node_list(request.group)
			return res
		except node.NodeError, e:
			raise CommandError('NODE_LIST', e)

	@staticmethod
	def GROUP_LIST(server, request):
		"""Return list of known groups."""
		logger.debug('GROUP_LIST')
		try:
			res = protocol.Response_DUMP()
			res.data = node.group_list()
			return res
		except node.NodeError, e:
			raise CommandError('GROUP_LIST', e)

	@staticmethod
	def BYE(server, request):
		"""Terminate UVMM daemon."""
		logger.debug('BYE')
		server.eos = True

	@staticmethod
	def DOMAIN_DEFINE(server, request):
		"""Define new domain on node."""
		if not isinstance(request.uri, basestring):
			raise CommandError('DOMAIN_DEFINE', _('uri != string: %(uri)s'), uri=request.uri)
		if not isinstance(request.domain, protocol.Data_Domain):
			raise CommandError('DOMAIN_DEFINE', _('definition != Domain: %(domain)s'), domain=request.domain)
		logger.debug('DOMAIN_DEFINE %s %s' % (request.uri, request.domain))
		try:
			uuid = node.domain_define(request.uri, request.domain)
			res = protocol.Response_DUMP()
			res.data = uuid
			return res
		except node.NodeError, e:
			raise CommandError('DOMAIN_DEFINE', e)

	@staticmethod
	def DOMAIN_STATE(server, request):
		"""Change running state of domain on node."""
		if not isinstance(request.uri, basestring):
			raise CommandError('DOMAIN_STATE', _('uri != string: %(uri)s'), uri=request.uri)
		if not isinstance(request.domain, basestring):
			raise CommandError('DOMAIN_STATE', _('domain != string: %(domain)s'), domain=request.domain)
		if not request.state in ('RUN', 'PAUSE', 'SHUTDOWN', 'RESTART'):
			raise CommandError('DOMAIN_STATE', _('unsupported state: %(state)s'), state=request.state)
		logger.debug('DOMAIN_STATE %s#%s %s' % (request.uri, request.domain, request.state))
		try:
			node.domain_state(request.uri, request.domain, request.state)
		except node.NodeError, e:
			raise CommandError('DOMAIN_STATE', e)

	@staticmethod
	def DOMAIN_SAVE(server, request):
		"""Save defined domain."""
		if not isinstance(request.uri, basestring):
			raise CommandError('DOMAIN_SAVE', _('uri != string: %(uri)s'), uri=request.uri)
		if not isinstance(request.domain, basestring):
			raise CommandError('DOMAIN_SAVE', _('domain != string: %(domain)s'), domain=request.domain)
		if not isinstance(request.statefile, basestring):
			raise CommandError('DOMAIN_SAVE', _('statefile != string: %(file)s'), file=request.statefile)
		logger.debug('DOMAIN_SAVE %s#%s %s' % (request.uri, request.domain, request.statefile))
		try:
			node.domain_save(request.uri, request.domain, request.statefile)
		except node.NodeError, e:
			raise CommandError('DOMAIN_SAVE', e)

	@staticmethod
	def DOMAIN_RESTORE(server, request):
		"""Restore defined domain."""
		if not isinstance(request.uri, basestring):
			raise CommandError('DOMAIN_RESTORE', _('uri != string: %(uri)s'), uri=request.uri)
		if not isinstance(request.domain, basestring):
			raise CommandError('DOMAIN_RESTORE', _('domain != string: %(domain)s'), domain=request.domain)
		if not isinstance(request.statefile, basestring):
			raise CommandError('DOMAIN_RESTORE', _('statefile != string: %(file)s'), file=request.statefile)
		logger.debug('DOMAIN_RESTORE %s %s' % (request.uri, request.statefile))
		try:
			node.domain_restore(request.uri, request.domain, request.statefile)
		except node.NodeError, e:
			raise CommandError('DOMAIN_RESTORE', e)

	@staticmethod
	def DOMAIN_UNDEFINE(server, request):
		"""Undefine a domain on a node."""
		if not isinstance(request.uri, basestring):
			raise CommandError('DOMAIN_UNDEFINE', _('uri != string: %(uri)s'), uri=request.uri)
		if not isinstance(request.domain, basestring):
			raise CommandError('DOMAIN_UNDEFINE', _('domain != string: %(domain)s'), domain=request.domain)
		if not isinstance(request.volumes, (list, tuple)):
			raise CommandError('DOMAIN_UNDEFINE', _('volumes != list: %(volumes)s'), volumes=request.volumes)
		for vol in request.volumes:
			if not isinstance(vol, basestring):
				raise CommandError('DOMAIN_UNDEFINE', _('volumes[] != string: %(volume)s'), volume=vol)
		logger.debug('DOMAIN_UNDEFINE %s#%s [%s]' % (request.uri, request.domain, ','.join(request.volumes)))
		try:
			node.domain_undefine(request.uri, request.domain, request.volumes)
		except node.NodeError, e:
			raise CommandError('DOMAIN_UNDEFINE', e)

	@staticmethod
	def DOMAIN_MIGRATE(server, request):
		"""Migrate a domain from node to the target node."""
		if not isinstance(request.uri, basestring):
			raise CommandError('DOMAIN_MIGRATE', _('uri != string: %(uri)s'), uri=request.uri)
		if not isinstance(request.domain, basestring):
			raise CommandError('DOMAIN_MIGRATE', _('domain != string: %(domain)s'), domain=request.domain)
		if not isinstance(request.target_uri, basestring):
			raise CommandError('DOMAIN_MIGRATE', _('target_uri != string: %(uri)s'), uri=request.target_uri)
		logger.debug('DOMAIN_MIGRATE %s#%s %s' % (request.uri, request.domain, request.target_uri))
		try:
			node.domain_migrate(request.uri, request.domain, request.target_uri)
		except node.NodeError, e:
			raise CommandError('DOMAIN_MIGRATE', e)

	@staticmethod
	def STORAGE_POOLS(server, request):
		"""List all pools."""
		if not isinstance(request.uri, basestring):
			raise CommandError('STORAGE_POOLS', _('uri != string: %(uri)s'), uri=request.uri)
		logger.debug('STORAGE_POOLS %s]' % (request.uri,))
		try:
			pools = storage.storage_pools(request.uri)
			res = protocol.Response_DUMP()
			res.data = pools
			return res
		except node.NodeError, e:
			raise CommandError('STORAGE_POOLS', e)

	@staticmethod
	def STORAGE_VOLUMES( server, request ):
		'''List all volumes in a pool.'''
		if not isinstance( request.uri, basestring ):
			raise CommandError( 'STORAGE_VOLUMES' , _( 'uri != string: %(uri)s' ), uri = request.uri )
		logger.debug('STORAGE_VOLUMES %s]' % request.uri )
		try:
			volumes = storage.get_storage_volumes( request.uri, request.pool, request.type )
			res = protocol.Response_DUMP()
			res.data = volumes
			return res
		except node.NodeError, e:
			raise CommandError( 'STORAGE_VOLUMES', e )

	@staticmethod
	def AUTHENTICATION(server, request):
		'''Handle authentication.'''
		# handled in unix.py#AuthenticatedStreamHandler
		pass

	def __getitem__(self, cmd):
		if cmd.startswith('_'):
			raise CommandError(cmd, _('Command "%(command)s" is restricted'))
		try:
			return getattr(self, cmd)
		except AttributeError, e:
			raise CommandError(cmd, _('Unknown command "%(command)s'))

commands = _Commands()
