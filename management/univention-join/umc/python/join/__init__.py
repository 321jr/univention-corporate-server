#!/usr/bin/python2.6
# -*- coding: utf-8 -*-
#
# Univention Management Console
#  module: system usage statistics
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

import traceback
import subprocess
import os
import tempfile
import socket
import glob
import re
import dns.resolver

import notifier.threads

import univention.management.console as umc
from univention.management.console.log import MODULE
from univention.management.console.modules import Base, UMC_CommandError
from univention.management.console.config import ucr
from univention.management.console.protocol.definitions import *
from univention.management.console.modules.decorators import simple_response, sanitize
from univention.management.console.modules.sanitizers import StringSanitizer, ListSanitizer, BooleanSanitizer

_ = umc.Translation('univention-management-console-module-join').translate

CMD_ENABLE_EXEC = ['/usr/share/univention-updater/enable-apache2-umc', '--no-restart']
CMD_DISABLE_EXEC = '/usr/share/univention-updater/disable-apache2-umc'
RE_HOSTNAME = re.compile('^[a-z]([a-z0-9-]*[a-z0-9])*(\.([a-z0-9]([a-z0-9-]*[a-z0-9])*[.])*[a-z0-9]([a-z0-9-]*[a-z0-9])*)?$')

def get_master_dns_lookup():
	# DNS lookup for the DC master entry
	try:
		query = '_domaincontroller_master._tcp.%s.' % ucr.get('domainname')
		result = dns.resolver.query(query, 'SRV')
		if result:
			return result[0].target.canonicalize().split(1)[0].to_text()
	except dns.resolver.NXDOMAIN as err:
		MODULE.error('Error to perform a DNS query for service record: %s' % query)
	return ''

class HostSanitizer(StringSanitizer):
	def _sanitize(self, value, name, further_args):
		value = super(HostSanitizer, self)._sanitize(value, name, further_args)
		try:
			return socket.getfqdn(value)
		except socket.gaierror:
			# invalid FQDN
			self.raise_validation_error(_('The entered FQDN is not a valid value'))

class Progress(object):
	def __init__(self, max_steps=100):
		self.reset(max_steps)

	def reset(self, max_steps=100):
		self.max_steps = max_steps
		self.finished = False
		self.steps = 0
		self.component = _('Initializing')
		self.info = ''
		self.errors = []

	def poll(self):
		return dict(
			finished=self.finished,
			steps=100 * float(self.steps) / self.max_steps,
			component=self.component,
			info=self.info,
			errors=self.errors,
		)

	def finish(self):
		self.finished = True

	def info_handler(self, info):
		MODULE.process(info)
		self.info = info

	def error_handler(self, err):
		MODULE.warn(err)
		self.errors.append(err)

	def step_handler(self, steps):
		self.steps = steps

	def add_steps(self, steps = 1):
		self.steps += steps

	def component_handler(self, component):
		self.component = component

# dummy function that does nothing
def _dummyFunc(*args):
	pass

def system_join(hostname, username, password, info_handler = _dummyFunc, error_handler = _dummyFunc, step_handler = _dummyFunc, component_handler = _dummyFunc):
	# get the number of join scripts
	nJoinScripts = len(glob.glob('%s/*.inst' % INSTDIR))
	stepsPerScript = 100.0 / (nJoinScripts+1)

	with tempfile.NamedTemporaryFile() as passwordFile:
		passwordFile.write('%s' % password)
		passwordFile.flush()

		MODULE.process('Performing system join...')
		cmd = ['/usr/sbin/univention-join', '-dcname', hostname, '-dcaccount', username, '-dcpwd', passwordFile.name]

		return run(cmd, stepsPerScript, info_handler, error_handler, step_handler, component_handler)

def run_join_scripts(scripts, force, username, password, info_handler = _dummyFunc, error_handler = _dummyFunc, step_handler = _dummyFunc, component_handler = _dummyFunc):
	with tempfile.NamedTemporaryFile() as passwordFile:
		cmd = ['/usr/sbin/univention-run-join-scripts']
		if username and password:
			# credentials are provided
			passwordFile.write('%s' % password)
			passwordFile.flush()
			cmd += ['-dcaccount', username, '-dcpwd', passwordFile.name]

		if force:
			cmd += ['--force']

		if scripts:
			# if scripts are provided only execute them instead of running all join scripts
			cmd += ['--run-scripts'] + scripts
		else:
			# we need the number of join scripts for the progressbar
			scripts = os.listdir(INSTDIR)
		stepsPerScript = 100.0 / (len(scripts)+1)

		MODULE.process('Executing join scripts ...')
		return run(cmd, stepsPerScript, info_handler, error_handler, step_handler, component_handler)

