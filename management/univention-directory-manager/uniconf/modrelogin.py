# -*- coding: utf-8 -*-
#
# Univention Directory Manager
#  the admin login and relogin part
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

from uniparts import *
import os
import sys
import time
import ldap
import locale
import string
import re
import unimodule
import settings
from local import _

import univention.debug
import univention.config_registry

configRegistry=univention.config_registry.ConfigRegistry ()
configRegistry.load ()
LANG_DE = 'de_DE.utf8'
#LANG_EN = 'en_EN.utf8'
LANG_EN = 'C'
#LANG_DEFAULT = configRegistry.get ('directory/manager/web/language', locale.getdefaultlocale ())
LANG_DEFAULT = configRegistry.get ('directory/manager/web/language', LANG_EN)

def create(a,b,c):
	return modrelogin(a,b,c)

def myname():
	return _("Login")

def mydescription():
	return _("Login")

def myrgroup():
	return ""

def mywgroup():
	return ""
def mysubmodules():
	return []
class modrelogin(unimodule.unimodule):
	def mytype(self):
		return "dialog"

	def mydescription(self):
		return mydescription()

	def mysubmodules(self):
		return []

	def myinit(self):
		pass

	def myinit(self):

		self.save=self.parent.save
		if self.inithandlemessages():
			return
		self.authfail=None
		if self.save.get("logout"):
			self.subobjs.append(logout("",{},{}))
			return

		self.uaccess = self.args['uaccess']

		self.subobjs.append(table("",
					  {'type':'content_header'},
					  {"obs":[tablerow("",{},{"obs":[tablecol("",{'type':'login_layout'},{"obs":[]})]})]})
				    )
		self.nbook=notebook('', {}, {'buttons': [(_('Login'), _('Login'))], 'selected': 0})
		self.subobjs.append(self.nbook)

		sessioninvalid = None
		if self.req and self.req.meta and self.req.meta.has_key ('Sessioninvalid') \
				and self.req.meta['Sessioninvalid'] == '1':
					description_caption = _('Session Timeout')
					description1 = _('To increase the session timeout log into Univention Management Console, select the Univention Config Registry module and change the value of <code>directory/manager/timeout</code>.')
					#description2 = _('As an alternative you can set the UCR variable with the following command line statement <code>univention-config-registry directory/manager/timeout=TIMEOUT_IN_SECONDS</code>.')
					sessioninvalid = htmltext ('login_messagebox', {}, \
							{'htmltext': [_("""
								<h1 style='text-align:center; margin-top:0; top:0; font-weight:bold;'>
								<img style='float:none;' src='/icon/warning.png' />&nbsp;%s
								</h1>
								<p>%s</p>
								""") % (description_caption, description1)]})
		unsupportedbrowser = None
		if self.req and self.req.meta and self.req.meta.has_key ('Unsupportedbrowser') \
				and self.req.meta['Unsupportedbrowser'] == '1':
					description_caption = _('Unsupported web browser')
					description1 = _('The Univention Directory Manager (UDM) has not been tested with your web browser. You should use Firefox since version 3.x or Microsoft Internet Explorer since version 6.0.')
					unsupportedbrowser = htmltext ('login_messagebox', {}, \
							{'htmltext': [_("""
								<h1 style='text-align:center; margin-top:0; top:0; font-weight:bold;'>
								<img style='float:none;' src='/icon/warning.png' />&nbsp;%s
								</h1>
								<p>%s</p>
								""") % (description_caption, description1)]})
		# input fields:
		self.usernamein=question_text(_("Username"),{'width':'265','puretext': '1'},{"usertext":self.save.get("relogin_username"),"helptext":_("Please enter your username.")})
		self.cabut=button(_("Cancel"),{'icon':'/style/cancel.gif'},{"helptext":_("cancel login procedure")})
		if int(os.environ["HTTPS"]) == 1 or self.save.get("http") == 1:
			self.passwdin=question_secure(_("Password"),{'width':'265','puretext': '1'},{"usertext":self.save.get("relogin_passwd"),"helptext":_("please enter your password.")})
			self.okbut=button(_("OK"),{'icon':'/style/ok.gif'},{"helptext":_("Login")})
		else:
			self.passwdin=question_secure(_("Password"),{'width':'265','passive':'true','puretext': '1'},
							{"usertext":self.save.get("relogin_passwd"),"helptext":_("please enter your password.")})
			self.okbut=button(_("OK"),{'passive':'true','icon':'/style/ok.gif'},{"helptext":_("Login")})

		rows=[]

		if sessioninvalid:
			rows.append(tablerow("",{},{"obs":[tablecol("",{"colspan":"2",'type':'login_layout'},{"obs":[self.usernamein]}), tablecol("",{"colspan":"2","rowspan":'5','type':'login_layout_session_timeout'},{"obs":[sessioninvalid]})]}))
		elif unsupportedbrowser:
			rows.append(tablerow("",{},{"obs":[tablecol("",{"colspan":"2",'type':'login_layout'},{"obs":[self.usernamein]}), tablecol("",{"colspan":"2","rowspan":'5','type':'login_layout_session_timeout'},{"obs":[unsupportedbrowser]})]}))
		else:
			rows.append(tablerow("",{},{"obs":[tablecol("",{"colspan":"2",'type':'login_layout'},{"obs":[self.usernamein]})]}))
		rows.append(tablerow("",{},{"obs":[tablecol("",{"colspan":"2", 'type':'login_layout'},{"obs":[self.passwdin]})]}))

                #check if http should realy be used
                if int(os.environ["HTTPS"]) != 1:
                        sel = ""
                        if self.save.get("http") == 1:
                                sel = "selected"
                        self.httpbut = button('httpbut',{},{"helptext":_("")})
                        self.httpbool= question_bool(   _("Not using a secure SSL connection. Please accept to continue anyway."), {},
                                                        {'helptext': _("Not using a secure SSL connection. Please accept to continue anyway."),'button':self.httpbut,'usertext':sel})

                        use_httpbool=tablecol("",{'colspan':'2','type':'login_layout'},{"obs":[self.httpbool]})
                        rows.append(tablerow("",{},{"obs":[use_httpbool]}))


		# select domain...
		domaindns=[]
		for i in self.uaccess.searchDn(filter='(objectClass=univentionBase)', scope='base+one'):
			domaindns.append(i)

		domainpos=univention.admin.uldap.position(self.uaccess.base)
		domainlist=[]
		for dn in domaindns:
			domainpos.setDn(dn)
			(domaindescr,domaindepth) = domainpos.getPrintable_depth()
			domainlist.append({"level":str(domaindepth),"name":domainpos.getDn(),"description":domaindescr})
		if domainlist:
			self.choosedomain=question_select(_("Login Domain:"),{'width':'265'},{"helptext":_("choose Domain for login"),"choicelist":domainlist})
			rows.append(tablerow("",{},{"obs":[tablecol("",{"colspan":"2",'type':'login_layout'},{"obs":[self.choosedomain]})]}))

		# select language
		# the installed languages can be obtained via locale -a
		# but I shouldn't check on that but rely on the languages I set
		# up for this tool
		langs = [
				{"level": '0', "name": 'de', "description": "Deutsch"},
				{"level": '0', "name": 'en', "description": "English"}
				]
		default_lang = None
		if LANG_DEFAULT:
			if LANG_DEFAULT == 'C':
				default_lang = 'en'
			elif LANG_DEFAULT:
				default_lang = LANG_DEFAULT.split ('_')[0]

		if default_lang:
			for l in langs:
				if l['name'] == default_lang:
					l['selected'] = default_lang
					break

		if langs:
			self.chooselang=language_dojo_select(_("Language:"),{'width':'265'},{"helptext":_("Choose language for this session"),"choicelist":langs})
			rows.append(tablerow("",{},{"obs":[tablecol("",{"colspan":"2",'type':'login_layout'},{"obs":[self.chooselang]})]}))

		# ok / cancel
		okcol=tablecol("",{'type':'login_layout'},{"obs":[self.okbut]})
		cacol=tablecol("",{'type':'login_layout'},{"obs":[self.cabut]})		
		rows.append(tablerow("",{},{"obs":[okcol,cacol]}))

		self.subobjs.append(table("",
					  {'type':'content_main'},
					  {"obs":[tablerow("",
							   {},
							   {"obs":[tablecol("",{},{"obs":[table("",{},{"obs":rows})]})]})]}
					  )
				    )


	def apply(self):
		userdn = ''

		if self.applyhandlemessages():
			return
		if self.authfail:
			self.save.put("authfail","1")
			return

		self.save.put("relogin_username",self.usernamein.xvars.get("usertext",""))
		self.save.put("relogin_password",self.passwdin.xvars.get("usertext",""))
		mu=0
		
		if int(os.environ["HTTPS"]) != 1 and self.httpbool.selected():
			self.save.put("http",1)
		else:
			self.save.put("http",0)

		if self.cabut.pressed():
			self.save.put("logout",1)

		if self.okbut.pressed() or mu and self.input:
			self.save.put("user",self.save.get("relogin_username"))
			self.save.put("pass",self.save.get("relogin_password"))

			position=self.save.get('ldap_position')
			if not position:
				position=univention.admin.uldap.position(self.uaccess.base)

			if hasattr(self, 'choosedomain'):
				domain=self.choosedomain.getselected()
			else:
				domain=position.getBase()

			position.setLoginDomain(domain)
			position.setDn(domain)
			self.save.put('ldap_position', position)

			language = None
			if hasattr(self, 'chooselang'):
				language = self.chooselang.getselected()

			if language:
				if language == 'de':
					language = LANG_DE
				elif language == 'en':
					language = LANG_EN
				else:
					language = LANG_DEFAULT
				# WARNING this code could cause an exception maybe it needs to be surrounded by parenthesis
				os.environ["LC_MESSAGES"] = language
				locale.setlocale( locale.LC_MESSAGES, language )

			user=self.save.get("user")

			auth_ok = False
			gpl_version = False
			try:
				if  user == 'admin':
					self.usermessage(_("You can't login with the admin user"))
				else:
					userdn=self.uaccess.searchDn("(&(objectClass=posixAccount)(uid=%s))" % user,position.getLoginDomain(),required=1,scope="domain")[0]
			except univention.admin.uexceptions.noObject, ex:
				self.usermessage(_("Wrong Username or Password for the selected Domain"))
				return
			except Exception,ex:
				pass
			try:
				self.uaccess.bind(userdn, self.save.get("pass"))
			except univention.admin.uexceptions.authFail,ex:
				self.usermessage(_("Wrong Username or Password for the selected Domain"))
			except univention.admin.uexceptions.licenseNotFound:
				self.usermessage(_('Licence not found. During this session add and modify are disabled. You can install a new License in the About section.'))
				self.userinfo(_("Login successful"))
				self.save.put("uc_module","none")
				self.save.put("auth_ok","1")
				self.save.put("authfail",None)
			except univention.admin.uexceptions.licenseAccounts:
				self.usermessage(_('You have too many user accounts for your licence. During this session add and modify are disabled. You can install a new License in the About section.'))
				self.userinfo(_("Login successful"))
				self.save.put("uc_module","none")
				self.save.put("auth_ok","1")
				self.save.put("authfail",None)
			except univention.admin.uexceptions.licenseClients:
				self.usermessage(_('You have too many client accounts for your licence. During this session add and modify are disabled. You can install a new License in the About section.'))
				self.userinfo(_("Login successful"))
				self.save.put("uc_module","none")
				self.save.put("auth_ok","1")
				self.save.put("authfail",None)
			except univention.admin.uexceptions.licenseDesktops:
				self.usermessage(_('You have too many desktop accounts for your licence. During this session add and modify are disabled. You can install a new License in the About section.'))
				self.userinfo(_("Login successful"))
				self.save.put("uc_module","none")
				self.save.put("auth_ok","1")
				self.save.put("authfail",None)
			except univention.admin.uexceptions.licenseGroupware:
				self.usermessage(_('You have too many groupware accounts for your licence. During this session add and modify are disabled. You can install a new License in the About section.'))
				self.userinfo(_("Login successful"))
				self.save.put("uc_module","none")
				self.save.put("auth_ok","1")
				self.save.put("authfail",None)
			except univention.admin.uexceptions.licenseExpired:
				self.usermessage(_('Your licence is expired. During this session add and modify are disabled. You can install a new License in the About section.'))
				self.userinfo(_("Login successful"))
				self.save.put("uc_module","none")
				self.save.put("auth_ok","1")
				self.save.put("authfail",None)
			except univention.admin.uexceptions.licenseWrongBaseDn:
				self.usermessage(_('Your licence is not valid for your LDAP-Base. During this session add and modify are disabled. You can install a new License in the About section.'))
				self.userinfo(_("Login successful"))
				self.save.put("uc_module","none")
				self.save.put("auth_ok","1")
				self.save.put("authfail",None)
			except univention.admin.uexceptions.licenseInvalid:
				self.usermessage(_('Your licence is not valid. During this session add and modify are disabled. You can install a new License in the About section.'))
				self.userinfo(_("Login successful"))
				self.save.put("uc_module","none")
				self.save.put("auth_ok","1")
				self.save.put("authfail",None)
			except univention.admin.uexceptions.licenseDisableModify:
				self.usermessage(_('Your licence does not allow modifications. During this session add and modify are disabled. You can install a new License in the About section.'))
				self.userinfo(_("Login successful"))
				self.save.put("uc_module","none")
				self.save.put("auth_ok","1")
				self.save.put("authfail",None)
			except univention.admin.uexceptions.licenseGPLversion:
				self.usermessage(_('Your license status could not be validated. Thus, you are not eligible to support and maintenance. If you have bought a license, please contact Univention or your vendor. You can install a new License in the About section.'))
				gpl_version = True
				auth_ok = True
			except univention.admin.uexceptions.freeForPersonalUse:
				self.save.put("personal_use","1")
				auth_ok = True
			else:
				auth_ok = True

			if auth_ok:
				warning = int( configRegistry.get( 'ssl/validity/warning', 30 ) )
				days = int( configRegistry.get( 'ssl/validity/days', 0 ) )
				now = int( time.time() / 60 / 60 / 24 )
				if days and ( days - now ) < warning:
					if gpl_version:
						self.usermessage += "<br> "
						self.usermessage += _( "Your SSL certificate will expire in %d days." ) % ( days - now )
					else:
						self.usermessage( _( "Your SSL certificate will expire in %d days." ) % ( days - now ) )

					self.userinfo(_("Login successful"))
					self.save.put( "uc_module", "none" )
					self.save.put( "auth_ok", "1" )
					self.save.put( "authfail", None )
				else:
					self.save.put("uc_module","none")
					self.save.put("auth_ok","1")
					self.save.put("authfail",None)

		if userdn:
			_settings=settings.settings(self.uaccess, userdn)
			self.save.put("settings", _settings)
			univention.debug.debug(univention.debug.ADMIN, univention.debug.INFO, "modrelogin: saved settings, allowed modules are %s" % _settings.list_adminModules)
			position.__loginDomain=_settings.base_dn
			self.save.put('ldap_position', position)

			if str(self.save.get("uc_module")) in ['', 'none', 'relogin'] and _settings and len(_settings.list_adminModules) == 1:
				self.save.put("uc_module", _settings.list_adminModules[0].replace('mod',''))
				if _settings.list_adminModules[0] == "modself":
					self.save.put("uc_submodule", "users/self")
					self.save.put("uc_virtualmodule", "self")
