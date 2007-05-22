#
# Univention Admin
#  show the about dialog
#
# Copyright (C) 2004, 2005, 2006 Univention GmbH
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

def create(a,b,c):
	return modabout(a,b,c)

def myinfo(settings):
	if settings.listAdminModule('modabout'):
		return unimodule.realmodule("about", _("About"), _("About Univention Admin"))
	else:
		return unimodule.realmodule("about", "", "")

def myrgroup():
	return ""

def mywgroup():
	return ""

def mymenunum():
	return 600

def mymenuicon():
	return '/icon/about.gif'

class modabout(unimodule.unimodule):
	def mytype(self):
		return "dialog"

	def myinit(self):
		self.save=self.parent.save
		self.lo=self.args["uaccess"]

		if self.inithandlemessages():
			return

		self.subobjs.append(table("",
					  {'type':'content_header'},
					  {"obs":[tablerow("",{},{"obs":[tablecol("",{'type':'about_layout'},{"obs":[]})]})]})
				    )

		self.nbook = notebook('', {}, {'buttons': [("%s %s" % (_('About'),_("Univention Admin")),"%s %s" % (_('About'),_("Univention Admin")))], 'selected': 0})
		self.subobjs.append(self.nbook)


		rows=[]

		baseConfig=univention_baseconfig.baseConfig()
		baseConfig.load()

		## Admin
		rows.append(tablerow("",{},{"obs":[
			tablecol("",{"colspan":"2",'type':'about_layout'},{"obs":[
			header(_("Univention Admin"),{"type":"4"},{})
			]})
			]}))

		rows.append(tablerow("",{},{"obs":[
			tablecol("",{'type':'about_layout'},{"obs":[text('',{},{'text':[ _('Version')]})]}),
			tablecol("",{'type':'about_layout'},{"obs":[text('',{},{'text':[self.getversion()]})]})
			]}))

		rows.append(tablerow("",{},{"obs":[
			tablecol("",{'type':'about_layout'},{"obs":[text('',{},{'text':[ _('Build')]})]}),
			tablecol("",{'type':'about_layout'},{"obs":[text('',{},{'text':[self.getbuild()]})]})
			]}))

		## UCS
		rows.append(tablerow("",{},{"obs":[
			tablecol("",{"colspan":"2",'type':'about_layout'},{"obs":[]})
			]}))

		rows.append(tablerow("",{},{"obs":[
			tablecol("",{'type':'about_layout'},{"obs":[text('',{},{'text':[ _('Hostname')]})]}),
			tablecol("",{'type':'about_layout'},{"obs":[text('',{},{'text':[baseConfig['hostname']]})]})
			]}))

		version_string = ""
		for key in ['version/version','version/patchlevel','version/security-patchlevel']:
			if baseConfig.has_key(key) and baseConfig[key]:
				if version_string:
					version_string = "%s-%s" % (version_string,baseConfig[key])
				else:
					version_string = baseConfig[key]

		rows.append(tablerow("",{},{"obs":[
			tablecol("",{'type':'about_layout'},{"obs":[text('',{},{'text':[ _('local Installation')]})]}),
			tablecol("",{'type':'about_layout'},{"obs":[text('',{},{'text':["%s %s" % (_('UCS Version'), version_string)]})]})
			]}))

		days = baseConfig.get( 'ssl/validity/days', '' )
		if days:
			days = datetime.datetime.fromtimestamp( int( days ) * 24 * 60 * 60 ).strftime( "%x" )

		rows.append(tablerow("",{},{"obs":[
			tablecol("",{'type':'about_layout'},{"obs":[text('',{},{'text':[ _('Validity date of the SSL certificate')]})]}),
			tablecol("",{'type':'about_layout'},{"obs":[text('',{},{'text':[ days ]})]})
			]}))

		rows.append(tablerow("",{},{"obs":[
			tablecol("",{"colspan":"2",'type':'about_layout'},{"obs":[]})
			]}))

		## Licence
		rows.append(tablerow("",{},{"obs":[
			tablecol("",{"colspan":"2",'type':'about_layout'},{"obs":[
			header(_("Licence"),{"type":"4"},{})
			]})
			]}))
		module=univention.admin.modules.get('settings/license')
		objects=module.lookup(None, self.lo, '')

		if objects:
			object=objects[0]
			object.open()
 			rows.append(tablerow("",{},{"obs":[
 				tablecol("",{'type':'about_layout'},{"obs":[text('',{},{'text':[object.descriptions['base'].short_description]})]}),
 				tablecol("",{'type':'about_layout'},{"obs":[text('',{},{'text':[object['base']]})]})
 				]}))

			if object['base'] == 'Free for personal use edition':
				self.save.put("personal_use","1")

 			rows.append(tablerow("",{},{"obs":[
 				tablecol("",{'type':'about_layout'},{"obs":[text('',{},{'text':[object.descriptions['accounts'].short_description]})]}),
 				tablecol("",{'type':'about_layout'},{"obs":[text('',{},{'text':[object['accounts']]})]})
 				]}))

			rows.append(tablerow("",{},{"obs":[
 				tablecol("",{'type':'about_layout'},{"obs":[text('',{},{'text':[object.descriptions['groupwareaccounts'].short_description]})]}),
 				tablecol("",{'type':'about_layout'},{"obs":[text('',{},{'text':[object['groupwareaccounts']]})]})
 				]}))

			rows.append(tablerow("",{},{"obs":[
 				tablecol("",{'type':'about_layout'},{"obs":[text('',{},{'text':[object.descriptions['clients'].short_description]})]}),
 				tablecol("",{'type':'about_layout'},{"obs":[text('',{},{'text':[object['clients']]})]})
 				]}))

			rows.append(tablerow("",{},{"obs":[
 				tablecol("",{'type':'about_layout'},{"obs":[text('',{},{'text':[object.descriptions['desktops'].short_description]})]}),
 				tablecol("",{'type':'about_layout'},{"obs":[text('',{},{'text':[object['desktops']]})]})
 				]}))

			rows.append(tablerow("",{},{"obs":[
 				tablecol("",{'type':'about_layout'},{"obs":[text('',{},{'text':[object.descriptions['expires'].short_description]})]}),
 				tablecol("",{'type':'about_layout'},{"obs":[text('',{},{'text':[object['expires']]})]})
 				]}))

			productTypes = ""
			for t in object['productTypes']:
				productTypes += ", " + t

 			rows.append(tablerow("",{},{"obs":[
  				tablecol("",{'type':'about_layout'},{"obs":[text('',{},{'text':[object.descriptions['productTypes'].short_description]})]}),
				tablecol("",{'type':'about_layout'},{"obs":[text('',{},{'text':[productTypes[2:]]})]})
  				]}))

			univention.debug.debug(univention.debug.ADMIN, univention.debug.ERROR, "check for personal use: %s" % self.save.get( 'personal_use' ))
			if self.save.get( 'personal_use' ) == '1':
				rows.append(tablerow("",{},{"obs":[
					tablecol("",{'type':'about_layout'},{"obs":[text('',{},{'text':[_('License')]})]}),
					tablecol("",{'type':'about_layout'},{"obs":[htmltext('',{},{'htmltext':[u'Die "Free For Personal Use" Ausgabe von Univention Corporate Server ist eine spezielle Softwarelizenz mit der Verbraucher im Sinne des � 13 BGB die kostenlose Nutzung von Univention Corporate Server und darauf basierenden Softwareprodukten f�r private Zwecke erm�glicht wird. <br><br>\
							Im Rahmen dieser Lizenz darf UCS von unseren Servern heruntergeladen, installiert und genutzt werden. Es ist jedoch nicht erlaubt, die Software Dritten zum Download oder zur Nutzung zur Verf�gung zu stellen oder sie im Rahmen einer �berwiegend beruflichen oder gewerbsm��igen Nutzung zu verwenden.  <br><br>\
							Die �berlassung der "Free For Personal Use"-Ausgabe von UCS erfolgt im Rahmen eines Schenkungsvertrages. Wir schlie�en deswegen alle Gew�hrleistungs- und Haftungsanspr�che aus, es sei denn, es liegt ein Fall des Vorsatzes oder der groben Fahrl�ssigkeit vor. Wir weisen darauf hin, dass bei der "Free For Personal Use"-Ausgabe die Haftungs-, Gew�hrleistungs-, Support- und Pflegeanspr�che, die sich aus unseren kommerziellen Softwarevertr�gen ergeben, nicht gelten.  <br><br>\
							Wir w�nschen Ihnen viel Freude bei der Nutzung der "Free For Personal Use" Ausgabe von Univention Corporate Server und freuen uns �ber Ihr Feedback. Bei Fragen wenden Sie sich bitte an unser Forum, dass Sie im Internet unter <a target=parent href=http://forum.univention.de/>http://forum.univention.de/</a> erreichen.']})]})
					]}))
 		else:
 			rows.append(tablerow("",{},{"obs":[
 				tablecol("",{"colspan":"2",'type':'about_layout'},{"obs":[text('',{},{'text':[_('no licence found')]})]})
 				]}))

		rows.append(tablerow("",{},{"obs":[
			tablecol("",{"colspan":"2",'type':'about_layout'},{"obs":[]})
			]}))

		## Contact
		rows.append(tablerow("",{},{"obs":[
			tablecol("",{"colspan":"2",'type':'about_layout'},{"obs":[
			header(_("Contact"),{"type":"4"},{})
			]})
			]}))

		rows.append(tablerow("",{},{"obs":[
			tablecol("",{'type':'about_layout'},{"obs":[text('',{},{'text':['Univention GmbH']})]}),
			tablecol("",{'type':'about_layout'},{"obs":[htmltext('',{},{'htmltext':[
			'<a href=http://www.univention.de target=parent>www.univention.de</a>'
			]})]})
			]}))

		rows.append(tablerow("",{},{"obs":[
			tablecol("",{'type':'about_layout'},{"obs":[text('',{},{'text':[_('ALL RIGHTS RESERVED')]})]}),
			tablecol("",{'type':'about_layout'},{"obs":[htmltext('',{},{'htmltext':[
			'<a href="mailto:info@univention.de">info@univention.de</a>'
			]})]})
			]}))

		rows.append(tablerow("",{},{"obs":[
			tablecol("",{"colspan":"2",'type':'about_layout'},{"obs":[]})
			]}))

		self.subobjs.append(table("",{'type':'content_main'},{"obs":rows}))

	def apply(self):
		self.applyhandlemessages()
