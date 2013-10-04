#!/usr/bin/python

from optparse import OptionParser
import sys

try:
	# with 3.1
	from univention.management.console.modules.appcenter.util import UMCConnection
except ImportError:
	# with 3.2
	from univention.lib.umc_connection import UMCConnection

from univention.config_registry import ConfigRegistry
ucr = ConfigRegistry()
ucr.load()

parser = OptionParser()
parser.add_option('-H', '--host', dest='host', default='localhost',
	help='host to connect to', metavar='HOST')
parser.add_option('-u', '--user', dest='username',
	help='username', metavar='UID', default='Administrator')
parser.add_option('-p', '--password', dest='password',
	help='password', metavar='PASSWORD')
parser.add_option('-o', '--ou', dest='ou',
	help='ou name of the school', metavar='OU')
parser.add_option('-S', '--single-server', dest='setup',
	action='store_const', const='singlemaster',
	help='install a single server setup on a master')
parser.add_option('-M', '--multi-server', dest='setup',
	action='store_const', const='multiserver',
	help='install a multi server setup')
parser.add_option('-m', '--master-host', dest='master', default=ucr['ldap/master'],
	help='on a slave the master host needs to be specified', metavar='HOST')
parser.add_option('-s', '--samba-version', dest='samba', default='4',
	help='the version of samba, either 3 or 4', metavar='HOST')

(options, args) = parser.parse_args()

if not options.setup:
	parser.error('Please specify a setup type: multi server (-M) or single server (-S)!')

if options.samba not in ('3', '4'):
	parser.error('Samba version needs to be either 3 or 4!')

if ucr['server/role'] != 'domaincontroller_master' and not options.master:
	parser.error('Please specify a master host (-m)!')

if not options.username or not options.password:
	parser.error('Please specify username (-u) and password (-p)!')

if not options.ou:
	if ucr['server/role'] == 'domaincontroller_slave' or options.setup == 'singlemaster':
		parser.error('Please specify a school OU (-o)!')
	options.ou = ''

connection = UMCConnection(options.host)
connection.auth(options.username, options.password)

params = {
	'setup': options.setup,
	'username': options.username,
	'password': options.password,
	'master': options.master,
	'samba': options.samba,
	'schoolOU': options.ou,
}

result = connection.request('schoolinstaller/install', params)
if not result['success']:
	print 'ERROR: Failed to run installer!'
	print 'output: %s' % result
	sys.exit(1)

print '=== INSTALLATION STARTED ==='
status = {'finished': False}
while not status['finished']:
	status = connection.request('schoolinstaller/progress')
	print '%(component)s - %(info)s' % status

if len(status['errors']) > 0:
	print 'ERROR: installation failed!'
	print 'output: %s' % status
	sys.exit(1)

result = connection.request('lib/server/restart')
if not result['success']:
	print 'ERROR: Failed to restart UMC'
	print 'output: %s' % result
	sys.exit(1)

sys.exit(0)
