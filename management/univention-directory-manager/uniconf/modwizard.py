# -*- coding: utf-8 -*-
#
# Univention Diectory Manager
#  handle the wizard objects
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

import unimodule
from uniparts import *
from local import _
from syntax import *

import univention.debug
import univention.admin.uldap
import univention.admin.modules
import univention.admin.objects
import unimodule
import univention.config_registry

import univention.directory.reports as udr

import operator
import shutil
import string
import ldap
import types
import re

ucr = univention.config_registry.ConfigRegistry()
ucr.load()
DEFAULT_SIZELIMIT=1000
directory_manager_web_ldap_sizelimit = ucr.get('directory/manager/web/ldap/sizelimit', DEFAULT_SIZELIMIT) # maximum number of results searched. This is more than the number of results that can be displayed !
activate_icons = ucr.get('directory/manager/web/searchresult/showicons', 'true').lower()

# if the definied sizelimit is invalid -> failback to default
try:
	max_results = int(directory_manager_web_ldap_sizelimit)
except:
	max_results = DEFAULT_SIZELIMIT

def create(a,b,c):
	return modwizard(a,b,c)

# most importantly, the menu entries are returned here
def myinfo(settings):
	if not settings.listAdminModule('modwizard'):
		return unimodule.realmodule("browse", "", "")

	modules=univention.admin.modules.modules
	moduleids=modules.keys()

	modlist=[]
	done=[]
	univention.debug.debug(univention.debug.ADMIN, univention.debug.INFO, "modwizard: Trying to catch super modules first.")
	for id in moduleids:
		module=univention.admin.modules.get(id)
		if univention.admin.modules.wantsWizard(module):
			univention.debug.debug(univention.debug.ADMIN, univention.debug.INFO, "modwizard: Module %s wants to be managed by wizard." % univention.admin.modules.name(module))
			if univention.admin.modules.childModules(module):
				univention.debug.debug(univention.debug.ADMIN, univention.debug.INFO, "modwizard: Module %s is super module of: %s." % (univention.admin.modules.name(module), univention.admin.modules.childModules(module)))
				done.extend(univention.admin.modules.childModules(module))
				submodlist=[]
				for id, info in univention.admin.modules.wizardOperations(module).items():
					univention.debug.debug(univention.debug.ADMIN, univention.debug.INFO, "modwizard: Adding wizard operation of module %s: %s" % (univention.admin.modules.name(module), id))
					submodlist.append(unimodule.submodule(id, info[0], info[1]))
				modlist.append(unimodule.virtualmodule(univention.admin.modules.name(module), univention.admin.modules.wizardMenuString(module), univention.admin.modules.wizardDescription(module), submodlist))

	univention.debug.debug(univention.debug.ADMIN, univention.debug.INFO, "modwizard: Done: %s. Now trying to process normal modules." % done)
	for id in moduleids:
		if not id in done:
			module=univention.admin.modules.get(id)
			if univention.admin.modules.wantsWizard(module) and not univention.admin.modules.childModules(module):
				univention.debug.debug(univention.debug.ADMIN, univention.debug.INFO, "modwizard: Module %s is normal module." % univention.admin.modules.name(module))
				submodlist=[]
				for id, info in univention.admin.modules.wizardOperations(module).items():
					univention.debug.debug(univention.debug.ADMIN, univention.debug.INFO, "modwizard: Adding wizard operation of module %s: %s" % (univention.admin.modules.name(module), id))
					submodlist.append(unimodule.submodule(id, info[0], info[1]))
				modlist.append(unimodule.virtualmodule(univention.admin.modules.name(module), univention.admin.modules.wizardMenuString(module), univention.admin.modules.wizardDescription(module), submodlist))

	known_modules=["users/user","groups/group","networks/network","computers/computer","dns/dns","dhcp/dhcp","shares/share","shares/print","policies/policy",]
	available_modules={}
	modules_sorted=[]

	for i in modlist:
		available_modules[i.id]=i

	# known modules are sorted manually, all others are appended later
	for i in known_modules:
		if i=="spacer":
			modules_sorted.append(i)
		elif i in available_modules.keys() and settings.listWizard(i):
			modules_sorted.append(available_modules[i])
			del available_modules[i]

	left_module_ids=available_modules.keys()
	left_module_ids.sort()
	for i in left_module_ids:
		if settings.listWizard(i):
			modules_sorted.append(available_modules[i])

	if not modules_sorted:
		return unimodule.realmodule("wizard", '')
	else:
		return unimodule.realmodule("wizard", _("Wizard"), virtualmodules=modules_sorted)

def myrgroup():
	return _("Account Operators")
def mywgroup():
	return _("Account Operators")
def mymenunum():
	return 300

