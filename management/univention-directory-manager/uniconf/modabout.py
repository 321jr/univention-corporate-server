# -*- coding: utf-8 -*-
#
# Univention Directory Manager
#  show the about dialog
#
# Copyright 2004-2010 Univention GmbH
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

import os
import sys
import ldap
import string
import re
import datetime

import unimodule
from uniparts import *
from local import _

import univention.admin.uldap
import univention.admin.modules
import univention_baseconfig
import univention.debug

import ldif

class ldifParser(ldif.LDIFParser):
	dn = None
	mod_list = []
	dncount = 0
	base = None
	err = ""

	def __init__(self, input_file, ignored_attr_types=None, max_entries=0, process_url_schemes=None, line_sep='\n' ):
		ldif.LDIFParser.__init__(self,input_file, ignored_attr_types, max_entries, process_url_schemes,line_sep)

	def check(self,base):
		ldif.LDIFParser.parse(self)

		#count dn
		if self.dncount == 0:
			self.err = _("No Base DN has been found.")
		elif self.dncount > 1:
			self.err = _("More than one Base DN has been defined.")

		#check base
		if self.base != base or base == None:
			self.err = _("Wrong Base DN. Expected was %s but %s has been found.") % (base,self.base)

		return self.err

	def handle(self,dn,entry):
		if dn == None or dn == "":
			self.err = _("No Base DN has been found.")
			return

		self.dn = dn
		self.dncount += 1

		if 'univentionLicenseBaseDN' in entry:
			self.base = "%s" % entry['univentionLicenseBaseDN'][0]
		else:
			self.err = _("No Base DN has been defined.")
			return

		#create modification list
		for atr in entry:
			self.mod_list.insert(0,(ldap.MOD_REPLACE, atr, entry[atr]))

def create(a,b,c):
	return modabout(a,b,c)

def myinfo(settings):
	if settings.listAdminModule('modabout'):
		return unimodule.realmodule("about", _("About"), _("About Univention Directory Manager"))
	else:
		return unimodule.realmodule("about", "", "")

def myrgroup():
	return ""

def mywgroup():
	return ""

def mymenunum():
	return 900

def mymenuicon():
	return unimodule.selectIconByName( 'about' )