def run(cmd, stepsPerScript, info_handler = _dummyFunc, error_handler = _dummyFunc, step_handler = _dummyFunc, component_handler = _dummyFunc):
	# disable UMC/apache restart
	MODULE.info('disabling UMC and apache server restart')
	subprocess.call(CMD_DISABLE_EXEC)

	try:
		# regular expressions for output parsing
		regError = re.compile('^\* Message:\s*(?P<message>.*)\s*$')
		regJoinScript = re.compile('(Configure|Running)\s+(?P<script>.*)\.inst.*$')
		regInfo = re.compile('^(?P<message>.*?)\s*:?\s*\x1b.*$')

		# call to univention-join
		MODULE.info('calling "%s"' % ' '.join(cmd))
		process = subprocess.Popen(cmd, shell=False, stdout=subprocess.PIPE, stderr=subprocess.PIPE)

		failedJoinScripts = []
		while True:
			# get the next line
			line = process.stdout.readline()
			if not line:
				# no more text from stdout
				break
			MODULE.process(line.strip())

			# parse output... first check for errors
			m = regError.match(line)
			if m:
				error_handler(_( "The system join process could not be completed:<br/><br/><i>%s</i><br/><br/> More details can be found in the log file <i>/var/log/univention/join.log</i>.<br/>Please retry after resolving any conflicting issues.") % m.groupdict().get('message'))
				continue

			# check for currently called join script
			m = regJoinScript.match(line)
			if m:
				component_handler(_('Executing join scripts'))
				info_handler(_('Executing join script %s') % m.groupdict().get('script'))
				step_handler(stepsPerScript)
				if 'failed' in line:
					failedJoinScripts.append(m.groupdict().get('script'))
				continue

			# check for other information
			m = regInfo.match(line)
			if m:
				info_handler(m.groupdict().get('message'))
				step_handler(stepsPerScript/10)
				continue

		# get all remaining output
		stdout, stderr = process.communicate()
		if stderr:
			# write stderr into the log file
			MODULE.warn('stderr: %s' % stderr)

		success = True
		# check for errors
		if process.returncode != 0:
			# error case
			MODULE.warn('Could not perform system join: %s%s' % (stdout, stderr))
			success = False
		elif failedJoinScripts:
			MODULE.warn('The following join scripts could not be executed: %s' % failedJoinScripts)
			error_handler(_('Some join scripts could not be executed. More details can be found in the log file <i>/var/log/univention/join.log</i>.<br/>Please retry to execute the join scripts after resolving any conflicting issues.'))

			success = False
		return success
	finally:
		# make sure that UMC servers and apache can be restarted again
		MODULE.info('enabling UMC and apache server restart')
		subprocess.call(CMD_ENABLE_EXEC)

INSTDIR = '/usr/lib/univention-install'
LOGFILE = '/var/log/univention/join.log'
LOCKFILE = '/var/lock/univention_umc_join.lock'
RE_JOINFILE = re.compile('^(?P<script>(?P<prio>\d+)(?P<name>.+))\.(inst|uinst)$')
RE_NOT_CONFIGURED = re.compile("^Warning: '([^']+)' is not configured.$")
RE_ERROR = re.compile('^Error: (.*?)$')

