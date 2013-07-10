
import univention.config_registry
import subprocess

def createMachinePassword():
	"""
	Returns a $(pwgen) generated password according to the 
	requirements in
		machine/password/length
		machine/password/complexity
	"""
	ucr = univention.config_registry.ConfigRegistry()
	ucr.load()
	length = ucr.get('machine/password/length', '20')
	compl = ucr.get('machine/password/complexity', 'scn')
	p = subprocess.Popen(["pwgen", "-1", "-" + compl, length], stdout=subprocess.PIPE, stderr=subprocess.PIPE)
	(stdout, stderr) = p.communicate()
	return stdout.strip()

def getLDAPURIs(configRegistryInstance = None):
	"""
	Returns a string with all configured LDAP servers,
	 ldap/server/name and ldap/server/additional
	Optional a UCR instance ca be given as parameter, for example
	if the function is used in a UCR template
	"""
	if configRegistryInstance:
		ucr = configRegistryInstance
	else:
		ucr = univention.config_registry.ConfigRegistry()
		ucr.load()

	uri_string = ''
	ldaphosts=[]
	port = ucr.get('ldap/server/port', '7389')
	ldap_server_name = ucr.get('ldap/server/name')
	ldap_server_addition = ucr.get('ldap/server/addition')

	if ldap_server_name:
		ldaphosts.append(ldap_server_name)
	if ldap_server_addition:
		ldaphosts.extend(ldap_server_addition.split())
	if ldaphosts:
		urilist=[ "ldap://%s:%s" % (host, port) for host in ldaphosts ]
		uri_string = ' '.join(urilist)

	return uri_string

