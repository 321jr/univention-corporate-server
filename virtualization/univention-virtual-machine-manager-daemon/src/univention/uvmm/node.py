#!/usr/bin/python
# -*- coding: utf-8 -*-
#
# Univention Virtual Machine Manager Daemon
#  node handler
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
"""UVMM node handler.

This module implements functions to handle nodes and domains. This is independent from the on-wire-format.
"""

import libvirt
import time
import socket
import logging
from xml.dom.minidom import parseString
import math
from helpers import TranslatableException, ms, N_ as _
from uvmm_ldap import ldap_annotation, LdapError, LdapConnectionError, ldap_modify
import univention.admin.uexceptions
import traceback
from univention.uvmm.eventloop import *
import threading
from storage import create_storage_pool, create_storage_volume, destroy_storage_volumes, get_all_storage_volumes, StorageError, storage_pools, get_storage_pool_info
from protocol import Data_Domain, Data_Node, Data_Snapshot, _map, Disk, Interface, Graphic
import os
try:
	import xml.etree.ElementTree as ET
except ImportError:
	import elementtree.ElementTree as ET
QEMU_URI = 'http://libvirt.org/schemas/domain/qemu/1.0'
QEMU_PXE_PREFIX = '/usr/share/kvm/pxe'

import univention.config_registry as ucr

configRegistry = ucr.ConfigRegistry()
configRegistry.load()

logger = logging.getLogger('uvmmd.node')

STATES = ['NOSTATE', 'RUNNING', 'IDLE', 'PAUSED', 'SHUTDOWN', 'SHUTOFF', 'CRASHED']

class NodeError(TranslatableException):
	"""Error while handling node."""
	pass

class StoragePool(object):
	"""Container for storage pool statistics."""
	def __init__(self, pool):
		self.uuid = pool.UUIDString()
		self.name = pool.name()
		self.update(pool)
	def __eq__(self, other):
		return self.uuid == other.uuid;
	def update(self, pool):
		"""Update statistics."""
		state, self.capacity, allocation, self.available = pool.info()


class DomainTemplate(object):
	'''Container for node capability.'''

	@staticmethod
	def list_from_xml(xml):
		"""Convert XML to list.
		>>> t = DomainTemplate.list_from_xml(KVM_CAPABILITIES)
		>>> len(t)
		3
		>>> t[0].os_type
		u'hvm'
		>>> t[0].arch
		u'i686'
		>>> t[0].domain_type
		u'qemu'
		>>> t[0].emulator
		u'/usr/bin/qemu'
		>>> t[0].machines
		[u'pc']
		>>> t[0].features
		['pae', u'acpi', u'apic']
		"""
		doc = parseString(xml)
		capas = doc.firstChild
		result = []
		for guest in filter(lambda f: f.nodeName == 'guest', capas.childNodes):
			os_type = DomainTemplate.__nv(guest, 'os_type')
			f_names = DomainTemplate.__get_features(guest)
			for arch in filter(lambda f: f.nodeName == 'arch', guest.childNodes):
				for dom in filter(lambda f: f.nodeName == 'domain', arch.childNodes):
					dom = DomainTemplate(arch, dom, os_type, f_names)
					result.append(dom)
		return result

	@staticmethod
	def __nv(node, name):
		return node.getElementsByTagName(name)[0].firstChild.nodeValue

	@staticmethod
	def __get_features(node):
		"""Return list of features."""
		f_names = []
		features = filter(lambda f: f.nodeName == 'features', node.childNodes)
		if features:
			for c in features[0].childNodes:
				if c.nodeType == 1:
					if c.nodeName == 'pae':
						if 'nonpae' not in f_names:
							f_names.append('pae')
					elif c.nodeName == 'nonpae':
						if 'pae' not in f_names:
							f_names.append('nonpae')
					elif c.getAttribute('default') == 'on':
						f_names.append(c.nodeName)
		return f_names

	def __init__(self, arch, domain_type, os_type, features):
		self.os_type = os_type
		self.features = features
		self.arch = arch.getAttribute('name')
		self.domain_type = domain_type.getAttribute('type')

		for n in [domain_type, arch]:
			try:
				self.emulator = DomainTemplate.__nv(n, 'emulator')
				break
			except IndexError:
				pass
		else:
			logger.error('No emulator specified in %s/%s' % (self.arch, self.domain_type))
			raise

		for n in [domain_type, arch]:
			self.machines = [m.firstChild.nodeValue for m in n.childNodes if m.nodeName == 'machine']
			if self.machines:
				break
		else:
			logger.error('No machines specified in %s/%s' % (self.arch, self.domain_type))
			raise

		try:
			self.loader = DomainTemplate.__nv(arch, 'loader')
		except:
			self.loader = None # optional

		# Work around for Bug #19120: Xen-Fv-64 needs <pae/>
		if self.domain_type == 'xen' and self.arch == 'x86_64' and not 'pae' in self.features:
			self.features.append('pae')

	def __str__(self):
		return 'DomainTemplate(arch=%s dom_type=%s os_type=%s): %s, %s, %s, %s' % (self.arch, self.domain_type, self.os_type, self.emulator, self.loader, self.machines, self.features)

	def matches(self, domain):
		'''Return True if domain matches os_type, arch and domain_type.'''
		return self.arch == domain.arch and self.domain_type == domain.domain_type and self.os_type == domain.os_type

