# -*- coding: utf-8 -*-
#
# Univention Mail Cyrus Kolab2
#  listener module: renaming mailboxes
#
# Copyright (C) 2010 Univention GmbH
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

import listener
import os, string, pwd, grp, univention.debug, subprocess, glob

name='cyrus-mailboxrename'
description='Rename default imap folders'
filter='(&(objectClass=univentionMail)(uid=*))'
attributes=['uid', 'mailPrimaryAddress', 'mailGlobalSpamFolder', 'kolabHomeServer']

def is_groupware_user(new):
	if new.has_key('objectClass'):
		for oc in new['objectClass']:
			if oc.lower() == 'kolabinetorgperson':
				return True
	return False

def is_cyrus_murder_backend():
	if (listener.baseConfig.get('mail/cyrus/murder/master') and listener.baseConfig.get('mail/cyrus/murder/backend/hostname')):
	# ucr currently gives '' if not set, might change to None
		return True
	else:
		return False

def cyrus_userlogfile_rename(new, old):
	userlogfiles = listener.baseConfig.get('mail/cyrus/userlogfiles')
	if userlogfiles and userlogfiles.lower() in ['true', 'yes']:
		newpath='/var/lib/cyrus/log/%s' % (string.lower(new['mailPrimaryAddress'][0]))
		oldpath='/var/lib/cyrus/log/%s' % (string.lower(old['mailPrimaryAddress'][0]))

		cyrus_id=pwd.getpwnam('cyrus')[2]
		mail_id=grp.getgrnam('mail')[2]

		if os.path.exists( oldpath ):
			os.rename(oldpath, newpath)
		else:
			os.mkdir( newpath )
		os.chmod(newpath,0750)
		os.chown(newpath,cyrus_id, mail_id)

def cyrus_userlogfile_delete(old):
	userlogfiles = listener.baseConfig.get('mail/cyrus/userlogfiles')
	if userlogfiles and userlogfiles.lower() in ['true', 'yes']:
		oldpath='/var/lib/cyrus/log/%s' % (string.lower(old['mailPrimaryAddress'][0]))

		if os.path.exists( oldpath ):
			r = glob.glob('%s/*' % oldpath)
			for i in r:
	 			os.unlink(i)
			os.rmdir(oldpath)

def cyrus_usermailbox_rename(new, old):
	mailboxrename = listener.baseConfig.get('mail/cyrus/mailbox/rename')
	if mailboxrename and mailboxrename.lower() in ['true', 'yes']:
		try:
			listener.setuid(0)

			returncode = subprocess.call(['/usr/sbin/univention-cyrus-mailbox-rename', '--user', string.lower(old['mailPrimaryAddress'][0]), string.lower(new['mailPrimaryAddress'][0])])

			cyrus_userlogfile_rename(new, old)
		finally:
			listener.unsetuid()

def cyrus_usermailbox_delete(old):
	mailboxdelete = listener.baseConfig.get('mail/cyrus/mailbox/delete')
	if mailboxdelete and mailboxdelete.lower() in ['true', 'yes']:
		try:
			listener.setuid(0)

			returncode = subprocess.call(['/usr/sbin/univention-cyrus-mailbox-delete', '--user', string.lower(old['mailPrimaryAddress'][0])])

			cyrus_userlogfile_delete(old)
		finally:
			listener.unsetuid()

def handler(dn, new, old):
	fqdn = '%s.%s' % (listener.baseConfig['hostname'], listener.baseConfig['domainname'])
	if old:
		old_kolabHomeserver = old.get('kolabHomeServer', [''])[0]
		old_mailPrimaryAddress = old.get('mailPrimaryAddress', [''])[0]
		if (is_groupware_user(old) and old_mailPrimaryAddress and old_kolabHomeserver == fqdn) or (not is_groupware_user(old)):
			# Old mailbox is local to this host
			if new:
				new_kolabHomeserver = new.get('kolabHomeServer', [''])[0]
				if (is_groupware_user(new) and new_kolabHomeserver == fqdn) or (not is_groupware_user(new)):
					# this host continues hosting the mailbox
					new_mailPrimaryAddress = new.get('mailPrimaryAddress', [''])[0]
					if new_mailPrimaryAddress:
						# in this case cyrus.py will create a new mailbox
						# univention.debug.debug(univention.debug.LISTENER, univention.debug.ERROR, 'cyrus-mailboxrename: new_mailPrimaryAddress "%s" old_mailPrimaryAddress: "%s"' % (new_mailPrimaryAddress, old_mailPrimaryAddress))
						if string.lower(new_mailPrimaryAddress) != string.lower(old_mailPrimaryAddress):
							cyrus_usermailbox_rename(new, old)
					else: # old_mailPrimaryAddress was removed:
						cyrus_usermailbox_delete(old)
				else:
					# this is true if is_groupware_user(new) and new_kolabHomeserver != fqdn):
					# Must not delete mailbox without checking if new_kolabHomeServer might call move_cyrus_murder_mailbox
					#if not is_cyrus_murder_backend():
					#	cyrus_usermailbox_delete(old)
					pass
			else: # object was removed
				cyrus_usermailbox_delete(old)
