# -*- coding: utf-8 -*-
#
# UCS Virtual Machine Manager Daemon
#  UVMM unix socket handler
#
# Copyright 2010-2018 Univention GmbH
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
"""UVMM unix-socket handler."""
# http://docs.python.org/library/socketserver.html
# http://akumakun.de/norbert/index.html

import os
import errno
import sys
import SocketServer
import protocol
from commands import commands, CommandError
from node import Nodes, node_frequency
from helpers import N_ as _
import socket
import select
import logging
import traceback

logger = logging.getLogger('uvmmd.unix')


class StreamHandler(SocketServer.StreamRequestHandler):

	"""Handle one client connection."""

	active_count = 0  # Number of active clients.
	client_count = 0  # Number of instances.

	def setup(self):
		"""Initialize connection."""
		StreamHandler.client_count += 1
		self.client_id = StreamHandler.client_count
		logger.info('[%d] New connection.' % (self.client_id,))
		# super(StreamHandler,self).setup()
		SocketServer.StreamRequestHandler.setup(self)
		if False and StreamHandler.active_count == 0:
			node_frequency(Nodes.USED_FREQUENCY)
		StreamHandler.active_count += 1

	def handle(self):
		"""Handle protocol."""
		try:
			self.eos = False
			buffer = ''
			while not self.eos:
				try:
					data = self.request.recv(1024)
				except socket.error as (err, errmsg):
					if err == errno.EINTR:
						continue
					else:
						raise
				logger.debug('[%d] Data recveived: %d' % (self.client_id, len(data)))
				if data == '':
					self.eos = True
				else:
					buffer += data
				try:
					packet = protocol.Packet.parse(buffer)
					if packet is None:
						continue  # waiting
				except protocol.PacketError as e:  # (translatable_text, dict):
					logger.warning("[%d] Invalid packet received: %s" % (self.client_id, e))
					if logger.isEnabledFor(logging.DEBUG):
						logger.debug("[%d] Dump: %r" % (self.client_id, data))
					break

				logger.debug('[%d] Received packet.' % (self.client_id,))
				(length, command) = packet
				buffer = buffer[length:]

				if isinstance(command, protocol.Request):
					res = self.handle_command(command)
				else:
					logger.warning('[%d] Packet is no UVMM Request. Ignored.' % (self.client_id,))
					res = protocol.Response_ERROR()
					res.translatable_text = _('Packet is no UVMM Request: %(type)s')
					res.values = {
						'type': type(command),
					}

				logger.debug('[%d] Sending response.' % (self.client_id,))
				packet = res.pack()
				self.wfile.write(packet)
				self.wfile.flush()
				logger.debug('[%d] Done.' % (self.client_id,))
		except EOFError:
			pass
		except socket.error as (err, errmsg):
			if err != errno.ECONNRESET:
				logger.error('[%d] Exception: %s' % (self.client_id, traceback.format_exc()))
				raise
			else:
				logger.warn('[%d] NetException: %s' % (self.client_id, traceback.format_exc()))
		except Exception as e:
			logger.critical('[%d] Exception: %s' % (self.client_id, traceback.format_exc()))
			raise

	def handle_command(self, command):
		"""Handle command packet."""
		logger.info('[%d] Request "%s" received' % (self.client_id, command.command,))
		try:
			cmd = commands[command.command]
		except KeyError as e:
			logger.warning('[%d] Unknown command "%s": %s.' % (self.client_id, command.command, str(e)))
			res = protocol.Response_ERROR()
			res.translatable_text = '[%(id)d] Unknown command "%(command)s".'
			res.values = {
				'id': self.client_id,
				'command': command.command,
			}
		else:
			try:
				res = cmd(self, command)
				if res is None:
					res = protocol.Response_OK()
			except CommandError as e:
				logger.warning('[%d] Error doing command "%s": %s' % (self.client_id, command.command, e))
				res = protocol.Response_ERROR()
				res.translatable_text, res.values = e.args
			except Exception as e:
				logger.error('[%d] Exception: %s' % (self.client_id, traceback.format_exc()))
				res = protocol.Response_ERROR()
				res.translatable_text = _('Exception: %(exception)s')
				res.values = {
					'exception': str(e),
				}
		return res

	def finish(self):
		"""Perform cleanup."""
		logger.info('[%d] Connection closed.' % (self.client_id,))
		StreamHandler.active_count -= 1
		if False and StreamHandler.active_count == 0:
			node_frequency(Nodes.IDLE_FREQUENCY)
		# super(StreamHandler,self).finish()
		SocketServer.StreamRequestHandler.finish(self)


def unix(options):
	"""Run UNIX SOCKET server."""
	try:
		if os.path.exists(options.socket):
			os.remove(options.socket)
	except OSError as (err, errmsg):
		logger.error("Failed to delete old socket '%s': %s" % (options.socket, errmsg))
		sys.exit(1)

	sockets = {}
	if options.socket:
		try:
			unixd = SocketServer.ThreadingUnixStreamServer(options.socket, StreamHandler)
			unixd.daemon_threads = True
			sockets[unixd.fileno()] = unixd
		except Exception as e:
			logger.error("Could not create SSL server: %s" % (e,))
	if not sockets:
		logger.error("No UNIX socket server.")
		return

	logger.info('Server is ready.')
	if hasattr(options, 'callback_ready'):
		options.callback_ready()

	keep_running = True
	while keep_running:
		try:
			rlist, wlist, xlist = select.select(sockets.keys(), [], [], None)
			for fd in rlist:
				sockets[fd].handle_request()
		except (select.error, socket.error) as (err, errmsg):
			if err == errno.EINTR:
				continue
			else:
				raise
		except KeyboardInterrupt:
			keep_running = False

	logger.info('Server is terminating.')
	try:
		os.remove(options.socket)
	except OSError as (err, errmsg):
		logger.warning("Failed to delete old socket '%s': %s" % (options.socket, errmsg))


if __name__ == '__main__':
	import doctest
	doctest.testmod()