class Domain(object):
	"""Container for domain statistics."""
	CPUTIMES = (10, 60, 5*60) # 10s 60s 5m
	def __init__(self, domain, node):
		self.node = node
		self.pd = Data_Domain() # public data
		self.pd.uuid = domain.UUIDString()
		self.pd.os_type = domain.OSType()
		self._time_stamp = 0.0
		self._time_used = 0L
		self._cpu_usage = 0
		self.update(domain)
		self.update_ldap()

	def __eq__(self, other):
		return self.pd.uuid == other.pd.uuid;

	def update(self, domain):
		"""Update statistics which may change often."""
		id = domain.ID()
		self.pd.name = domain.name()
		for i in range(5):
			info = domain.info()
			if info[0] != libvirt.VIR_DOMAIN_NOSTATE: # ignore =?= libvirt's transient error
				break
			if not domain.isActive():
				info[0] = libvirt.VIR_DOMAIN_SHUTOFF
				break
			time.sleep(1)
		else:
			logger.warning('No state for %s: %s' % (self.pd.name, info))
			return

		self.pd.state, maxMem, curMem, self.pd.vcpus, runtime = info

		if domain.ID() == 0 and domain.connect().getType() == 'Xen':
			# xen://#Domain-0 always reports (1<<32)-1
			maxMem = domain.connect().getInfo()[1]
			self.pd.maxMem = long(maxMem) << 20 # GiB
		else:
			self.pd.maxMem = long(maxMem) << 10 # KiB

		if self.pd.state in (libvirt.VIR_DOMAIN_SHUTOFF, libvirt.VIR_DOMAIN_CRASHED):
			self.pd.curMem = 0L
			delta_used = 0L
			self._time_used = 0L
		else:
			self.pd.curMem = long(curMem) << 10 # KiB
			delta_used = runtime - self._time_used # running [ns]
			self._time_used = runtime

		# Calculate historical CPU usage
		# http://www.teamquest.com/resources/gunther/display/5/
		now = time.time()
		delta_t = now - self._time_stamp # wall clock [s]
		if delta_t > 0.0 and delta_used >= 0L:
			try:
				self._cpu_usage = delta_used / delta_t / self.pd.vcpus / 1000000 # ms
			except ZeroDivisionError:
				self._cpu_usage = 0
			for i in range(len(Domain.CPUTIMES)):
				if delta_t < Domain.CPUTIMES[i]:
					e = math.exp(-1.0 * delta_t / Domain.CPUTIMES[i])
					self.pd.cputime[i] *= e
					self.pd.cputime[i] += (1.0 - e) * self._cpu_usage
				else:
					self.pd.cputime[i] = self._cpu_usage
		self._time_stamp = now
		self.update_expensive(domain)

	def update_expensive(self, domain):
		"""Update statistics."""
		# Full XML efinition
		self.xml2obj( domain )
		# List of snapshots

		snapshots = None
		if self.node.pd.supports_snapshot:
			has_snapshot_disk = False
			for dev in self.pd.disks:
				if dev.readonly:
					continue
				if dev.driver_type in ('qcow2',):
					has_snapshot_disk = True
					continue
				break
			else:
				if has_snapshot_disk:
					snapshots = {}
					for name in domain.snapshotListNames(0):
						snap = domain.snapshotLookupByName(name, 0)
						xml = snap.getXMLDesc(0)
						doc = parseString(xml)
						ctime = doc.getElementsByTagName('creationTime')[0].firstChild.nodeValue
						s = Data_Snapshot()
						s.name = name
						s.ctime = int(ctime)
						snapshots[name] = s
		self.pd.snapshots = snapshots

	def update_ldap(self):
		"""Update annotations from LDAP."""
		try:
			self.pd.annotations = ldap_annotation(self.pd.uuid)
		except LdapError, e:
			self.pd.annotations = {}

	def xml2obj( self, domain ):
		"""Parse XML into python object."""
		xml = domain.XMLDesc(libvirt.VIR_DOMAIN_XML_SECURE)
		doc = parseString(xml)
		devices = doc.getElementsByTagName( 'devices' )[ 0 ]
		self.pd.domain_type = doc.documentElement.getAttribute('type')
		if not self.pd.domain_type:
			logger.error("Failed /domain/@type from %s" % xml)
		os = doc.getElementsByTagName( 'os' )
		if os:
			os = os[ 0 ]
			type = os.getElementsByTagName( 'type' )
			if type and type[ 0 ].firstChild and type[ 0 ].firstChild.nodeValue:
				self.pd.os_type = type[0].firstChild.nodeValue
				# we should use the identifier xen instead of linux
				if self.pd.os_type == 'linux':
					self.pd.os_type = 'xen'
				if type[ 0 ].hasAttribute( 'arch' ):
					self.pd.arch = type[0].getAttribute('arch')
			kernel = os.getElementsByTagName( 'kernel' )
			if kernel and kernel[ 0 ].firstChild and kernel[ 0 ].firstChild.nodeValue:
				self.pd.kernel = kernel[0].firstChild.nodeValue
			cmdline = os.getElementsByTagName( 'cmdline' )
			if cmdline and cmdline[ 0 ].firstChild and cmdline[ 0 ].firstChild.nodeValue:
				self.pd.cmdline = cmdline[0].firstChild.nodeValue
			initrd = os.getElementsByTagName( 'initrd' )
			if initrd and initrd[ 0 ].firstChild and initrd[ 0 ].firstChild.nodeValue:
				self.pd.initrd = initrd[0].firstChild.nodeValue
			boot = os.getElementsByTagName('boot')
			if boot:
				self.pd.boot = [dev.attributes['dev'].value for dev in boot]
		bootloader = doc.getElementsByTagName( 'bootloader' )
		if bootloader:
			if bootloader[ 0 ].firstChild and bootloader[ 0 ].firstChild.nodeValue:
				self.pd.bootloader = bootloader[ 0 ].firstChild.nodeValue
			args = doc.getElementsByTagName( 'bootloader_args' )
			if args and args[ 0 ].firstChild and args[ 0 ].firstChild.nodeValue:
				self.pd.bootloader_args = args[ 0 ].firstChild.nodeValue

		self.pd.disks = []
		disks = devices.getElementsByTagName( 'disk' )
		for disk in disks:
			dev = Disk()
			dev.type = Disk.map_type( name = disk.getAttribute( 'type' ) )
			dev.device = Disk.map_device( name = disk.getAttribute( 'device' ) )
			driver = disk.getElementsByTagName('driver')
			if driver:
				dev.driver = driver[0].getAttribute('name')
				dev.driver_type = driver[0].getAttribute('type')
				dev.driver_cache = driver[0].getAttribute('cache')
			source = disk.getElementsByTagName( 'source' )
			if source:
				if dev.type == Disk.TYPE_FILE:
					dev.source = source[0].getAttribute('file')
				elif dev.type == Disk.TYPE_BLOCK:
					dev.source = source[0].getAttribute('dev')
				else:
					raise NodeError(_('Unknown disk type: %(type)d'), type=dev.type)
			target = disk.getElementsByTagName( 'target' )
			if target:
				dev.target_dev = target[ 0 ].getAttribute( 'dev' )
				dev.target_bus = target[ 0 ].getAttribute( 'bus' )
			if disk.getElementsByTagName( 'readonly' ):
				dev.readonly = True

			self.pd.disks.append(dev)

		self.pd.interfaces = []
		interfaces = devices.getElementsByTagName( 'interface' )
		for iface in interfaces:
			dev = Interface()
			dev.type = Interface.map_type( name = iface.getAttribute( 'type' ) )
			mac = iface.getElementsByTagName( 'mac' )
			if mac:
				dev.mac_address = mac[ 0 ].getAttribute( 'address' )
			source = iface.getElementsByTagName( 'source' )
			if source:
				if dev.type == Interface.TYPE_BRIDGE:
					dev.source = source[0].getAttribute('bridge')
				elif dev.type == Interface.TYPE_NETWORK:
					dev.source = source[0].getAttribute('network')
				elif dev.type == Interface.TYPE_DIRECT:
					dev.source = source[0].getAttribute('dev')
			script = iface.getElementsByTagName( 'script' )
			if script:
				dev.script = script[ 0 ].getAttribute( 'path' )
			target = iface.getElementsByTagName( 'target' )
			if target:
				dev.target_dev = target[ 0 ].getAttribute( 'dev' )
			model = iface.getElementsByTagName( 'model' )
			if model:
				dev.model = model[ 0 ].getAttribute( 'type' )

			self.pd.interfaces.append(dev)

		self.pd.graphics = []
		graphics = devices.getElementsByTagName( 'graphics' )
		for graphic in graphics:
			dev = Graphic()
			type = graphic.getAttribute('type')
			dev.type = Graphic.map_type(name=type)
			if dev.type == Graphic.TYPE_VNC:
				dev.port = int(graphic.getAttribute('port'))
				dev.autoport = graphic.getAttribute('autoport').lower() == 'yes'
				if graphic.hasAttribute('listen'):
					dev.listen = graphic.getAttribute('listen')
				if graphic.hasAttribute('passwd'):
					dev.passwd = graphic.getAttribute('passwd')
				dev.keymap = graphic.getAttribute('keymap')
			elif dev.type == Graphic.TYPE_SDL:
				pass
			else:
				logger.error('Unsupported graphics type: %s' % type)
			self.pd.graphics.append(dev)

	def key(self):
		"""Return a unique key for this domain and generation."""
		return hash((self.pd.uuid, self._time_stamp))

