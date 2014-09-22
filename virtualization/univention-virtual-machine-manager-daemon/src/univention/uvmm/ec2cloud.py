# -*- coding: utf-8 -*-
#
# UCS Virtual Machine Manager Daemon
#  cloud connection to EC2 instances
#
# Copyright 2014 Univention GmbH
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
"""UVMM cloud ec2 handler"""

from libcloud.common.types import LibcloudError, MalformedResponseError, ProviderError, InvalidCredsError
from libcloud.compute.types import Provider, NodeState, KeyPairDoesNotExistError
from libcloud.compute.providers import get_driver
from libcloud.compute.drivers.ec2 import IdempotentParamError

import time
import logging
import threading
import fnmatch
import re
import errno
import ssl

from node import PersistentCached
from helpers import TranslatableException
from cloudconnection import CloudConnection
from protocol import Cloud_Data_Instance, Cloud_Data_Location, Cloud_Data_Secgroup, Cloud_Data_Size, Cloud_Data_Network, Cloud_Data_Image
import univention.config_registry as ucr

configRegistry = ucr.ConfigRegistry()
configRegistry.load()

logger = logging.getLogger('uvmmd.ec2connection')

# Mapping of ldap attribute to libcloud parameter name
EC2_CONNECTION_ATTRIBUTES = {
		"access_id": "key",
		"password": "secret",
		"secure": "secure",
		"host": "host",
		"port": "port",
		"region": "region",
		}

EC2_CREATE_ATTRIBUTES = {
		"name": "name",
		"size_id": "size",
		"image_id": "image",
		"location": "location",
		"keyname": "ex_keyname",
		"userdata": "ex_userdata",
		"security_group_ids": "ex_security_groups",
		"metadata": "ex_metadata",
		"min_instance_count": "ex_mincount",
		"max_instance_count": "ex_maxcount",
		"clienttoken": "ex_clienttoken",
		"blockdevicemappings": "ex_blockdevicemappings",
		"iamprofile": "ex_iamprofile",
		"ebs_optimized": "ex_ebs_optimized",
		"subnet": "ex_subnet"
	}


LIBCLOUD_EC2_UVMM_STATE_MAPPING = {
		NodeState.RUNNING: "RUNNING",
		NodeState.PENDING: "PENDING",
		NodeState.TERMINATED: "NOSTATE",
		NodeState.UNKNOWN: "NOSTATE",
		NodeState.STOPPED: "SHUTDOWN",
		}


PROVIDER_MAPPING = {
		"EC2_US_EAST": Provider.EC2_US_EAST,
		"EC2_EU_WEST": Provider.EC2_EU_WEST,
		"EC2_US_WEST": Provider.EC2_US_WEST,
		"EC2_US_WEST_OREGON": Provider.EC2_US_WEST_OREGON,
		"EC2_AP_SOUTHEAST": Provider.EC2_AP_SOUTHEAST,
		"EC2_AP_NORTHEAST": Provider.EC2_AP_NORTHEAST,
		"EC2_SA_EAST": Provider.EC2_SA_EAST,
		"EC2_AP_SOUTHEAST2": Provider.EC2_AP_SOUTHEAST2,
		}


class EC2CloudConnectionError(TranslatableException):
	pass


