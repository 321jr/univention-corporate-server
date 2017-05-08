import ldap
import univention.config_registry
import sys
import copy
import ldap_glue_s4
import univention.s4connector.s4 as s4
from time import sleep
import univention.testing.utils as utils

configRegistry = univention.config_registry.ConfigRegistry()
configRegistry.load()


class S4Connection(ldap_glue_s4.LDAPConnection):
	'''helper functions to modify AD-objects'''

	def __init__(self, configbase='connector', no_starttls=False):
		self.configbase = configbase
		self.adldapbase = configRegistry['%s/s4/ldap/base' % configbase]
		self.addomain = self.adldapbase.replace(',DC=', '.').replace('DC=', '')
		self.login_dn = configRegistry['%s/s4/ldap/binddn' % configbase]
		self.pw_file = configRegistry['%s/s4/ldap/bindpw' % configbase]
		self.host = configRegistry['%s/s4/ldap/host' % configbase]
		self.port = configRegistry['%s/s4/ldap/port' % configbase]
		self.ssl = configRegistry.get('%s/s4/ldap/ssl', "no")
		self.ca_file = configRegistry['%s/s4/ldap/certificate' % configbase]
		self.protocol = configRegistry.get('%s/s4/ldap/protocol' % self.configbase, 'ldap').lower()
		self.socket = configRegistry.get('%s/s4/ldap/socket' % self.configbase, '')
		self.connect(no_starttls)

	def _set_module_default_attr(self, attributes, defaults):
		"""
		Returns the given attributes, extented by every property given in defaults if not yet set.
		"defaults" should be a tupel containing tupels like "('username', <default_value>)".
		"""
		attr = copy.deepcopy(attributes)
		for prop, value in defaults:
			attr.setdefault(prop, value)
		return attr

	def createuser(self, username, position=None, cn=None, sn=None, description=None):
		if not position:
			position = 'cn=users,%s' % self.adldapbase

		if not cn:
			cn = username

		if not sn:
			sn = 'SomeSurName'

		newdn = 'cn=%s,%s' % (ldap.dn.escape_dn_chars(cn), position)

		attrs = {}
		attrs['objectclass'] = ['top', 'user', 'person', 'organizationalPerson']
		attrs['cn'] = cn
		attrs['sn'] = sn
		attrs['sAMAccountName'] = username
		attrs['userPrincipalName'] = '%s@%s' % (username, self.addomain)
		attrs['displayName'] = '%s %s' % (username, sn)
		if description:
			attrs['description'] = description

		self.create(newdn, attrs)

	def group_create(self, groupname, position=None, description=None):
		if not position:
			position = 'cn=groups,%s' % self.adldapbase

		attrs = {}
		attrs['objectclass'] = ['top', 'group']
		attrs['sAMAccountName'] = groupname
		if description:
			attrs['description'] = description

		self.create('cn=%s,%s' % (ldap.dn.escape_dn_chars(groupname), position), attrs)

	def getprimarygroup(self, user_dn):
		try:
			res = self.lo.search_ext_s(user_dn, ldap.SCOPE_BASE, timeout=10)
		except:
			return None
		primaryGroupID = res[0][1]['primaryGroupID'][0]
		res = self.lo.search_ext_s(
			self.adldapbase,
			ldap.SCOPE_SUBTREE,
			'objectClass=group',
			timeout=10
		)

		import re
		regex = '^(.*?)-%s$' % primaryGroupID
		for r in res:
			if r[0] is None or r[0] == 'None':
				continue  # Referral
			if re.search(regex, s4.decode_sid(r[1]['objectSid'][0])):
				return r[0]

	def setprimarygroup(self, user_dn, group_dn):
		res = self.lo.search_ext_s(group_dn, ldap.SCOPE_BASE, timeout=10)
		import re
		groupid = (re.search('^(.*)-(.*?)$', s4.decode_sid(res[0][1]['objectSid'][0]))).group(2)
		self.set_attribute(user_dn, 'primaryGroupID', groupid)

	def container_create(self, name, position=None, description=None):

		if not position:
			position = self.adldapbase

		attrs = {}
		attrs['objectClass'] = ['top', 'container']
		attrs['cn'] = name
		if description:
			attrs['description'] = description

		self.create('cn=%s,%s' % (ldap.dn.escape_dn_chars(name), position), attrs)

	def createou(self, name, position=None, description=None):

		if not position:
			position = self.adldapbase

		attrs = {}
		attrs['objectClass'] = ['top', 'organizationalUnit']
		attrs['ou'] = name
		if description:
			attrs['description'] = description

		self.create('ou=%s,%s' % (ldap.dn.escape_dn_chars(name), position), attrs)


def check_object(object_dn, sid=None, old_object_dn=None):
	S4 = S4Connection()
	object_dn_modified = _replace_uid_with_cn(object_dn)
	object_found = S4.exists(object_dn_modified)
	if not sid:
		if object_found:
			print ("Object synced to Samba")
		else:
			sys.exit("Object not synced")
	elif sid:
		object_dn_modified_sid = get_object_sid(object_dn)
		old_object_dn_modified = _replace_uid_with_cn(old_object_dn)
		old_object_gone = not S4.exists(old_object_dn_modified)
		if old_object_gone and object_found and object_dn_modified_sid == sid:
			print ("Object synced to Samba")
		else:
			sys.exit("Object not synced")


def get_object_sid(dn):
	S4 = S4Connection()
	dn_modified = _replace_uid_with_cn(dn)
	sid = S4.get_attribute(dn_modified, 'objectSid')
	return sid


def _replace_uid_with_cn(dn):
	if dn.startswith('uid') or dn.startswith('UID'):
		dn_modified = 'cn' + dn[3:]
	else:
		dn_modified = dn
	return dn_modified


def correct_cleanup(group_dn, groupname2, udm_test_instance, return_new_dn=False):
	modified_group_dn = 'cn=%s,%s' % (ldap.dn.escape_dn_chars(groupname2), ldap.dn.dn2str(ldap.dn.str2dn(group_dn)[1:4]))
	udm_test_instance._cleanup['groups/group'].append(modified_group_dn)
	if return_new_dn:
		return modified_group_dn


def verify_users(group_dn, users):
	print (" Checking Ldap Objects")
	utils.verify_ldap_object(group_dn, {
		'uniqueMember': [user for user in users],
		'memberUid': [ldap.dn.str2dn(user)[0][0][1] for user in users]
	})


def modify_username(user_dn, new_user_name, udm_instance):
	newdn = ldap.dn.dn2str([[('uid', new_user_name, ldap.AVA_STRING)]] + ldap.dn.str2dn(user_dn)[1:])
	udm_instance._cleanup['users/user'].append(newdn)
	udm_instance.modify_object('users/user', dn=user_dn, username=new_user_name)
	return newdn


def connector_running_on_this_host():
	return configRegistry.is_true("connector/s4/autostart")


def exit_if_connector_not_running():
	if not connector_running_on_this_host():
		print
		print ("Univention S4 Connector not configured")
		print
		sys.exit(77)


def wait_for_sync(min_wait_time=0):
	synctime = int(configRegistry.get("connector/s4/poll/sleep", 7))
	synctime = ((synctime + 3) * 2)
	if min_wait_time > synctime:
		synctime = min_wait_time
	print ("Waiting {0} seconds for sync...".format(synctime))
	sleep(synctime)
