#!/usr/bin/python2.7
# -*- coding: utf-8 -*-
#
# Univention Common Python Library
#  Connections to remote UMC Servers
#
# Copyright 2013-2016 Univention GmbH
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

from httplib import HTTPSConnection, HTTPException
from json import loads, dumps
from socket import error as SocketError

from univention.config_registry import ConfigRegistry
ucr = ConfigRegistry()
ucr.load()


class UMCConnection(object):

	def __init__(self, host, username=None, password=None, error_handler=None):
		self._host = host
		self._headers = {
			'Content-Type': 'application/json; charset=UTF-8',
			'Accept': 'application/json; q=1, text/html; q=0.5; */*; q=0.1',
			'X-Requested-With': 'XMLHttpRequest',
		}
		self._base_uri = '/univention/'
		self._error_handler = error_handler
		if username is not None:
			self.auth(username, password)

	def get_connection(self):
		'''Creates a new HTTPSConnection to the host'''
		# once keep-alive is over, the socket closes
		#   so create a new connection on every request
		return HTTPSConnection(self._host)

	@classmethod
	def get_machine_connection(cls, error_handler=None):
		'''Creates a connection with the credentials of the local host
		to the DC Master'''
		username = '%s$' % ucr.get('hostname')
		password = ''
		try:
			with open('/etc/machine.secret') as machine_file:
				password = machine_file.readline().strip()
		except (OSError, IOError) as e:
			if error_handler:
				error_handler('Could not read /etc/machine.secret: %s' % e)
		try:
			connection = cls(ucr.get('ldap/master'))
			connection.auth(username, password)
			return connection
		except (HTTPException, SocketError) as e:
			if error_handler:
				error_handler('Could not connect to UMC on %s: %s' % (ucr.get('ldap/master'), e))
		return None

	def auth(self, username, password, auth_type=None):
		'''Tries to authenticate against the host and preserves the
		cookie. Has to be done only once (but keep in mind that the
		session probably expires after 10 minutes of inactivity)'''
		data = self.build_data({'username': username, 'password': password, 'auth_type': auth_type})
		try:
			response = None
			response = self.__request('POST', 'auth', data, headers=self._headers)
			cookie = response.getheader('set-cookie')
			if cookie is None:
				raise ValueError('No cookie')
			self._headers['Cookie'] = cookie  # FIXME: transform Set-Cookie to Cookie
		except Exception as exc:
			raise
			err = (exc if response is None else response.read())
			if self._error_handler:
				self._error_handler(str(exc))
			error_message = '%s: Authentication failed: %s' % (self._host, err)
			raise HTTPException(error_message)

	def build_data(self, data, flavor=None):
		'''Returns a dictionary as expected by the UMC Server'''
		data = {'options': data}
		if flavor:
			data['flavor'] = flavor
		return dumps(data)

	def request(self, url, data=None, flavor=None, command='command'):
		'''Sends a request and returns the data from the response. url
		as in the XML file of that UMC module.
		command may be anything that UMCP understands, especially:
		 * command (default)
		 * get (and url could be 'ucr' then)
		 * set (and url would be '' and data could be {'locale':'de_DE'})
		 * upload (url could be 'udm/license/import')
		'''
		if data is None:
			data = {}
		data = self.build_data(data, flavor)
		path = command
		if url:
			path = '%s/%s' % (command, url)
		response = self.__request('POST', path, data, headers=self._headers)
		if response.status != 200:
			error_message = '%s on %s (%s): %s' % (response.status, self._host, url, response.read())
			if response.status == 403:
				# 403 is either command is unknown
				#   or command is known but forbidden
				if self._error_handler:
					self._error_handler(error_message)
				raise NotImplementedError('command forbidden: %s' % url)
			raise HTTPException(error_message)
		content = response.read()
		content = loads(content)  # FIXME: inspect Content-Type response header
		if isinstance(content, dict):
			return content.get('result', content)
		return content

	def __request(self, method, path, data, headers):
		uri = '%s%s' % (self._base_uri, path)
		con = self.get_connection()
		con.request(method, uri, data, headers=headers)
		response = con.getresponse()
		if response.status == 404:
			if self._base_uri == '/univention/':
				# UCS 4.0
				self._base_uri = '/univention-management-console/'
				return self.__request(method, path, data, headers)
			elif self._base_uri == '/univention-management-console/':
				# UCS 3.X
				self._base_uri = '/umcp/'
				return self.__request(method, path, data, headers)
		return response