class modwizard(unimodule.unimodule):
	def mytype(self):
		return "dialog"


	def add(self, module_type):
		position=self.position
		position.setDn(position.getBase())
		settings=self.save.get('settings')

		###########################################################################
		# header
		###########################################################################
		self.div_start('content-wrapper')

		module=univention.admin.modules.get(module_type)
		module_description=univention.admin.modules.short_description(module)
		#self.subobjs.append(table("",
		#			  {'type':'content_header'},
		#			  {"obs":[tablerow("",{},{"obs":[tablecol("",{},{"obs":[]})]})]}))

		tab_line = htmltext ('', {}, \
			{'htmltext': ["""
					<div id="content-head">
					<!-- @start tab-navigation -->
					<ul class="tabs">
						<li class="active">
				""" ]})
		self.subobjs.append(tab_line)
		#self.nbook=notebook('', {}, {'buttons': [(univention.admin.modules.wizardOperations(module).get("add", ['',''])[1],
		#					  univention.admin.modules.wizardOperations(module).get("add", ['',''])[1])], 'selected': 0})
		self.nbook=button(univention.admin.modules.wizardOperations(module).get("add", ['',''])[1],{'link': '1'},{'helptext': univention.admin.modules.wizardOperations(module).get("add", ['',''])[1]})
		self.subobjs.append(self.nbook)

		tab_line = htmltext ('', {}, \
			{'htmltext': ["""
						</li>
					</ul>
					<!-- @end tab-navigation -->
				</div>
				""" ]})
		self.subobjs.append(tab_line)

		self.div_start('content')

		#headline = htmltext ('', {}, \
		#	{'htmltext': ["""
		#		<h2 class=inline>%s</h2>
		#		""" % univention.admin.modules.wizardOperations(module).get("add", ['',''])[1]
		#		]})
		#self.subobjs.append(headline)

		self.div_start('form-wrapper', divtype='class')

		###########################################################################
		# Select Domain
		###########################################################################

		domaindns=[]
		# search LDAP directory for domains
		for i in self.lo.searchDn(filter='(objectClass=univentionBase)', base=position.getBase(), scope='sub'):
			univention.debug.debug(univention.debug.ADMIN, univention.debug.INFO, "modwizard: Found domain: %s" % i)
			domaindns.append(i)

		# temporary position object
		domainpos=univention.admin.uldap.position(position.getBase())

		# append search results to a list of XML objects

		domain_preselect=self.save.get('wizard_domain')
		if not domain_preselect:
			domain_preselect=position.getLoginDomain()


		domainlist=[]
		for dn in domaindns:
			domainpos.setDn(dn)

			if domainpos.getDn() == domain_preselect:
				domainlist.append({"name":domainpos.getDn(),"description":domainpos.getPrintable(), "selected":domainpos.getDn()})
			else:
				domainlist.append({"name":domainpos.getDn(),"description":domainpos.getPrintable()})
		# create select box
		self.select_domain_button=button(_("apply"),{},{"helptext":""})
		self.domain_select=question_select(_("Select domain:"),{},{"helptext":_("Where to create the new object"),"choicelist":domainlist,"button":self.select_domain_button})
		domain_select_col=tablecol("",{'type':'wizard_layout'},{"obs":[self.domain_select]})

		###########################################################################
		# select creation path
		###########################################################################

		if self.save.get('wizard_find_pathlist',None) and self.save.get('wizard_find_displaypathlist',None):
			pathlist=self.save.get('wizard_find_pathlist',None)
			displaypathlist=self.save.get('wizard_find_displaypathlist',None)
		else:
			pathlist=[]
			displaypathlist=[]

			container_name=string.split(module_type, '/')[0]
			if settings.default_containers.has_key(container_name):
				pathlist.extend(settings.default_containers[container_name])
			else:
				# retrieve path info from 'cn=directory,cn=univention,...' object
				pathResult = self.lo.get('cn=directory,cn=univention,'+domain_preselect)
				if not pathResult:
					pathResult = self.lo.get('cn=default containers,cn=univention,'+domain_preselect)
				infoattr=univention.admin.modules.wizardPath(module)
				if not infoattr:
					infoattr="univention%s%sObject" % (container_name[0].upper(), container_name[1:])
				univention.debug.debug(univention.debug.ADMIN, univention.debug.INFO, "Search path setting: %s " % infoattr)
				if pathResult.has_key(infoattr) and pathResult[infoattr]:
					pathlist=pathResult[infoattr]
				if not pathlist:
					pathlist.extend( univention.admin.modules.defaultContainers( module ) )
			new_pathlist=[]
			for i in settings.filterDNs(pathlist, parents=0):
				try:
					self.lo.searchDn(base=i, scope='base')
					new_pathlist.append(i)
				except Exception, e:
					pass
			pathlist=new_pathlist

			if pathlist:
				# temporary position object
				pathpos=univention.admin.uldap.position(position.getBase())

				displaypathlist=[]
				for pathname in pathlist:
					pathpos.setDn(pathname)
					displaypathlist.append({"name":pathpos.getDn(),"description":pathpos.getPrintable(long=1)})
				displaypathlist.sort()

		path_preselect=self.save.get('wizard_path')
		if path_preselect:
			for i in displaypathlist:
				if i['name'] == path_preselect:
					i['selected']=i['name']
				else:
					i['selected']=''

		if displaypathlist:
			self.path_select=question_select(_("Select container:"),{},{"helptext":_("Choose a position for your object"),"choicelist":displaypathlist})
			path_select_obj=self.path_select
		else:
			path_select_obj=text('',{},{'text':[_('no default path found')]})

		self.save.put('wizard_select_pathlist',pathlist)
		self.save.put('wizard_select_displaypathlist',displaypathlist)

		self.div_start('form-item col', divtype='class')
		self.subobjs.append(path_select_obj)
		self.div_stop('form-item col')


		rows=[]
		###########################################################################
		# select superordinate if neccessary
		###########################################################################

		if hasattr(module,"wizardsuperordinates"):
			superordinatetypes=module.wizardsuperordinates
			superordinatelist=[]
			path=self.save.get('wizard_path')
			for sot in superordinatetypes:
				if sot=="None":
					slist=[None]
				else:
					smod=univention.admin.modules.get(sot)
					slist=univention.admin.modules.lookup(smod,None,self.lo, base=path, filter=None, scope="sub")
				superordinatelist+=slist
			superordinate=self.save.get("wizard_superordinate")
			if not superordinate:
				if superordinatelist[0]:
					superordinate=superordinatelist[0].dn
				else:
					superordinate="None"
				self.save.put("wizard_superordinate",superordinate)
			superordinatechoicelist=[]
			for s in superordinatelist:
				if s==None:
					temp={"name":"None","description":_("None")}
					stype="None"
				else:
					temp={"name":s.dn,"description":s.dn}
					stype=s.module
				if temp["name"]==superordinate:
					temp["selected"]=temp["name"]
					self.save.put("wizard_superordinatetype",stype)
				superordinatechoicelist.append(temp)
			self.select_superordinate_button=button(_("apply"),{},{"helptext":""})
			self.superordinate_select=question_select(_("Superordinate:"),{},{"helptext":_("Superordinate Object"),"choicelist":superordinatechoicelist,"button":self.select_superordinate_button})
			superordinate_select_col=tablecol("",{'type':'wizard_layout'},{"obs":[self.superordinate_select]})
			self.new_row()
			self.div_start('form-item col', divtype='class')
			self.subobjs.append(self.superordinate_select)
			self.div_stop('form-item col')


		# check for child modules
		child_ids=univention.admin.modules.childModules(module)
		if pathlist and child_ids:
			childlist=[]
			for child_id in child_ids:
				if hasattr(module,"wizardtypesforsuper"):
					if child_id not in module.wizardtypesforsuper.get(self.save.get("wizard_superordinatetype"),[]):
						continue
				if univention.admin.modules.wizardOperations(child_id).get('add'):
					childmodule=univention.admin.modules.get(child_id)
					childlist.append({"name":univention.admin.modules.name(childmodule), "description":"%s"%univention.admin.modules.short_description(childmodule).split(':',1)[-1]})
			childlist.sort()
			child_preselect=self.save.get('wizard_child')
			if not child_preselect:
				child_preselect = ucr.get ('directory/manager/web/modules/%s/add/default' % (module.module), None)
			if child_preselect:
				for i in childlist:
					if i['name'] == child_preselect:
						i['selected']=i['name']
					else:
						i['selected']=''
			else:
				childlist[0]["selected"]="1"
			self.child_module_select=question_select(_("Select Type:"),{},{"helptext":_("Choose the desired object type."), "choicelist":childlist})
			self.div_start('form-item col', divtype='class')
			self.subobjs.append(self.child_module_select)
			self.div_stop('form-item col')
			self.new_row()
			#rows.append(tablerow('',{},{'obs':[tablecol("",{"colspan":"2",'type':'wizard_layout'},{"obs":[self.child_module_select]})]}))

		# check if module has templates
		if hasattr(module,'template') and module.template:
			template_module=univention.admin.modules.get(module.template)
			templatelist = [{"name":"None", "description":_("no template")}] # represents "no" template

			for template in univention.admin.modules.lookup(template_module,None,self.lo,scope='sub'):
				template.open()
				templatelist.append({"name":template.dn,"description":template["name"]})
			
			# check the UCR for a default template to be selected automatically 
			# when creating a new instance (e.g., a new user)
			template_preselected = ucr.get ('directory/manager/web/modules/%s/add/default' % (module.module), None)
			if template_preselected:
				for i in templatelist:
					if i['description'] == template_preselected:
						i['selected']=i['name']
					else:
						i['selected']=''

			self.template_select=question_select(_("Select Template:"),{},{"helptext":_("Which template should new the new object be based on?"),
																		   "choicelist":templatelist})
			# rows.append(tablerow('',{},{'obs':[tablecol("",{"colspan":"2",'type':'wizard_layout'},{"obs":[self.template_select]})]}))
			self.div_start('form-item col', divtype='class')
			self.subobjs.append(self.template_select)
			self.div_stop('form-item col')
			self.new_row()

		if not child_ids and not (hasattr(module,'template') and module.template):
			self.new_row()


		# generate table
		main_rows = []
		#main_rows.append(
		#	tablerow("",{},{"obs":[tablecol("",{'type':'content_main'},{"obs":[table("",{'type':'search_header'},{"obs":rows})]})]})
		#)

		self.div_start('form-item col', divtype='class')
		self.div_stop('form-item col')

		self.div_start('form-item col', divtype='class')
		attr={'class':'submit'}
		if not pathlist:
			attr['passive']='1'
		attr['defaultbutton']='1'
		self.cancel_button=button(_('Cancel'),{'class':'cancel'},{'helptext':_('Cancel')})
		self.subobjs.append(self.cancel_button)
		self.next_button=button(_('Next'),attr,{'helptext':_('go ahead')})
		self.subobjs.append(self.next_button)
		self.div_stop('form-item col')
		self.new_row()

		self.div_stop('form-wrapper')
		self.div_stop('content')
		self.div_stop('content-wrapper')

	def report( self, search_type ):
		'''creates reports for all objects defined by the search criterias'''

		# get the relevant admin module
		module_object = univention.admin.modules.get( search_type )
		module_description=univention.admin.modules.short_description( module_object )
		if not module_object:
			return

		self.div_start('content-wrapper', divtype='id')

		title = _( 'Create %s Reports' ) % univention.admin.modules.short_description( module_object )
		self.nbook=notebook('', {}, {'buttons': [( title, title )], 'selected': 0})
		self.subobjs.append(self.nbook)
		self.div_start('content', divtype='id')

		rows = []
		# Available reports
		mods = univention.admin.modules.childModules( module_object )
		mods.insert( 0, univention.admin.modules.name( module_object ) )
		udr_cfg = univention.directory.reports.Config()
		report_list = []
		univention.debug.debug(univention.debug.ADMIN, univention.debug.INFO, 'report: %s' % mods )
		first = None
		for mod in mods:
			reports = udr_cfg.get_report_names( mod )
			mod_obj = univention.admin.modules.get( mod )
			mod_descr = univention.admin.modules.short_description( mod_obj )
			for report in reports:
				key = '%s:%s' % ( mod, report )
				description = '%s (%s)' % ( mod_descr, report )
				if report == udr_cfg.default_report_name and mod == mods[ 0 ]:
					first = { 'name' : key, 'description' : description }
				else:
					report_list.append( { 'name' : key, 'description' : description } )

		report_list = sorted( report_list, key = operator.itemgetter( 'description' ) )
		if first:
			report_list.insert( 0, first )
		sel = self.save.get( 'uc_report_template', None )
		if sel:
			for i in range( len( report_list ) ):
				if report_list[ i ][ 'name' ] == sel:
					report_list[ i ][ 'selected' ] = '1'
					break
		self.report_select = question_select('', { 'width' : '300' }, { "helptext" : _( "Select Report" ), "choicelist" : report_list } )
		self.create_report_button=button(_('create report'),{'class':'submit'},{'helptext':_('Create Report')})

		description = _( 'Select the report you want to create: ' )
		rows.append(tablerow("",{},{"obs":[
			tablecol("",{"colspan": "3", 'type' : 'wizard_layout' },
					 { 'obs' : [ text('',{},{'text':[ description ]}) ] } )	]}))
		rows.append(tablerow("",{},{"obs":[
			tablecol( '', { 'type':'wizard_layout'},{'obs':[self.report_select]}),
			tablecol( '', { 'type' : 'wizard_layout_bottom' },{ 'obs' : [ self.create_report_button ] } ),
												]}))
		rows.append(tablerow("",{},{"obs":[
			tablecol( '', { 'colspan' : '3', 'type' : 'wizard_layout' },{ 'obs' : [ text('',{},{'text':[ '' ] } ) ] } )
												]}))

		# generate search table
		main_rows = []
		main_rows.append(
			tablerow("",{},{"obs":[tablecol("",{'type':'content_main'},{"obs":[table("",{'type':'search_header'},{"obs":rows})]})]})
		)

		main_rows.append(
			tablerow("",{},{"obs":[tablecol("",{'type':'wizard_layout'},{"obs":[space('',{'size':'1'},{})]})]})
		)

		if self.save.get( 'uc_report_create' ) == True:
			nresults, module_descr, report_name, url, rep_type = self.create_report()
			self.save.put( 'uc_report_create', False )
			if url:
				univention.debug.debug(univention.debug.ADMIN, univention.debug.INFO, 'create report: url: %s' % url )
				if rep_type == udr.Document.TYPE_LATEX:
					icon_path = unimodule.selectIconByName( 'pdf-report' )
				else:
					icon_path = unimodule.selectIconByName( 'csv-report' )

				icon_widget = icon( '', { 'url' : icon_path }, {} )
				icon_col = tablecol("",{'type':'wizard_layout_icon'},{ "obs":[ icon_widget, ] } )
				url_col = tablecol("",{'type':'wizard_layout'},{ "obs":[ htmltext( "", {}, { "htmltext" : [ url ] }) ] } )
				main_rows.append(
					tablerow( '', {},
							  { "obs" : [ tablecol( '', { 'type' : 'wizard_layout' },
													{ 'obs' : [ header( _( "Report was created successfully: %(count)d '%(module)s' objects included" ) % { 'count' : nresults, 'module' : module_descr },
																		{ "type" : "2" }, {} ) ] } ) ] } ) )
				main_rows.append(
					tablerow("",{},{"obs":[ table( "",{'type':'content_main'},{"obs": [ tablerow( '', {},
							  { "obs" : [ icon_col, url_col ] } ) ] } ) ] } ) )

		# main table
		self.subobjs.append(table("",
					  {'type':'content_main'},
					  {"obs":main_rows})
				    )
		self.div_stop('content')
		self.div_stop('content-wrapper')

	def create_report( self ):
		position=self.position
		position.setDn(position.getBase())
		settings=self.save.get('settings')
		if self.save.get('reload_settings'):
			self.save.put('reload_settings', None)
			settings.reload(self.lo)

		module_name, report_name = self.save.get( 'uc_report_template', ':' ).split( ':', 1 )
		module_obj = univention.admin.modules.get( module_name )
		module_descr = univention.admin.modules.short_description( module_obj )

		search_domain_only=1
		search_one_level=0

		search_property_name = self.save.get('wizard_search_property')
		if not module_obj.property_descriptions.has_key( search_property_name ):
			search_property_name = '*'

		if search_property_name != '*':
			search_value=self.save.get('wizard_search_value')
		else:
			search_value='*'
		univention.debug.debug(univention.debug.ADMIN, univention.debug.INFO, 'create report: search_property: %s' % search_property_name )

		allstr = _( "all registered %s containers" ) % module_descr
		domainstr = _( "selected domain" )
		domainincsubstr = _( "selected domain including subdomains" )

		if self.save.get( 'wizard_find_pathlist', None ):
			pathlist = self.save.get('wizard_find_pathlist',None)
		else:
			pathlist=[]

			container_name=string.split(search_type, '/')[0]
			if settings.default_containers.has_key(container_name):
				pathlist.extend(settings.default_containers[container_name])
			else:
				# retrieve path info from 'cn=directory,cn=univention,...' object
				pathResult = self.lo.get('cn=directory,cn=univention,'+domain_preselect)
				if not pathResult:
					pathResult = self.lo.get('cn=default containers,cn=univention,'+domain_preselect)
				infoattr=univention.admin.modules.wizardPath(search_module)
				if not infoattr:
					infoattr="univention%s%sObject" % (container_name[0].upper(), container_name[1:])
				if pathResult.has_key(infoattr) and pathResult[infoattr]:
					pathlist=pathResult[infoattr]
				if not pathlist:
					pathlist.extend( univention.admin.modules.defaultContainers( search_module ) )

			new_pathlist=[]
			for i in settings.filterDNs(pathlist, parents=0):
				try:
					self.lo.searchDn(base=i, scope='base')
					new_pathlist.append(i)
				except Exception, e:
					pass
			pathlist=new_pathlist

			# temporary position object
			pathpos=univention.admin.uldap.position(position.getBase())

			self.save.put('wizard_find_pathlist',pathlist)

		path_preselect=self.save.get('wizard_path')
		if not path_preselect:
			if pathlist:
				path_preselect=allstr
			else:
				path_preselect=domainstr

		domain_preselect=self.save.get('wizard_domain')
		if not domain_preselect:
			domain_preselect=position.getLoginDomain()

		searchpath=[path_preselect]
		if searchpath[0] == allstr:
			# search all registered containers
			searchpath=pathlist
			search_one_level=1
			search_domain_only=0
		if searchpath[0] == domainstr:
			# search entire domain
			searchpath=[domain_preselect]
		if searchpath[0] == domainincsubstr:
			# search entire domain including sub domains
			searchpath=[domain_preselect]
			search_domain_only=0

		if search_domain_only:
			scope="domain"
		elif search_one_level:
			scope="one"
		else:
			scope="sub"

		result={}
		nresults=0
		cache=0
		univention.debug.debug(univention.debug.ADMIN, univention.debug.INFO, 'create report: search_path: %s' % searchpath )
		univention.debug.debug(univention.debug.ADMIN, univention.debug.INFO, 'create report: scope: %s' % scope )
		for path in searchpath:
			searchposition=univention.admin.uldap.position(position.getBase())
			searchposition.setDn(path)

			# search...
			if search_property_name != '*':
				filter=univention.admin.filter.expression(search_property_name, search_value)
			else:
				filter=''
			try:
				bas=searchposition.getDn()
				result[ searchposition.getDn() ] = settings.filterObjects( univention.admin.modules.lookup( module_obj, None, self.lo, base = bas, filter = filter, scope = scope ) )
				nresults = nresults + len( result[ searchposition.getDn() ] )
				univention.debug.debug(univention.debug.ADMIN, univention.debug.INFO, 'create report: more results: %s' % len( result[ searchposition.getDn() ] ) )
			except univention.admin.uexceptions.ldapError, msg:
				result = {}

			list_attributes = settings.getListAttributes( module_name )
			if result.has_key( searchposition.getDn() ) and ( search_property_name != '*' or list_attributes ):
				for i in result[ searchposition.getDn() ]:
					if not i.has_key( search_property_name ) or not i[ search_property_name ] or list_attributes:
						try:
							univention.debug.debug( univention.debug.ADMIN, univention.debug.INFO, 'open object %s' % ( i ) )
							univention.admin.objects.open( i )
						except univention.admin.uexceptions.insufficientInformation, m:
							self.usermessage(_('Failed to open object, insufficient or ambiguous values returned from search (%s)')%m)
							try:
								univention.debug.debug(univention.debug.ADMIN, univention.debug.ERROR, 'Failed to open object, insufficient or ambiguous values returned from search (%s) at result %s'%(m,i))
							except:
								univention.debug.debug(univention.debug.ADMIN, univention.debug.ERROR, 'Failed to open object, insufficient or ambiguous values returned from search (%s)'%(m))

		univention.debug.debug(univention.debug.ADMIN, univention.debug.INFO, 'create report: results: %s' % result.values() )
		sorting_helper_list=[]
		for pos, items in result.items():
			# sort items
			for n in range( len( items ) ):
				name = univention.admin.objects.description(items[n])
				sorting_helper_list.append( ( name, items[ n ] ) )

		def caseigncompare(a, b):
			a2=a.upper()
			b2=b.upper()
			if a2 == b2:
				# fallback to casecompare
				if a == b:
					return 0
				l=[a, b]
				l.sort()
				if l.index(a) < l.index(b):
					return -1
				else:
					return 1

			l=[a2, b2]
			l.sort()

			if l.index(a2) < l.index(b2):
				return -1
			else:
				return 1

		sorting_helper_list = sorted( sorting_helper_list, cmp = caseigncompare, key = operator.itemgetter( 0 ) )
		udr.admin.connect( access = self.lo )
		udr.admin.clear_cache()
		cfg = udr.Config()
		template = cfg.get_report( module_name, report_name )
		doc = udr.Document( template, header = cfg.get_header(module_name, report_name), footer = cfg.get_footer(module_name, report_name) )
		tmpfile = doc.create_source( [ item[ 1 ] for item in sorting_helper_list ] )
		if doc._type == udr.Document.TYPE_LATEX:
			pdffile = doc.create_pdf( tmpfile )
			os.unlink( tmpfile )
		else:
			pdffile = tmpfile
		univention.debug.debug( univention.debug.ADMIN, univention.debug.INFO, 'create report: LaTeX file: %s' % tmpfile )
		univention.debug.debug( univention.debug.ADMIN, univention.debug.INFO, 'create report: LaTeX file: %s' % pdffile )
		doc_type = doc._type
		univention.debug.debug( univention.debug.ADMIN, univention.debug.INFO, 'create report: DOC-TYPE: %s' % doc_type )
		del result, sorting_helper_list, cfg, doc
		try:
			os.unlink( tmpfile[ : -4 ] + 'aux' )
			os.unlink( tmpfile[ : -4 ] + 'log' )
		except:
			pass
		if pdffile:
			shutil.copy( pdffile, '/usr/share/univention-directory-manager/www/directory-reports' )
			os.unlink( pdffile )

			url = '/univention-directory-manager/directory-reports/%s' % os.path.basename( pdffile )
			link = '<a target="_blank" href="%s">%s (%s)</a>' % ( url, module_descr, report_name )

			return ( nresults, module_descr, report_name, link, doc_type )
		else:
			return ( 0, module_descr, report_name, '<b>%s</b>' % _( 'Error: The report could not be created!' ), doc_type )


	def find(self, search_type):
		position=self.position
		position.setDn(position.getBase())
		settings=self.save.get('settings')
		if self.save.get('reload_settings'):
			self.save.put('reload_settings', None)
			settings.reload(self.lo)

		search_module=univention.admin.modules.get(search_type)
		if not search_module:
			return
		module_description=univention.admin.modules.short_description(search_module)

		###########################################################################
		# header
		###########################################################################

		self.div_start('content-wrapper')

		#self.subobjs.append(table("",
		#			  {'type':'content_header'},
		#			  {"obs":[tablerow("",{},{"obs":[tablecol("",{'type':'wizard_layout'},{"obs":[]})]})]}))

		tab_line = htmltext ('', {}, \
			{'htmltext': ["""
					<div id="content-head">
					<!-- @start tab-navigation -->
					<ul class="tabs">
						<li class="active">
				""" ]})
		self.subobjs.append(tab_line)
		self.nbook=button(univention.admin.modules.wizardOperations(search_module).get("find", ['',''])[1],{'link': '1'},{'helptext': univention.admin.modules.wizardOperations(search_module).get("find", ['',''])[1]})
		# self.nbook=button(univention.admin.modules.wizardOperations(search_module).get("find", ['',''])[1],{'link': '1'},{'helptext': _('Find')})
		self.subobjs.append(self.nbook)

		#self.nbook=notebook('', {}, {'buttons': [(univention.admin.modules.wizardOperations(search_module).get("find", ['',''])[1],
		#					  univention.admin.modules.wizardOperations(search_module).get("find", ['',''])[1])], 'selected': 0})

		tab_line = htmltext ('', {}, \
			{'htmltext': ["""
						</li>
					</ul>
					<!-- @end tab-navigation -->
				</div>
				""" ]})
		self.subobjs.append(tab_line)

		self.div_start('content')

		#headline = htmltext ('', {}, \
		#	{'htmltext': ["""
		#		<h2 class=inline>%s</h2>
		#		""" % univention.admin.modules.wizardOperations(search_module).get("find", ['',''])[1]
		#		]})
		#self.subobjs.append(headline)

		#self.nbook=notebook('', {}, {'buttons': [(univention.admin.modules.wizardOperations(search_module).get("find", ['',''])[1],
		#					  univention.admin.modules.wizardOperations(search_module).get("find", ['',''])[1])], 'selected': 0})
		#self.subobjs.append(self.nbook)

		###########################################################################
		# begin search table
		self.div_start('form-wrapper', divtype='class')

		rows=[]

		###########################################################################
		# Select Domain
		###########################################################################

		domaindns=[]
		# search LDAP directory for domains
		for i in self.lo.searchDn(filter='(objectClass=univentionBase)', base=position.getBase(), scope='sub'):
			univention.debug.debug(univention.debug.ADMIN, univention.debug.INFO, "modwizard: Found domain: %s" % i)
			domaindns.append(i)

		# temporary position object
		domainpos=univention.admin.uldap.position(position.getBase())

		# append search results to a list of XML objects
		domain_preselect=self.save.get('wizard_domain')
		if not domain_preselect:
			domain_preselect=position.getLoginDomain()

		domainlist=[]
		for dn in domaindns:
			domainpos.setDn(dn)

			if domainpos.getDn() == domain_preselect:
				domainlist.append({"name":domainpos.getDn(),"description":domainpos.getPrintable(), "selected":domainpos.getDn()})
			else:
				domainlist.append({"name":domainpos.getDn(),"description":domainpos.getPrintable()})
		# create select box
		self.select_domain_button=button(_("apply"),{},{"helptext":""})
		self.domain_select=question_select(_("Select domain:"),{},{"helptext":_("Select domain"),"choicelist":domainlist,"button":self.select_domain_button})
		# domain_select_col=tablecol("",{'type':'wizard_layout'},{"obs":[self.domain_select]})
		# self.div_start('form-item col', divtype='class')
		# self.subobjs.append(self.domain_select)
		# self.div_stop('form-item col')

		###########################################################################
		# select search path
		###########################################################################

		try:
			visible_default = int(ucr.get ('directory/manager/web/modwizard/defaults/visible-results', '10'))
		except:
			univention.debug.debug(univention.debug.ADMIN, univention.debug.WARN, "modwizard: Failed to parse directory/manager/web/modwizard/defaults/visible-results, maybe it is no integer?")
			visible_default = 10
		
		visible = self.save.get('wizard_search_visible', visible_default)
		if visible > 1000:
			visible = 1000
		if visible < 1:
			visible = 1
		start=self.save.get('wizard_table_start', 0) # is this needed anymore with dynamic_longtable?

		search_domain_only=1
		search_one_level=0

		allstr=_("all registered %s containers") % module_description
		domainstr=_("selected domain")
		domainincsubstr=_("selected domain including subdomains")

		if self.save.get('wizard_find_pathlist',None) and self.save.get('wizard_find_displaypathlist',None):
			pathlist=self.save.get('wizard_find_pathlist',None)
			displaypathlist=self.save.get('wizard_find_displaypathlist',None)
		else:
			pathlist=[]

			container_name=string.split(search_type, '/')[0]
			if settings.default_containers.has_key(container_name):
				pathlist.extend(settings.default_containers[container_name])
			else:
				# retrieve path info from 'cn=directory,cn=univention,...' object
				pathResult = self.lo.get('cn=directory,cn=univention,'+domain_preselect)
				if not pathResult:
					pathResult = self.lo.get('cn=default containers,cn=univention,'+domain_preselect)
				infoattr=univention.admin.modules.wizardPath(search_module)
				if not infoattr:
					infoattr="univention%s%sObject" % (container_name[0].upper(), container_name[1:])
				if pathResult.has_key(infoattr) and pathResult[infoattr]:
					pathlist=pathResult[infoattr]
				if not pathlist:
					pathlist.extend( univention.admin.modules.defaultContainers( search_module ) )

			new_pathlist=[]
			for i in settings.filterDNs(pathlist, parents=0):
				try:
					self.lo.searchDn(base=i, scope='base')
					new_pathlist.append(i)
				except Exception, e:
					pass
			pathlist=new_pathlist

			# temporary position object
			pathpos=univention.admin.uldap.position(position.getBase())

			displaypathlist=[]
			for pathname in pathlist:
				pathpos.setDn(pathname)
				displaypathlist.append({"name":pathpos.getDn(),"description":_("only %s") % pathpos.getPrintable(long=1)})
			displaypathlist.sort()

			if pathlist:
				displaypathlist.insert(0, {"name":allstr,"description":allstr})
			displaypathlist.append({"name":domainstr,"description":domainstr})
			displaypathlist.append({"name":domainincsubstr,"description":domainincsubstr})

			self.save.put('wizard_find_pathlist',pathlist)
			self.save.put('wizard_find_displaypathlist',displaypathlist)


		path_preselect=self.save.get('wizard_path')
		if not path_preselect:
			path_default = ucr.get('directory/manager/web/modules/%s/search/path' % search_module.module, None)
			path_preselect = {'CONTAINERS': allstr, 'DOMAIN': domainstr, 'SUBDOMAINS': domainincsubstr}.get(path_default, path_default)
			univention.debug.debug(univention.debug.ADMIN, univention.debug.INFO, "%s.find() default=%s path_preselect=%s" % (search_module.module, path_default, path_preselect))

			# reset path_preselect in case the given path does not exist
			# otherwise the UDM shows an ugly traceback (see Bug #20972, comment #2)
			try:
				# try to find the DN
				self.lo.searchDn(base=path_preselect, scope='base')
			except univention.admin.uexceptions.noObject, e:
				# since the error is certainly related to a wrong UCR search path setting, 
				# log an error message 
				univention.debug.debug(univention.debug.ADMIN, univention.debug.ERROR, "Could not find given search path '%s', please check your UCR variable 'directory/manager/web/modules/%s/search/path'" % (path_preselect, search_module.module))
				# exception is thrown in case the DN does not exist => reset path_preselect
				path_preselect = ""

		if not path_preselect:
			if pathlist and not hasattr(search_module,"wizardsuperordinates"):
				path_preselect=allstr
			elif pathlist and hasattr(search_module,"wizardsuperordinates"):
				path_preselect=domainstr
			else:
				path_preselect=domainstr

		if path_preselect:
			self.save.put('wizard_path', path_preselect)

		for i in displaypathlist:
			if i['name'] == path_preselect:
				i['selected']=i['name']
			else:
				i['selected']=''

		self.select_path_button=button(_("apply"),{},{"helptext":""})
		self.path_select=question_select(_("Search:"),{},{"helptext":_("Where to search"),"choicelist":displaypathlist,"button":self.select_path_button})
		# path_select_col=tablecol("",{"colspan":"2",'type':'wizard_layout'},{"obs":[self.path_select]})
		if not hasattr(search_module,"wizardsuperordinates"):
			self.div_start('form-item col', divtype='class')
			self.subobjs.append(self.path_select)
			self.div_stop('form-item col')

		searchpath=[path_preselect]
		if searchpath[0] == allstr:
			# search all registered containers
			searchpath=pathlist
			search_one_level=1
			search_domain_only=0
		if searchpath[0] == domainstr:
			# search entire domain
			searchpath=[domain_preselect]
		if searchpath[0] == domainincsubstr:
			# search entire domain including sub domains
			searchpath=[domain_preselect]
			search_domain_only=0

		if search_domain_only:
			scope="domain"
		elif search_one_level:
			scope="one"
		else:
			scope="sub"
		###########################################################################
		# select superordinate if neccessary
		###########################################################################

		if hasattr(search_module,"wizardsuperordinates"):
			superordinatetypes=search_module.wizardsuperordinates
			superordinatelist=[]
			for path in searchpath:
				for sot in superordinatetypes:
					if sot=="None":
						slist=[None]
					else:
						smod=univention.admin.modules.get(sot)
						slist=univention.admin.modules.lookup(smod,None,self.lo, base=path, filter=None, scope=scope)
					superordinatelist+=slist
			superordinate=self.save.get("wizard_superordinate")
			if not superordinate:
				if superordinatelist[0]:
					superordinate=superordinatelist[0].dn
				else:
					superordinate="None"
				self.save.put("wizard_superordinate",superordinate)
			superordinatechoicelist=[]
			for s in superordinatelist:
				if s==None:
					temp={"name":"None","description":_("None")}
					stype="None"
				else:
					temp={"name":s.dn,"description":s.dn}
					stype=s.module
				if temp["name"]==superordinate:
					temp["selected"]=temp["name"]
					self.save.put("wizard_superordinatetype",stype)
				superordinatechoicelist.append(temp)
			self.select_superordinate_button=button(_("apply"),{},{"helptext":""})
			self.superordinate_select=question_select(_("Superordinate:"),{},{"helptext":_("Superordinate Object"),"choicelist":superordinatechoicelist,"button":self.select_superordinate_button})
			self.div_start('form-item col', divtype='class')
			self.subobjs.append(self.superordinate_select)
			self.div_stop('form-item col')
			# superordinate_select_col=tablecol("",{'type':'wizard_layout'},{"obs":[self.superordinate_select]})
			#pathrow=tablerow("",{},{"obs":[path_select_col]})
			#superrow=tablerow("",{},{"obs":[superordinate_select_col]})
			#supertab=table("",{},{"obs":[pathrow,superrow]})
			#rows.append(tablerow("",{},{"obs":[domain_select_col,tablecol("",{"colspan":"2"},{"obs":[supertab]})]})) # 3 cols
		#else:
		#	rows.append(tablerow("",{},{"obs":[domain_select_col, path_select_col]})) # 3 cols



		###########################################################################
		# search select
		###########################################################################

		searchcols=[]

		size_limit_reached = 0

		# check for child modules
		child_ids=univention.admin.modules.childModules(search_module)
		if child_ids:
			childlist=[{"name":univention.admin.modules.name(search_module), "description":univention.admin.modules.short_description(search_module)}]
			for child_id in child_ids:
				if hasattr(search_module,"wizardtypesforsuper"):
					if child_id not in search_module.wizardtypesforsuper.get(self.save.get("wizard_superordinatetype"),[]):
						continue
				if univention.admin.modules.wizardOperations(child_id).get('find'):
					childmodule=univention.admin.modules.get(child_id)
					childlist.append({"name":univention.admin.modules.name(childmodule), "description":'%s'%univention.admin.modules.short_description(childmodule).split(':',1)[-1]})
			childlist.sort()

			# super module search type/module is no longer needed
			type_preselect = self.save.get("wizard_search_type")
			if not type_preselect:
				type_preselect = ucr.get('directory/manager/web/modules/%s/search/type' % search_module.module, None)
				univention.debug.debug(univention.debug.ADMIN, univention.debug.INFO, "%s.find() type_preselect=%s" % (search_module.module, type_preselect))
			if type_preselect:
				# switch to selected child module only if it exists
				child_module = univention.admin.modules.get(type_preselect)
				if child_module:
					search_type = type_preselect
					search_module = child_module
					module_description = univention.admin.modules.short_description(search_module)
					self.save.put('wizard_search_type', search_type)
			for i in childlist:
				if i["name"]==search_type:
					i["selected"]="1"
					break
			else:
				childlist[0]["selected"]="1"
			self.child_module_button=button('go',{},{'helptext':_('go ahead')})
			self.child_module_select=question_select(_("Select Type:"),{},{"helptext":_("Select Type"), "choicelist":childlist, "button":self.child_module_button})
			self.div_start('form-item col', divtype='class')
			self.subobjs.append(self.child_module_select)
			self.div_stop('form-item col')
			# searchcols.append(tablecol("",{'type':'wizard_layout'},{"obs":[self.child_module_select]}))

		self.new_row()
		univention.admin.modules.init(self.lo, self.position, search_module )

		search_property_name=self.save.get('wizard_search_property')
		tmp_search_property_name = search_property_name
		if not search_module.property_descriptions.has_key(search_property_name):
			search_property_name='*'

		search_properties=[]
		search_properties.append({'name': '*', 'description': _('any')})

		default_search_property = ucr.get ('directory/manager/web/modules/%s/search/default' % (search_module.module, ), None)
		for name, property in search_module.property_descriptions.items():
			if not (hasattr(property, 'dontsearch') and property.dontsearch==1):
				search_properties.append({'name': name, 'description':property.short_description})
				if search_property_name == '*' \
						and default_search_property != None\
						and default_search_property == name:
					if tmp_search_property_name != search_property_name:
						search_property_name = name
						univention.debug.debug(univention.debug.ADMIN, univention.debug.INFO, \
								"default search: set to '%s' from UCR variable %s" % \
								(name, 'directory/manager/web/modules/%s/search/default' % (search_module.module, )))

		search_properties.sort()

		for i in search_properties:
			if i['name']==search_property_name:
				i['selected']='1'

		if search_property_name != '*':
			search_property=search_module.property_descriptions[search_property_name]
			search_value=self.save.get('wizard_search_value')

			if tmp_search_property_name == '' and not search_value:
				search_value = '*'
			self.search_input=question_property('',{'focus': '1'},{'property': search_property, 'value': search_value, 'search': '1', 'lo': self.lo})
		else:
			search_value='*'
			self.search_input=text('',{},{'text':['']})

		self.search_property_button=button(_('go'),{},{'helptext':_('go ahead')})
		self.search_property_select=question_select(_('Property'),{},{'helptext':_('Choose property'),'choicelist':search_properties,'button':self.search_property_button})

		# searchcols.append(tablecol('',{'type':'wizard_layout'},{'obs':[self.search_property_select]}))
		self.div_start('form-item col', divtype='class')
		self.subobjs.append(self.search_property_select)
		self.div_stop('form-item col')
		if child_ids:
			# we have got three widgets, so the last widget should be in the right column, see Bug #13160
			#searchcols2 = []
			#searchcols2.append(tablecol('',{'type':'wizard_layout'},{'obs':[self.search_input]}))
			#rows.append(tablerow("",{},{"obs":[	tablecol('',{'colspan':'2'},{'obs':[table('',{},{'obs':[tablerow("",{},{"obs":searchcols}),]})]}), 
			#									tablecol('',{'colspan':'1'},{'obs':[table('',{},{'obs':[tablerow("",{},{"obs":searchcols2}),]})]})
			#								]}))
			self.div_start('form-item col', divtype='class')
			self.subobjs.append(self.search_input)
			self.div_stop('form-item col')
		else:
			#searchcols.append(tablecol('',{'type':'wizard_layout'},{'obs':[self.search_input]}))
			# rows.append(tablerow("",{},{"obs":[tablecol('',{'colspan':'2'},{'obs':[table('',{},{'obs':[tablerow("",{},{"obs":searchcols})]})]})]}))
			self.div_start('form-item col', divtype='class')
			self.subobjs.append(self.search_input)
			self.div_stop('form-item col')

		self.new_row()
		self.search_visible=question_text(_('Results per page'), {'validregex':'\d*', 'invalidmessage':str(_('Please enter a number.'))},
						  {'usertext': str(visible)})
		self.div_start('form-item col', divtype='class')
		self.subobjs.append(self.search_visible)
		self.div_stop('form-item col')

		self.search_button=button(_('search'),{'defaultbutton': '1', 'class':'submit'},{'helptext':_('Display (new) search results')})

		mods = univention.admin.modules.childModules( search_module )
		mods.insert( 0, univention.admin.modules.name( search_module ) )
		udr_cfg = univention.directory.reports.Config()
		reports = []
		for mod in mods:
			reports.extend( udr_cfg.get_report_names( mod ) )
		self.div_start('form-item col', divtype='class')
		if reports:
			self.reset_button=button(_('reset'),{'class':'cancel spacer'},{'helptext':_("reset search")})
			self.subobjs.append(self.reset_button)
			self.report_button=button(_('create report'),{'class':'cancel'},{'helptext':_('Create Reports')})
			self.subobjs.append(self.report_button)
		else:
			self.reset_button=button(_('reset'),{'class':'cancel'},{'helptext':_("reset search")})
			self.subobjs.append(self.reset_button)
		self.subobjs.append(self.search_button)
		self.div_stop('form-item col')

		# generate search table
		main_rows = []
		#main_rows.append(
		#	tablerow("",{},{"obs":[tablecol("",{'type':'content_main'},{"obs":[table("",{'type':'search_header'},{"obs":rows})]})]})
		#)

		#main_rows.append(
		#	tablerow("",{},{"obs":[tablecol("",{'type':'wizard_layout'},{"obs":[space('',{'size':'1'},{})]})]})
		#)

		self.new_row()
		self.div_stop('form-wrapper')
		# end search table
		###########################################################################

		###########################################################################
		# display search results if any
		###########################################################################

		# display default search results
		_off = ('0', 'false', 'off', 'no')
		_on = ('1', 'true', 'on', 'yes')
		autosearch = True
		if ucr.get ('directory/manager/web/modules/autosearch', '0').lower () in _on:
			# default value MUST be 1 because autosearch is already switched on
			# and it will be turned off only when there IS a value set for
			# autosearch AND it IS in _off
			if ucr.get ('directory/manager/web/modules/%s/search/autosearch' % search_module.module, '1').lower () in _off:
				autosearch = False
		else:
			if ucr.get ('directory/manager/web/modules/%s/search/autosearch' % search_module.module, '0').lower () in _on:
				autosearch = True
			else:
				autosearch = False

		nomatches=0
		if not self.save.get('wizard_search_do') and not autosearch:
			result_list=self.save.get('wizard_search_result')
			if not result_list:
				result_list=[]
				cache=0
			else:
				cache=1
		else:
			result={}
			nresults=0
			cache=0
			for path in searchpath:
				searchposition=univention.admin.uldap.position(position.getBase())
				searchposition.setDn(path)

				# search...
				if search_property_name != '*':
					if not search_value:
						search_value = '*'
					filter=univention.admin.filter.expression(search_property_name, search_value)
				else:
					filter=''
				try:
					if self.save.get("wizard_superordinate") and not self.save.get("wizard_superordinate") == "None" :
						super=self.save.get("wizard_superordinate")
						bas=searchposition.getDn()
						superob=univention.admin.objects.get(univention.admin.modules.get(self.save.get("wizard_superordinatetype")), None, self.lo, '', dn=super)
					else:
						super=None
						bas=searchposition.getDn()
						superob=None
					result[searchposition.getDn()]=settings.filterObjects(univention.admin.modules.lookup(search_module,None, self.lo, superordinate=superob, base=bas, filter=filter, scope=scope, sizelimit=max_results-nresults))
					nresults = nresults+len(result[searchposition.getDn()])
				except univention.admin.uexceptions.ldapError, msg:
					size_limit_reached = 1
					result = {}

				list_attributes = settings.getListAttributes(search_type)
				if result.has_key(searchposition.getDn()) and (search_property_name != '*' or list_attributes):
					for i in result[searchposition.getDn()]:
						if not i.has_key(search_property_name) or not i[search_property_name] or list_attributes:
							try:
								univention.debug.debug(univention.debug.ADMIN, univention.debug.INFO, 'open object %s'%(i))

								univention.admin.objects.open(i)
							except univention.admin.uexceptions.insufficientInformation, m:
								self.usermessage(_('Failed to open object, insufficient or ambiguous values returned from search (%s)')%m)
								try:
									univention.debug.debug(univention.debug.ADMIN, univention.debug.ERROR, 'Failed to open object, insufficient or ambiguous values returned from search (%s) at result %s'%(m,i))
								except:
									univention.debug.debug(univention.debug.ADMIN, univention.debug.ERROR, 'Failed to open object, insufficient or ambiguous values returned from search (%s)'%(m))

			sorted_result={}
			for pos, items in result.items():
				# sort items
				sorting_helper_list=[]
				sorting_helper_dict={}
				for n in range(len(items)):
					name=univention.admin.objects.description(items[n])
					if not sorting_helper_list.count(name):
						sorting_helper_list.append(name)
					if not sorting_helper_dict.has_key(name):
						sorting_helper_dict[name]=[]
					sorting_helper_dict[name].append(n)
				def caseigncompare(a, b):
					a2=a.upper()
					b2=b.upper()
					if a2 == b2:
						# fallback to casecompare
						if a == b:
							return 0
						l=[a, b]
						l.sort()
						if l.index(a) < l.index(b):
							return -1
						else:
							return 1

					l=[a2, b2]
					l.sort()

					if l.index(a2) < l.index(b2):
						return -1
					else:
						return 1
				sorting_helper_list.sort(caseigncompare)
				univention.debug.debug(univention.debug.ADMIN, univention.debug.INFO, 'modwizard: sorting: helper_list=%s' % sorting_helper_list)

				sorted=[]
				# add containers first...
				for helper in sorting_helper_list:
					for n in sorting_helper_dict[helper]:
						sub_object_type=univention.admin.objects.module(items[n])
						sub_object_module=univention.admin.modules.get(sub_object_type)
						if univention.admin.modules.childs(sub_object_module):
							sorted.append(items[n])
				# then add other objects
				for helper in sorting_helper_list:
					for n in sorting_helper_dict[helper]:
						sub_object_type=univention.admin.objects.module(items[n])
						sub_object_module=univention.admin.modules.get(sub_object_type)
						if not univention.admin.modules.childs(sub_object_module):
							sorted.append(items[n])
				sorted_result[pos]=sorted

			result=sorted_result

			result_list=[]
			for pos, items in result.items():
				result_list += items

			self.save.put('wizard_search_result', result_list)
			self.save.put('wizard_search_do', None)
			if not result_list:
				nomatches=1

		result_list=self.save.get('wizard_search_result')
		if size_limit_reached:
			self.subobjs.append ( htmltext ('', {}, \
				{'htmltext': ["""
					<h3>%s</h3>
					""" % _("More than %d results, please redefine search.")%max_results
					]}))
		elif result_list and not nomatches:

			###########################################################################
			# listing head
			###########################################################################

			self.div_start('search-result', divtype='class')

			# list
			self.editbuts=[]
			self.delboxes=[]

			resultsrows=[]
			cols=[]
			cols.append(tablecol("",{'type':'wizard_layout'},{"obs":[header(_("Object"),{"type":"6"},{})]}))
			if search_property_name != '*' \
					and not search_module.property_descriptions[search_property_name].identifies:
				cols.append(tablecol("",{'type':'wizard_layout'},{"obs":[header(search_property.short_description,{"type":"6"},{})]}))
			list_attributes = settings.getListAttributes(search_type)
			for list_attribute in list_attributes:
				if search_module.property_descriptions.has_key(list_attribute) and search_module.property_descriptions[list_attribute].short_description:
					cols.append(tablecol("",{'type':'wizard_layout'},{"obs":[header(search_module.property_descriptions[list_attribute].short_description,{"type":"6"},{})]}))
				else:
					cols.append(tablecol("",{'type':'wizard_layout'},{"obs":[header(list_attribute,{"type":"6"},{})]}))
			cols.append(tablecol("",{'type':'wizard_layout'},{"obs":[header(_("Location"),{"type":"6"},{})]}))
			cols.append(tablecol("",{'type':'wizard_layout'},{"obs":[header(_("Select"),{"type":"6"},{})]}))
			resultsrows.append(tablerow("",{'type':'header'},{"obs": cols})) # 3 or 4 cols

			###########################################################################
			# listing objects
			###########################################################################
			
			for sub_object in result_list:
				if not hasattr(sub_object, 'dn') or not sub_object.dn:
					continue

				cols=[]

				sub_object_type=univention.admin.objects.module(sub_object)
				sub_object_module=univention.admin.modules.get(sub_object_type)

				# skip items that can't be displayed
				if not sub_object_module:
					continue

				icon_attribute={}
				if activate_icons in ['true', 'yes', '1', 'on']:
					icon_path = unimodule.selectIconByName( sub_object_type, small=True )
					univention.debug.debug(univention.debug.ADMIN, univention.debug.INFO, 'icon path for %s: %s' % (sub_object_type,icon_path))
					icon_attribute['icon']=icon_path
				else:
					icon_attribute['icon']='icon/empty_eeeeee.png'

				name=univention.admin.objects.description(sub_object)

				icon_attribute['class'] = 'search_result'
				edit_button=button(name,icon_attribute,{'helptext':_('edit "%s"') % univention.admin.objects.description(sub_object)})
				self.editbuts.append((edit_button, sub_object.dn, sub_object_type, univention.admin.objects.arg(sub_object)))
				cols.append(tablecol("",{'type':'wizard_layout'},{"obs":[edit_button]}))

				if search_property_name != '*' and sub_object.has_key(search_property_name) and sub_object[search_property_name] \
					and not search_module.property_descriptions[search_property_name].identifies:
					tmpvalue=sub_object[search_property_name]
					if type(tmpvalue) is not types.ListType:
						displayvalue=[tmpvalue]
					else:
						stop=0
						try:
							_re=re.compile(search_value)
						except Exception, e:
							try:
								_re=re.compile(re.sub("\\*", ".*", search_value))
							except Exception, e:
								stop=1
						if not stop:
							displayvalue=[]
							for i in tmpvalue:
								if _re.search(i):
									displayvalue.append(i)
						else:
							displayvalue=tmpvalue
					property_text=text('',{},{'text':displayvalue})
					cols.append(tablecol("",{'type':'wizard_layout'},{"obs":[property_text]}))
				list_attributes = settings.getListAttributes(search_type)
				for list_attribute in list_attributes:
					tmpvalue=sub_object[list_attribute]
					if type(tmpvalue) is not types.ListType:
						displayvalue=[tmpvalue]
					else:
						displayvalue=tmpvalue
					property_text=text('',{},{'text':displayvalue})
					cols.append(tablecol("",{'type':'wizard_layout'},{"obs":[property_text]}))

				locationpos=univention.admin.uldap.position(position.getBase())
				locationpos.setDn(sub_object.dn)
				if not hasattr(sub_object, 'superordinate') or not sub_object.superordinate or not sub_object.dn == sub_object.superordinate.dn:
					locationpos.switchToParent()
				location=text('',{},{'text':[locationpos.getPrintable(long=1)]})
				cols.append(tablecol("",{'type':'wizard_layout'},{"obs":[location]}))

				if hasattr(sub_object, 'arg'):
					arg=sub_object.arg
				else:
					arg=None
				selected_dns=self.save.get('wizard_selected_dns', {})
				if selected_dns.get((sub_object.dn, univention.admin.modules.name(sub_object_type), arg)):
					selected = '1'
				else:
					selected = ''
				delete=question_bool('',{},{'usertext': selected,'helptext':_('select %s') % univention.admin.objects.description(sub_object)})
				self.delboxes.append((delete, sub_object.dn, sub_object_type, univention.admin.objects.arg(sub_object)))
				cols.append(tablecol("",{'type':'wizard_layout'},{"obs":[delete]}))

				resultsrows.append(tablerow("",{},{"obs":cols})) # 3 or 4 cols

			
			dynlongtable = dynamic_longtable("",
							 {'header' : str(1), 'total': str(len(result_list)),
							  'start': str(start), 'visible': str(visible)},
							 {"obs":resultsrows})
			main_rows.append(tablerow("",
						  {},
						  {"obs":[tablecol("",{},{"obs":[dynlongtable]})]}))


			###########################################################################
			# delete, edit, ... drop-down
			###########################################################################

			footerCols = []




			#footerCols.append(tablecol("",{'type':'browse_layout_right'},
			#			   {"obs":[table("",
			#					 {'type':'browse_layout_right'},
			#					 {"obs" : [ tablerow("",
			#							     {'type':'browse_layout_right'},
			#							     {"obs": [ tablecol("",
			#									      {'type':'browse_layout_right'},
			#									      {"obs":[self.selection_select]})]
			#							      })]
			#					  })]
			#			    }))
			#footerTable = table("", {'type':'table_fullwidth'}, {"obs" : [ tablerow("",{'type':'table_fullwidth'},{"obs": footerCols}) ]})
			#main_rows.append(tablerow("", {}, {"obs":[tablecol("",{'type':'table_fullwidth'}, {"obs":[footerTable]},)]}))


		if nomatches and not size_limit_reached:
			#main_rows.append(
			#	tablerow("",{'type':'wizard_layout'},{"obs":[ 
			#		tablecol("",{'type':'wizard_layout_icon'},{"obs":
			#			[icon( '', { 'url' : 'icon/dialog-warning.png' }, {} )]
			#		}),
			#		tablecol("",{'type':'wizard_layout'},{"obs":[
			#			header(_('Your search did not match any objects.'),{"type":"5"},{})
			#			]
			#		})
			#	]})
			#)

			# main table
			#self.subobjs.append(table("",
			#			  {'type':'content_main'},
			#			  {"obs":main_rows})
			#			)
			self.subobjs.append ( htmltext ('', {}, \
				{'htmltext': ["""
					<h3>%s</h3>
					""" % _('Your search did not match any objects.')
					]}))
		else:

			# main table
			self.subobjs.append(table("",
						  {'type':'content_main'},
						  {"obs":main_rows}))

			# info: number of search results
			resultinfoCols = []
			if result_list:
				if cache:
					self.subobjs.append(header(_("%d search result(s) (cached)") % len(result_list),{"type":"5"},{}))
				else:
					self.subobjs.append(header(_("%d search result(s)") % len(result_list),{"type":"5"},{}))

				# drop-down: move, edit, ...
				self.selection_commit_button=button(_("Do"),{},{"helptext":_("Do action with selected objects.")})
				self.selection_select=question_select(_('Do with selected objects...'),{'width':'200'},{"helptext":_("Do with selected objects...."),"choicelist":[
					{'name': "uidummy098", 'description': "---"},
					{'name': "invert", 'description': _("Invert selection")},
					{'name': "edit", 'description': _("Edit")},
					{'name': "recursive_delete", 'description': _("Delete")},
				],"button":self.selection_commit_button})
				
				self.div_start('form-item', divtype='class')
				self.div_start('form-right', divtype='class')
				self.subobjs.append(self.selection_select)
				self.div_stop('form-right')
				self.div_stop('form-item')
				self.div_stop('search-result')


		main_rows = []
		self.div_stop('content')
		self.div_stop('content-wrapper')


	def delmode(self, removelist):
		position=self.position

		self.div_start('content-wrapper', divtype='id')

		self.nbook=notebook('', {}, {'buttons': [(_('delete'), _('delete'))], 'selected': 0})
		self.subobjs.append(self.nbook)
		self.div_start('content', divtype='id')

		#begin table:
		self.div_start('wizard_layout_header', divtype='class')
		if len(removelist) > 1:
			self.subobjs.append(header(_("Are you sure you want to delete these %d objects and referring objects if enabled?") % len(removelist),{"type":"3"},{}))
		elif len(removelist) > 0:
			self.subobjs.append(header(_("Are you sure you want to delete this object as well as referring objects if enabled?"),{"type":"3"},{}))
		self.div_stop('wizard_layout_header')

		rows=[]
		cols=[]
		cols.append(tablecol("",{'type':'wizard_layout'},{"obs":[header(_("Object"),{"type":"6"},{})]}))
		cols.append(tablecol("",{'type':'wizard_layout'},{"obs":[header(_("Location"),{"type":"6"},{})]}))
		cols.append(tablecol("",{'type':'wizard_layout'},{"obs":[header(_("Delete?"),{"type":"6"},{})]}))
		cols.append(tablecol("",{'type':'wizard_layout'},{"obs":[header(_("Delete referring objects?"),{"type":"6"},{})]}))
		rows.append(tablerow("",{'type':'wizard_layout'},{"obs": cols}))

		#rows.append(tablerow("",{},{"obs": [
		#	tablecol("",{'type':'wizard_layout'},{"obs":[space('',{'size':'1'},{})]}),
		#	tablecol("",{'type':'wizard_layout'},{"obs":[space('',{'size':'1'},{})]}),
		#	tablecol("",{'type':'wizard_layout'},{"obs":[space('',{'size':'1'},{})]}),
		#	tablecol("",{'type':'wizard_layout'},{"obs":[space('',{'size':'1'},{})]}),
		#]}))

		removelist_withcleanup=[]

		self.ignore_buttons=[]
		self.final_delboxes=[]
		self.cleanup_delboxes=[]
		for i in removelist:
			cols=[]
			univention.debug.debug(univention.debug.ADMIN, univention.debug.INFO, "creating object handler")
			object_module=univention.admin.modules.get(i[1])
			object=univention.admin.objects.get(object_module, None, self.lo, self.position, dn=i[0], arg=i[2])
			object_type=univention.admin.objects.module(object)

			# We need to verify that the objects still exist. When a multidelete operation
			# is canceled, for example, there will be objects that don't exist anymore.
			if not object.dn:
				removelist.remove(i)
				continue

			icon_path = unimodule.selectIconByName( object_type, small=True )

			name=univention.admin.objects.description(object)
			description=univention.admin.modules.short_description(object_module)

			object_button=button(name,{'icon':icon_path, 'passive':"1"},{'helptext':_('%s object') % description})
			self.ignore_buttons.append(object_button)
			cols.append(tablecol("",{'type':'wizard_layout'},{"obs":[object_button]}))

			locationpos=univention.admin.uldap.position(self.position.getBase())
			locationpos.setDn(object.dn)
			if not hasattr(object, 'superordinate') or not object.superordinate or not object.dn == object.superordinate.dn:
				locationpos.switchToParent()
			location=text('',{},{'text':[locationpos.getPrintable(long=1)]})
			cols.append(tablecol("",{'type':'wizard_layout'},{"obs":[location]}))

			final_delete=question_bool('',{},{'usertext':"1",'helptext':_('select %s') % name})
			self.final_delboxes.append((final_delete, object.dn, object_type, univention.admin.objects.arg(object)))
			cols.append(tablecol("",{'type':'wizard_layout', 'align': 'center'},{"obs":[final_delete]}))

			univention.debug.debug(univention.debug.ADMIN, univention.debug.INFO, "check if cleanup neccessary: %s" % i[0])
			if univention.admin.objects.wantsCleanup(object):
				removelist_withcleanup.append(i)
				cleanup_delete=question_bool('',{},{'usertext': '1', 'helptext':_('select %s') % name})
				self.cleanup_delboxes.append((cleanup_delete, object.dn, object_type, univention.admin.objects.arg(object)))
				cols.append(tablecol("",{'type':'wizard_layout', 'align': 'center'},{"obs":[cleanup_delete]}))
			else:
				cols.append(tablecol("",{'type':'wizard_layout'},{"obs":[text('',{},{'text':[""]})]}))
			rows.append(tablerow("",{},{"obs":cols}))

		if removelist_withcleanup:
			self.save.put('removelist_withcleanup', removelist_withcleanup)

		# generate table
		main_rows = []
		main_rows.append(
			tablerow("",{},{"obs":[tablecol("",{'type':'content_main'},{"obs":[table("",{"type":"content_list"},{"obs":rows})]})]})
		)
		#end table
		self.cancel_delbut=button(_("Cancel"),{'class':'cancel'},{"helptext":_("Cancel")})
		self.final_delbut=button(_('OK'),{'class':'submit'},{'helptext':_('Really delete selected objects and referring objects if enabled.')})

		self.subobjs.append(table("",
					  {'type':'content_main'},
					  {"obs":[tablerow("",{},{"obs":[tablecol("",{'type':'content_main'},{"obs":main_rows})]})]})
				    )
		self.subobjs.append(table("",
					  {'type':'content_main'},
					  {"obs":[tablerow("",{},{"obs":[
							tablecol("",{'type':'cancel'},{"obs":[self.cancel_delbut]}),
							tablecol("",{'type':'okcancel'},{"obs":[self.final_delbut]})
						]})]}))

		self.div_stop('content')
		self.div_stop('content-wrapper')

		self.save.put('wizard_search_result', None) ## reset after delete
		self.save.put('wizard_selected_dns', {})

	def myinit(self):
		self.save=self.parent.save
		if self.inithandlemessages():
			return

		self.lo=self.args["uaccess"]

		position_bak=self.save.get('ldap_position_bak')
		if position_bak:
			self.save.put('ldap_position', position_bak)
			self.position=position_bak
		else:
			self.position=self.save.get('ldap_position')

		if self.save.get("removelist"):
			self.delmode(self.save.get("removelist"))
		elif self.save.get("uc_submodule")=="add":
			self.add(self.save.get("uc_virtualmodule"))
		else:
			if self.save.get( 'uc_report' ) == True:
				self.report(self.save.get("uc_virtualmodule"))
			else:
				self.find(self.save.get("uc_virtualmodule"))

	def apply(self):
		if self.applyhandlemessages():
			return

		self.cancel = 0

		position=self.save.get('ldap_position')

		#delmode
		if hasattr(self, 'ignore_buttons'):
			for i in self.ignore_buttons:
				if i.pressed():
					return

		if hasattr(self, 'cancel_delbut') and self.cancel_delbut.pressed():
			univention.debug.debug(univention.debug.ADMIN, univention.debug.INFO, "cancel delete")
			self.save.put('removelist', None)
			return

		if hasattr(self, 'final_delbut') and self.final_delbut.pressed():
			removelist=self.save.get("removelist")
			if not removelist or not type(removelist) is types.ListType:
				return

			removelist_withcleanup=self.save.get("removelist_withcleanup")
			if not removelist_withcleanup or not type(removelist_withcleanup) is types.ListType:
				removelist_withcleanup=[]

			remove_childs=self.save.get("remove_children")
			self.multidelete_status=[0,len(removelist),0]
			multidelete_errors=[]
			for i in removelist:
				if self.cancel:
					raise SystemExit
				dontdel=0
				dontcleanup=0
				for final in self.final_delboxes:
					if final[1]==i[0] and not final[0].get_input():
						dontdel=1
						break
				if dontdel:
					continue
				for cleanup in self.cleanup_delboxes:
					if cleanup[1]==i[0] and not cleanup[0].get_input():
						dontcleanup=1
				module=univention.admin.modules.get(i[1])
				if i[3]:
					superordinate=univention.admin.objects.get(univention.admin.modules.superordinate(module), None, self.lo, '', dn=i[3])
				else:
					superordinate=None
				object=univention.admin.objects.get(module, None, self.lo, position,superordinate=superordinate, dn=i[0], arg=i[2])
				univention.debug.debug(univention.debug.ADMIN, univention.debug.INFO, "delete: %s" % i[0])
				if i in removelist_withcleanup and not dontcleanup:
					univention.debug.debug(univention.debug.ADMIN, univention.debug.INFO, "perform cleanup for: %s" % i[0])
					univention.admin.objects.performCleanup(object)
				try:
					object.remove(remove_childs)
				except univention.admin.uexceptions.base, ex:
					message=str(ex)
					if message=="Operation not allowed on non-leaf":
						message="Object is a non-empty container"

					multidelete_errors.append("%s: %s %s" % (univention.admin.uldap.explodeDn(i[0], 1)[0], message, ex.message))
					self.multidelete_status[2] += 1
				self.multidelete_status[0] += 1
			self.save.put("remove_children", None)
			if multidelete_errors:
				self.usermessage(_("Removing %d/%d selected objects failed: %s") % (self.multidelete_status[2], self.multidelete_status[1], string.join(multidelete_errors, '<br>'))) # XXX
			else:
				self.userinfo(_("Removed %d/%d objects successfully.") % (self.multidelete_status[0], self.multidelete_status[1]))
			self.save.put("removelist", None)
			self.save.put("removelist_withcleanup", None)
			self.save.put('wizard_search_result', None)
			self.save.put('wizard_selected_dns', {})
			self.save.put('wizard_search_do', '1')
			return

		# add
		if hasattr(self, 'next_button') and self.next_button.pressed():
			if hasattr(self, 'path_select') and self.path_select.getselected():
				newposition=self.save.get('ldap_position')
				self.save.put('ldap_position_bak', newposition)
				if not self.save.get("wizard_superordinate") or self.save.get("wizard_superordinate") == 'None':
					newposition.setDn(self.path_select.getselected())
				else:
					newposition.setDn(self.save.get("wizard_superordinate"))
				self.save.put('ldap_position', newposition)
				edit_type=self.save.get("uc_virtualmodule")
				if hasattr(self, "child_module_select"):
					edit_type=self.child_module_select.getselected()
				self.save.put('edit_type', edit_type)

				template_dn="None"
				if hasattr(self, "template_select"):
					template_dn=self.template_select.getselected()
				self.save.put('template_dn',template_dn)

				self.save.put('edit_return_to', 'wizard')
				self.save.put('uc_module', 'edit')
				self.save.put('wizard_path', self.path_select.getselected())
				if hasattr(self,'child_module_select'):
					self.save.put('wizard_child', self.child_module_select.getselected())
				return

		if hasattr(self, 'cancel_button') and self.cancel_button.pressed():
			self.save.put('uc_submodule', None)
			return

		# add/search
		if hasattr(self, 'select_domain_button') and self.select_domain_button.pressed():
			self.save.put('wizard_domain', self.domain_select.getselected())
			# preserve the search value on selecting another domain
			self.save.put('wizard_search_value', self.search_input.get_input ())
			self.save.put('wizard_superordinate', None)
			self.save.put('wizard_search_result', None)
			self.save.put('wizard_selected_dns', {})
			return
		if hasattr(self,"select_superordinate_button") and self.select_superordinate_button.pressed():
			self.save.put('wizard_superordinate',self.superordinate_select.getselected())
			self.save.put('wizard_search_type', None)
			self.save.put('wizard_search_value', None)

		# search
		old_start = self.save.get('wizard_table_start', 0)
		if hasattr(self, 'resultstab'):
			self.save.put('wizard_table_start', self.resultstab.getcontent())

		if hasattr(self, 'select_path_button') and self.select_path_button.pressed():
			self.save.put('wizard_path', self.path_select.getselected())
			# preserve the search value on selecting another path
			self.save.put('wizard_search_value', self.search_input.get_input ())
			self.save.put('wizard_superordinate', None)
			self.save.put('wizard_search_type', None)
			self.save.put('wizard_search_result', None)
			self.save.put('wizard_selected_dns', {})
			return

		if hasattr(self, 'child_module_button') and self.child_module_button.pressed():
			self.save.put('wizard_search_type', self.child_module_select.getselected())
			self.save.put('wizard_search_value', None)
			# Enable this to save the search for values when another child module is
			# selected
			# WARNING: different child modules have different property types
			# and they probably expect different input! -
			# i.e. any = *, Disabled = 0/1 Boolean/Int - if you enable this
			# without any modifications the user might run into trouble because
			# he doesn't know what kind of input is expected
			#self.save.put('wizard_search_value', self.search_input.get_input ())
			self.save.put('wizard_search_result', None)
			self.save.put('wizard_selected_dns', {})
			return

		if hasattr(self, 'search_property_button') and self.search_property_button.pressed():
			self.save.put('wizard_search_property', self.search_property_select.getselected())
			self.save.put('wizard_search_value', None)
			# Enable this to save the search for values when another property type is
			# selected
			# WARNING: different property types expect different input! -
			# i.e. any = *, Disabled = 0/1 Boolean/Int - if you enable this
			# without any modifications the user might run into trouble because
			# he doesn't know what kind of input is expected
			#self.save.put('wizard_search_value', self.search_input.get_input ())
			self.save.put('wizard_search_result', None)
			self.save.put('wizard_selected_dns', {})
			return

		if hasattr(self, 'search_input') and self.search_input.get_input():
			self.save.put('wizard_search_value', self.search_input.get_input())


		if hasattr(self, 'search_visible') and self.search_visible.get_input():
			try:
				self.save.put('wizard_search_visible', int(self.search_visible.get_input()))
			except:
				pass # use old value

		if hasattr(self, 'search_button') and self.search_button.pressed():
			self.save.put('wizard_search_do', '1')
			return

		if hasattr(self, 'reset_button') and self.reset_button.pressed():
			self.save.put('wizard_domain', None)
			self.save.put('wizard_path', None)
			self.save.put('wizard_search_type', None)
			self.save.put('wizard_search_property', None)
			self.save.put('wizard_search_value', None)
			self.save.put('wizard_search_do', None)
			self.save.put('wizard_search_result', None)
			self.save.put('wizard_selected_dns', {})
			return

		self.save.put( 'uc_report', False )
		if hasattr(self, 'create_report_button') and self.create_report_button.pressed():
			self.save.put( 'uc_report_create', True )
			self.save.put( 'uc_report_template', self.report_select.getselected() )
			self.save.put( 'uc_report', True )
			return

		if hasattr(self, 'report_button') and self.report_button.pressed():
			self.save.put('wizard_search_property', self.search_property_select.getselected())
			self.save.put('wizard_search_value', self.search_input.get_input())
			self.save.put( 'uc_report', True )
			return

		if hasattr(self, 'delboxes') and hasattr(self, 'selection_commit_button'):
			# get all selected elements
			selected_dns=self.save.get('wizard_selected_dns', {})

			# check and remove a dns entry that does not exist .. check only when one entry 
			# is selected since then its name (and thus dn) may have been modified (Bug #18349)
			listDns = [key for key, val in selected_dns.iteritems() if val == 1]
			if len(listDns) == 1:
				iDn = listDns[0]
				try:
					# try to find the DN
					self.lo.searchDn(base=iDn[0], scope='base')
				except univention.admin.uexceptions.noObject, e:
					# exception is thrown in case the DN does not exist, therefore remove 
					# entry from the selected_dns list to avoid problems
					selected_dns.pop(iDn)
						
			invert_selection=self.selection_select.getselected() == "invert" and self.selection_commit_button.pressed()

			if invert_selection:
				self.save.put('wizard_table_start', old_start)

			for i in self.delboxes:
				if (not i[0].get_input() and not invert_selection) or (i[0].get_input() and invert_selection):
					selected_dns[(i[1],i[2],i[3])]=0
				else:
					selected_dns[(i[1],i[2],i[3])]=1

			self.save.put('wizard_selected_dns', selected_dns)
			self.userinfo(_('%d object(s) are selected.') % selected_dns.values().count(1))


			if not self.selection_commit_button.pressed() or invert_selection:
				pass

			elif self.selection_select.getselected() == "recursive_delete":
				removelist=[]
				for i, val in selected_dns.items():
					if val:
						removelist.append((i[0], i[1], i[2], self.save.get('wizard_superordinate')))
				if removelist:
					self.save.put("removelist", removelist)
				self.save.put("remove_children", 1)
				return

			elif self.selection_select.getselected() == "edit":
				edit_dn_list=[]
				edit_type=''
				for i, val in selected_dns.items():
					if val:
						if not edit_type:
							edit_type=i[1]
						elif edit_type != i[1]:
							# objects with different types have been selected
							edit_dn_list=[]
							self.usermessage(_('Cannot edit multiple objects with different types.'))
							return
						edit_dn_list.append((i[0], i[2]))
				if edit_dn_list:
					if len( edit_dn_list ) > 1:
						self.save.put('edit_dn', '')
						self.save.put('edit_dn_list', edit_dn_list)
					else:
						self.save.put('edit_dn_list', '')
						self.save.put('edit_dn', edit_dn_list[ 0 ][ 0 ] )
					self.save.put('edit_type', edit_type)
					self.save.put('edit_return_to', 'wizard')
					self.save.put('uc_module', 'edit')
					self.save.put('wizard_table_start', old_start)
				return

		if not hasattr(self, 'editbuts'):
			return

		for i in self.editbuts:
			if i[0].pressed():
				self.save.put('edit_dn', i[1])
				self.save.put('edit_type', i[2])
				self.save.put('edit_arg', i[3])
				self.save.put('edit_return_to', 'wizard')
				self.save.put('uc_module', 'edit')
				self.save.put('wizard_table_start', old_start)
				return

	def waitmessage(self):
		if hasattr(self, 'multidelete_status'):
			return _('Removed %d/%d objects (%d errors).') % (self.multidelete_status[0], self.multidelete_status[1], self.multidelete_status[2])

	def waitcancel(self):
		self.cancel = 1