class Node(object):
	"""Container for node statistics."""
	def __init__(self, uri):
		self.pd = Data_Node() # public data
		self.uri = uri
		self._lock = threading.Lock()
		self.conn = None
		self.domains = {}
		self.config_frequency = Nodes.IDLE_FREQUENCY
		self.current_frequency = Nodes.IDLE_FREQUENCY

		def timer_callback(timer, *opaque):
			try:
				"""Handle regular poll. Also checks connection liveness."""
				logger.debug("timer_callback#%d: %s)" % (timer, self.uri,))
				try:
					self._lock.acquire()
					self.update_autoreconnect()
				finally:
					self._lock.release()
			except Exception, e:
				logger.error("%s: Exception in timer_callbck", (self.uri,), exc_info=True)
				# don't crash the event handler

		self.timerID = virEventAddTimerImpl(self.current_frequency, timer_callback, (None,None))
		self.domainCB = None

	def update_autoreconnect(self):
		"""(Re-)connect after connection broke."""
		try:
			if self.conn == None:
				self.conn = libvirt.open(self.uri)
				logger.info("Connected to '%s'" % (self.uri,))
				self.update_once()
				self._register_default_pool()
				# reset timer after successful re-connect
				self.current_frequency = self.config_frequency
				virEventUpdateTimerImpl(self.timerID, self.config_frequency)
			self.update()
			self.pd.last_try = self.pd.last_update = time.time()
		except libvirt.libvirtError, e:
			self.pd.last_try = time.time()
			# double timer interval until maximum
			hz = min(self.current_frequency * 2, Nodes.BEBO_FREQUENCY)
			logger.warning("'%s' broken? next check in %s. %s" % (self.uri, ms(hz), e))
			if hz > self.current_frequency:
				self.current_frequency = hz
				virEventUpdateTimerImpl(self.timerID, self.current_frequency)
			if self.conn != None:
				try:
					self.conn.domainEventDeregister(self.domainCB)
				except Exception, e:
					logger.error("%s: Exception in domainEventRegister", (self.uri,), exc_info=True)
					pass
				self.domainCB = None
				try:
					self.conn.close()
				except Exception, e:
					logger.error('%s: Exception in conn.close', (self.uri,), exc_info=True)
					pass
				self.conn = None

	def __eq__(self, other):
		return (self.uri, self.pd.name) == (other.uri, other.pd.name)

	def __del__(self):
		"""Free Node and deregister callbacks."""
		self.unregister()
		del self.pd
		del self.domains

	def _register_default_pool( self ):
		'''create a default storage pool if not available'''
		for pool in storage_pools(node=self):
			if pool.name == 'default':
				logger.debug("default pool already registered on %s" % self.pd.name)
				break
		else:
			logger.info("creating default pool on %s" % self.pd.name)
			create_storage_pool( self.conn, configRegistry.get( 'uvmm/pool/default/path', '/var/lib/libvirt/images' ) )

	def update_once(self):
		"""Update once on (re-)connect."""
		self.pd.name = self.conn.getHostname()
		info = self.conn.getInfo()
		self.pd.phyMem = long(info[1]) << 20 # MiB
		self.pd.cpus = info[2]
		self.pd.cores = info[4:8]
		xml = self.conn.getCapabilities()
		self.pd.capabilities = DomainTemplate.list_from_xml(xml)
		type = self.conn.getType()
		self.pd.supports_suspend = False
		self.pd.supports_snapshot = False
		if type == 'QEMU':
			# Qemu/Kvm supports managedSave
			self.pd.supports_suspend = True
			self.pd.supports_snapshot = True
		elif type == 'Xen':
			# As of libvirt-0.8.5 Xen doesn't support managedSave, but test dom0
			d = self.conn.lookupByID(0)
			try:
				d.hasManagedSaveImage(0)
				self.pd.supports_suspend = True
			except libvirt.libvirtError, e:
				if e.get_error_code() != libvirt.VIR_ERR_NO_SUPPORT:
					logger.error('%s: Exception testing managedSave' % (self.uri,), exc_info=True)
			# As of libvirt-0.8.5 Xen doesn't support snapshot-*, but test dom0
			try:
				d.snapshotListNames(0)
				self.pd.supports_snapshot = True
			except libvirt.libvirtError, e:
				if e.get_error_code() != libvirt.VIR_ERR_NO_SUPPORT:
					logger.error('%s: Exception testing snapshots' % (self.uri,), exc_info=True)

		def domain_callback(conn, dom, event, detail, node):
			try:
				"""Handle domain addition, update and removal."""
				eventStrings = ("Added", "Removed", "Started", "Suspended", "Resumed", "Stopped", "Saved", "Restored")
				logger.debug("domain_callback %s(%s) %s %d" % (dom.name(), dom.ID(), eventStrings[event], detail))
				uuid = dom.UUIDString()
				if event == libvirt.VIR_DOMAIN_EVENT_DEFINED:
					domStat = Domain(dom, node=self)
					self.domains[uuid] = domStat
				elif event == libvirt.VIR_DOMAIN_EVENT_UNDEFINED:
					if uuid in self.domains:
						del self.domains[uuid]
				else: # VIR_DOMAIN_EVENT_STARTED _SUSPENDED _RESUMED _STOPPED
					try:
						domStat = self.domains[uuid]
						domStat.update( dom )
					except KeyError, e:
						# during migration events are not ordered causal
						pass
			except Exception, e:
				logger.error('%s: Exception handling callback' % (self.uri,), exc_info=True)
				# don't crash the event handler

		self.conn.domainEventRegister(domain_callback, self)
		self.domainCB = domain_callback

	def unregister(self):
		"""Unregister callbacks doing updates."""
		if self.timerID != None:
			virEventRemoveTimerImpl(self.timerID)
			self.timerID = None
		if self.domainCB != None:
			self.conn.domainEventDeregister(self.domainCB)
			self.domainCB = None
		if self.conn != None:
			self.conn.close()
			self.conn = None

	def set_frequency(self, hz):
		"""Set polling frequency for update."""
		self.config_frequency = hz
		self.current_frequency = hz
		virEventUpdateTimerImpl(self.timerID, hz)

	def update(self):
		"""Update node statistics."""
		curMem = 0
		maxMem = 0
		cpu_usage = 0
		cached_domains = self.domains.keys()
		def all_domains():
			for id in self.conn.listDomainsID():
				yield self.conn.lookupByID(id)
			for name in self.conn.listDefinedDomains():
				yield self.conn.lookupByName(name)
		for dom in all_domains():
			uuid = dom.UUIDString()
			if uuid in self.domains:
				# Update existing domains
				domStat = self.domains[uuid]
				domStat.update(dom)
				try:
					cached_domains.remove(uuid)
				except ValueError:
					pass
			else:
				# Add new domains
				domStat = Domain(dom, node=self)
				self.domains[uuid] = domStat
			curMem += domStat.pd.curMem
			maxMem += domStat.pd.maxMem
			cpu_usage += domStat._cpu_usage
		for uuid in cached_domains:
			# Remove obsolete domains
			del self.domains[uuid]
		self.pd.curMem = curMem
		self.pd.maxMem = maxMem
		self.pd.cpu_usage = min(1000, cpu_usage)

	def wait_update(self, domain, state_key, timeout=10):
		"""Wait until domain gets updated."""
		while timeout > 0:
			try:
				if state_key != self.domains[domain].key():
					break
			except KeyError, e:
				pass
			time.sleep(1)
			timeout -= 1
		else:
			logger.warning('Timeout waiting for update.')