class Instance(Base):

	def init(self):
		self.progress_state = Progress()

	@simple_response
	def query(self):
		"""collects status about join scripts"""

		# unjoined system?
		if not self._joined:
			return []

		# List all join scripts
		files = {}
		for fname in os.listdir(INSTDIR):
			match = RE_JOINFILE.match(fname)
			if match:
				entry = match.groupdict()
				entry['configured'] = True
				entry['status'] = '1:%s' % (entry['prio'])
				files[entry['name']] = entry

		# check for unconfigured scripts
		process = subprocess.Popen(['/usr/sbin/univention-check-join-status'], shell=False, stdout=subprocess.PIPE)
		stdout, stderr = process.communicate()
		if process.returncode == 0:
			return files.values()

		for line in stdout.splitlines():
			# is there a general error?
			match = RE_ERROR.match(line)
			if match and not line.startswith('Error: Not all install files configured'):
				raise UMC_CommandError(_('Error: %s') % match.groups()[0])

			# unconfigured script
			match = RE_NOT_CONFIGURED.match(line)
			if match:
				name = match.groups()[0]
				files[name]['configured'] = False
				files[name]['status'] = '0:%s' % (files[name]['prio'])

		return files.values()

	@simple_response
	def joined(self):
		return self._joined

	@simple_response
	def progress(self):
		return self.progress_state.poll()

	@simple_response
	def running(self):
		""" returns true if a join script is running. """
		return self._running

	@simple_response
	def master(self):
		""" returns the hostname of the domaincontroller master as fqdn """
		return get_master_dns_lookup()

	@property
	def _joined(self):
		return os.path.exists('/var/univention-join/joined')
	
	@property
	def _running(self):
		return os.path.exists(LOCKFILE)

	def _lock(self):
		try:
			open(LOCKFILE, 'a').close()
		except (IOError, OSError), ex:
			MODULE.warn('_lock: %s' % (ex))

	def _unlock(self):
		try:
			if self._running:
				os.unlink(LOCKFILE)
		except (IOError, OSError), ex:
			MODULE.warn('_unlock: %s' % (ex))

	def __del__(self):
		self._unlock()

	# TODO __finalize__?

	@simple_response
	def logview(self):
		"""Returns the last 2MB of the join.log file"""
		with open(LOGFILE) as fd:
			return fd.read(2097152)

	@sanitize(
		username=StringSanitizer(required=True),
		password=StringSanitizer(required=True),
		hostname=HostSanitizer(required=True, regex_pattern=RE_HOSTNAME),
	)
	def join(self, request):
		username, password, hostname = (request.options['username'], request.options['password'], request.options['hostname'])

		def _error(msg):
			self.finished(request.id, dict(success=False, error=msg), success=False, status=400)

		# Check if already a join process is running
		if self._running:
			_error(_('A join process is already running.'))

		# check for valid server role
		if ucr.get('server/role') == 'domaincontroller_master':
			_error(_('Invalid server role! A master domain controller can not be joined.'))

		def _thread():
			self.progress_state.reset()
			self.progress_state.component = _('Domain join')
			self._lock()
			return system_join(
				hostname, username, password,
				info_handler=self.progress_state.info_handler,
				step_handler=self.progress_state.add_steps,
				error_handler=self.progress_state.error_handler,
				component_handler=self.progress_state.component_handler,
			)

		def _finished(thread, result):
			MODULE.info('Finished joining')
			self._unlock()
			self.progress_state.info = _('finished...')
			self.progress_state.finish()
			if isinstance(result, BaseException):
				msg = '%s\n%s: %s\n' % (''.join(traceback.format_tb(thread.exc_info[2])), thread.exc_info[0].__name__, str(thread.exc_info[1]))
				MODULE.warn('Exception during domain join: %s' % msg)
				self.progress_state.error_handler(_('An unexpected error occurred: %s') % result)

		# launch thread
		thread = notifier.threads.Simple('join', _thread, _finished)
		thread.run()

		request.status = 202
		self.finished(request.id, {'success': True})

	@sanitize(
		username=StringSanitizer(),
		password=StringSanitizer(),
		scripts=ListSanitizer(required=True, min_elements=1),
		force=BooleanSanitizer(default=False)
	)
	def run(self, request):
		"""runs the given join scripts"""

		def _error(msg):
			self.finished(request.id, dict(success=False, error=msg), success=False, status=400)

		# Check if already a join process is running
		if self._running:
			_error(_('A join process is already running.'))

		scripts, username, password, force = (request.options['scripts'], request.options.get('username'), request.options.get('password'), request.options.get('force', False))

		# sort scripts
		scripts.sort(key=lambda i: int(re.match('^(\d+)', i).group()))

		def _thread():
			# reset progress state and lock against other join processes
			self.progress_state.reset()
			self.progress_state.component = _('Authentication')
			self._lock()
			return run_join_scripts(
				scripts, force, username, password,
				info_handler=self.progress_state.info_handler,
				step_handler=self.progress_state.add_steps,
				error_handler=self.progress_state.error_handler,
				component_handler=self.progress_state.component_handler,
			)

		def _finished(thread, result):
			MODULE.info('Finished running join scripts')
			self._unlock()
			self.progress_state.info = _('finished...')
			self.progress_state.finish()
			if isinstance(result, BaseException):
				msg = '%s\n%s: %s\n' % (''.join(traceback.format_tb(thread.exc_info[2])), thread.exc_info[0].__name__, str(thread.exc_info[1]))
				MODULE.warn('Exception during running join scripts: %s' % msg)
				self.progress_state.error_handler(_('An unexpected error occurred: %s') % result)

		# launch thread
		thread = notifier.threads.Simple('join', _thread, _finished)
		thread.run()

		# finish request
		request.status = 202
		self.finished(request.id, {'success': True})
