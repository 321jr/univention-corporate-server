#!/usr/bin/python2.4
# -*- coding: utf-8 -*-
#
# Univention Management Console
#  module: manages quota support for locale hard drives
#
# Copyright 2006-2010 Univention GmbH
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

import univention.management.console as umc
import univention.management.console.handlers as umch
import univention.management.console.dialog as umcd
import univention.management.console.tools as umct
import univention.management.console.protocol as umcp

import univention_baseconfig

import notifier.popen
import notifier.threads

import df
import fstab
import mtab
import tools
import partition
import user

import _revamp
import _types

import univention.debug as ud

_ = umc.Translation( 'univention.management.console.handlers.quota' ).translate

icon = 'quota/module'
short_description = _( 'Filesystem quotas' )
long_description = _( 'Set, unset and modify filesystem quota' )
categories = [ 'all' ]

command_description = {
	'quota/list': umch.command(
		short_description = _( 'List partitions' ),
		long_description = _( 'List available partitions' ),
		method = 'quota_list',
		values = {},
		startup = True,
		priority = 100
	),
	'quota/partition/show': umch.command(
		short_description = _( 'Show partition' ),
		long_description = _( 'Show details to one selected partition'),
		method = 'quota_partition_show',
		values = { 'partition' : _types.partition },
	),
	'quota/partition/activate': umch.command(
		short_description = _( 'Activate quota support' ),
		long_description = _( 'Activate quota support for a partition' ),
		method = 'quota_partition_activate',
		values = { 'partition' : _types.partition },
	),
	'quota/partition/deactivate': umch.command(
		short_description = _( 'Deactivate quota support' ),
		long_description = _( 'Deactivate quota support for a partition' ),
		method = 'quota_partition_deactivate',
		values = { 'partition' : _types.partition },
	),
	'quota/user/set': umch.command(
		short_description = _( 'Set/modify user settings' ),
		long_description = _( 'Modify quota settings for a user' ),
		method = 'quota_user_set',
		values = { 'user' : _types.user,
				   'partition' : _types.partition,
				   'block_soft' : _types.bsoft,
				   'block_hard' : _types.bhard,
				   'file_soft' : _types.fsoft,
				   'file_hard' : _types.fhard },
	),
	'quota/user/remove': umch.command(
		short_description = _( "Delete user's quota settings" ),
		long_description = _( "Delete the user's quota settings for a specific partition" ),
		method = 'quota_user_remove',
		values = { 'user' : _types.user,
				   'partition' : _types.partition },
	),
	'quota/user/show': umch.command(
		short_description = _( 'User settings' ),
		long_description = _( 'Show detailed quota information for a user' ),
		method = 'quota_user_show',
		values = { 'user' : _types.user,
				   'partition' : _types.partition },
	),
}

class Partition( object ):
	def __init__( self, params, quota_written, quota_used, mounted, size, free ):
		self.params = params
		self.quota_written = quota_written
		self.quota_used = quota_used
		self.mounted = mounted
		self.size = size
		self.free = free

class handler( umch.simpleHandler, _revamp.Web, partition.Commands,
			   user.Commands ):
	def __init__( self ):
		global command_description
		umch.simpleHandler.__init__( self, command_description )
		_revamp.Web.__init__( self )
		partition.Commands.__init__( self )
		user.Commands.__init__( self )

	def quota_list( self, object ):
		fs = fstab.File()
		mt = mtab.File()
		partitions = fs.get( [ 'xfs', 'ext3', 'ext2' ], False )

		result = []

		for part in partitions:
			mounted = mt.get( part.spec )
			written = ( 'usrquota' in part.options )
			if mounted:
				info = df.DeviceInfo( part.mount_point )
				size = tools.block2byte( info.size(), 1 )
				free = tools.block2byte( info.free(), 1 )
				used = ( 'usrquota' in mounted.options )
				ud.debug( ud.ADMIN, ud.INFO, "%s: used: %s, written: %s" % ( part.mount_point, used, written ) )
			else:
				size = '-'
				free = '-'
			result.append( Partition( part, written, used, mounted, size, free ) )

		self.finished( object.id(), result )
