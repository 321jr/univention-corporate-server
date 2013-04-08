#!/usr/bin/python2.6
# -*- coding: utf-8 -*-
#
# Univention Management Console
#  module: software management
#
# Copyright 2011-2013 Univention GmbH
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

# standard library
from contextlib import contextmanager
import urllib2

# related third party
#import psutil # our psutil is outdated. reenable when methods are supported
from httplib import HTTPSConnection, HTTPException
from simplejson import loads, dumps

# univention
from univention.management.console.log import MODULE
import univention.config_registry
from univention.admin.handlers.computers import domaincontroller_master
from univention.admin.handlers.computers import domaincontroller_backup


# local application
from constants import COMPONENT_BASE, COMP_PARAMS, STATUS_ICONS, DEFAULT_ICON, PUT_SUCCESS, PUT_PROCESSING_ERROR

def get_hosts(module, lo, ucr=None):
 	hosts = module.lookup(None, lo, None)
	hostnames = []
	if ucr is not None:
		local_hostname = ucr.get('hostname')
	else:
		local_hostname = None
	for host in hosts:
		host.open() # needed for fqdn. it may be enough to return 'name'
		hostname = host.info.get('name')
		if hostname == local_hostname:
			MODULE.process('%s is me. Skipping' % host.dn)
			continue
		if 'LDAP' not in host.info.get('service', []):
			MODULE.warn('%s does not provide LDAP. Skipping' % host.dn)
			continue
		if 'fqdn' not in host.info:
			MODULE.warn('%s does not have an FQDN. Skipping' % host.dn)
			continue
		hostnames.append(host.info['fqdn'])
	MODULE.process('Found hosts: %r' % hostnames)
	return hostnames

def get_master(lo):
	MODULE.process('Searching DC Master')
	return get_hosts(domaincontroller_master, lo)[0]

def get_all_backups(lo, ucr=None):
	MODULE.process('Searching DC Backup')
	return get_hosts(domaincontroller_backup, lo, ucr)

class UMCConnection(object):
	def __init__(self, host, username=None, password=None):
		self._host = host
		self._headers = {
			'Content-Type' : 'application/json; charset=UTF-8'
		}
		if username is not None:
			self.auth(username, password)

	def get_connection(self):
		# once keep-alive is over, the socket closes
		#   so create a new connection on every request
		return HTTPSConnection(self._host)

	def auth(self, username, password):
		data = self.build_data({'username' : username, 'password' : password})
		con = self.get_connection()
		try:
			con.request('POST', '/umcp/auth', data)
		except Exception as e:
			# probably unreachable
			MODULE.warn(str(e))
			error_message = '%s: Authentication failed while contacting: %s' % (self._host, e)
			raise HTTPException(error_message)
		else:
			try:
				response = con.getresponse()
				cookie = response.getheader('set-cookie')
				if cookie is None:
					raise ValueError('No cookie')
				self._headers['Cookie'] = cookie
			except Exception as e:
				MODULE.warn(str(e))
				error_message = '%s: Authentication failed: %s' % (self._host, response.read())
				raise HTTPException(error_message)

	def build_data(self, data, flavor=None):
		data = {'options' : data}
		if flavor:
			data['flavor'] = flavor
		return dumps(data)

	def request(self, url, data=None, flavor=None):
		if data is None:
			data = {}
		data = self.build_data(data, flavor)
		con = self.get_connection()
		con.request('POST', '/umcp/command/%s' % url, data, headers=self._headers)
		response = con.getresponse()
		if response.status != 200:
			error_message = '%s on %s (%s): %s' % (response.status, self._host, url, response.read())
			if response.status == 403:
				# 403 is either command is unknown
				#   or command is known but forbidden
				# as the user was allowed to invoke the same command
				# on the local host, it means that the command
				# is unknown (older app center)
				MODULE.warn(error_message)
				raise NotImplementedError
			raise HTTPException(error_message)
		content = response.read()
		return loads(content)['result']

# TODO: this should probably go into univention-lib
# and hide urllib/urllib2 completely
# i.e. it should be unnecessary to import them directly
# in a module
def install_opener(ucr):
	proxy_http = ucr.get('proxy/http')
	if proxy_http:
		proxy = urllib2.ProxyHandler({'http': proxy_http, 'https': proxy_http})
		opener = urllib2.build_opener(proxy)
		urllib2.install_opener(opener)