class EC2CloudConnection(CloudConnection, PersistentCached):
	def __init__(self, cloud, cache_dir):
		super(EC2CloudConnection, self).__init__(cloud, cache_dir)
		self._check_connection_attributes(cloud)

		self.publicdata.url = cloud["region"]

		self._locations = []
		self._security_groups = []

		# Start thread for periodic updates
		self.updatethread = threading.Thread(group=None, target=self.run, name="%s-%s" % (self.publicdata.name, self.publicdata.url), args=(), kwargs={})
		self.updatethread.start()

	def _check_connection_attributes(self, cloud):
		if "access_id" not in cloud:
			raise EC2CloudConnectionError("access_id attribute is required")
		if "password" not in cloud:
			raise EC2CloudConnectionError("password attribute is required")
		if "region" not in cloud:
			raise EC2CloudConnectionError("region attribute is required")

	def _create_connection(self, cloud):
		logger.debug("Creating connection to %s" % cloud["region"])
		params = {}
		for param in cloud:
			if param in EC2_CONNECTION_ATTRIBUTES and cloud[param]:
				params[EC2_CONNECTION_ATTRIBUTES[param]] = cloud[param]

		os = get_driver(PROVIDER_MAPPING[cloud["region"]])

		p = params.copy()
		p["secret"] = "******"
		logger.debug("params passed to driver: %s" % p)
		self.driver = os(**params)

	def update_expensive(self):
		logger.debug("Expensive update for %s: %s" % (self.publicdata.name, self.publicdata.url))
		# self._images = self._exec_libcloud(lambda: self.driver.list_images(ex_owner="aws-marketplace"))
		self._images = self._exec_libcloud(lambda: self.driver.list_images())
		self._sizes = self._exec_libcloud(lambda: self.driver.list_sizes())
		self._locations = self._exec_libcloud(lambda: self.driver.list_locations())
		self._keypairs = self._exec_libcloud(lambda: self.driver.list_key_pairs())
		self._security_groups = self._exec_libcloud(lambda: self.driver.ex_get_security_groups())  # ex_get_ for ec2!
		self._networks = self._exec_libcloud(lambda: self.driver.ex_list_networks())
		self._last_expensive_update = time.time()

	def list_instances(self, pattern="*"):
		regex = re.compile(fnmatch.translate(pattern), re.IGNORECASE)
		instances = []
		for instance in self._instances:
			if regex.match(instance.name) is not None or regex.match(instance.id) is not None:
				i = Cloud_Data_Instance()
				i.name = instance.name
				# filter detailed network information
				extra = instance.extra
				extra['network_interfaces'] = 'removed_by_ucs'
				i.extra = extra
				i.id = instance.id
				i.image = instance.extra['image_id']
				i.private_ips = instance.private_ips
				i.public_ips = instance.public_ips
				i.size = i.u_size_name = instance.size
				i.state = LIBCLOUD_EC2_UVMM_STATE_MAPPING[instance.state]
				i.uuid = instance.uuid
				i.available = self.publicdata.available

				instances.append(i)

		return instances

	def list_locations(self):
		locations = []
		for location in self._locations:
			l = Cloud_Data_Location()
			l.name = location.name
			l.id = location.id
			l.driver = location.driver.name
			l.country = location.country

			locations.append(l)

		return locations

	def list_secgroups(self):
		secgroups = []
		for secgroup in self._security_groups:
			s = Cloud_Data_Secgroup()
			s.id = secgroup.id
			s.name = secgroup.name
			s.description = secgroup.extra["description"]
			s.in_rules = secgroup.ingress_rules
			s.out_rules = secgroup.egress_rules
			s.extra = secgroup.extra
			s.tenant_id = secgroup.extra["owner_id"]

			secgroups.append(s)

		return secgroups

	def list_sizes(self):
		sizes = []
		for size in self._sizes:
			i = Cloud_Data_Size()
			i.name = size.name
			i.extra = size.extra
			i.id = size.id
			i.driver = size.driver.name
			i.uuid = size.uuid
			i.ram = size.ram
			i.disk = size.disk
			i.bandwidth = size.bandwidth
			i.price = size.price
			i.u_displayname = "%s - %s" % (i.id, i.name)

			sizes.append(i)

		return sizes

	def list_networks(self):
		networks = []
		for network in self._networks:
			s = Cloud_Data_Network()
			s.id = network.id
			s.name = network.name
			s.extra = network.extra
			s.cidr = network.cidr_block

			networks.append(s)

		return networks

	def list_images(self, pattern="*"):
		# Expand pattern with *
		pattern = "*%s*" % pattern
		regex = re.compile(fnmatch.translate(pattern), re.IGNORECASE)
		images = []
		for image in self._images:
			if ((image.name and regex.match(image.name)) or
				(image.id and regex.match(image.id)) or
				(image.extra['owner_id'] and regex.match(image.extra['owner_id']))):
				i = Cloud_Data_Image()
				i.name = image.name
				i.extra = image.extra
				i.id = image.id
				i.driver = image.driver.name
				i.uuid = image.uuid

				images.append(i)

		return images

	def _boot_instance(self, instance):
		self._exec_libcloud(lambda: self.driver.ex_start_node(instance))

	def _softreboot_instance(self, instance):
		self._exec_libcloud(lambda: self.driver.reboot_node(instance))

	def _reboot_instance(self, instance):
		raise EC2CloudConnectionError("RESTART: Not yet implemented")

	def _pause_instance(self, instance):
		raise EC2CloudConnectionError("PAUSE: Not yet implemented")

	def _unpause_instance(self, instance):
		raise EC2CloudConnectionError("RESUME: Not yet implemented")

	def _shutdown_instance(self, instance):
		raise EC2CloudConnectionError("SHUTDOWN: Not yet implemented")

	def _shutoff_instance(self, instance):
		self._exec_libcloud(lambda: self.driver.ex_stop_node(instance))

	def _suspend_instance(self, instance):
		raise EC2CloudConnectionError("SUSPEND: Not yet implemented")

	def _resume_instance(self, instance):
		raise EC2CloudConnectionError("RESUME: Not yet implemented")

	def instance_state(self, instance_id, state):
		# instance is a libcloud.Node object
		instance = self._get_instance_by_id(instance_id)

		OS_TRANSITION = {
				# (NodeState.TERMINATED, "*"): None, cannot do anything with terminated instances
				(NodeState.RUNNING,    "RUN"): None,
				(NodeState.PENDING,    "RUN"): None,
				(NodeState.UNKNOWN,    "RUN"): self._boot_instance,
				(NodeState.STOPPED,    "RUN"): self._boot_instance,
				(NodeState.RUNNING,    "SOFTRESTART"): self._reboot_instance,
				(NodeState.PENDING,    "RESTART"): None,
				(NodeState.RUNNING,    "SHUTDOWN"): self._shutdown_instance,
				(NodeState.RUNNING,    "SHUTOFF"): self._shutoff_instance,
				(NodeState.REBOOTING,  "SHUTOFF"): self._shutoff_instance,
				(NodeState.PENDING,    "SHUTOFF"): self._shutoff_instance,
				(NodeState.UNKNOWN,    "SHUTOFF"): self._shutoff_instance,
				}
		logger.debug("STATE: connection: %s instance %s (id:%s), oldstate: %s (%s), requested: %s" % (self.publicdata.name, instance.name, instance.id, instance.state, instance.state, state))
		try:
			transition = OS_TRANSITION[(instance.state, state)]
			if transition:
				transition(instance)
			else:
				logger.debug("NOP state transition: %s -> %s" % (instance.state, state))
		except KeyError:
			raise EC2CloudConnectionError("Unsupported State transition (%s -> %s) requested" % (instance.state, state))
		except Exception, e:
			raise EC2CloudConnectionError("Error trying to %s instance %s (id:%s): %s" % (state, instance.name, instance_id, e))
		logger.debug("STATE: done")
		self.timerEvent.set()

	def instance_terminate(self, instance_id):
		# instance is a libcloud.Node object
		instance = self._get_instance_by_id(instance_id)
		name = instance.name
		try:
			self._exec_libcloud(lambda: self.driver.destroy_node(instance))
			# Update instance information
			self.timerEvent.set()
		except Exception, e:  # Unfortunately, libcloud only throws "Exception"
			raise EC2CloudConnectionError("Error while destroying instance %s (id:%s): %s" % (name, instance_id, e))
		logger.info("Destroyed instance %s (id:%s), using connection %s" % (name, instance_id, self.publicdata.name))

	def instance_create(self, args):
		# Check args
		kwargs = {}
		if "name" not in args:
			raise EC2CloudConnectionError("<name> attribute required for new instance")
		else:
			kwargs[EC2_CREATE_ATTRIBUTES["name"]] = args["name"]

		if "keyname" not in args:
			raise EC2CloudConnectionError("<keyname> attribute required for new instance")
		else:
			key = [kp for kp in self._keypairs if kp.name == args["keyname"]]
			if not key:
				raise EC2CloudConnectionError("No keypair with name %s found." % args["keyname"])

			kwargs[EC2_CREATE_ATTRIBUTES["keyname"]] = args["keyname"]

		if "size_id" not in args:
			raise EC2CloudConnectionError("<size_id> attribute required for new instance")
		else:
			size = [s for s in self._sizes if s.id == args["size_id"]]
			if not size:
				raise EC2CloudConnectionError("No size with id %s found." % args["size_id"])

			kwargs[EC2_CREATE_ATTRIBUTES["size_id"]] = size[0]

		if "image_id" not in args:
			raise EC2CloudConnectionError("<image_id> attribute required for new instance")
		else:
			image = [i for i in self._images if i.id == args["image_id"]]
			if not image:
				raise EC2CloudConnectionError("No image with id %s found." % args["image_id"])

			kwargs[EC2_CREATE_ATTRIBUTES["image_id"]] = image[0]

		if "location_id" in args:
			if not isinstance(args["location_id"], str):
				raise EC2CloudConnectionError("<location_id> attribute must be a string")
			kwargs[EC2_CREATE_ATTRIBUTES["location_id"]] = args["location_id"]

		if "userdata" in args:
			if not (isinstance(args["userdata"], str) or isinstance(args["userdata"], unicode)):
				raise EC2CloudConnectionError("<userdata> attribute must be a string")
			kwargs[EC2_CREATE_ATTRIBUTES["userdata"]] = args["userdata"]

		if "metadata" in args:
			if not isinstance(args["metadata"], dict):
				logger.debug("metadata type: %s" % args["metadata"].__class__)
				raise EC2CloudConnectionError("<metadata> attribute must be a dict")
			kwargs[EC2_CREATE_ATTRIBUTES["metadata"]] = args["metadata"]

		if "security_group_ids" in args:
			if not (isinstance(args["security_group_ids"], list)):
				raise EC2CloudConnectionError("<security_group_ids> attribute must be a list")

			secgroups = [s for s in self._security_groups if s.id in args["security_group_ids"]]
			if not secgroups:
				raise EC2CloudConnectionError("No security group with id %s found." % args["security_group_ids"])

			kwargs[EC2_CREATE_ATTRIBUTES["security_group_ids"]] = [s.name for s in secgroups]

		if "min_instance_count" in args:
			if not (isinstance(args["min_instance_count"], int)):
				raise EC2CloudConnectionError("<min_instance_count> attribute must be an integer")
			kwargs[EC2_CREATE_ATTRIBUTES["min_instance_count"]] = args["min_instance_count"]

		if "max_instance_count" in args:
			if not (isinstance(args["max_instance_count"], int)):
				raise EC2CloudConnectionError("<max_instance_count> attribute must be an integer")
			kwargs[EC2_CREATE_ATTRIBUTES["max_instance_count"]] = args["max_instance_count"]

		if ("min_instance_count" in args) and ("max_instance_count" in args):
			if args["min_instance_count"] >= args["max_instance_count"]:
				raise EC2CloudConnectionError("<min_instance_count> must be smaller than <max_instance_count>")

		if "clienttoken" in args:
			if not (isinstance(args["clienttoken"], str)):
				raise EC2CloudConnectionError("<clienttoken> attribute must be a string")
			kwargs[EC2_CREATE_ATTRIBUTES["clienttoken"]] = args["clienttoken"]

		if "blockdevicemappings" in args:
			if not (isinstance(args["blockdevicemappings"], list)):
				raise EC2CloudConnectionError("<blockdevicemappings> attribute must be a list")
			kwargs[EC2_CREATE_ATTRIBUTES["blockdevicemappings"]] = args["blockdevicemappings"]

		if "iamprofile" in args:
			if not (isinstance(args["iamprofile"], str)):
				raise EC2CloudConnectionError("<iamprofile> attribute must be a string")
			kwargs[EC2_CREATE_ATTRIBUTES["iamprofile"]] = args["iamprofile"]

		if "ebs_optimized" in args:
			if not (isinstance(args["ebs_optimized"], bool)):
				raise EC2CloudConnectionError("<ebs_optimized> attribute must be a bool")
			kwargs[EC2_CREATE_ATTRIBUTES["ebs_optimized"]] = args["ebs_optimized"]

		if "subnet" in args:
			if not (isinstance(args["subnet"], str)):
				raise EC2CloudConnectionError("<subnet> attribute must be a string")
			kwargs[EC2_CREATE_ATTRIBUTES["subnet"]] = args["subnet"]

		# libcloud call
		try:
			logger.debug("CREATE INSTANCE, connection:%s ARGS: %s" % (self.publicdata.name, kwargs))
			self._exec_libcloud(lambda: self.driver.create_node(**kwargs))
		except Exception, e:
			raise EC2CloudConnectionError("Instance could not be created: %s" % e)

	# Execute lambda function
	def _exec_libcloud(self, func):
		try:
			return func()
		except InvalidCredsError as e:
			logger.error("Invalid credentials provided for connection %s: %s" % (self.publicdata.name, self.publicdata.url))
			raise
		except MalformedResponseError as e:
			logger.error("Malformed response from connection, correct endpoint specified? %s: %s; %s" % (self.publicdata.name, self.publicdata.url, str(e)))
			raise
		except ProviderError as e:
			logger.error("Connection %s: %s: httpcode: %s, %s" % (self.publicdata.name, self.publicdata.url, e.http_code, e))
			raise
		except IdempotentParamError as e:
			logger.error("Connection %s: %s, same client token sent, but made different request" % (self.publicdata.name, self.publicdata.url))
			raise
		except KeyPairDoesNotExistError as e:
			logger.error("Connection %s: %s the requested keypair does not exist" % (self.publicdata.name, self.publicdata.url))
			raise
		except LibcloudError as e:
			logger.error("Connection %s: %s: %s" % (self.publicdata.name, self.publicdata.url, e))
			raise
		except ssl.SSLError as e:
			logger.error("Error with SSL connection %s: %s: %s" % (self.publicdata.name, self.publicdata.url, e))
			raise
		except Exception as e:
			if hasattr(e, 'errno'):
				if e.errno == errno.ECONNREFUSED:
					logger.error("Connection %s: %s refused (ECONNREFUSED)" % (self.publicdata.name, self.publicdata.url))
				elif e.errno == errno.EHOSTUNREACH:
					logger.error("Connection %s: %s no route to host (EHOSTUNREACH)" % (self.publicdata.name, self.publicdata.url))

				else:
					logger.error("Unknown exception %s with unknown errno %s: %s" % (self.publicdata.name, e.errno, self.publicdata.url), exc_info=True)
			elif hasattr(e, 'message'):
				logger.error("%s: %s Error: %s" % (self.publicdata.name, self.publicdata.url, e.message))
				if "RequestExpired" in e.message:
					raise EC2CloudConnectionError("RequestExpired for connection %s, check system time" % self.publicdata.name)
			else:
				logger.error("Unknown exception %s: %s, %s" % (self.publicdata.name, self.publicdata.url, dir(e)), exc_info=True)
			raise

if __name__ == '__main__':
	import doctest
	doctest.testmod()
