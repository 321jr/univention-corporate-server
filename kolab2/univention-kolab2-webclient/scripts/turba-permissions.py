#!/usr/bin/python2.4
# -*- coding: utf-8 -*-
#
# Univention Kolab2 Webclient
#  set turba permissions
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

import pg

secret = open( '/etc/horde.secret', 'r' )
password = secret.readlines()[ 0 ][ : -1 ]
secret.close()

db = pg.connect( dbname = 'horde', user = 'horde', passwd = password )

def get_next_id( ):
	try:
		global db
		result = db.query('select last_value,increment_by from horde_datatree_seq;').dictresult()
		return result[-1][ 'last_value' ] + result[-1][ 'increment_by' ]
	except:
		return 100

id1 = get_next_id( )
db.query( "INSERT INTO horde_datatree ( datatree_id, group_uid, user_uid,datatree_name, datatree_parents, datatree_data, datatree_serialized ) VALUES ( '"+str(id1)+"', 'horde.perms', 'administrator', 'turba', '', 'a:2:{s:4:\"type\";s:6:\"matrix\";s:7:\"default\";i:30;}', '15' );" )
id2 = id1 + 1
db.query( "INSERT INTO horde_datatree ( datatree_id, group_uid, user_uid,datatree_name, datatree_parents, datatree_data, datatree_serialized ) VALUES ( '"+str(id2)+"', 'horde.perms', 'administrator', 'sources', ':"+ str( id1 ) +"', 'a:2:{s:4:\"type\";s:6:\"matrix\";s:7:\"default\";i:30;}', '15' );" )
id3 = id1 + 2
db.query( "INSERT INTO horde_datatree ( datatree_id, group_uid, user_uid,datatree_name, datatree_parents, datatree_data, datatree_serialized ) VALUES ( '"+str(id3)+"', 'horde.perms', 'administrator', 'kolab_global', '"+ str( id1 ) +":"+ str( id2 ) +"', 'a:2:{s:4:\"type\";s:6:\"matrix\";s:7:\"default\";i:6;}', '15' );" )