def urlopen(request):
	# use this in __init__ and app_center
	# to have the proxy handler installed globally
	return urllib2.urlopen(request)

def get_current_ram_available():
	''' Returns RAM currently available in MB, excluding Swap '''
	#return (psutil.avail_phymem() + psutil.phymem_buffers() + psutil.cached_phymem()) / (1024*1024) # psutil is outdated. reenable when methods are supported
	# implement here. see http://code.google.com/p/psutil/source/diff?spec=svn550&r=550&format=side&path=/trunk/psutil/_pslinux.py
	with open('/proc/meminfo', 'r') as f:
		splitlines = map(lambda line: line.split(), f.readlines())
		meminfo = dict([(line[0], int(line[1]) * 1024) for line in splitlines]) # bytes
	avail_phymem = meminfo['MemFree:']
	phymem_buffers = meminfo.get('Buffers:', 0) # OpenVZ does not have Buffers, calculation still correct, see Bug #30659
	cached_phymem = meminfo['Cached:']
	return (avail_phymem + phymem_buffers + cached_phymem) / (1024 * 1024)

def component_registered(component_id, ucr):
	''' Checks if a component is registered (enabled or disabled).
	Moved outside of ComponentManager to avoid dependencies for
	UniventionUpdater when just using Application.all() '''
	return '%s/%s' % (COMPONENT_BASE, component_id) in ucr

class Changes(object):
	def __init__(self, ucr):
		self.ucr = ucr
		self._changes = {}

	def changed(self):
		return bool(self._changes)

	def _bool_string(self, variable, value):
		"""Returns a boolean string representation for a boolean UCR variable. We need
			this as long as we don't really know that all consumers of our variables
			transparently use the ucr.is_true() method to process the values. So we
			write the strings that we think are most suitable for the given variable.

			*** NOTE *** I would like to see such function in the UCR base class
				so we could call

								ucr.set_bool(variable, boolvalue)

				and the ucr itself would know which string representation to write.
		"""
		yesno = ['no', 'yes']
		#truefalse = ['False', 'True']
		enabled = ['disabled', 'enabled']
		#enable = ['disable', 'enable']
		onoff = ['off', 'on']
		#onezero = ['0', '1']		# strings here! UCR doesn't know about integers

		# array of strings to match against the variable name, associated with the
		# corresponding bool representation to use. The first match is used.
		# 'yesno' is default if nothing matches.
		#
		# *** NOTE *** Currently these strings are matched as substrings, not regexp.

		setup = [
			['repository/online/component', enabled],
			['repository/online', onoff]
		]

		intval = int(bool(value))			# speak C:  intval = value ? 1 : 0;

		for s in setup:
			if s[0] in variable:
				return s[1][intval]
		return yesno[intval]

	def set_registry_var(self, name, value):
		""" Sets a registry variable and tracks changedness in a private variable.
			This enables the set_save_commit_load() method to commit the files being affected
			by the changes we have made.

			Function handles boolean values properly.
		"""
		try:
			oldval = self.ucr.get(name, '')
			if isinstance(value, bool):
				value = self._bool_string(name, value)

			# Don't do anything if the value being set is the same as
			# the value already found.
			if value == oldval:
				return

			# Possibly useful: if the value is the empty string -> try to unset this variable.
			# FIXME Someone please confirm that there are no UCR variables that need
			#		to be set to an empty string!
			if value == '':
				if name in self.ucr:
					MODULE.info("Deleting registry variable '%s'" % name)
					del self.ucr[name]
			else:
				MODULE.info("Setting registry variable '%s' = '%s'" % (name, value))
				self.ucr[name] = value
			self._changes[name] = (oldval, value)
		except Exception as e:
			MODULE.warn("set_registry_var('%s', '%s') ERROR %s" % (name, value, str(e)))

	def commit(self):
		handler = univention.config_registry.configHandlers()
		handler.load()
		handler(self._changes.keys(), (self.ucr, self._changes))

@contextmanager
def set_save_commit_load(ucr):
	ucr.load()
	changes = Changes(ucr)
	yield changes
	ucr.save()
	ucr.load()
	if changes.changed():
		changes.commit()

