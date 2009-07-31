#!/usr/bin/python2.4
# -*- coding: utf-8 -*-
#
# Univention Installer
#  installer module: network configuration
#
# Copyright (C) 2004-2009 Univention GmbH
#
# http://www.univention.de/
#
# All rights reserved.
#
# This program is free software; you can redistribute it and/or modify
# it under the terms of the GNU General Public License version 2 as
# published by the Free Software Foundation.
#
# Binary versions of this file provided by Univention to you as
# well as other copyrighted, protected or trademarked materials like
# Logos, graphics, fonts, specific documentations and configurations,
# cryptographic keys etc. are subject to a license agreement between
# you and Univention.
#
# This program is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU General Public License for more details.
#
# You should have received a copy of the GNU General Public License
# along with this program; if not, write to the Free Software
# Foundation, Inc., 51 Franklin St, Fifth Floor, Boston, MA  02110-1301  USA

#
# Results of previous modules are placed in self.all_results (dictionary)
# Results of this module need to be stored in the dictionary self.result (variablename:value[,value1,value2])
#

import objects, re, string, curses
from objects import *
from local import _
import inspect
import os, subprocess

class object(content):

	def __init__(self,max_y,max_x,last=(1,1), file='/tmp/installer.log', cmdline={}):
		content.__init__(self,max_y,max_x,last, file, cmdline)

		if self.cmdline.has_key('mode') and self.cmdline['mode'] == 'setup':
			self.already_redraw=1
		else:
			self.already_redraw=0

		self.interfaces=[]

		#For more nameservers and dns-forwarders
		self.dns={}

	def debug(self, txt):
		info = inspect.getframeinfo(inspect.currentframe().f_back)[0:3]
		line = info[1]
		content.debug(self, 'NETWORK:%d: %s' % (line,txt))