class modabout(unimodule.unimodule):
	def mytype(self):
		return "dialog"

	def __add_row(self, left_text, right_text):

		self.div_start('form-item col', divtype='class')
		self.subobjs.append(htmltext ('', {}, {'htmltext': [left_text]}))
		self.div_stop('form-item col')

		self.div_start('form-item col right', divtype='class')
		self.subobjs.append(htmltext ('', {}, {'htmltext': [right_text]}))
		self.div_stop('form-item col right')

		self.subobjs.append(htmltext ('', {}, {'htmltext': ['<br class="clear" />']}))

	def myinit(self):
		self.save=self.parent.save
		self.lo=self.args["uaccess"]

		if self.inithandlemessages():
			return

		#self.subobjs.append(table("",
		#			  {'type':'content_header'},
		#			  {"obs":[tablerow("",{},{"obs":[tablecol("",{'type':'about_layout'},{"obs":[]})]})]})
		#		    )
		self.div_start('content-wrapper', divtype='id')

		self.div_start('content-head', divtype='id')
		self.subobjs.append(htmltext ('', {}, {'htmltext': ['<h2>%s</h2>' % _('About Univention Directory Manager')]}))
		# self.nbook = notebook('', {}, {'buttons': [("%s %s" % (_('About'),_("Univention Directory Manager")),"%s %s" % (_('About'),_("Univention Directory Manager")))], 'selected': 0})
		#self.subobjs.append(self.nbook)

		self.div_start('content', divtype='id')


		rows=[]

		baseConfig=univention_baseconfig.baseConfig()
		baseConfig.load()

		self.subobjs.append(htmltext ('', {}, {'htmltext': ['<h3 class="about">%s</h3>' % _('General')]}))

		self.div_start('form-wrapper about', divtype='class')

		self.__add_row(_('Version'), self.getversion() )
		self.__add_row(_('Build'), self.getbuild() )


		self.__add_row(_('Hostname'),'%s.%s' % (baseConfig['hostname'],baseConfig['domainname']))

		version_string = ""
		codename = ""

		for key in ['version/version','version/patchlevel','version/security-patchlevel']:
			if baseConfig.has_key(key) and baseConfig[key]:
				if version_string:
					version_string = "%s-%s" % (version_string,baseConfig[key])
				else:
					version_string = baseConfig[key]

		if baseConfig.has_key("version/releasename"):
			codename = baseConfig["version/releasename"]

		self.__add_row(_('local Installation'), "%s %s (%s)" % (_('Univention Corporate Server'), version_string, codename))

		days = baseConfig.get( 'ssl/validity/days', '' )
		if days:
			days = datetime.datetime.fromtimestamp( int( days ) * 24 * 60 * 60 ).strftime( "%x" )

		self.__add_row( _('Validity date of the SSL certificate'), days)

		if baseConfig.get( 'univention-ox-directory-integration/oxae', 'false').lower() in [ 'true', 'yes', '1' ] or \
				baseConfig.get( 'univention-ox-directory-integration/oxse', 'false').lower() in [ 'true', 'yes', '1' ]:
			## OX
			self.div_stop('form-wrapper about')
			self.subobjs.append(htmltext ('', {}, {'htmltext': ['<h3 class="about">%s</h3>' % _('Open-Xchange')]}))
			self.div_start('form-wrapper about', divtype='class')

			### get ox context and integration versions
			ldap_base = baseConfig['ldap_base']
			domain_name = "%s.%s" % (baseConfig['hostname'], baseConfig['domainname'])
			result_set = self.lo.search("(&(objectClass=oxContext)(oxHomeServer=%s))" % domain_name)

			for ox_context in result_set:
				name = ox_context[0].split(",")[0][3:]
				ox_context_info = ox_context[1]
				self.__add_row( _('Context'), name)
				if ox_context_info.has_key("oxAdminDaemonVersion"):
					self.__add_row( _('Admin Daemon Version'), ox_context_info['oxAdminDaemonVersion'][0])
				if ox_context_info.has_key("oxGroupwareVersion"):
					self.__add_row( _('Groupware Version'), ox_context_info['oxGroupwareVersion'] [0])
				if ox_context_info.has_key("oxGuiVersion"):
					self.__add_row( _('GUI Version'), ox_context_info['oxGuiVersion'][0])
				if ox_context_info.has_key("oxIntegrationVersion"):
					self.__add_row( _('Integration Version:'), ox_context_info['oxIntegrationVersion'][0])


		## Licence
		self.div_stop('form-wrapper about')
		self.subobjs.append(htmltext ('', {}, {'htmltext': ['<h3 class="about">%s</h3>' % _('Licence')]}))
		self.div_start('form-wrapper about', divtype='class')

		module=univention.admin.modules.get('settings/license')
		objects=module.lookup(None, self.lo, '')

		if objects:
			object=objects[0]
			object.open()
			self.__add_row( object.descriptions['base'].short_description, object['base'])

			if object['base'] == 'Free for personal use edition':
				self.save.put("personal_use","1")

			self.__add_row( object.descriptions['accounts'].short_description, object['accounts'])

			self.__add_row( object.descriptions['groupwareaccounts'].short_description, object['groupwareaccounts'])
			self.__add_row( object.descriptions['clients'].short_description, object['clients'])

			self.__add_row(object.descriptions['desktops'].short_description, object['desktops'])
			self.__add_row(object.descriptions['expires'].short_description, object['expires'])

			productTypes = ""
			for t in object['productTypes']:
				productTypes += ", " + t

			oemProductTypes = ""
			for t in object['oemProductTypes']:
				if t:
					oemProductTypes += ", " + t

			if oemProductTypes:
				self.__add_row(object.descriptions['oemProductTypes'].short_description, oemProductTypes[2:])
			else:
				self.__add_row(object.descriptions['productTypes'].short_description, productTypes[2:])

			univention.debug.debug(univention.debug.ADMIN, univention.debug.ERROR, "check for personal use: %s" % self.save.get( 'personal_use' ))
			if self.save.get( 'personal_use' ) == '1':
				self.__add_row(_('License'), u'Die "Free For Personal Use" Ausgabe von Univention Corporate Server ist eine spezielle Softwarelizenz mit der Verbraucher im Sinne des § 13 BGB die kostenlose Nutzung von Univention Corporate Server und darauf basierenden Softwareprodukten für private Zwecke ermöglicht wird. <br><br>\
							Im Rahmen dieser Lizenz darf UCS von unseren Servern heruntergeladen, installiert und genutzt werden. Es ist jedoch nicht erlaubt, die Software Dritten zum Download oder zur Nutzung zur Verfügung zu stellen oder sie im Rahmen einer überwiegend beruflichen oder gewerbsmäßigen Nutzung zu verwenden.  <br><br>\
							Die Überlassung der "Free For Personal Use"-Ausgabe von UCS erfolgt im Rahmen eines Schenkungsvertrages. Wir schließen deswegen alle Gewährleistungs- und Haftungsansprüche aus, es sei denn, es liegt ein Fall des Vorsatzes oder der groben Fahrlässigkeit vor. Wir weisen darauf hin, dass bei der "Free For Personal Use"-Ausgabe die Haftungs-, Gewährleistungs-, Support- und Pflegeansprüche, die sich aus unseren kommerziellen Softwareverträgen ergeben, nicht gelten.  <br><br>\
							Wir wünschen Ihnen viel Freude bei der Nutzung der "Free For Personal Use" Ausgabe von Univention Corporate Server und freuen uns über Ihr Feedback. Bei Fragen wenden Sie sich bitte an unser Forum, dass Sie im Internet unter <a target=parent href=http://forum.univention.de/>http://forum.univention.de/</a> erreichen.')
		else:
			self.__add_row(_('License'), _('no licence found'))

		self.div_stop('form-wrapper about')
		self.subobjs.append(htmltext ('', {}, {'htmltext': ['<h3 class="about">%s</h3>' % _('License update')]}))
		self.div_start('form-wrapper about', divtype='class')

		self.subobjs.append(htmltext ('', {}, {'htmltext': ["""
							<div class="form-item col">
								%(update)s
							</div>							
							<div class="form-item col right">
							""" % {'update': _("Update License via File")}
							]}))
		self.certBrowse = question_file('', {} , {"helptext":_("Select a file")})
		self.certLoadBtn = button(_("Update"),{'class':'submit'},{"helptext":_("Upload selected file")})
		self.subobjs.append(self.certBrowse)
		#self.subobjs.append(htmltext ('', {}, {'htmltext': ["""
		#					</div>							
		#					<div class="form-item col right">
		#					"""
		#					]}))
		self.subobjs.append(self.certLoadBtn)
		self.subobjs.append(htmltext ('', {}, {'htmltext': ['</div><br class="clear" />']}))



		#Upload License as Text-Copy from License-Mail
		self.subobjs.append(htmltext ('', {}, {'htmltext': ["""
							<div class="form-item col">
								%(update)s
							</div>							
							<div class="form-item col right">
							""" % {'update':_("Insert License Key") }
							]}))

		self.certText =	 question_ltext('', {}, {'helptext': _("Copy the License Code into this field")})
		self.certLoadTextBtn = button(_("Update"),{'class':'submit'},{"helptext":_("Upload the License")})
		self.subobjs.append(self.certText)
		#self.subobjs.append(htmltext ('', {}, {'htmltext': ["""
		#					</div>							
		#					<div class="form-item col right">
		#					"""
		#					]}))
		self.subobjs.append(self.certLoadTextBtn)
		self.subobjs.append(htmltext ('', {}, {'htmltext': ['</div><br class="clear" />']}))

		self.div_stop('form-wrapper about')

		if oemProductTypes:

			feedback_description=baseConfig.get('directory/manager/web/feedback/description')
			feedback_mail=baseConfig.get('directory/manager/web/feedback/mail')
			if feedback_description and feedback_mail:
				self.subobjs.append(htmltext ('', {}, {'htmltext': ['<h3 class="about">%s</h3>' % _('Contact')]}))
				self.div_start('form-wrapper about', divtype='class')
				self.__add_row( '%s' % feedback_description, '<a href="mailto:%s">%s</a>' % (feedback_mail, feedback_mail) )
				self.div_stop('form-wrapper about')
		else:
			self.subobjs.append(htmltext ('', {}, {'htmltext': ['<h3 class="about">%s</h3>' % _('Contact')]}))
			self.div_start('form-wrapper about', divtype='class')
			self.__add_row('Univention GmbH', '<a href=http://www.univention.de target=parent>www.univention.de</a>')
			self.__add_row( _('ALL RIGHTS RESERVED'), '<a href="mailto:info@univention.de">info@univention.de</a>')
			self.div_stop('form-wrapper about')

		self.div_stop('content')

		self.div_stop('content-wrapper')

		self.div_stop('content-head')

	def apply(self):
		# license import
		if (hasattr(self,'certLoadBtn') and self.certLoadBtn.pressed()) or (hasattr(self,'certLoadTextBtn') and self.certLoadTextBtn.pressed()):
				if self.certBrowse.get_input() or (self.certText.get_input() and self.certText.get_input() != ""):
						import subprocess, tempfile

						if self.certBrowse.get_input():
							#read content from license file
							certFile = open(self.certBrowse.get_input())
						else:
							#remove everythingt which is not part of the lizense
							mail_text = self.certText.get_input()
							license_text = []
							#extrakt license from mail
							license_start = False
							license_end = False
							linebreak = False
							for line in mail_text.split("\n"):
								line = line.lstrip(" ")
								if line.startswith("dn: cn=admin,cn=license"):
									license_start = True

								if linebreak:
									license_text[-1] = 'univentionLicenseSignature: %s' % line
									license_end = True
									break

								if license_start:
									license_text.append(line)

								if line in [ "univentionLicenseSignature:", "univentionLicenseSignature: ", "univentionLicenseSignature:  "]:
									linebreak=True
								elif line.startswith("univentionLicenseSignature:"):
									license_end = True
									break

							mail_text = ""
							if license_end:
								for line in license_text:
									try:
										univention.debug.debug(univention.debug.ADMIN, univention.debug.ERROR, "XXXX: [%s] : [%s]" % (line.split(':',1)[0].strip(' '),line.split(':',1)[1].strip(' ')))
										mail_text = "%s%s: %s\n" % (mail_text, line.split(':',1)[0].strip(' '),line.split(':',1)[1].strip(' '))
									except IndexError:
										mail_text = "%s%s\n" % (mail_text, line)


							#create license file from mail
							if mail_text != "":
								certFileTemp = tempfile.mkstemp()
								certFile = file("%s" % certFileTemp[1], "w")
								certFile.write("%s" % mail_text)
								certFile.close()

								certFile = file("%s" % certFileTemp[1], "r")
							else:
								certFile = None

						if certFile != None:
							#read license from file
							ldif_parser = ldifParser(certFile)

							#check license
							position = self.save.get('ldap_position')
							base = position.getDomain()
							res = ldif_parser.check(base)

							#close
							certFile.close()
							os.remove(certFile.name)
						else:
							res = _("The License you have entered is invalid.")

							#return result
						if res:
							self.usermessage(_("An Error has occured:<br> %s") % res)
						else:
							#install license
							settings = self.save.get("settings")
							pwd = self.save.get("pass")

							ldap_con = ldap.open("localhost")
							ldap_con.simple_bind_s(settings.userdn, pwd)
							ldap_con.modify_s(ldif_parser.dn,ldif_parser.mod_list)
							ldap_con.unbind_s()

							self.usermessage(_("The License has been sucessfully installed. You have to relogin."))
							self.save.put("LOGOUT",1)
							self.save.put("logout",1)
							self.save.put("uc_module","relogin")
							self.save.put("uc_submodule","none")
								
						return

		self.applyhandlemessages()