class Nodes(dict):
	"""Handle registered nodes."""
	IDLE_FREQUENCY = 15*1000 # ms
	USED_FREQUENCY = 10*1000 # ms
	BEBO_FREQUENCY = 5*60*1000 # ms
	def __init__(self):
		super(Nodes,self).__init__()
		self.frequency = -1
	def __delitem__(self, uri):
		"""x.__delitem__(i) <==> del x[i]"""
		self[uri].unregister()
		super(Nodes, self).__delitem__(uri)
	def set_frequency(self, hz):
		"""Set polling frequency for update."""
		for node in self.values():
			node.set_frequency(hz)

nodes = Nodes()

def node_add(uri):
	"""Add node to watch list.
	>>> #node_add("qemu:///session")
	>>> #node_add("xen:///")"""
	global nodes
	if uri in nodes:
		raise NodeError(_('Hypervisor "%(uri)s" is already connected.'), uri=uri)

	node = Node(uri)
	nodes[uri] = node

	logger.debug("Hypervisor '%s' added." % (uri,))

def node_remove(uri):
	"""Remove node from watch list."""
	global nodes
	try:
		del nodes[uri]
	except KeyError:
		raise NodeError(_('Hypervisor "%(uri)s" is not connected.'), uri=uri)
	logger.debug("Hypervisor '%s' removed." % (uri,))

def node_query(uri):
	"""Get domain data from node."""
	global nodes
	try:
		node = nodes[uri]
		if node.conn is None:
			raise NodeError(_('Hypervisor "%(uri)s" is unavailable.'), uri=uri)
		return node
	except KeyError:
		raise NodeError(_('Hypervisor "%(uri)s" is not connected.'), uri=uri)

def node_frequency(hz=Nodes.IDLE_FREQUENCY, uri=None):
	"""Set frequency for polling nodes."""
	global nodes
	if uri == None:
		nodes.set_frequency(hz)
	else:
		node = node_query(uri)
		node.set_frequency(hz)

def node_list(group):
	"""Return list of watched nodes."""
	global nodes
	if group == 'default': # FIXME
		return [uri for uri in nodes]
	else:
		return []

def group_list():
	"""Return list of groups for nodes."""
	return ['default'] # FIXME

def _domain_backup(dom, save=True):
	"""Save domain definition to backup file."""
	backup_dir = configRegistry.get('uvmm/backup/directory', '/var/backups/univention-virtual-machine-manager-daemon')
	uuid = dom.UUIDString()
	xml = dom.XMLDesc(libvirt.VIR_DOMAIN_XML_SECURE)
	if len(xml) < 300: # minimal XML descriptor length
		logger.error("Failed to backup domain %s: %s" % (uuid, xml))
		raise NodeError("Failed to backup domain %(domain)s: %(xml)s", domain=uuid, xml=xml)
	now = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
	suffix = 'xml'
	if save:
		suffix += '.save'
	tmp_file = os.path.join(backup_dir, "%s_%s.%s" % (uuid, now, suffix))
	file = os.path.join(backup_dir, "%s.%s" % (uuid, suffix))
	umask = os.umask(0177)
	f = open(tmp_file, "w")
	try:
		f.write(xml)
	finally:
		f.close()
	os.umask(umask)
	os.rename(tmp_file, file)
	logger.info("Domain backuped to %s." % (file,))

