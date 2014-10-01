#!/usr/bin/python2.7
# -*- coding: utf-8 -*-

import re
from univention.management.console.modules.diagnostic import Warning, ProblemFixed, MODULE
from univention.management.console.config import ucr
from univention.config_registry import handler_set

from univention.lib.i18n import Translation
_ = Translation('univention-management-console-module-diagnostic').translate

suggested_limit_hard = 32828
suggested_limit_soft = 32828

title = _('Samba often uses too many opened file descriptors')
description = '\n'.join([
	_('The limits for max_open_files are currently not configured properly.'),
	_('This can cause errors in Samba4 when copying many files between different shares.'),
	_('Suggestion is to increase the value manually by using {ucr} or to use the automatically suggested limits:'),
	'<pre>security/limits/user/*/soft/nofile=%s' % (suggested_limit_soft,),
	'security/limits/user/*/hard/nofile=%s</pre>' % (suggested_limit_hard,),
	_('More related information can be found at the "{sdb}"'),
])
links = [{
	'name': 'sdb',
	'href': _('http://forum.univention.de/viewtopic.php?f=48&t=2100'),
	'label': _('Samba4 max open files - Univention Forum')
}]
buttons = [{
	'name': 'adjust',
	'label': _('Adjust to suggested limits'),
	'action': 'adjust'
}]
actions = {}  # filled at bottom


def run():
	MODULE.info(_('Checking samba logfiles for "Too many open files" messages'))
	try:
		with open('/var/log/samba/log.smbd', 'rb') as fd:
			counter = len(re.findall('Too many open files', fd.read()))
	except OSError:
		pass  # logfile does not exists

	ucr.load()
	try:
		soft = int(ucr.get('security/limits/user/*/soft/nofile', 0))
		hard = int(ucr.get('security/limits/user/*/hard/nofile', 0))
	except ValueError:
		soft = hard = 0

	if counter and hard < suggested_limit_hard or soft < suggested_limit_soft:
		raise Warning(umc_modules=[{'module': 'ucr'}])


def adjust():
	handler_set([
		'security/limits/user/*/soft/nofile=%d' % (suggested_limit_soft,),
		'security/limits/user/*/hard/nofile=%d' % (suggested_limit_hard,)
	])
	raise ProblemFixed(_('The limits have been adjusted to the suggested value.'), buttons=[])
actions['adjust'] = adjust


if __name__ == '__main__':
	from univention.management.console.modules.diagnostic import main
	main()