##	Uncomment this to prevent the ESC-Key close a window that has a sub or warning window
#
#	def kill_subwin(self):
#		#self.debug('kill_subwin(net module)')
#		#Defined to prevent subwin from killing
#		if hasattr(self.sub, 'sub'):
#			self.sub.sub.exit()
#		elif hasattr(self.sub, 'warn'):
#			delattr(self.sub,'warn')
#			self.draw()
#		else:
#			self.sub.exit()

	def dhclient(self, interface):
		self.debug('DHCP broadcast on %s' % interface)
		tempfilename='/tmp/dhclient%s.out' % os.getpid()
		open(tempfilename, 'w').close()	# touch the file in case dhclient does not receive a propper answer
		cmd='/sbin/dhclient -lf /tmp/dhclient.leases -sf /lib/univention-installer/dhclient-script-wrapper -e dhclientscript_outputfile="%s" %s' % (tempfilename, interface)
		p = subprocess.Popen(cmd, shell=True, stderr=subprocess.PIPE, stdout=subprocess.PIPE)
		self.debug('DHCP output: %s' % p.stderr.read())
		file = open(tempfilename)
		dhcp_dict={}
		for line in file.readlines():
			key, value = line.strip().split(':', 1)
			dhcp_dict[key]=value.strip()
		self.debug('DHCP answer: %s' % dhcp_dict)
		file.close()
		os.unlink(tempfilename)
		return dhcp_dict

	def start(self):
		for i in range(0,4):
			if self.all_results.has_key('eth%d_type' % i) and (self.all_results['eth%d_type' % i] == 'dynamic' or self.all_results['eth%d_type' % i] == 'dhcp'):
				self.interfaces.append(['eth%d' % i, '', '', '', '', 'dynamic', 0])
			elif self.all_results.has_key('eth%d_ip' % i) and self.all_results['eth%d_ip' % i] and self.all_results.has_key('eth%d_netmask' % i) and self.all_results.has_key('eth%d_broadcast' % i) and self.all_results.has_key('eth%d_network' % i):
				self.interfaces.append(['eth%d' % i, self.all_results['eth%d_ip' % i], self.all_results['eth%d_netmask' % i], self.all_results['eth%d_broadcast' % i], self.all_results['eth%d_network' % i], 'static', 0])
			for j in range(0,4):
				if self.all_results.has_key('eth%d:%d_type' % (i,j)) and self.all_results['eth%d:%d_type' % (i,j)] and (self.all_results['eth%d:%d_type' % (i,j)] == 'dynamic' or self.all_results['eth%d:%d_type' % (i,j)] == 'dhcp'):
					self.interfaces.append(['eth%d:%d' % (i,j), '', '', '', '', 'dynamic', 'virtual'])
				elif self.all_results.has_key('eth%d:%d_ip' % (i,j)) and self.all_results['eth%d:%d_ip' % (i,j)] and self.all_results.has_key('eth%d:%d_netmask' % (i,j)) and self.all_results.has_key('eth%d:%d_broadcast' % (i,j)) and self.all_results.has_key('eth%d:%d_network' % (i,j)):
					self.interfaces.append(['eth%d:%d' % (i,j), self.all_results['eth%d:%d_ip' % (i,j)], self.all_results['eth%d:%d_netmask' % (i,j)], self.all_results['eth%d:%d_broadcast' % (i,j)], self.all_results['eth%d:%d_network' % (i,j)], 'static', 'virtual'])
				elif self.all_results.has_key('eth%d_%d_ip' % (i,j)) and self.all_results.has_key('eth%d_%d_ip' % (i,j)) and self.all_results.has_key('eth%d_%d_netmask' % (i,j)) and self.all_results.has_key('eth%d_%d_broadcast' % (i,j)) and self.all_results.has_key('eth%d_%d_network' % (i,j)):
					self.interfaces.append(['eth%d:%d' % (i,j), self.all_results['eth%d_%d_ip' % (i,j)], self.all_results['eth%d_%d_netmask' % (i,j)], self.all_results['eth%d_%d_broadcast' % (i,j)], self.all_results['eth%d_%d_network' % (i,j)], 'static', 'virtual'])

		if self.all_results.has_key('gateway'):
			self.container['Gateway']=[]
			self.container['Gateway'].append(self.all_results['gateway'])
		if self.all_results.has_key('proxy_http'):
			self.container['proxy_http']=[]
			self.container['proxy_http'].append(self.all_results['proxy_http'])
		if self.all_results.has_key('nameserver_1'):
			self.container['Nameserver']=[]
			self.container['Nameserver'].append(self.all_results['nameserver_1'])
		if self.all_results.has_key('dns_forwarder_1'):
			self.container['DNS-Forwarder']=[]
			self.container['DNS-Forwarder'].append(self.all_results['dns_forwarder_1'])

		for key in  ['nameserver_2', 'nameserver_3', 'dns_forwarder_2', 'dns_forwarder_3']:
			if self.all_results.has_key(key):
				self.dns[key]=self.all_results[key]

		if self.cmdline:
			if self.cmdline.has_key('interface'):
				self.mode='edit'
				self.sub=self.edit(self,self.minY,self.minX+3,self.maxWidth-10,self.maxHeight-8,'edit')
				self.sub.draw()

	def checkname(self):
		return ['gateway','eth0_ip','eth0_netmask','eth0_broadcast','eth0_network']

	def modvars(self):
		return ['gateway','eth0_type', 'eth0_ip','eth0_netmask','eth0_broadcast','eth0_network', 'proxy_http', 'nameserver_1', 'nameserver_2', 'nameserver_3', 'dns_forwarder_1', 'dns_forwarder_2', 'dns_forwarder_3' ]

	def profile_prerun(self):
		self.already_redraw=1
		if self.all_results.has_key('gateway'):
			self.container['Gateway']=[]
			self.container['Gateway'].append(self.all_results['gateway'])
		if self.all_results.has_key('nameserver_1'):
			self.container['Nameserver']=[]
			self.container['Nameserver'].append(self.all_results['nameserver_1'])
		if self.all_results.has_key('dns_forwarder_1'):
			self.container['DNS-Forwarder']=[]
			self.container['DNS-Forwarder'].append(self.all_results['dns_forwarder_1'])
		if self.all_results.has_key('proxy_http'):
			self.container['proxy_http']=[]
			self.container['proxy_http'].append(self.all_results['proxy_http'])

		for key in  ['nameserver_2', 'nameserver_3', 'dns_forwarder_2', 'dns_forwarder_3']:
			if self.all_results.has_key(key):
				self.dns[key]=self.all_results[key]

		for i in range(0,4):
			for j in range(0,4):
				for ekey in ['type', 'ip','netmask','broadcast','network']:
					key='eth%d:%d_%s' % (i,j,ekey)
					if self.all_results.has_key(key):
						self.container[key]=self.all_results[key]
			for ekey in ['type', 'ip','netmask','broadcast','network']:
				key='eth%d_%s' % (i,ekey)
				if self.all_results.has_key(key):
					self.container[key]=self.all_results[key]

	def profile_complete(self):
		if self.check('gateway') | self.check('nameserver_1') | self.check('nameserver_2') | self.check('nameserver_3') | \
			self.check('dns_forwarder_1') | self.check('dns_forwarder_2') | self.check('dns_forwarder_3') | \
			self.check('eth0_type') | self.check( 'eth0_ip') | self.check('eth0_netmask') | self.check('eth0_broadcast') | self.check('eth0_network') | \
			self.check('eth1_type') | self.check( 'eth1_ip') | self.check('eth1_netmask') | self.check('eth1_broadcast') | self.check('eth1_network') | \
			self.check('eth2_type') | self.check( 'eth2_ip') | self.check('eth2_netmask') | self.check('eth2_broadcast') | self.check('eth2_network') | \
			self.check('eth3_type') | self.check( 'eth3_ip') | self.check('eth3_netmask') | self.check('eth3_broadcast') | self.check('eth3_network'):
			return False
		invalid=_("Following value is invalid: ")
		if not self.all_results['gateway'].strip() == '':
			if not self.is_ip(self.all_results['gateway']):
				if not self.ignore('gateway'):
					self.message=invalid+_("Gateway")
					return False
		if not self.all_results['nameserver_1'].strip() == '':
			if not self.is_ip(self.all_results['nameserver_1']):
				if not self.ignore('nameserver_1'):
					self.message=invalid+_("Name server")
					return False
		if not self.all_results['dns_forwarder_1'].strip() == '':
			if not self.all_results['dns_forwarder_1']:
				if not self.ignore('dsn_forwarder_1'):
					self.message=invalid+_("DNS Forwarder")
					return False

		proxy = self.all_results['proxy_http'].strip()
		self.debug('PROXY=%s' % proxy)
		if proxy and proxy !='http://' and proxy !='https://':
			if not (proxy.startswith('http://') or proxy.startswith('https://')):
				if not self.ignore('proxy_http'):
					self.debug('PROXY INVALID!')
					self.message=invalid+_('Proxy, example http://10.201.1.1:8080')
					return False

		_re=re.compile('eth.*_ip')
		_re2=re.compile('eth.*_type')
		interfaces=[]
		complete=[]
		for key in self.all_results.keys():
			self.debug('check key = [%s]' % key)
			if _re.match(key) and len(self.all_results[key]) > 0:
				self.debug('re match')
				key=key.replace('_ip', '')
				if not key in interfaces:
					interfaces.append(key)
					self.debug('append interface %s' % key)
			elif _re2.match(key) and len(self.all_results[key]) > 0:
				self.debug('re2 match')
				complete.append(key.replace('_type',''))

		for i in interfaces:
			ip='%s_ip' % i
			netmask='%s_netmask' % i
			broadcast='%s_broadcast' % i
			network='%s_network' % i
			keys=self.all_results.keys()
			if ip in keys and broadcast in keys and network in keys and netmask in keys:
				complete.append(i)

		if len(complete) < 1:
			if not self.ignore('interfaces'):
				self.message=_("You have to add one or more Network interfaces.")
				return False

		return True

	def profile_f12_run(self):
		# send the F12 key event to the subwindow
		if hasattr(self, 'sub'):
			self.sub.input(276)
			self.sub.exit()
			return 1

	def formdict(self, interfaces):
		tmpinterfaces=[]
		self.mapping=[]
		count=0
		interfaces.sort()
		vorher=''
		for l  in interfaces:

			if not l[0].startswith(vorher) and not l[0].split(':')[0].startswith(vorher.split(':')[0]):
				tmpinterfaces.append('   %s' %_('New Virtual Device'))
				self.mapping.append([_('New Virtual Device'),count])
				count+=1

			if l[5] == 'dynamic':
				if l[6] == 'virtual':
					tmpinterfaces.append('   %-10s %s' %(l[0], _('Dynamic (DHCP)')))
				else:
					tmpinterfaces.append('%-10s %s' %(l[0], _('Dynamic (DHCP)')))
			else:
				if l[6] == 'virtual':
					tmpinterfaces.append('   %-10s%-18s%-16s' %(l[0], l[1], l[2]))
				else:
					tmpinterfaces.append('%-10s%-18s%-16s' %(l[0], l[1], l[2]))

			self.mapping.append([l[0],count])

			vorher=l[0]
			count+=1

		tmpinterfaces.append('   %s'%_('New Virtual Device'))
		self.mapping.append([_('New Virtual Device'), count])
		count+=1
		tmpinterfaces.append(_('New Device'))
		self.mapping.append([_('New Device'),count])
		count+=1
		return tmpinterfaces

	def addinterface(self, dev, ip, netm, broad, netw, mode, virtual=''):
		#Add an interface to the list
		if ip == '' and not mode in ['dynamic', 'dhcp']:
			return 1
		remove_list=[]
		for i in range(0,len(self.interfaces)):
			if self.interfaces[i][0] == dev:
				remove_list.append(self.interfaces[i])
		for i in range(0,len(remove_list)):
			self.interfaces.remove(remove_list[i])
		self.debug('Adding Interface %s with Options [%s, %s, %s, %s, %s, %s]'%(dev, ip, netm, broad, netw, mode, virtual))
		self.interfaces.append([dev, ip, netm, broad, netw, mode, virtual])
		self.redraw()
		return 1

	def delinterface(self):
		device=self.ifaceselected()
		self.debug('Deleting Interface: "%s"'%self.ifaceselected())
		if device:
			self.interfaces.remove(device)
			self.redraw()

	def redraw(self):
		#For secure redrawing of the main window. Saving all values.
		self.debug('Redrawing Main Window')
		self.container['Gateway']=[self.elements[8].result().strip()]
		self.container['Nameserver']=[self.elements[10].result().strip()]
		self.container['DNS-Forwarder']=[self.elements[13].result().strip()]
		self.container['proxy_http']=[self.elements[16].result().strip()]
		self.container['current']=self.current
		if self.already_redraw:
			self.already_redraw=1
			self.layout()
		else:
			self.already_redraw=1
			self.layout()
			self.elements[3].set_off()
			self.elements[0].set_off()
			self.current=8
			self.elements[8].set_on()
		self.draw()

	def nextiface(self, iface=''):
		'''
		Generate the next available real or virtual interface.
		'''
		self.debug('NetxInterface')
		if len(self.interfaces) < 1: #nextiface is called the first time, dont return eth0+1
			return 'eth0'
		if iface == '': #Get the next real interface
			count=0
			for dev in self.interfaces:
				if dev[0].startswith('eth') and dev[6] == '': #Real Interface
					if dev[0][3:] >= count:
						count=int(dev[0][3:])
			count+=1
			return 'eth%d'%count
		elif iface and iface.startswith('eth'):
			count=[]
			#example: [device, ip, netmask, broadcast, network, mode, virtual='']
			for dev in self.interfaces:
				if dev[0].startswith(iface) and dev[6] == 'virtual': #Virtual interface
					count.append(int(dev[0].split(':')[1]))
			i=0
			for i in range(0,len(count)):
				if i != count[i]:
					break
				i+=1
			return '%s:%d' %(iface,i)
		else:
			return 1

	def getnext(self):
		'''
		Get the next interface to configure, uses nextiface()
		'''
		self.debug('Getnext')
		line=self.elements[3].result()[0]
		self.debug('Line: %s'%self.elements[3].result())
		if line:
			entry=self.mapping[line][0].strip()
			if entry == _('New Device'):
				dev=self.nextiface()
				return [entry, dev]
			elif entry == _('New Virtual Device'):
				device=self.mapping[line-1][0].strip() #Get line-1
				if len(device.split(':')) > 1:
					device=device[:device.rfind(':')]
				dev=self.nextiface(device)
				return [entry, dev]
			elif entry.startswith('eth'):
				self.debug('NextIface="%s"'%self.nextiface())
				return ['',self.nextiface()]
		else:
			return ['',self.nextiface()]

	def ifaceselected(self):
		'''
		Get the selected line from the selectbox and check if it is an interface
		'''
		line=self.elements[3].result()[0]
		entry=self.mapping[line][0].strip()
		device=[]
		if entry == _('New Device'):
			return 0
		elif entry == _('New Virtual Device'):
			return 0
		elif entry.startswith('eth'):
			for i in range(0,len(self.interfaces)):
				if self.interfaces[i][0] == entry:
					device=self.interfaces[i]
					break
			return device
		else:
			return 0

	def layout(self):
		MAXIP=18
		self.elements=[]
		self.std_button()
		text=_('Device        IP               Netmask')
		self.elements.append(textline(text,self.minY,self.minX+2)) #2

		self.elements.append(select(self.formdict(self.interfaces),self.minY+1,self.minX+2,self.maxWidth-4,4))#3
		self.elements.append(button(_('F2-Add'),self.minY+6,self.minX+2,13))#4
		self.elements.append(button(_('F3-Edit'),self.minY+6,self.minX+(self.width/2)-3,align="middle"))#5
		self.elements.append(button(_('F4-Delete'),self.minY+6,self.minX+(self.width)-4,align="right"))#6

		# - Gateway
		self.elements.append(textline(_('Gateway'),self.minY+10,self.minX+2)) #7
		if not self.container.has_key('Gateway'):
			self.elements.append(input('',self.minY+10,self.minX+20,MAXIP+8)) #8
		else:
			self.elements.append(input('%s'%self.container['Gateway'][0],self.minY+10,self.minX+20,MAXIP+8)) #8

		# - Nameserver
		self.elements.append(textline(_('Name server'),self.minY+12,self.minX+2)) #9
		if not self.container.has_key('Nameserver'):
			self.elements.append(input('',self.minY+12,self.minX+20,MAXIP+8)) #10
		else:
			self.elements.append(input('%s'%self.container['Nameserver'][0],self.minY+12,self.minX+20,MAXIP+8)) #10
		self.elements.append(button(_('More'),self.minY+12,self.minX+(self.width)-4,align="right")) #11

		# - DNS Forwarder
		self.elements.append(textline(_('DNS Forwarder'),self.minY+14,self.minX+2)) #12
		if not self.container.has_key('DNS-Forwarder'):
			self.elements.append(input('',self.minY+14,self.minX+20,MAXIP+8)) #13
		else:
			self.elements.append(input('%s'%self.container['DNS-Forwarder'][0],self.minY+14,self.minX+20,MAXIP+8)) #13
		self.elements.append(button(_('More'),self.minY+14,self.minX+(self.width)-4,align="right")) #14

		# - Proxy
		self.elements.append(textline(_('HTTP proxy'),self.minY+16,self.minX+2)) #15
		if not self.container.has_key('proxy_http'):
			self.elements.append(input('http://',self.minY+16,self.minX+20,MAXIP+8)) #16
		else:
			self.elements.append(input('%s'%self.container['proxy_http'][0],self.minY+16,self.minX+20,MAXIP+8)) #16

		if not self.already_redraw:
			#add first device
			init=1
			for i in range(0, len(self.interfaces)):
				if self.interfaces[i][0].startswith('eth'):
					init=0
			if init:
				if os.system('/bin/ifconfig -a| grep eth0 >/dev/null') != 0:
					self.debug("could not find eth0")
					msglist=[_('Currently no network card could be detected. Depending on'),
							 _('the selected services and system role an operative network'),
							 _('card is required to successfully complete the installation.'),
							 _('Please check the network card of the computer.'),
							 _('If a network card is installed, try to load additional'),
							 _('kernel modules at the beginning of the installation.'),
							 _('If the installation will be continued without operative'),
							 _('network card, a virtual dummy network card will be loaded'),
							 _('automatically to complete installation.'),
							 ]
					self.sub=msg_win(self, self.pos_y+4, self.pos_x-16, self.width+12, self.height-18, msglist)
					self.needs_draw_all = True
					self.sub.draw()
				else:
					self.sub=self.edit(self,self.minY,self.minX+3,self.maxWidth-10,self.maxHeight-8)
					self.sub.draw()

	def input(self,key):
		#self.debug('DEBUG: input(net object): %d' % key)
		if hasattr(self,"sub"):
			resultkey=self.sub.input(key)
			if not resultkey:
				self.subresult=self.sub.get_result()
				self.sub.exit()
				self.draw()
			elif resultkey == 'tab':
				self.sub.tab()
		elif key == 266:# F2 - Add
			self.sub=self.edit(self,self.minY,self.minX,self.maxWidth,self.maxHeight-8)
			self.sub.draw()
		elif key == 267:# F3 - Edit
			if self.ifaceselected():
				self.sub=self.edit(self,self.minY,self.minX,self.maxWidth,self.maxHeight-8,'edit')
				self.sub.draw()
			else:
				pass
		elif key == 268:# F4 - Delete
			self.delinterface()
		elif key in [ 10, 32 ] and self.btn_next():
			return 'next'
		elif key in [ 10, 32 ] and self.btn_back():
			return 'prev'
		elif key in [ 10, 32 ] and self.elements[4].usable() and self.elements[4].get_status():# Enter & Button: Add
			if not self.ifaceselected():
				self.sub=self.edit(self,self.minY,self.minX+3,self.maxWidth-10,self.maxHeight-8)
				self.sub.draw()
			else:
				pass
		elif key in [ 10, 32 ] and self.elements[5].usable() and self.elements[5].get_status():# Enter & Button: Edit
			if self.ifaceselected():
				self.sub=self.edit(self,self.minY,self.minX+3,self.maxWidth-10,self.maxHeight-8,'edit')
				self.sub.draw()
			else:
				pass
		elif key in [ 10, 32 ] and self.elements[6].usable() and self.elements[6].get_status():# Enter & Button: Delete
			self.delinterface()
		elif key in [ 10, 32 ] and self.elements[11].usable() and self.elements[11].get_status():# Enter & Button: More Nameserver
			if not self.elements[10].result().strip() == '' and self.is_ip(self.elements[10].result().strip()):
				self.sub=self.more(self,self.minY+4,self.minX+3,self.maxWidth-10,self.maxHeight-8, _("Name server"))
				self.sub.draw()
			else:
				#DNS-Forwarder input is not filled
				pass
		elif key in [ 10, 32 ] and self.elements[14].usable() and self.elements[14].get_status():# Enter & Button: More DNS-Forwarder
			if not self.elements[13].result().strip() == '' and self.is_ip(self.elements[13].result().strip()):
				self.sub=self.more(self,self.minY+4,self.minX+3,self.maxWidth-10,self.maxHeight-8, _("DNS Forwarder"))
				self.sub.draw()
			else:
				#DNS-Forwarder input is not filled
				pass

		elif key == curses.KEY_DOWN or key == curses.KEY_UP:
			self.elements[3].key_event(key)
		elif key == 10 and self.elements[self.current].usable():
			return self.elements[self.current].key_event(key)
		else:
			self.elements[self.current].key_event(key)

	def incomplete(self):
		invalid=_("Following value is invalid: ")
		if not self.elements[8].result().strip() == '':
			if not self.is_ip(self.elements[8].result()):
				return invalid+_("Gateway")
		if not self.elements[10].result().strip() == '':
			if not self.is_ip(self.elements[10].result()):
				return invalid+_("Name server")
		if not self.elements[13].result().strip() == '':
			if not self.is_ip(self.elements[13].result()):
				return invalid+_("DNS Forwarder")
		if self.elements[16]:
			proxy = self.elements[16].result().strip()
			self.debug('PROXY=%s' % proxy)
			if proxy and not proxy.startswith('http://') and not proxy.startswith('https://'):
				self.debug('INVALID PROXY!')
				return invalid+_('Proxy, example http://10.201.1.1:8080')

		if len(self.interfaces) == 0:
			return _("You have to add one or more network interfaces.")
		return 0

	def helptext(self):
		return _('Network \n \n In this module the network configuration is done. \n \n Select \"New Interface\" to add a new interface. Select \"New Virtual Interface\" to create a new virtual interface. \n \n Interface: \n Select the interface you want to configure. \n \n Dynamic (DHCP): \n Mark this field if you want this interface to retrieve its IP configuration via DHCP (Dynamic Host Configuration Protocol). \n \n Static: \n Mark this field if you want this interface to be configured manually. \n \n Enter IP, netmask, broadcast and network address of this interface. \n\n Gateway: \n Default gateway to be use. \n \n Name server: \n Enter the IP address of the primary name server, if you are adding a system to an existing domain. \n More: \n Enter additional name servers \n \n DNS Forwarder: \n Enter the IP address of a DNS server to forward queries to. \n More: \n Enter additional DNS forwarders \n \n HTTP-Proxy: \n Enter the IP address and port number for the HTTP-Proxy (example: http://192.168.1.123:5858)')

	def modheader(self):
		return _('Network')

	def is_hostname(self, host):
		if len(host) < 1:
			return 0
		valid=1
		for i in host:
			if i.isdigit() or i in ['!', '#','*','.',':',';']:
				valid=0
				break
		return valid

	def is_port(self, port):
		if len(port) < 1:
			return 0
		for i in port:
			if not i.isdigit():
				return 0
		return 1

	def is_ip(self, ip):
		test=ip.split('.')
		if len(test) != 4:
			return 0
		else:
			for i in test:
				if not i.isdigit() or int(i) < 0 or int(i) > 255:
					return 0
		return 1

	def result(self):
		result={}
		if self.elements[8].result().strip():
			result['gateway']='%s' %self.elements[8].result().strip()
		else:
			result['gateway']=''
		if self.elements[10].result().strip():
			result['nameserver_1']='%s' %self.elements[10].result().strip()
		else:
			result['nameserver_1']=''
		if self.elements[13].result().strip():
			result['dns_forwarder_1']='%s' %self.elements[13].result().strip()
		else:
			result['dns_forwarder_1']=''

		proxy = self.elements[16].result().strip()
		result['proxy_http']=''
		if proxy and  proxy != 'http://' and proxy != 'https://':
			result['proxy_http']='%s' % proxy

		#Fill in more Forwarders and Nameservers
		for key in self.dns.keys():
			self.debug('[%s]=%s'%(key,self.dns[key]))
			result[key]=self.dns[key]

		#Fill in interfaces
		#example: [device, ip, netmask, broadcast, network, mode, virtual='']
		for dev in self.interfaces:
			if dev[6] == 'virtual':
				device=dev[0].replace(':','_')
			else:
				device=dev[0]

			if dev[5] in [ 'dynamic', 'dhcp']:
				result['%s_type'%device]=dev[5]
				if self.serverrole:
					result['%s_ip'%device]=dev[1]
					result['%s_netmask'%device]=dev[2]
					result['%s_broadcast'%device]=dev[3]
					result['%s_network'%device]=dev[4]
			else:
				result['%s_ip'%device]=dev[1]
				result['%s_netmask'%device]=dev[2]
				result['%s_broadcast'%device]=dev[3]
				result['%s_network'%device]=dev[4]

		for i in range(0,4):
			for val in ['ip', 'netmask', 'broadcast', 'network']:
				if not result.has_key('eth%d_%s' % (i,val)):
					result['eth%s_%s' % (i,val)]=''
			for j in range(0,4):
				for val in ['ip', 'netmask', 'broadcast', 'network']:
					if not result.has_key('eth%d_%d_%s' % (i,j,val)):
						result['eth%d_%d_%s' % (i,j,val)]=''

		return result

	class edit(subwin):
		def __init__(self,parent,pos_y,pos_x,width,heigh,mode=''):
			self.mode=mode
			self.tabinit=0
			subwin.__init__(self,parent,pos_y,pos_x,width,heigh)
			if 'system_role' in self.parent.all_results and (self.parent.all_results['system_role'] in [ 'managed_client',  'mobile_client', 'basesystem', 'fatclient', 'mobileclient', 'managedclient']):
				self.serverrole=False
			else:
				self.serverrole=True

		def layout(self):
			self.minY=self.parent.minY
			self.minX=self.parent.minX-16
			self.maxWidth=self.parent.maxWidth
			self.maxHeight=self.parent.maxHeight
			MAXIP=18
			#example: [device, ip, netmask, broadcast, network, mode, virtual='']
			if self.mode == 'edit':
				if not self.parent.cmdline.has_key('interface'): # The windows are not yet created in direct interface edit mode
					device=self.parent.ifaceselected()
				else:
					for i in range(0,len(self.parent.interfaces)):
						if self.parent.interfaces[i][0] == self.parent.cmdline['interface']:
							device=self.parent.interfaces[i]

			if self.mode == 'edit':
				interface_str=device[0]
			else:
				interface_str=self.parent.getnext()[1]

			if len(interface_str.strip().split(':')) > 1:
				virtual='virtual'
			else:
				virtual=''

			if self.mode == 'edit':
				ip_str=device[1]
				netmask_str=device[2]
				if device[5] == "dynamic":
					dhcp_checkbox_value=[0]
				else:
					dhcp_checkbox_value=[]
			else:
				ip_str=''
				netmask_str=''
				if not self.serverrole:
					dhcp_checkbox_value=[0]
				else:
					dhcp_checkbox_value=[]	# default for server roles

			self.add_elem('edit.TXT_INTERFACE', textline(_('Device:'),self.pos_y+2,self.pos_x+2))#0
			self.add_elem('edit.INPUT_INTERFACE', input(interface_str, self.pos_y+2, self.pos_x+10, 10))#1

			if not virtual:
				dict={_('Dynamic (DHCP)'): ['dhcp',1]}
				self.add_elem('edit.CHECKBOX_DHCP', checkbox(dict,self.pos_y+2,self.pos_x+31,18,2,dhcp_checkbox_value))#5

			self.add_elem('edit.TXT_IP', textline(_('IP address:'), self.pos_y+4, self.pos_x+2))#1
			self.add_elem('edit.INPUT_IP', input(ip_str, self.pos_y+4, self.pos_x+14, MAXIP))#2
			if not virtual:
				self.add_elem('edit.BUTTON_DHCLIENT', button('F5-'+_('DHCP Query'),self.pos_y+4,self.pos_x+(self.width)-4,align='right')) #12

			self.add_elem('edit.TXT_NETMASK', textline(_('Netmask:'), self.pos_y+5, self.pos_x+2))#3
			self.add_elem('edit.INPUT_NETMASK', input(netmask_str, self.pos_y+5, self.pos_x+14, MAXIP))#4

			self.add_elem('edit.BUTTON_CANCEL', button('ESC-'+_('Cancel'),self.pos_y+7,self.pos_x+4)) #12
			self.add_elem('edit.BUTTON_OK', button('F12-'+_('Ok'),self.pos_y+7,self.pos_x+(self.width)-4,align='right')) #11

			if not dhcp_checkbox_value:
				self.enable()	# enable the main edit textboxes
				self.current=self.get_elem_id('edit.INPUT_IP')	# set the tab cursor
			else:
				self.disable()	# disable the main edit textboxes
				self.current=self.get_elem_id('edit.BUTTON_DHCLIENT')	# set the tab cursor


			self.elements[self.current].set_on()		# set the focus highlight

		def disable(self):
			self.get_elem('edit.INPUT_IP').disable()
			self.get_elem('edit.INPUT_NETMASK').disable()

		def enable(self):
			self.get_elem('edit.INPUT_IP').enable()
			self.get_elem('edit.INPUT_NETMASK').enable()

		def tab(self):
			if not (self.elem_exists('edit.CHECKBOX_DHCP') and self.get_elem('edit.CHECKBOX_DHCP').result()) and self.tabinit <= 1:
				if self.current == self.get_elem_id('edit.INPUT_IP'):
					ip_str=self.get_elem('edit.INPUT_IP').result().strip()
					if ip_str and self.parent.is_ip(ip_str):
						element=self.get_elem('edit.INPUT_NETMASK')
						if not (element.text):
							element.text='255.255.255.0'
							element.set_cursor(len(element.text))
						self.tabinit=1	# traditional flag of unknown function
			subwin.tab(self)

		def ipcalc(self, ip, netmask):
			ip_list=ip.split('.')
			netmask_list=netmask.split('.')
			net=[]
			wildcard=[]
			pointerok=0
			broadcast=[]
			for i in range(4):
				try:
					int(ip_list[i])
				except ValueError:
					return ["",""]
				if netmask_list[i] == '255':
					net.append(ip_list[i])
					wildcard.append(0)
					broadcast.append(ip_list[i])
				else:
					net.append(str(int(ip_list[i]) & int(netmask_list[i])))
					if not pointerok:
						pointer=ip_list[i:]
						pointerok=1
					pointer.reverse()
					calc = 255 - int(netmask_list[i])
					if not calc:
						wildcard.append(0)
					wildcard.append(calc)
					calc = int(wildcard[i]) ^ int(net[i])
					if calc == '0' and i == '4':
						broadcast.append(str('255'))
					else:
						broadcast.append(str(calc))
			return [string.join(net,'.'),string.join(broadcast,'.')]

		def helptext(self):
			return self.parent.helptext()

		def modheader(self):
			return _(' Interface configuration')

		def put_result(self):
			result={}
			virtual=''
			if len(self.get_elem('edit.INPUT_INTERFACE').result().strip().split(':')) > 1:
				virtual='virtual'
			networkbcast=self.ipcalc(self.get_elem('edit.INPUT_IP').result().strip(),self.get_elem('edit.INPUT_NETMASK').result().strip())
			if (self.elem_exists('edit.CHECKBOX_DHCP') and self.get_elem('edit.CHECKBOX_DHCP').result()):
				mode='dynamic'
			else:
				mode='static'
			interface_parameters=[self.get_elem('edit.INPUT_IP').result().strip(), self.get_elem('edit.INPUT_NETMASK').result().strip(), networkbcast[1], networkbcast[0], mode, virtual]
			#example: result['eth0']=[ip, netmask, broadcast, network, mode]
			result[self.get_elem('edit.INPUT_INTERFACE').result().strip()]=interface_parameters
			#example: [device, ip, netmask, broadcast, network, mode, virtual='']
			self.parent.addinterface(self.get_elem('edit.INPUT_INTERFACE').result().strip(), *interface_parameters)
			return result

		def incomplete(self):
			missing=_('The following value is missing: ')
			invalid=_('The following value is invalid: ')
			#Device
			ethregexp=re.compile('^eth[0-9]+:[0-9]+$|^eth[0-9]+$')

			interface_str=self.get_elem('edit.INPUT_INTERFACE').result().strip()
			if interface_str == '':
				return missing+_('Device')
			elif not re.match(ethregexp, interface_str):
				return invalid+_('Device')

			ip_str=self.get_elem('edit.INPUT_IP').result().strip()
			if not (self.elem_exists('edit.CHECKBOX_DHCP') and self.get_elem('edit.CHECKBOX_DHCP').result()):
				netmask_str=self.get_elem('edit.INPUT_NETMASK').result().strip()
				#IP
				if ip_str == '':
					return missing+_('IP address')
				elif not self.parent.is_ip(ip_str.strip('\n')):
					return invalid+_('IP address')
				#Netmask
				elif netmask_str == '':
					return missing+_('Netmask')
				elif not self.parent.is_ip(netmask_str.strip('\n')):
					return invalid+_('Netmask')
				else:
					return 0
			else:
				if not self.serverrole:
					return 0
				else:
					return _('For a server role an IP address must be determined at this point, please press F5 or deselect the DHCP option')


		def input(self,key):
			#self.parent.debug('DEBUG: input(edit): %d' % key)
			if hasattr(self,'warn'):
				if not self.warn.key_event(key):
					delattr(self,"warn")
				self.parent.draw()
				self.draw()
			ok_button=self.get_elem('edit.BUTTON_OK')
			cancel_button=self.get_elem('edit.BUTTON_CANCEL')
			if ( key in [ 10, 32 ] and ok_button.usable() and ok_button.get_status() ) or key == 276: # Ok
				if self.incomplete() != 0:
					self.warn=warning(self.incomplete(),self.pos_y+25,self.pos_x+90)
					self.warn.draw()
					return 1
				self.put_result()
				return 0
			elif key in [ 10, 32 ] and cancel_button.usable() and cancel_button.get_status(): #Cancel
				return 0
			elif ( key in [ 10, 32 ] and self.elem_exists('edit.BUTTON_DHCLIENT') and self.get_elem('edit.BUTTON_DHCLIENT').usable() and self.get_elem('edit.BUTTON_DHCLIENT').get_status() ) or key == 269: # F5
				self.act = self.dhclient_active(self,_('DHCP Query'),_('Please wait ...'),name='act')
				self.act.draw()
			elif key in [ 10, 32 ] and self.elem_exists('edit.CHECKBOX_DHCP') and self.get_elem('edit.CHECKBOX_DHCP').usable() and self.get_elem('edit.CHECKBOX_DHCP').active: #Space in Checkbox
				dhcp_checkbox=self.get_elem('edit.CHECKBOX_DHCP')
				self.elements[self.current].key_event(32)	# send the event to the widget
				if dhcp_checkbox.result():
					self.disable()
					dhcp_checkbox.set_off()
					self.current=self.get_elem_id('edit.BUTTON_DHCLIENT')	# set the tab cursor
				else:
					self.enable()
					dhcp_checkbox.set_off()
					self.current=self.get_elem_id('edit.INPUT_IP')	# set the tab cursor
				self.get_elem_by_id(self.current).set_on()	# set the focus highlight
				self.draw()
			elif key == 260:
				#move left
				active=0
				for elemid in ['edit.BUTTON_OK']:
					if self.get_elem(elemid).active:
						active=self.get_elem_id(elemid)
				if active:
					self.get_elem_by_id(active).set_off()
					self.get_elem_by_id(active-1).set_on()
					self.current=active-1
					self.draw()
			elif key == 261:
				#move right
				active=0
				for elemid in ['edit.BUTTON_CANCEL']:
					if self.get_elem(elemid).active:
						active=self.get_elem_id(elemid)
				if active:
					self.get_elem_by_id(active).set_off()
					self.get_elem_by_id(active+1).set_on()
					self.current=active+1
					self.draw()
			elif self.elements[self.current].usable():
				self.elements[self.current].key_event(key)
			return 1

		class dhclient_active(act_win):
			def __init__(self,parent,header,text,name):
				# set this further right to avoid backdrop on left_menu, which fails to be redrawn
				self.pos_x=parent.minX+17
				self.pos_y=parent.minY+5
				act_win.__init__(self,parent,header,text,name)

			def function(self):
				interface=self.parent.get_elem('edit.INPUT_INTERFACE').result().strip()
				dhcp_dict=self.parent.parent.dhclient(interface)
				ip_input=self.parent.get_elem('edit.INPUT_IP')
				ip_input.text=dhcp_dict.get('address') or ''
				ip_input.set_cursor(len(ip_input.text))
				ip_input.paste_text()
				ip_input.draw()
				netmask_input=self.parent.get_elem('edit.INPUT_NETMASK')
				netmask_input.text=dhcp_dict.get('netmask') or ''
				netmask_input.set_cursor(len(netmask_input.text))
				netmask_input.paste_text()
				netmask_input.draw()
				#self.parent.container['Gateway']=dhcp_dict.get('gateway') or ''
				#self.parent.container['Nameserver']=dhcp_dict.get('nameserver_1'] or ''
				#self.parent.dns['nameserver_2']=dhcp_dict.get('nameserver_2'] or ''
				#self.parent.dns['nameserver_3']=dhcp_dict.get('nameserver_3'] or ''
				self.stop()

	class more(subwin):
		def __init__(self,parent,pos_y,pos_x,width,heigh,type):
			self.type=type
			subwin.__init__(self,parent,pos_y,pos_x,width,heigh)
		def layout(self):
			MAXIP=18
			# 1. Nameserver/DNS-Fwd
			self.elements.append(textline( _('1. %s') % self.type,self.pos_y+2,self.pos_x+2)) #0
			if self.type == 'Nameserver':
				server=self.parent.elements[10].result().strip()
			elif self.type == 'DNS-Forwarder':
				server=self.parent.elements[13].result().strip()
			else:
				server=''
			self.elements.append(textline(server,self.pos_y+2,self.pos_x+20)) #1
			# 2.Nameserver/DNS-Fwd
			self.elements.append(textline( _('2. %s') % self.type,self.pos_y+3,self.pos_x+2)) #2
			if self.type == 'Nameserver' and self.parent.dns.has_key('nameserver_2') and self.parent.dns['nameserver_2']:
				self.elements.append(input(self.parent.dns['nameserver_2'],self.pos_y+3,self.pos_x+20,MAXIP)) #3
			elif self.type == 'DNS-Forwarder' and self.parent.dns.has_key('dns_forwarder_2') and self.parent.dns['dns_forwarder_2']:
				self.elements.append(input(self.parent.dns['dns_forwarder_2'],self.pos_y+3,self.pos_x+20,MAXIP)) #3
			else:
				self.elements.append(input('',self.pos_y+3,self.pos_x+20,MAXIP)) #3
			# 3. Nameserver/DNS-Fwd
			self.elements.append(textline(_('3. %s') % self.type,self.pos_y+4,self.pos_x+2)) #4
			if self.type == 'Nameserver' and self.parent.dns.has_key('nameserver_3') and self.parent.dns['nameserver_3']:
				self.elements.append(input(self.parent.dns['nameserver_3'],self.pos_y+4,self.pos_x+20,MAXIP)) #5
			elif self.type == 'DNS-Forwarder' and self.parent.dns.has_key('dns_forwarder_3') and self.parent.dns['dns_forwarder_3']:
				self.elements.append(input(self.parent.dns['dns_forwarder_3'],self.pos_y+4,self.pos_x+20,MAXIP)) #5
			else:
				self.elements.append(input('',self.pos_y+4,self.pos_x+20,MAXIP)) #5

			self.elements.append(button('F12-'+_('Ok'),self.pos_y+7,self.pos_x+8,13)) #6
			self.elements.append(button('ESC-'+_('Cancel'),self.pos_y+7,self.pos_x+(self.width)-8,align="right")) #7

			self.current=3
			self.elements[self.current].set_on()
		def helptext(self):
			return self.parent.helptext()
		def modheader(self):
			return _( ' More %ss' ) % self.type
		def put_result(self):
			result={}
			i=2
			string=''
			if self.type == 'Nameserver':
				string='nameserver_'
			elif self.type == 'DNS-Forwarder':
				string='dns_forwarder_'
			else:
				string='error'
			result['%s%d'%(string,i)]=[self.elements[3].result().strip()]
			self.parent.dns['%s%d'%(string,i)]=self.elements[3].result().strip()
			i+=1
			result['%s%d'%(string,i)]=[self.elements[5].result().strip()]
			self.parent.dns['%s%d'%(string,i)]=self.elements[5].result().strip()
			return result
		def incomplete(self):
			missing=_('The following value is missing: ')
			invalid=_('The following value is invalid: ')
			if not self.elements[3].result().strip() == '':
				if not self.parent.is_ip(self.elements[3].result()):
					return invalid+'2. %s'%self.type
			if not self.elements[5].result().strip() == '':
				if self.elements[3].result().strip() == '':
					return missing+'2. %s'%self.type
				elif not self.parent.is_ip(self.elements[5].result()):
					return invalid+'3. %s'%self.type
			return 0
		def input(self,key):
			if hasattr(self,'warn'):
				if not self.warn.key_event(key):
					delattr(self,"warn")
				self.parent.draw()
				self.draw()
			if ( key in [ 10, 32 ] and self.elements[6].usable() and self.elements[6].get_status() ) or key == 276: #Ok
				if self.incomplete() != 0:
					self.parent.debug('incompl: %s'%self.incomplete())
					self.warn=warning(self.incomplete(),self.pos_y+25,self.pos_x+90)
					self.warn.draw()
					return 1
				self.put_result()
				return 0
			elif key in [ 10, 32 ] and self.elements[7].usable() and self.elements[7].get_status(): #Cancel
				return 0
			elif key == 10 and self.elements[self.current].usable():
				return self.elements[self.current].key_event(key)
			elif self.elements[self.current].usable():
				self.elements[self.current].key_event(key)
				return 1