def _domain_edit(node, dom_stat, xml):
	"""Apply python object 'dom_stat' to an XML domain description."""
	if xml:
		defaults = False
	else:
		xml = '<domain/>'
		defaults = True

	def update(_node_parent, _node_name, _node_value, **attr):
		'''Create, update or delete node named '_node_name' of '_node_parent'.'''
		node = _node_parent.find(_node_name)
		if _node_value is None and not filter(lambda v: v is not None, attr.values()):
			if node is not None:
				_node_parent.remove(node)
		else:
			if node is None:
				node = ET.SubElement(_node_parent, _node_name)
			node.text = _node_value or ''
			node.attrib.update(attr)
		return node

	# find loader
	logger.debug('Searching for template: arch=%s domain_type=%s os_type=%s' % (dom_stat.arch, dom_stat.domain_type, dom_stat.os_type))
	for template in node.pd.capabilities:
		logger.debug('template: %s' % template)
		if template.matches(dom_stat):
			break
	else:
		template = None

	# /domain @type
	domain = ET.fromstring(xml)
	domain.attrib['type'] = dom_stat.domain_type
	# /domain/uuid
	domain_uuid = update(domain, 'uuid', dom_stat.uuid)
	# /domain/name
	domain_name = update(domain, 'name', dom_stat.name)
	# /domain/description
	description = dom_stat.annotations.get('description') or None
	domain_description = update(domain, 'description', description)
	# /domain/os
	domain_os = domain.find('os')
	if domain_os is None:
		domain_os = ET.SubElement(domain, 'os')
	# /domain/os/type @arch
	domain_os_type = update(domain_os, 'type', dom_stat.os_type, arch=dom_stat.arch)
	# /domain/os/loader
	if defaults and template and template.loader:
		domain_os_loader = update(domain_os, 'loader', template.loader)
	if dom_stat.os_type in ('linux', 'xen'):
		# /domain/os/kernel
		domain_os_kernel = update(domain_os, 'kernel', dom_stat.kernel)
		# /domain/os/cmdline
		domain_os_cmdline = update(domain_os, 'cmdline', dom_stat.cmdline)
		# /domain/os/initrd
		domain_os_initrd = update(domain_os, 'initrd', dom_stat.initrd)
	elif dom_stat.os_type == 'hvm':
		# /domain/os/boot[]
		domain_os_boots = domain_os.findall('boot')
		boot = {}
		for domain_os_boot in domain_os_boots:
			dev = domain_os_boot.attrib['dev']
			boot[dev] = domain_os_boot
			domain_os.remove(domain_os_boot)
		for dev in dom_stat.boot:
			try:
				domain_os_boot = boot[dev]
				domain_os.append(domain_os_boot)
			except LookupError, e:
				domain_os_boot = ET.SubElement(domain_os, 'boot', dev=dev)
	else:
		raise NodeError("Unknown os/type='%(type)s'", type=d.os_type)
	if dom_stat.bootloader:
		# /domain/bootloader
		domain_bootloader = update(domain, 'bootloader', dom_stat.bootloader)
		# /domain/bootloader_args
		domain_bootloader_args = update(domain, 'bootloader_args', dom_stat.bootloader_args)
	# /domain/memory
	domain_memory = update(domain, 'memory', '%d' % (dom_stat.maxMem >> 10)) # KiB
	if False:
		# /domain/currentMemory
		domain_currentMemory = update(domain, 'currentMemory', '%d' % (dom_stat.curMem >> 10)) # KiB
	# /domain/vcpu
	domain_vcpu = update(domain, 'vcpu', '%d' % dom_stat.vcpus)

	# /domain/features
	if defaults and template and template.features:
		domain_features = update(domain, 'features', '')
		for f_name in template.features:
			domain_features_x = update(domain_features, f_name, '')

	# /domain/clock @offset @timezone @adjustment
	if defaults and False:
		domain_clock = update(domain, 'clock', '', offset='localtime') # timezone='', adjustment=0
	# /domain/on_poweroff
	if defaults:
		domain_on_poweroff = update(domain, 'on_poweroff', 'destroy') # (destroy|restart|preserve|rename-restart)
	# /domain/on_reboot
	if defaults:
		domain_on_reboot = update(domain, 'on_reboot', 'destroy') # (destroy|restart|preserve|rename-restart)
	# /domain/on_crash
	if defaults:
		domain_on_crash = update(domain, 'on_crash', 'destroy') # (destroy|restart|preserve|rename-restart)

	# /domain/devices/*[]
	domain_devices = update(domain, 'devices', '')

	# /domain/devices/emulator
	if defaults and template and template.emulator:
		domain_devices_emulator = update(domain_devices, 'emulator', template.emulator)

	# /domain/devices/disk[]
	domain_devices_disks = domain_devices.findall('disk')
	disks = {}
	for domain_devices_disk in domain_devices_disks:
		domain_devices_disk_target = domain_devices_disk.find('target')
		bus = domain_devices_disk_target.attrib['bus']
		dev = domain_devices_disk_target.attrib['dev']
		key = (bus, dev)
		disks[key] = domain_devices_disk
		domain_devices.remove(domain_devices_disk)
	for disk in dom_stat.disks:
		logger.debug('DISK: %s' % disk)
		# /domain/devices/disk @type @device
		try:
			key = (disk.target_bus, disk.target_dev)
			domain_devices_disk = disks[key]
			domain_devices.append(domain_devices_disk)
		except LookupError, e:
			domain_devices_disk = ET.SubElement(domain_devices, 'disk')
			# /domain/devices/disk/target @bus @dev
			domain_devices_disk_target = ET.SubElement(domain_devices_disk, 'target')
			domain_devices_disk_target.attrib['bus'] = disk.target_bus
			domain_devices_disk_target.attrib['dev'] = disk.target_dev
		domain_devices_disk.attrib['type'] = Disk.map_type(id=disk.type)
		domain_devices_disk.attrib['device'] = Disk.map_device(id=disk.device)
		# /domain/devices/disk/driver @name @type @cache
		domain_devices_disk_driver = update(domain_devices_disk, 'driver', None, name=disk.driver, type=disk.driver_type, cache=Disk.map_cache(id=disk.driver_cache))
		# /domain/devices/disk/source @file @dev
		if disk.type == Disk.TYPE_FILE:
			domain_devices_disk_source = update(domain_devices_disk, 'source', '', file=disk.source, dev=None)
		elif disk.type == Disk.TYPE_BLOCK:
			domain_devices_disk_source = update(domain_devices_disk, 'source', '', file=None, dev=disk.source)
		else:
			raise NodeError("Unknown disk/type='%(type)s'", type=disk.type)
		# /domain/devices/disk/readonly
		domain_devices_disk_readonly = domain_devices_disk.find('readonly')
		if disk.readonly:
			if domain_devices_disk_readonly is None:
				ET.SubElement(domain_devices_disk, 'readonly')
		else:
			if domain_devices_disk_readonly is not None:
				domain_devices_disk.remove(domain_devices_disk_readonly)

	# /domain/devices/interface[]
	domain_devices_interfaces = domain_devices.findall('interface')
	interfaces = {}
	for domain_devices_interface in domain_devices_interfaces:
		domain_devices_interface_mac = domain_devices_interface.find('mac')
		key = domain_devices_interface_mac.attrib['address']
		interfaces[key] = domain_devices_interface
		domain_devices.remove(domain_devices_interface)
	for interface in dom_stat.interfaces:
		logger.debug('INTERFACE: %s' % interface)
		# /domain/devices/interface @type @device
		try:
			key = interface.mac_address
			domain_devices_interface = interfaces[key]
			domain_devices.append(domain_devices_interface)
		except LookupError, e:
			domain_devices_interface = ET.SubElement(domain_devices, 'interface')
			# /domain/devices/interface/mac @address
			domain_devices_interface_mac = ET.SubElement(domain_devices_interface, 'mac')
			domain_devices_interface_mac.attrib['address'] = interface.mac_address
		domain_devices_interface.attrib['type'] = Interface.map_type(id=interface.type)
		# /domain/devices/interface/source @bridge @network @dev
		if interface.type == Interface.TYPE_BRIDGE:
			domain_devices_interface_source = update(domain_devices_interface, 'source', '', bridge=interface.source, network=None, dev=None)
		elif interface.type == Interface.TYPE_NETWORK:
			domain_devices_interface_source = update(domain_devices_interface, 'source', '', bridge=None, network=interface.source, dev=None)
		elif interface.type == Interface.TYPE_DIRECT:
			domain_devices_interface_source = update(domain_devices_interface, 'source', '', bridge=None, network=None, dev=interface.source)
		else:
			raise NodeError("Unknown interface/type='%(type)s'", type=interface.type)
		# /domain/devices/interface/script @bridge
		domain_devices_interface_script = update(domain_devices_interface, 'script', None, path=interface.script)
		# /domain/devices/interface/target @dev
		domain_devices_interface_target = update(domain_devices_interface, 'target', None, dev=interface.target)
		# /domain/devices/interface/model @dev
		domain_devices_interface_model = update(domain_devices_interface, 'model', None, type=interface.model)

	# /domain/devices/input @type @bus
	if dom_stat.os_type == 'hvm':
		# define a tablet usb device which has absolute cursor movement for a better VNC experience. Bug #19244
		domain_devices_inputs = domain_devices.findall('input')
		for domain_devices_input in domain_devices_inputs:
			if domain_devices_input.attrib['type'] == 'tablet' and domain_devices_input.attrib['bus'] == 'usb':
				break
		else:
			domain_devices_input = ET.SubElement(domain_devices, 'input', type='tablet', bus='usb')

	# /domain/devices/graphics[]
	domain_devices_graphics = domain_devices.findall('graphics')
	for domain_devices_graphic in domain_devices_graphics:
		domain_devices.remove(domain_devices_graphic)
	for graphics in dom_stat.graphics:
		# /domain/devices/graphics @type
		key = Graphic.map_type(id=graphics.type)
		for domain_devices_graphic in domain_devices_graphics:
			if key == domain_devices_graphic.attrib['type']:
				domain_devices.append(domain_devices_graphic)
				break
		else:
			domain_devices_graphic = ET.SubElement(domain_devices, 'graphics', type=key)
		# /domain/devices/graphics @autoport
		if graphics.autoport:
			domain_devices_graphic.attrib['autoport'] = 'yes'
		else:
			domain_devices_graphic.attrib['autoport'] = 'no'
		# /domain/devices/graphics @port @keymap @listen @passwd
		domain_devices_graphic.attrib['port'] = '%d' % graphics.port
		domain_devices_graphic.attrib['keymap'] = graphics.keymap
		domain_devices_graphic.attrib['listen'] = graphics.listen
		domain_devices_graphic.attrib['passwd'] = graphics.passwd
	
	if dom_stat.domain_type in ('kvm'): # 'qemu'
		models = set()
		for iface in dom_stat.interfaces:
			model = getattr(iface, 'model', None) or 'rtl8139'
			models.add(model)
		if 'network' not in dom_stat.boot: # qemu-kvm_0.12.4 ignores boot-order and always prefers Network
			models = set()
		models &= set(['e1000', 'ne2k_isa', 'ne2k_pci', 'pcnet', 'rtl8139', 'virtio'])
		roms = set(['%s-%s.bin' % (QEMU_PXE_PREFIX, model) for model in models])

		# install XML Name Space mapping: prefix must be qemu!
		ET._namespace_map[QEMU_URI] = 'qemu'
		domain.attrib['xmlns:qemu'] = QEMU_URI

		# /domain/qemu:commandline/
		QEMU_COMMANDLINE = '{%s}commandline' % QEMU_URI
		domain_qemu_commandline = update(domain, QEMU_COMMANDLINE, '')
		# /domain/qemu:commandline/qemu:arg
		QEMU_ARG = '{%s}arg' % QEMU_URI
		i = 0
		i_option_rom = None
		while i < len(domain_qemu_commandline):
			if domain_qemu_commandline[i].tag == QEMU_ARG:
				val = domain_qemu_commandline[i].attrib['value']
				if val == '-option-rom':
					i_option_rom = i
				elif i_option_rom is not None and val.startswith(QEMU_PXE_PREFIX):
					try:
						roms.remove(val)
					except LookupError, e:
						del domain_qemu_commandline[i]
						del domain_qemu_commandline[i_option_rom]
						i -= 2
						i_option_rom = None
			i += 1
		for rom in roms:
			domain_qemu_commandline_arg = ET.SubElement(domain_qemu_commandline, QEMU_ARG, value='-option-rom')
			domain_qemu_commandline_arg = ET.SubElement(domain_qemu_commandline, QEMU_ARG, value=rom)

	# Make ET happy and cleanup None values
	for n in domain.getiterator():
		if n.text is None:
			n.text = ''
		for k, v in n.attrib.items():
			if v is None or v == '':
				del n.attrib[k]
			elif not isinstance(v, basestring):
				n.attrib[k] = '%s' % v

	return ET.tostring(domain)