class ComponentManager(object):
	def __init__(self, ucr, updater):
		self.ucr = ucr
		self.uu = updater

	def component(self, component_id):
		"""Returns a dict of properties for the component with this id.
		"""
		entry = {}
		entry['name'] = component_id
		# ensure a proper bool
		entry['enabled'] = self.ucr.is_true('%s/%s' % (COMPONENT_BASE, component_id), False)
		# Most values that can be fetched unchanged
		for attr in COMP_PARAMS:
			regstr = '%s/%s/%s' % (COMPONENT_BASE, component_id, attr)
			entry[attr] = self.ucr.get(regstr, '')
		# Get default packages (can be named either defaultpackage or defaultpackages)
		entry['defaultpackages'] = list(self.uu.get_component_defaultpackage(component_id))  # method returns a set
		# Explicitly enable unmaintained component
		entry['unmaintained'] = self.ucr.is_true('%s/%s/unmaintained' % (COMPONENT_BASE, component_id), False)
		# Component status as a symbolic string
		entry['status'] = self.uu.get_current_component_status(component_id)
		entry['installed'] = self.uu.is_component_defaultpackage_installed(component_id)

		# correct the status to 'installed' if (1) status is 'available' and (2) installed is true
		if entry['status'] == 'available' and entry['installed']:
			entry['status'] = 'installed'

		# Possibly this makes sense? add an 'icon' column so the 'status' column can decorated...
		entry['icon'] = STATUS_ICONS.get(entry['status'], DEFAULT_ICON)

		# Allowance for an 'install' button: if a package is available, not installed, and there's a default package specified
		entry['installable'] = entry['status'] == 'available' and bool(entry['defaultpackages']) and not entry['installed']

		return entry

	def is_registered(self, component_id):
		return component_registered(component_id, self.ucr)

	def put_app(self, app):
		# ATTENTION: changes made here have to be done
		# in univention-add-app
		app_data = {
			'server' : app.get_server(),
			'prefix' : '',
			'unmaintained' : False,
			'enabled' : True,
			'name' : app.component_id,
			'description' : app.get('description'),
			'username' : '',
			'password' : '',
			'version' : 'current',
			'localmirror' : 'false',
		}
		with set_save_commit_load(self.ucr) as super_ucr:
			self.put(app_data, super_ucr)

	def remove_app(self, app):
		with set_save_commit_load(self.ucr) as super_ucr:
			self._remove(app.component_id, super_ucr)
			# errata component was added before Bug #30406
			# -> remove them if installed
			self._remove(app.component_id + '-errata', super_ucr)

	def put(self, data, super_ucr):
		"""	Does the real work of writing one component definition back.
			Will be called for each element in the request array of
			a 'put' call, returns one element that has to go into
			the result of the 'put' call.
			Function does not throw exceptions or print log messages.
		"""
		result = {
			'status': PUT_SUCCESS,
			'message': '',
			'object': {},
		}
		try:
			name = data.pop('name')
			named_component_base = '%s/%s' % (COMPONENT_BASE, name)
			for key, val in data.iteritems():
				if val is None:
					# was not given, so dont update
					continue
				if key in COMP_PARAMS:
					super_ucr.set_registry_var('%s/%s' % (named_component_base, key), val)
				elif key == 'enabled':
					super_ucr.set_registry_var(named_component_base, val)
		except Exception as e:
			result['status'] = PUT_PROCESSING_ERROR
			result['message'] = "Parameter error: %s" % str(e)

		# Saving the registry and invoking all commit handlers is deferred until
		# the end of the loop over all request elements.

		return result

	def remove(self, component_id):
		""" Removes one component. Note that this does not remove
			entries below repository/online/component/<id> that
			are not part of a regular component definition.
		"""
		result = {}
		result['status'] = PUT_SUCCESS

		try:
			with set_save_commit_load(self.ucr) as super_ucr:
				self._remove(component_id, super_ucr)

		except Exception as e:
			result['status'] = PUT_PROCESSING_ERROR
			result['message'] = "Parameter error: %s" % str(e)

		return result

	def _remove(self, component_id, super_ucr):
		named_component_base = '%s/%s' % (COMPONENT_BASE, component_id)
		for var in COMP_PARAMS:
			super_ucr.set_registry_var('%s/%s' % (named_component_base, var), '')

		super_ucr.set_registry_var(named_component_base, '')