def domain_define( uri, domain ):
	"""Convert python object to an XML document."""
	node = node_query(uri)
	conn = node.conn
	logger.debug('PY DUMP: %r' % domain.__dict__)

	# Check for (name,uuid) collision
	old_dom = None
	old_xml = None
	try:
		old_dom = conn.lookupByName(domain.name)
		if old_dom.UUIDString() != domain.uuid:
			raise NodeError(_('Domain name "%(domain)s" already used by "%(uuid)s"'), domain=domain.name, uuid=domain.uuid)
		old_xml = old_dom.XMLDesc(libvirt.VIR_DOMAIN_XML_SECURE)
	except libvirt.libvirtError, e:
		if e.get_error_code() != libvirt.VIR_ERR_NO_DOMAIN:
			logger.error(e)
			raise NodeError(_('Error retrieving old domain "%(domain)s": %(error)s'), domain=domain.name, error=e.get_error_message())
		# rename: name changed, uuid unchanged
		try:
			if domain.uuid:
				old_dom = conn.lookupByUUIDString(domain.uuid)
				old_xml = old_dom.XMLDesc(libvirt.VIR_DOMAIN_XML_SECURE)
		except libvirt.libvirtError, e:
			if e.get_error_code() != libvirt.VIR_ERR_NO_DOMAIN:
				logger.error(e)
				raise NodeError(_('Error retrieving old domain "%(domain)s": %(error)s'), domain=domain.uuid, error=e.get_error_message())

	old_stat = None
	warnings = []
	if domain.uuid:
		old_stat = node.domains[domain.uuid].key()
	
	new_xml = _domain_edit(node, domain, old_xml)

	# create new disks
	logger.debug('DISKS: %s' % domain.disks)
	for disk in domain.disks:
		if disk.device == Disk.DEVICE_DISK:
			try:
				# FIXME: If the volume is outside any pool, ignore error
				create_storage_volume(conn, domain, disk)
			except StorageError, e:
				raise NodeError(e)

	# remove old domain definitions
	if old_dom:
		try:
			_domain_backup(old_dom)
			if old_dom.name() != domain.name: # rename needs undefine
				old_dom.undefine() # all snapshots are destroyed!
				logger.info('Old domain "%s" removed.' % (domain.uuid,))
		except libvirt.libvirtError, e:
			if e.get_error_code() != libvirt.VIR_ERR_NO_DOMAIN:
				logger.error(e)
				raise NodeError(_('Error removing domain "%(domain)s": %(error)s'), domain=domain.uuid, error=e.get_error_message())

	try:
		logger.debug('XML DUMP: %s' % new_xml.replace('\n', ' '))
		d = conn.defineXML(new_xml)
		domain.uuid = d.UUIDString()
		_domain_backup(d, save=False)
	except libvirt.libvirtError, e:
		logger.error(e)
		raise NodeError(_('Error defining domain "%(domain)s": %(error)s'), domain=domain.name, error=e.get_error_message())
	logger.info('New domain "%s"(%s) defined.' % (domain.name, domain.uuid))

	if domain.annotations:
		try:
			record = ldap_modify(domain.uuid)
			modified = False
			for key, cur_value in record.items():
				if key == 'uuid':
					new_value = domain.uuid
				else:
					new_value = domain.annotations.get(key, cur_value)
				if new_value != cur_value:
					record[key] = new_value
					modified = True
			if modified:
				record.commit()
		except LdapConnectionError, e:
			logger.error('Updating LDAP failed, insufficient permissions: %s' % (e,))
			warnings.append( _( 'Failed to update the additionally information in the LDAP directory.' ) )
		except ( univention.admin.uexceptions.ldapError, univention.admin.uexceptions.objectExists ), e:
			logger.error('Updating LDAP failed: %s %s' % (e, record))
			warnings.append( _( 'Failed to update the additionally information in the LDAP directory.' ) )

	node.wait_update(domain.uuid, old_stat)

	return ( domain.uuid, warnings )

def domain_state(uri, domain, state):
	"""Change running state of domain on node and wait for updated state."""
	try:
		node = node_query(uri)
		conn = node.conn
		dom = conn.lookupByUUIDString(domain)
		dom_stat = node.domains[domain]
		try:
			TRANSITION = {
					(libvirt.VIR_DOMAIN_RUNNING,  'PAUSE'   ): dom.suspend,
					(libvirt.VIR_DOMAIN_RUNNING,  'RESTART' ): lambda:dom.destroy(None),
					(libvirt.VIR_DOMAIN_RUNNING,  'RUN'     ): None,
					(libvirt.VIR_DOMAIN_RUNNING,  'SHUTDOWN'): dom.destroy,
					(libvirt.VIR_DOMAIN_RUNNING,  'SUSPEND' ): lambda:dom.managedSave(0),
					(libvirt.VIR_DOMAIN_BLOCKED,  'PAUSE'   ): dom.suspend,
					(libvirt.VIR_DOMAIN_BLOCKED,  'RESTART' ): lambda:dom.destroy(None),
					(libvirt.VIR_DOMAIN_BLOCKED,  'RUN'     ): None,
					(libvirt.VIR_DOMAIN_BLOCKED,  'SHUTDOWN'): dom.destroy,
					(libvirt.VIR_DOMAIN_BLOCKED,  'SUSPEND' ): lambda:dom.managedSave(0),
					(libvirt.VIR_DOMAIN_PAUSED,   'PAUSE'   ): None,
					(libvirt.VIR_DOMAIN_PAUSED,   'RUN'     ): dom.resume,
					(libvirt.VIR_DOMAIN_PAUSED,   'SHUTDOWN'): dom.destroy,
					(libvirt.VIR_DOMAIN_SHUTDOWN, 'RUN'     ): dom.create,
					(libvirt.VIR_DOMAIN_SHUTDOWN, 'SHUTDOWN'): None,
					(libvirt.VIR_DOMAIN_SHUTOFF,  'RUN'     ): dom.create,
					(libvirt.VIR_DOMAIN_SHUTOFF,  'SHUTDOWN'): None,
					(libvirt.VIR_DOMAIN_CRASHED,  'RUN'     ): dom.create,
					(libvirt.VIR_DOMAIN_CRASHED,  'SHUTDOWN'): None, # TODO destroy?
					}
			transition = TRANSITION[(dom_stat.pd.state, state)]
		except KeyError, e:
			cur_state = STATES[dom_stat.pd.state]
			raise NodeError(_('Unsupported state transition %(cur_state)s to %(next_state)s'), cur_state=cur_state, next_state=state)

		if transition:
			transition()
			ignore_states = [libvirt.VIR_DOMAIN_NOSTATE]
			if state == 'RUN':
				ignore_states.append(libvirt.VIR_DOMAIN_PAUSED)
			for t in range(20):
				cur_state = dom.info()[0]
				if cur_state not in ignore_states:
					# xen does not send event, do update explicitly
					dom_stat.pd.state = cur_state
					break
				time.sleep(1)
	except KeyError, e:
		logger.error("Domain %s not found" % (e,))
		raise NodeError(_('Error managing domain "%(domain)s"'), domain=domain)
	except libvirt.libvirtError, e:
		logger.error(e)
		raise NodeError(_('Error managing domain "%(domain)s": %(error)s'), domain=domain, error=e.get_error_message())

def domain_save(uri, domain, statefile):
	"""Save defined domain."""
	try:
		node = node_query(uri)
		conn = node.conn
		dom = conn.lookupByUUIDString(domain)
		old_state = node.domains[ domain ].key()
		dom.save(statefile)
		node.domains[ domain ].update( dom )
		node.wait_update( domain, old_state )
	except libvirt.libvirtError, e:
		logger.error(e)
		raise NodeError(_('Error saving domain "%(domain)s": %(error)s'), domain=domain, error=e.get_error_message())

def domain_restore(uri, domain, statefile):
	"""Restore defined domain."""
	try:
		node = node_query(uri)
		conn = node.conn
		dom = conn.lookupByUUIDString(domain)
		old_state = node.domains[ domain ].key()
		conn.restore(statefile)
		node.domains[ domain ].update( dom )
		node.wait_update( domain, old_state )
	except libvirt.libvirtError, e:
		logger.error(e)
		raise NodeError(_('Error restoring domain "%(domain)s": %(error)s'), domain=domain, error=e.get_error_message())

def domain_undefine(uri, domain, volumes=[]):
	"""Undefine a domain and its volumes on a node."""
	try:
		node = node_query(uri)
		conn = node.conn
		dom = conn.lookupByUUIDString(domain)
		_domain_backup(dom)
		if volumes is None:
			volumes = get_all_storage_volumes(conn, dom,)
		destroy_storage_volumes(conn, volumes, ignore_error=True)
		try:
			if dom.hasManagedSaveImage(0):
				ret = dom.managedSaveRemove(0)
		except libvirt.libvirtError, e:
			# libvirt returns an 'internal error' when no save image exists
			if e.get_error_code() != libvirt.VIR_ERR_INTERNAL_ERROR:
				logger.debug(e)
		dom.undefine()
	except libvirt.libvirtError, e:
		logger.error(e)
		raise NodeError(_('Error undefining domain "%(domain)s": %(error)s'), domain=domain, error=e.get_error_message())

def domain_migrate(source_uri, domain, target_uri):
	"""Migrate a domain from node to the target node."""
	try:
		source_node = node_query(source_uri)
		source_conn = source_node.conn
		source_dom = source_conn.lookupByUUIDString(domain)
		for t in range(10):
			source_state = source_dom.info()[0]
			if source_state != libvirt.VIR_DOMAIN_NOSTATE:
				break
			time.sleep(1)
		target_node = node_query(target_uri)
		target_conn = target_node.conn

		if source_state in (libvirt.VIR_DOMAIN_RUNNING, libvirt.VIR_DOMAIN_BLOCKED):
			# running domains are live migrated
			flags = libvirt.VIR_MIGRATE_LIVE | libvirt.VIR_MIGRATE_PERSIST_DEST | libvirt.VIR_MIGRATE_UNDEFINE_SOURCE
			target_dom = source_dom.migrate(target_conn, flags, None, None, 0)
		elif source_state in (libvirt.VIR_DOMAIN_SHUTDOWN, libvirt.VIR_DOMAIN_SHUTOFF, libvirt.VIR_DOMAIN_CRASHED):
			# for domains not running their definition is migrated
			xml = source_dom.XMLDesc(libvirt.VIR_DOMAIN_XML_SECURE)
			target_conn.defineXML(xml)
			source_dom.undefine()
		elif True or source_state in (libvirt.VIR_DOMAIN_PAUSED):
			raise NodeError(_('Domain "%(domain)s" in state "%(state)s" can not be migrated'), domain=domain, state=STATES[source_state])

		# Updates are handled via the callback mechanism, but remove domain
		# info as soon as possible to not show stale data
		try:
			del source_node.domains[domain]
		except KeyError, e:
			pass
		#target_node.domains[domain] = Domain(target_dom, node=target_node)
		for t in range(10):
			if domain not in source_node.domains and domain in target_node.domains:
				break
			time.sleep(1)
		else:
			logger.warning('Domain "%(domain)s" still not migrated from "%(source)s" to "%(target)s"' % {'domain':domain, 'source':source_uri, 'target':target_uri})
	except libvirt.libvirtError, e:
		logger.error(e)
		raise NodeError(_('Error migrating domain "%(domain)s": %(error)s'), domain=domain, error=e.get_error_message())

def domain_snapshot_create(uri, domain, snapshot):
	"""Create new snapshot of domain."""
	try:
		node = node_query(uri)
		if not node.pd.supports_snapshot:
			raise NodeError(_('Snapshot not supported "%(node)s"'), node=uri)
		conn = node.conn
		dom = conn.lookupByUUIDString(domain)
		dom_stat = node.domains[domain]
		if dom_stat.pd.snapshots is None:
			raise NodeError(_('Snapshot not supported "%(node)s"'), node=uri)
		old_state = dom_stat.key()
		xml = '''<domainsnapshot><name>%s</name></domainsnapshot>''' % snapshot
		s = dom.snapshotCreateXML(xml, 0)

		dom_stat.update(dom)
		node.wait_update(domain, old_state)
	except libvirt.libvirtError, e:
		logger.error(e)
		raise NodeError(_('Error creating "%(domain)s" snapshot: %(error)s'), domain=domain, error=e.get_error_message())

def domain_snapshot_revert(uri, domain, snapshot):
	"""Revert to snapshot of domain."""
	try:
		node = node_query(uri)
		if not node.pd.supports_snapshot:
			raise NodeError(_('Snapshot not supported "%(node)s"'), node=uri)
		conn = node.conn
		dom = conn.lookupByUUIDString(domain)
		dom_stat = node.domains[domain]
		if dom_stat.pd.snapshots is None:
			raise NodeError(_('Snapshot not supported "%(node)s"'), node=uri)
		old_state = dom_stat.key()
		snap = dom.snapshotLookupByName(snapshot, 0)
		r = dom.revertToSnapshot(snap, 0)
		if r != 0:
			raise NodeError(_('Error reverting "%(domain)s" to snapshot: %(error)s'), domain=domain, error=e.get_error_message())

		dom_stat.update(dom)
		node.wait_update(domain, old_state)
	except libvirt.libvirtError, e:
		logger.error(e)
		raise NodeError(_('Error reverting "%(domain)s" to snapshot: %(error)s'), domain=domain, error=e.get_error_message())

def domain_snapshot_delete(uri, domain, snapshot):
	"""Delete snapshot of domain."""
	try:
		node = node_query(uri)
		if not node.pd.supports_snapshot:
			raise NodeError(_('Snapshot not supported "%(node)s"'), node=uri)
		conn = node.conn
		dom = conn.lookupByUUIDString(domain)
		dom_stat = node.domains[domain]
		if dom_stat.pd.snapshots is None:
			raise NodeError(_('Snapshot not supported "%(node)s"'), node=uri)
		old_state = dom_stat.key()
		snap = dom.snapshotLookupByName(snapshot, 0)
		r = snap.delete(0)
		if r != 0:
			raise NodeError(_('Error deleting "%(domain)s" snapshot: %(error)s'), domain=domain, error=e.get_error_message())

		try:
			del node.domains[domain].pd.snapshots[snapshot]
		except KeyError, e:
			dom_stat.update(dom)
			node.wait_update(domain, old_state)
	except libvirt.libvirtError, e:
		logger.error(e)
		raise NodeError(_('Error deleting "%(domain)s" snapshot: %(error)s'), domain=domain, error=e.get_error_message())

def domain_update(domain):
	"""Trigger update of domain.
	Unfound domains are ignored."""
	global nodes
	# 1st: find domain on the previous host using only (stale) internal data
	for node in nodes.itervalues():
		conn = node.conn
		try:
			dom_stat = node.domains[domain]
			dom = conn.lookupByUUIDString(domain)
			dom_stat.update(dom)
			dom_stat.update_ldap()
			return
		except libvirt.libvirtError, e:
			if e.get_error_code() != libvirt.VIR_ERR_NO_DOMAIN:
				logger.error(e)
				raise NodeError(_('Error updating domain "%(domain)s"'), domain=domain)
			# remove stale data
			del node.domains[domain]
		except KeyError, e:
			# domain not on this node
			pass
	# 2nd: failed to find existing data, search again all hosts
	for node in nodes.itervalues():
		conn = node.conn
		try:
			dom = conn.lookupByUUIDString(domain)
			dom_stat = Domain(dom, node=node)
			node.domains[domain] = dom_stat
			return
		except libvirt.libvirtError, e:
			if e.get_error_code() != libvirt.VIR_ERR_NO_DOMAIN:
				logger.error(e)
				raise NodeError(_('Error updating domain "%(domain)s"'), domain=domain)
			else:
				continue # skip this node
	else:
		logger.info('Domain %s not found for update' % domain)
		raise NodeError(_('Failto to update domain "%(domain)s"'), domain=domain)

if __name__ == '__main__':
	XEN_CAPABILITIES = '''<capabilities>
		<host>
			<cpu>
				<arch>x86_64</arch>
				<features>
					<pae/>
				</features>
			</cpu>
			<migration_features>
				<live/>
				<uri_transports>
					<uri_transport>xenmigr</uri_transport>
				</uri_transports>
			</migration_features>
			<topology>
				<cells num='1'>
					<cell id='0'>
						<cpus num='1'>
							<cpu id='0'/>
						</cpus>
					</cell>
				</cells>
			</topology>
		</host>
		<guest>
			<os_type>xen</os_type>
			<arch name='x86_64'>
				<wordsize>64</wordsize>
				<emulator>/usr/lib64/xen/bin/qemu-dm</emulator>
				<machine>xenpv</machine>
				<domain type='xen'>
				</domain>
			</arch>
		</guest>
		<guest>
			<os_type>xen</os_type>
			<arch name='i686'>
				<wordsize>32</wordsize>
				<emulator>/usr/lib64/xen/bin/qemu-dm</emulator>
				<machine>xenfv</machine>
				<domain type='xen'>
				</domain>
			</arch>
			<features>
				<pae/>
				<nonpae/>
				<acpi default='on' toggle='yes'/>
				<apic default='on' toggle='yes'/>
			</features>
		</guest>
	</capabilities>'''
	KVM_CAPABILITIES = '''<capabilities>
		<host>
			<uuid>00020003-0004-0005-0006-000700080009</uuid>
			<cpu>
				<arch>x86_64</arch>
				<model>phenom</model>
				<topology sockets='1' cores='2' threads='1'/>
				<feature name='wdt'/>
			</cpu>
			<migration_features>
				<live/>
				<uri_transports>
					<uri_transport>tcp</uri_transport>
				</uri_transports>
			</migration_features>
		</host>
		<guest>
			<os_type>hvm</os_type>
			<arch name='i686'>
				<wordsize>32</wordsize>
				<emulator>/usr/bin/qemu</emulator>
				<machine>pc</machine>
				<domain type='qemu'>
				</domain>
				<domain type='kvm'>
					<emulator>/usr/bin/kvm</emulator>
					<machine>pc-0.12</machine>
					<machine canonical='pc-0.12'>pc</machine>
				</domain>
			</arch>
			<features>
				<cpuselection/>
				<pae/>
				<nonpae/>
				<acpi default='on' toggle='yes'/>
				<apic default='on' toggle='no'/>
			</features>
		</guest>
		<guest>
			<os_type>hvm</os_type>
			<arch name='arm'>
				<wordsize>32</wordsize>
				<emulator>/usr/bin/qemu-system-arm</emulator>
				<machine>integratorcp</machine>
				<domain type='qemu'>
				</domain>
			</arch>
		</guest>
	</capabilities>'''

	import doctest
	doctest.testmod()
