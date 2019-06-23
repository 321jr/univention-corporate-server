#!/usr/bin/python2.7
# -*- coding: utf-8 -*-
#
# Univention Management Console
#  Univention Directory Manager Module
#
# Copyright 2017-2019 Univention GmbH
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

from __future__ import absolute_import
from __future__ import division
from __future__ import print_function
from __future__ import unicode_literals

import os
import re
import io
import json
import time
import copy
import uuid
import zlib
import urllib
import base64
import inspect
import httplib
import hashlib
import binascii
import datetime
import traceback
from email.utils import parsedate
from urlparse import urljoin, urlparse, urlunparse, parse_qs
from urllib import quote, unquote

import tornado.web
import tornado.gen
import tornado.log
import tornado.ioloop
import tornado.httpclient
import tornado.httputil
from tornado.web import RequestHandler, HTTPError, Finish
from tornado.concurrent import run_on_executor
from concurrent.futures import ThreadPoolExecutor

import ldap
from ldap.filter import filter_format
from ldap.dn import explode_rdn
from ldap.controls import SimplePagedResultsControl
from ldap.controls.sss import SSSRequestControl
import xml.etree.cElementTree as ET
import xml.dom.minidom
from genshi import XML
from genshi.output import HTMLSerializer

from univention.management.console.config import ucr
from univention.management.console.log import MODULE
from univention.management.console.ldap import get_user_connection, get_machine_connection
from univention.management.console.modules.udm.udm_ldap import get_module, UDM_Module, ldap_dn2path, read_syntax_choices, _get_syntax, container_modules, UDM_Error
from univention.management.console.modules.udm.udm_ldap import SuperordinateDoesNotExist, NoIpLeft
from univention.management.console.modules.udm.tools import check_license, LicenseError, LicenseImport as LicenseImporter, dump_license
from univention.management.console.modules.sanitizers import MultiValidationError, ValidationError, DictSanitizer, StringSanitizer, ListSanitizer, IntegerSanitizer, ChoicesSanitizer, DNSanitizer, EmailSanitizer, LDAPSearchSanitizer, Sanitizer, BooleanSanitizer
from univention.management.console.error import UMC_Error, LDAP_ServerDown, LDAP_ConnectionFailed, UnprocessableEntity

import univention.directory.reports as udr
import univention.admin.uexceptions as udm_errors
import univention.admin.modules as udm_modules
import univention.admin.syntax as udm_syntax
from univention.config_registry import handler_set

import univention.udm

from univention.lib.i18n import Translation
# FIXME: prevent in the javascript UMC module that navigation container query is called with container=='None'
# FIXME: it seems request.path contains the un-urlencoded path, could be security issue!
# TODO: 0f77c317e03844e8a16c484dde69abbcd2d2c7e3 is not integrated
# TODO: replace etree with genshi, etc.
# TODO: modify layout and properties for app-tabs
# TODO: loading the policies probably unnecessarily slows down things
# TODO: create a own translation domain for this file

_ = Translation('univention-management-console-module-udm').translate

MAX_WORKERS = 35

if 422 not in tornado.httputil.responses:
	tornado.httputil.responses[422] = 'Unprocessable Entity'  # Python 2 is missing this status code


def add_sanitizers(type_, sanitizers):
	def _decorator(method):
		setattr(method, 'sanitizers', getattr(method, 'sanitizers', {}))
		method.sanitizers[type_] = sanitizers
		return method
	return _decorator


def sanitize_body_arguments(**sanitizers):
	return add_sanitizers('body', sanitizers)


def sanitize_query_string(**sanitizers):
	return add_sanitizers('query', sanitizers)


class RequestSanitizer(DictSanitizer):

	def __init__(self, resource):
		sanitizers = getattr(getattr(resource, resource.request.method.lower()), 'sanitizers', {})
		super(RequestSanitizer, self).__init__({
			'query_string': QueryStringSanitizer(sanitizers.get('query', {}), required=True, further_arguments=['resource'], _copy_value=False),
			'body_arguments': DictSanitizer(sanitizers.get('body', {}), required=True, further_arguments=['resource'], _copy_value=False)
		}, further_arguments=['resource'], _copy_value=False)

	def sanitize(self, resource, *args, **kwargs):
		payload = {
			'query_string': resource.request.query_arguments or {},
			'body_arguments': resource.request.body_arguments or {},
			'__resource': resource,
			'__args': args,
			'__kwargs': kwargs,
		}
		if isinstance(payload['query_string'], dict):
			payload['query_string']['__resource'] = resource
		if isinstance(payload['body_arguments'], dict):
			payload['body_arguments']['__resource'] = resource
		value = super(RequestSanitizer, self).sanitize('request.arguments', {'request.arguments': payload, 'resource': resource})
		resource.request.query_arguments = value['query_string']
		resource.request.body_arguments = value['body_arguments']
		return value

	def _sanitize(self, value, name, further_arguments):
		return super(RequestSanitizer, self)._sanitize(value, name, further_arguments)


class QueryStringSanitizer(DictSanitizer):

	def _sanitize(self, value, name, further_arguments):
		if isinstance(value, dict):
			for key, sanitizer in self.sanitizers.items():
				if len(value.get(key, [])) == 1 and not isinstance(sanitizer, ListSanitizer):
					value[key] = value[key][0]

		return super(QueryStringSanitizer, self)._sanitize(value, name, further_arguments)


class DefaultDictSanitizer(DictSanitizer):

	def __init__(self, sanitizers, allow_other_keys=True, **kwargs):
		self.default_sanitizer = kwargs.pop('default_sanitizer', None)
		super(DefaultDictSanitizer, self).__init__(sanitizers, allow_other_keys=allow_other_keys, **kwargs)

	def _sanitize(self, value, name, further_arguments):
		if not isinstance(value, dict):
			self.raise_formatted_validation_error(_('Not a "dict"'), name, type(value).__name__)

		if not self.allow_other_keys and any(key not in self.sanitizers for key in value):
			self.raise_validation_error(_('Has more than the allowed keys'))

		altered_value = copy.deepcopy(value) if self._copy_value else value

		multi_error = MultiValidationError()
		for attr in value:
			sanitizer = self.sanitizers.get(attr, self.default_sanitizer)
			try:
				if sanitizer:
					altered_value[attr] = sanitizer.sanitize(attr, value)
			except ValidationError as e:
				multi_error.add_error(e, attr)

		if multi_error.has_errors():
			raise multi_error

		return altered_value


class ObjectPropertySanitizer(StringSanitizer):

	def __init__(self, **kwargs):
		"""A LDAP attribute name.
			must at least be 1 character long.

			This sanitizer prevents LDAP search filter injections in the attribute name.

			TODO: in theory we should only allow existing searchable properties for the requested object type
		"""
		args = dict(
			minimum=0,
			regex_pattern=r'^[\w\d\-;]*$',
		)
		args.update(kwargs)
		StringSanitizer.__init__(self, **args)


class PropertiesSanitizer(DefaultDictSanitizer):

	def __init__(self, *args, **kwargs):
		super(PropertiesSanitizer, self).__init__({}, *args, default_sanitizer=PropertySanitizer(), **kwargs)

	def sanitize(self, resource, module, obj):
		# FIXME: for the automatic IP address assignment, we need to make sure that
		# the network is set before the IP address (see Bug #24077, comment 6)
		# The following code is a workaround to make sure that this is the
		# case, however, this should be fixed correctly.
		# This workaround has been documented as Bug #25163.
		def _tmp_cmp(i, j):
			if i[0] == 'network':
				return -1
			return 0
		properties = resource.request.body_arguments['properties']
		# TODO: add sanitizer for e.g. required properties (respect options!)

		properties = dict(encode_properties(module.name, properties, resource.ldap_connection))

		self.default_sanitizer._module = module
		self.default_sanitizer._obj = obj
		try:
			properties = super(PropertiesSanitizer, self).sanitize('properties', {'properties': properties})
		finally:
			self.default_sanitizer._module = None
			self.default_sanitizer._obj = None

		password_properties = module.password_properties
		for property_name, value in sorted(properties.items(), _tmp_cmp):
			if property_name in password_properties:
				MODULE.info('Setting password property %s' % (property_name,))
			else:
				MODULE.info('Setting property %s to %r' % (property_name, value))

			try:
				try:
					obj[property_name] = value
				except udm_errors.valueMayNotChange:
					if obj[property_name] == value:  # UDM does not check equality before raising the exception
						continue
					raise
			except (udm_errors.valueInvalidSyntax, udm_errors.valueError, udm_errors.valueMayNotChange, udm_errors.valueRequired, udm_errors.noProperty) as exc:
				multi_error = MultiValidationError()
				try:
					self.raise_formatted_validation_error(_('The property %(name)s has an invalid value: %(details)s'), property_name, value, details=str(exc))
				except ValidationError as exc:
					multi_error.add_error(exc, property_name)
					raise multi_error

		resource.request.body_arguments['properties'] = properties
		return properties


class PropertySanitizer(Sanitizer):

	def __init__(self, *args, **kwargs):
		self._module = None
		self._obj = None
		super(PropertySanitizer, self).__init__(*args, **kwargs)

	def _sanitize(self, value, name, further_arguments):
		property_obj = self._module.get_property(name)

		if property_obj is None:
			self.raise_validation_error(_('The %(module)s module has no property %(name)s.'), module=self._module.title)

		if not self._obj.has_property(name):
			return value  # value will not be set, so no validation is required

		# check each element if 'value' is a list
		if isinstance(value, (tuple, list)) and property_obj.multivalue:
			errors = []
			new_value = []
			for val in value:
				try:
					new_value.append(property_obj.syntax.parse(val))
				except (udm_errors.valueInvalidSyntax, udm_errors.valueError, TypeError) as exc:
					errors.append(str(exc))
			if errors:
				self.raise_validation_error(_('The property %(property)s has an invalid value: %(details)s'), property=property_obj.short_description, details='\n'.join(errors))
			value = new_value
		else:  # otherwise we have a single value
			try:
				value = property_obj.syntax.parse(value)
			except (udm_errors.valueInvalidSyntax, udm_errors.valueError) as exc:
				self.raise_validation_error(_('The property %(property)s has an invalid value: %(details)s'), property=property_obj.short_description, details=str(exc))

		return value


class BoolSanitizer(ChoicesSanitizer):

	def __init__(self, **kwargs):
		super(BoolSanitizer, self).__init__(choices=['1', 'on', 'true', 'false', '0', 'off', '', None], **kwargs)

	def _sanitize(self, value, name, further_arguments):
		return super(BoolSanitizer, self)._sanitize(value, name, further_arguments) in ('1', 'on', 'true')


class NotFound(HTTPError):

	def __init__(self, object_type, dn=None):
		super(NotFound, self).__init__(404, None, '%r %r' % (object_type, dn or ''))  # FIXME: create error message


class RessourceBase(object):

	pool = ThreadPoolExecutor(max_workers=MAX_WORKERS)

	requires_authentication = True
	authenticated = {}

	def force_authorization(self):
		self.set_header('WWW-Authenticate', 'Basic realm="Univention Management Console"')
		self.set_status(401)
		self.finish()

	def set_default_headers(self):
		self.set_header('Server', 'Univention/1.0')  # TODO:

	def prepare(self):
		self.request.path_decoded = urllib.unquote(self.request.path)
		authorization = self.request.headers.get('Authorization')
		if not authorization:
			if self.requires_authentication:
				return self.force_authorization()

		try:
			if authorization:
				self.parse_authorization(authorization)
		finally:
			self.request.content_negotiation_lang = 'html'
			self.request.content_negotiation_lang = self.check_acceptable()
			self.decode_request_arguments()
			self.sanitize_arguments(RequestSanitizer(self), self)

	def parse_authorization(self, authorization):
		if authorization in self.authenticated:
			(self.request.user_dn, self.request.username, self.ldap_connection, self.ldap_position) = self.authenticated[authorization]
			if self.ldap_connection.whoami():
				return  # the ldap connection is still valid and bound
		try:
			if not authorization.lower().startswith('basic '):
				raise ValueError()
			username, password = base64.decodestring(authorization.split(' ', 1)[1]).split(':', 1)
		except (ValueError, IndexError, binascii.Error):
			raise HTTPError(400)

		lo, po = get_machine_connection(write=False)
		try:
			userdn = lo.searchDn(filter_format('(&(objectClass=person)(uid=%s))', [username]), unique=True)[0]
			self.ldap_connection, self.ldap_position = get_user_connection(bind=lambda lo: lo.bind(userdn, password), write=True)
			self.request.user_dn = userdn
			self.request.username = username
		except Exception:
			return self.force_authorization()
		else:
			self.authenticated[authorization] = (userdn, username, self.ldap_connection, self.ldap_position)

	def get_module(self, object_type):
		module = UDM_Module(object_type, ldap_connection=self.ldap_connection, ldap_position=self.ldap_position)
		if not module or not module.module:
			raise NotFound(object_type)
		return module

	def get_object(self, object_type, dn):
		module = self.get_module(object_type)
		obj = module.get(dn)
		if not obj:
			raise NotFound(object_type, dn)
		return obj

	def check_acceptable(self):
		accept = self.request.headers.get('Accept', 'text/html').split(',')
		langs = []
		for language in accept:
			score = 1.0
			parts = language.strip().split(";")
			for part in (x for x in parts[1:] if x.strip().startswith("q=")):
				try:
					score = float(part.strip()[2:])
					break
				except (ValueError, TypeError):
					raise
					score = 0.0
			langs.append((parts[0].strip(), score))
		langs.sort(key=lambda pair: pair[1], reverse=True)
		lang = None
		for name, q in langs:
			if q <= 0:
				continue
			if name in ('text/html', 'text/xml', 'application/xml', 'text/*', '*/*'):
				lang = 'html'
				break
			elif name in ('application/json', 'application/*'):
				lang = 'json'
				break
		if not lang:
			raise HTTPError(406)
		return lang

	def decode_request_arguments(self):
		content_type = self.request.headers.get('Content-Type', '')
		if content_type.startswith('application/json'):
			try:
				self.request.body_arguments = json.loads(self.request.body)
			except ValueError as exc:
				raise HTTPError(400, _('Invalid JSON document: %r') % (exc,))
		elif content_type.startswith('application/x-www-form-urlencoded') or content_type.startswith('multipart/form-data'):
			self.decode_form_arguments()

	def decode_form_arguments(self):
		pass

	def get_body_argument(self, name, *args):
		if self.request.headers.get('Content-Type', '').startswith('application/json'):
			return self.request.body_arguments.get(name)
		return super(RessourceBase, self).get_body_argument(name, *args)

	def get_body_arguments(self, name, *args):
		if self.request.headers.get('Content-Type', '').startswith('application/json'):
			return self.request.body_arguments.get(name)
		return super(RessourceBase, self).get_body_arguments(name, *args)

	def sanitize_arguments(self, sanitizer, *args, **kwargs):
		try:
			try:
				return sanitizer.sanitize(*args, **kwargs)
			except MultiValidationError:
				raise
			except ValidationError as exc:
				multi_error = MultiValidationError()
				multi_error.add_error(exc, 'request.arguments')
				raise multi_error
		except MultiValidationError as e:
			raise UnprocessableEntity(str(e), result=e.result())

	def content_negotiation(self, response):
		self.add_header('Vary', ', '.join(self.vary()))
		lang = self.request.content_negotiation_lang
		formatter = getattr(self, '%s_%s' % (self.request.method.lower(), lang), getattr(self, 'get_%s' % (lang,)))
		codec = getattr(self, 'content_negotiation_%s' % (lang,))
		self.finish(codec(formatter(response)))

	def content_negotiation_json(self, response):
		self.set_header('Content-Type', 'application/json')
		return json.dumps(response)

	def content_negotiation_html(self, response):
		self.set_header('Content-Type', 'text/html; charset=UTF-8')

		root = ET.Element("html")
		head = ET.SubElement(root, "head")
		titleelement = ET.SubElement(head, "title")
		titleelement.text = 'FIXME: fallback title'  # FIXME: set title
		ET.SubElement(head, 'meta', content='text/html; charset=utf-8', **{'http-equiv': 'content-type'})
		body = ET.SubElement(root, "body")
		header = ET.SubElement(body, 'header')
		topnav = ET.SubElement(header, 'nav')
		h1 = ET.SubElement(topnav, 'h1', id='logo')
		home = ET.SubElement(h1, 'a', rel='home', href=self.abspath('/'))
		home.text = ' '
		nav = ET.SubElement(body, 'nav')
		links = ET.SubElement(nav, 'ul')
		main = ET.SubElement(body, 'main')
		_links = {}
		navigation_relations = self.navigation()
		for link in self._headers.get_list('Link'):
			link, foo, _params = link.partition(';')
			link = link.strip().lstrip('<').rstrip('>')
			params = {}
			if _params.strip():
				params = dict((x.strip(), y.strip().strip('"').replace('\\"', '"').replace('\\\\', '\\')) for x, y in ((param.split('=', 1) + [''])[:2] for param in _params.split(';')))
			ET.SubElement(head, "link", href=link, **params)
			_links[params.get('rel')] = dict(params, href=link)
			if params.get('rel') == 'self':
				titleelement.text = params.get('title') or link or 'FIXME:notitle'
			if params.get('rel') in ('stylesheet', 'icon', 'self', 'up', 'udm/relation/object/remove', 'udm/relation/object/edit'):
				continue
			if params.get('rel') in navigation_relations:
				continue
			if params.get('rel') in ('udm/relation/user-photo',):
				ET.SubElement(nav, 'img', src=link, style='max-width: 200px')
				continue
			elif params.get('rel') in ('create-form', 'edit-form'):
				ET.SubElement(ET.SubElement(nav, 'form'), 'button', formaction=link, **params).text = params.get('title', link)
				continue
			#if params.get('rel') in ('udm/relation/tree',):
			#	self.set_header('X-Frame-Options', 'SAMEORIGIN')
			#	body.insert(1, ET.Element('iframe', src=link, name='tree'))
			#	continue
			li = ET.SubElement(links, "li")
			ET.SubElement(li, "a", href=link, **params).text = params.get('title', link) or link

		for name in navigation_relations:
			params = _links.get(name)
			if params:
				ET.SubElement(topnav, 'a', **params).text = '›› %s' % (params.get('title') or params['href'],)

		if isinstance(response, (list, tuple)):
			main.extend(response)
		elif response is not None:
			main.append(response)

		ajax = self.request.headers.get('X-Requested-With', '').lower() == 'xmlhttprequest'
		if not ajax:
			stream = XML(xml.dom.minidom.parseString(ET.tostring(root, encoding='utf-8', method='xml')).toprettyxml())
			#stream = XML(ET.tostring(root, encoding='utf-8', method='html'))
			self.write(''.join((HTMLSerializer('html5')(stream))))
		else:
			self.write('<!DOCTYPE html>\n')
			tree = ET.ElementTree(body if ajax else root)
			tree.write(self)

	def get_json(self, response):
		return response

	def get_html(self, response):
		root = []
		if isinstance(response, dict):
			self.add_link(response, 'stylesheet', self.abspath('css/style.css'))
			for _form in response.get('_forms', []):
				root.insert(0, self.get_html_form(_form, response))
			if isinstance(response.get('error'), dict) and response['error'].get('code', 0) >= 400:
				error = ET.Element('div')
				root.append(error)
				ET.SubElement(error, 'h1').text = _('HTTP-Error %d: %s') % (response['error']['code'], response['error']['title'])
				ET.SubElement(error, 'p', style='white-space: pre').text = response['error']['message']
				if response['error'].get('traceback'):
					ET.SubElement(error, 'pre').text = response['error']['traceback']
				response = None

		if isinstance(response, (list, tuple)):
			print('WARNING: uses deprecated LIST response')
			for thing in response:
				pre = ET.Element("pre")
				pre.text = json.dumps(thing, indent=4)
				root.append(pre)
				root.append(ET.Element("br"))
		elif isinstance(response, dict):
			r = response.copy()
			r.pop('_forms', None)
			r.pop('_links', None)
			if r:
				pre = ET.Element("pre")
				pre.text = json.dumps(r, indent=4)
				root.append(pre)
		return root

	def get_html_layout(self, root, layout, properties):
		for sec in layout:
			section = ET.SubElement(root, 'section')
			ET.SubElement(section, 'h1').text = sec['label']
			fieldset = ET.SubElement(section, 'fieldset')
			ET.SubElement(fieldset, 'legend').text = sec['description']
			self.render_layout(sec['layout'], fieldset, properties)
		return root

	def render_layout(self, layout, fieldset, properties):
		for elem in layout:
			if isinstance(elem, dict):
				sub_fieldset = ET.SubElement(fieldset, 'fieldset')
				ET.SubElement(sub_fieldset, 'legend').text = elem['label']
				if elem['description']:
					ET.SubElement(sub_fieldset, 'h2').text = elem['description']
				self.render_layout(elem['layout'], sub_fieldset, properties)
				continue
			elements = [elem] if isinstance(elem, basestring) else elem
			for elem in elements:
				try:
					field = [x for x in properties if x['name'] in (elem, 'properties[%s]' % elem)][0]
				except IndexError:
					print('ELEM', elem)
				else:
					self.render_form_field(fieldset, field)
			if elements:
				ET.SubElement(fieldset, 'br')

	def get_html_form(self, _form, response):
		form = ET.Element('form', **dict((p, _form[p]) for p in ('id', 'name', 'method', 'action', 'rel', 'enctype') if _form.get(p)))
		if _form.get('layout'):
			self.get_html_layout(form, response['layout'], _form.get('fields'))
			return form
		for field in _form.get('fields', []):
			self.render_form_field(form, field)
			form.append(ET.Element('br'))
		form.append(ET.Element('hr'))
		return form

	def render_form_field(self, form, field):
		name = field['name']
		label = ET.Element('label', **{'for': name})
		label.text = field.get('label', name)
		form.append(label)
		elemattrs = dict((p, field[p]) for p in ('disabled', 'form', 'multiple', 'required', 'size', 'type', 'placeholder', 'accept', 'alt', 'autocomplete', 'checked', 'max', 'min', 'minlength', 'pattern', 'readonly', 'src', 'step') if field.get(p))
		elemattrs.setdefault('type', 'text')
		elemattrs.setdefault('placeholder', name)
		if field.get('type') == 'checkbox' and field.get('checked'):
			elemattrs['checked'] = 'checked'
		element = ET.Element(field.get('element', 'input'), name=name, value=str(field['value']), **elemattrs)
		form.append(element)
		if field['element'] == 'select':
			for option in field.get('options', []):
				kwargs = {}
				if field['value'] == option['value'] or (isinstance(field['value'], list) and option['value'] in field['value']):
					kwargs['selected'] = 'selected'
				ET.SubElement(element, 'option', value=option['value'], **kwargs).text = option.get('label', option['value'])

	def urljoin(self, *args, **query):
		base = urlparse(self.request.full_url())
		query_string = ''
		if query:
			qs = parse_qs(base.query)
			qs.update(dict((key, val if isinstance(val, (list, tuple)) else [val]) for key, val in query.items()))
			query_string = '?%s' % (urllib.urlencode(qs, True),)
		return urljoin(urljoin(urlunparse((base.scheme, base.netloc, 'univention/' if self.request.headers.get('X-Forwarded-Host') else '/', '', '', '')), self.request.path_decoded.lstrip('/')), '/'.join(args)) + query_string

	def abspath(self, *args):
		return urljoin(self.urljoin('/univention/udm/' if self.request.headers.get('X-Forwarded-Host') else '/udm/'), '/'.join(args))

	def add_link(self, obj, relation, href, **kwargs):
		def quote_param(s):
			return s.replace('\\', '\\\\').replace('"', '\\"')
		links = obj.setdefault('_links', {})
		links.setdefault(relation, []).append(dict(kwargs, href=href))
		self.add_header('Link', '<%s>; rel="%s"; name="%s"; title="%s"' % (href, quote_param(relation), quote_param(kwargs.get('name', '')), quote_param(kwargs.get('title', ''))))

	def add_form(self, obj, action, method, **kwargs):
		form = {
			'action': action,
			'method': method,
		}
		form.setdefault('enctype', 'application/x-www-form-urlencoded')
		form.update(kwargs)
		obj.setdefault('_forms', []).append(form)
		return form

	def add_form_element(self, form, name, value, type='text', element='input', **kwargs):
		field = {
			'name': name,
			'value': value,
			'type': type,
			'element': element,
		}
		field.update(kwargs)
		form.setdefault('fields', []).append(field)
		return field

	def log_exception(self, typ, value, tb):
		if isinstance(value, UMC_Error):
			return
		super(RessourceBase, self).log_exception(typ, value, tb)

	def write_error(self, status_code, exc_info=None, **kwargs):
		if not exc_info:  # or isinstance(exc_info[1], HTTPError):
			return super(RessourceBase, self).write_error(status_code, exc_info=exc_info, **kwargs)

		etype, exc, etraceback = exc_info
		if isinstance(exc, udm_errors.ldapError) and isinstance(getattr(exc, 'original_exception', None), (ldap.SERVER_DOWN, ldap.CONNECT_ERROR, ldap.INVALID_CREDENTIALS)):
			exc = exc.original_exception
		if isinstance(exc, ldap.SERVER_DOWN):
			exc = LDAP_ServerDown()
		if isinstance(exc, ldap.CONNECT_ERROR):
			exc = LDAP_ConnectionFailed(exc)
		_traceback = None
		message = str(exc)
		title = ''
		result = {}
		if isinstance(exc, UMC_Error):
			status_code = exc.status
			title = exc.msg
			if status_code == 503:
				self.add_header('Retry-After', '15')
			if title == message:
				title = httplib.responses.get(status_code)
			if isinstance(exc.result, dict):
				result = exc.result
		if isinstance(exc, UnprocessableEntity):
			error = ''
			for key, value in exc.result.items():
				formatter = _('Request argument "%s" %s\n')
				if key == 'query_string':
					formatter = _('Query string "%s": %s\n')
				if isinstance(value, dict):
					for k, v in value.items():
						error += formatter % (k, v)
				else:
					error += formatter % (key, value)
			message = '%s:\n%s' % (message, error)

		if not isinstance(exc, (UDM_Error, UMC_Error)) and status_code >= 500:
			_traceback = ''.join(traceback.format_exception(etype, exc, etraceback))

		self.set_status(status_code)
		self.content_negotiation({
			'error': {
				'title': title,
				'code': status_code,
				'message': message,
				'traceback': _traceback if self.application.settings.get("serve_traceback", True) else None,
				'error': result,
			},
		})

	def add_caching(self, expires=None, public=False, must_revalidate=False, no_cache=False, no_store=False, no_transform=False, max_age=None, shared_max_age=None, proxy_revalidate=False):
		control = [
			'public' if public else 'private',
			'must-revalidate' if must_revalidate else '',
			'no-cache' if no_cache else '',
			'no-store' if no_store else '',
			'no-transform' if no_transform else '',
			'max-age=%d' % (max_age,) if max_age else '',
			's-maxage=%d' % (shared_max_age,) if shared_max_age else '',
			'proxy-revalidate' if proxy_revalidate else '',
		]
		cache_control = ', '.join(x for x in control if x)
		if cache_control:
			self.add_header('Cache-Control', cache_control)
		if expires:
			self.add_header('Expires', expires)

	def vary(self):
		return ['Accept', 'Accept-Language', 'Accept-Encoding', 'Authorization']

	def get_parent_object_type(self, module):
		flavor = module.flavor
		if '/' not in flavor:
			return module
		return UDM_Module(flavor, ldap_connection=self.ldap_connection, ldap_position=self.ldap_position)

	def navigation(self):
		return ('udm/relation/object-modules', 'udm/relation/object-module', 'udm/relation/object-type', 'up', 'self')


class Ressource(RessourceBase, RequestHandler):
	pass


class Favicon(RessourceBase, tornado.web.StaticFileHandler):

	@classmethod
	def get_absolute_path(cls, root, object_type=''):
		value = object_type.replace('/', '-')
		if value == 'favicon':
			return root
		if not value.replace('-', '').replace('_', '').isalpha():
			raise NotFound(object_type)
		return os.path.join(root, 'udm-%s.png' % (value,))


class Relations(Ressource):

	def get(self, relation):
		iana_relations = {
			'search': 'Refers to a resource that can be used to search through the link\'s context and related resources.',
			'create-form': 'The target IRI points to a resource where a submission form can be obtained.',
			'edit': 'Refers to a resource that can be used to edit the link\'s context.',
			'edit-form': 'The target IRI points to a resource where a submission form for editing associated resource can be obtained.',
			'first': 'An IRI that refers to the furthest preceding resource in a series of resources.',
			'help': 'Refers to context-sensitive help.',
			'index': 'Refers to an index.',
			'item': 'The target IRI points to a resource that is a member of the collection represented by the context IRI.',
			'last': 'An IRI that refers to the furthest following resource in a series of resources.',
			'latest-version': 'Points to a resource containing the latest (e.g., current) version of the context.',
			'next': 'Indicates that the link\'s context is a part of a series, and that the next in the series is the link target. ',
			'original': 'The Target IRI points to an Original Resource.',
			'prev': 'Indicates that the link\'s context is a part of a series, and that the previous in the series is the link target. ',
			'preview': 'Refers to a resource that provides a preview of the link\'s context.',
			'previous': 'Refers to the previous resource in an ordered series of resources. Synonym for "prev".',
			'self': 'Conveys an identifier for the link\'s context. ',
			'start': 'Refers to the first resource in a collection of resources.',
			'type': 'Refers to a resource identifying the abstract semantic type of which the link\'s context is considered to be an instance.',
			'up': 'Refers to a parent document in a hierarchy of documents.',
			'icon': 'Refers to an icon representing the link\'s context.',
		}
		univention_relations = {
			'': 'description of all relations',
			'object': '',
			'object-modules': 'list of available module categories',
			'object-module': 'the module belonging to the current selected resource',
			'object-types': 'list of object types matching the given flavor or container',
			'object-type': 'the object type belonging to the current selected resource',
			'children-types': 'list of object types which can be created underneath of the container or superordinate',
			'properties': 'properties of the given object type',
			'tree': 'list of tree content for providing a hierarchical navigation',
			'policy-result': 'policy result by virtual policy object containing the values that the given object or container inherits',
			'report': 'create a report',
			'default-search': 'default search pattern/value for the given object property',
			'next-free-ip': 'next IP configuration based on the given network object',
			'property-choices': 'determine valid values for a given syntax class',
			'object/remove': 'remove this object, edit-form is preferable',
			'object/move': 'move objects to a certain position',
			'object/edit': 'modify this object, edit-form is preferable',
			'user-photo': 'photo of the object',
			'license': 'information about UCS license',
			'license-request': 'Request a new UCS Core Edition license',
			'license-check': 'Check if the license limits are reached',
			'license-import': 'Import a new license in LDIF format',
		}
		self.add_caching(public=True)
		result = {}
		self.add_link(result, 'self', self.urljoin(''), title=_('Link relations'))
		self.add_link(result, 'up', self.urljoin('../'), title=_('All modules'))
		if relation:
			result['relation'] = univention_relations.get(relation, iana_relations.get(relation))
			if not result['relation']:
				raise NotFound()
		else:
			for relation in iana_relations:
				self.add_link(result, 'udm/relation/', self.urljoin(relation), name=relation, title=relation)
			for relation in univention_relations:
				self.add_link(result, 'udm/relation/', self.urljoin(relation), name='udm/relation/%s' % relation, title='udm/relation/%s' % relation)
		self.content_negotiation(result)


class Swagger(Ressource):

	requires_authentication = False

	def prepare(self):
		super(Swagger, self).prepare()
		self.request.content_negotiation_lang = 'json'
		self.ldap_connection, self.ldap_position = get_machine_connection(write=False)

	def get(self):
		responses = {}
		paths = {}
		tags = []
		definitions = {}
		parameters = {}
		parameters['search'] = [{
			"in": "query",
			"name": "position",
			"type": "string",
			"format": "dn",
			"description": "Position which is used as search base",
		}, {
			"in": "query",
			"name": "scope",
			"type": "string",
			"description": "The LDAP search scope (sub, base, one)",
		}, {
			"in": "query",
			"name": "property",
			"type": "string",
			"description": "A property name to filter for",
		}, {
			"in": "query",
			"name": "propertyvalue",
			"type": "string",
			"description": "The value to search for",
		}, {
			"in": "query",
			"name": "hidden",
			"type": "boolean",
			"description": "Include hidden/system objects in the response",
		}, {
			"in": "query",
			"name": "superordinate",
			"type": "string",
			"format": "dn",
			"description": "The superordinate DN of the objects to find",
		}, {
			"in": "query",
			"name": "pagesize",
			"type": "integer",
			"description": "How many results should be shown per page",
		}, {
			"in": "query",
			"name": "page",
			"type": "integer",
			"description": "Which search page",
		}, {
			"in": "query",
			"name": "dir",
			"type": "string",
			"description": "Sort direction (ASC or DESC)",
		}, {
			"in": "query",
			"name": "by",
			"type": "string",
			"description": "Sort result by property",
		}]
		widget_type_map = {
			'umc/modules/udm/LockedCheckBox': bool,
			'umc/modules/udm/MultiObjectSelect': list,
			'umc/modules/udm/PortalContent': str,
			'CheckBox': bool,
			'PasswordInputBox': (str, 'password'),
			'DateBox': (str, 'date'),
			'TimeBox': (str, 'time'),
			'umc/modules/udm/LinkList': str,
			'ComboBox': str,
			'TextBox': str,
			'umc/modules/udm/ComboBox': str,
			'UnixAccessRights': str,
			'UnixAccessRightsExtended': str,
			'MultiSelect': list,
			'umc/modules/udm/CertificateUploader': (str, 'byte'),
			'ImageUploader': (str, 'binary'),
			'TextArea': str,
			'Editor': (str, 'html'),
			'TextBox': str,
			'MultiInput': list,
			'ComplexInput': str,
		}
		typemap = {
			int: 'integer',
			float: 'number',
			str: 'string',
			bool: 'boolean',
			None: 'void',
			dict: 'object',
			list: 'array',
		}
		for name, mod in sorted(udm_modules.modules.items()):
			module = UDM_Module(name, ldap_connection=self.ldap_connection, ldap_position=self.ldap_position)
			tag = name
			tag_escaped = name.replace('/', '~1')
			tags.append({
				'description': '%s objects' % (module.title,),
				'name': tag,
			})
			objects_pathes = {}
			if 'search' in module.operations:
				objects_pathes['get'] = {
					"operationId": "list",
					"parameters": parameters['search'],
					#[
					#	{
					#		"$ref": "#/parameters/search"
					#	}
					#],
					"responses": {
						201: {
							"description": "Success",
							"schema": {
								"type": "object",
								"properties": {
									"entries": {
										"items": {
											"$ref": "#/definitions/%s" % (tag_escaped,)
										},
										"type": "array"
									}
								}
							}
						}
					},
					"summary": "List all %s" % (module.object_name_plural,),
					"tags": [tag],
				}
			if 'add' in module.operations:
				objects_pathes['post'] = {
					"operationId": "create",
					"parameters": [{
						"in": "body",
						"name": "payload",
						"required": True,
						"schema": {
							"$ref": "#/definitions/%s" % (tag_escaped,)
						}
					}],
					"responses": {
						201: {
							"description": "Success",
							"schema": {
								"$ref": "#/definitions/%s" % (tag_escaped,)
							}
						}
					},
					"summary": "Create a new %s object" % (module.object_name,),
					"tags": [tag],
				}
			object_pathes = {
				"parameters": [
					{
						"description": "The objects DN (urlencoded)",
						"in": "path",
						"name": "dn",
						"required": True,
						"type": "string",
						"format": "dn",
					}
				],
				"get": {
					"operationId": "get",
					"responses": {
						"200": {
							"description": "Success",
							"schema": {
								"$ref": "#/definitions/%s" % (tag_escaped,)
							}
						},
						"404": {
							"description": "Object not found"
						}
					},
					"summary": "Get a representation of the %s object" % (module.object_name,),
					"tags": [tag]
				},
			}
			if 'remove' in module.operations:
				object_pathes["delete"] = {
					"operationId": "delete",
					"parameters": [
						{
							"in": "query",
							"name": "cleanup",
							"type": "boolean",
							"description": "Whether to perform a cleanup (e.g. of temporary objects, locks, etc).",
						},
						{
							"in": "query",
							"name": "recursive",
							"type": "boolean",
							"description": "Whether to remove referring objects (e.g. DNS or DHCP references).",
						}
					],
					"responses": {
						"204": {
							"description": "Object deleted"
						},
						"404": {
							"description": "Object not found"
						}
					},
					"summary": "Remove a %s object" % (module.object_name_plural,),
					"tags": [tag],
				}
			if set(module.operations) & {'edit', 'move', 'move_subtree'}:
				object_pathes["put"] = {
					"operationId": "modify",
					"parameters": [
						{
							"in": "body",
							"name": "payload",
							"required": True,
							"schema": {
								"$ref": "#/definitions/%s" % (tag_escaped,)
							}
						},
					],
					"responses": {
						"200": {
							"description": "Success",
							"schema": {
								"$ref": "#/definitions/%s" % (tag_escaped,)
							}
						},
						"404": {
							"description": "Object not found"
						}
					},
					"summary": "Modify or move an %s object" % (module.object_name,),
					"tags": [tag],
				}
				object_pathes['patch'] = object_pathes['put'].copy()
				object_pathes['patch']['operationId'] = 'patch'
			paths['/%s/' % (name,)] = objects_pathes
			paths['/%s/{dn}' % (name,)] = object_pathes
			definitions[tag] = {
				"allOf": [
					{
						"$ref": "#/definitions/base"
					},
					{
						"properties": {
							"properties": {
								"$ref": "#/definitions/%s_properties" % (tag_escaped,)
							},
							"uri": {
								"type": "string",
								"format": "uri"
							},
							"options": {
								"description": "Object type specific options.",
								"properties": dict((oname, {
									"description": opt.short_description,
									"type": "boolean",
								}) for oname, opt in module.options.items()),
								"type": "object"
							},
							"policies": {
								"description": "Policies which apply for this object.",
								"properties": dict((pol['objectType'], {
									"type": "string",
									"format": "dn",
									"description": pol['label'],
								}) for pol in module.policies),
								"type": "object"
							},
						},
						"type": "object"
					}
				]
			}
			if module.superordinate_names:
				definitions[tag]['allOf'].append({'$ref$': '#/definitions/superordinate'})
			properties = {}
			for prop in module.properties(None):
				name = prop['id']
				if name.startswith('$'):
					continue
				properties[name] = {
					"type": "string",
					"description": prop['label'],
				}
				ptype = widget_type_map.get(prop['type'], str)
				if isinstance(ptype, tuple):
					ptype, properties[name]['format'] = ptype
				properties[name]['type'] = typemap[ptype]
				# Swagger is not capable of having array containig different types... OpenAPI 3 might do it
				#for subtype in prop.get("subtypes_", []):
				#	item = {}
				#	ptype = widget_type_map.get(prop['type'], str)
				#	if isinstance(ptype, tuple):
				#		ptype, item['format'] = ptype
				#	item['type'] = typemap[ptype]
				#	properties[name].setdefault('items', []).append(item)
				if ptype is list:
					properties[name].setdefault('items', {'type': 'string', 'description': 'subtype'})

			definitions['%s_properties' % (tag,)] = {
				"type": "object",
				"description": "Properties of the %s" % (module.title,),
				"properties": properties,
			}

		definitions["base"] = {
			"properties": {
				"dn": {
					"description": "DN of this object (read only)",
					"type": "string",
					"format": "dn",
				},
				"position": {
					"description": "DN of LDAP node below which the object is located.",
					"type": "string",
					"format": "dn",
				},
				#"id": {
				#	"description": "ID of this object.",
				#	"type": "string"
				#},
			},
			"type": "object"
		}
		definitions["superordinate"] = {
			"properties": {
				"superordinate": {
					"type": "string",
					"format": "dn",
				}
			},
			"type": "object"
		}
		specs = {
			'swagger': '2.0',
			'basePath': self.abspath(''),
			'paths': paths,
			'info': {
				'description': 'Schema definition for the Univention Directory Manager JSON-HTTP interface',
				'title': 'Univention Directory Manager JSON-HTTP interface',
				'version': '1.0',
			},
			'produces': ['application/json', 'text/html'],
			'consumes': ['application/json', 'application/x-www-form-urlencoded', 'multipart/form-data'],
			'securityDefinitions': {"basic": {"type": "basic"}},
			'security': [{"basic": []}],
			'tags': tags,
			'definitions': definitions,
			'parameters': parameters,
			'responses': responses or None,
			'host': '%s.%s' % (ucr['hostname'], ucr['domainname']),
		}
		self.content_negotiation(specs)


class Modules(Ressource):

	mapping = {
		'users': 'users/user',
		'contacts': 'users/contact',
		'computers': 'computers/computer',
		'groups': 'groups/group',
		'networks': 'networks/network',
		'dhcp': 'dhcp/dhcp',
		'dns': 'dns/dns',
		'shares': 'shares/share',
		'printers': 'shares/print',
		'mail': 'mail/mail',
		'nagios': 'nagios/nagios',
		'policies': 'policies/policy',
		'self': 'users/self',
		'portal': 'settings/portal_all',
		'saml': 'saml/serviceprovider',
		'appcenter': 'appcenter/app',
		'kerberos': 'kerberos/kdcentry',
		'settings': 'settings/settings',
		'navigation': 'object',
		'container': 'container',
	}

	def get(self):
		result = {}
		self.add_link(result, 'self', self.urljoin(''), title=_('All modules'))
		for main_type, name in sorted(self.mapping.items(), key=lambda x: 0 if x[0] == 'navigation' else x[0]):
			title = _('All %s types') % (name,)
			if '/' in name:
				title = UDM_Module(name, ldap_connection=self.ldap_connection, ldap_position=self.ldap_position).object_name_plural

			self.add_link(result, 'udm/relation/object-modules', self.urljoin(quote(main_type)) + '/', name='all' if main_type == 'navigation' else main_type, title=title)
		self.add_link(result, 'udm/relation/license', self.urljoin('license') + '/', name='license', title=_('UCS license'))
		self.add_link(result, 'udm/relation/ldap-base', self.urljoin('ldap/base') + '/', title=_('LDAP base'))
		self.add_link(result, 'udm/relation/', self.urljoin('relation') + '/', name='relation', title=_('All link relations'))
		self.add_caching(public=True)
		self.content_negotiation(result)

	def navigation(self):
		return ['self']


class ObjectTypes(Ressource):
	"""get the object types of a specific flavor"""

	@sanitize_query_string(
		superordinate=DNSanitizer(required=False, allow_none=True)
	)
	def get(self, module_type):
		object_type = Modules.mapping.get(module_type)
		if not object_type:
			raise NotFound(object_type)

		title = _('All object types')
		module = None
		if '/' in object_type:
			# FIXME: what was/is the superordinate for?
			superordinate = self.request.query_arguments['superordinate']
			module = UDM_Module(object_type, ldap_connection=self.ldap_connection, ldap_position=self.ldap_position)
			if superordinate:
				module = get_module(object_type, superordinate, self.ldap_connection) or module  # FIXME: the object_type param is wrong?!
			title = module.object_name_plural

		result = {'entries': [], }

		self.add_link(result, 'up', self.urljoin('../'), title=_('All modules'))
		self.add_link(result, 'self', self.urljoin(''), title=title)
		if module_type == 'navigation':
			self.add_link(result, 'udm/relation/tree', self.abspath('container/dc/tree'))
		elif module and module.has_tree:
			self.add_link(result, 'udm/relation/tree', self.urljoin('../', object_type, 'tree'))

		if module and (module.help_link or module.help_text):
			self.add_link(result, 'help', module.help_link or '', title=module.help_text or module.help_link)

		if module_type == 'navigation':
			modules = udm_modules.modules.keys()
		elif module_type == 'container':
			modules = container_modules()
		else:
			modules = [x['id'] for x in module.child_modules]

		for name in sorted(modules):
			_module = UDM_Module(name, ldap_connection=self.ldap_connection, ldap_position=self.ldap_position)
			# TODO: get rid of entries. all of it can be put into the link!?
			result['entries'].append({
				'id': _module.name,
				'label': _module.title,
				'object_name': _module.object_name,
				'object_name_plural': _module.object_name_plural,
				#'help_link': _module.help_link,
				#'help_text': _module.help_text,
				'columns': _module.columns,  # FIXME: move to Objects?
				#'has_tree': _module.has_tree,
			})
			self.add_link(result, 'udm/relation/object-types', self.urljoin('../%s' % quote(_module.name)) + '/', name=_module.name, title=_module.title)

		self.add_caching(public=True)
		self.content_negotiation(result)


class SubObjectTypes(Ressource):
	"""A list of possible sub-object-types which can be created underneath of the specified container or superordinate."""

	def get(self, object_type=None, position=None):
		"""Returns the list of object types matching the given flavor or container.

		requests.options = {}
			'superordinate' -- if available only types for the given superordinate are returned (not for the navigation)
			'container' -- if available only types suitable for the given container are returned (only for the navigation)
		"""
		if not position:
			# no container is specified, return all existing object types
			return self.module_definition(udm_modules.modules.keys())

		position = unquote_dn(position)

		# create a list of modules that can be created
		# ... all container types except container/dc
		allowed_modules = set([m for m in udm_modules.containers if udm_modules.name(m) != 'container/dc'])

		# the container may be a superordinate or have one as its parent
		# (or grandparent, ....)
		superordinate = udm_modules.find_superordinate(position, None, self.ldap_connection)
		if superordinate:
			# there is a superordinate... add its subtypes to the list of allowed modules
			allowed_modules.update(udm_modules.subordinates(superordinate))
		else:
			# add all types that do not have a superordinate
			allowed_modules.update(mod for mod in udm_modules.modules.values() if not udm_modules.superordinates(mod))

		# make sure that the object type can be created
		allowed_modules = [mod for mod in allowed_modules if udm_modules.supports(mod, 'add')]

		return self.module_definition(allowed_modules)

	def module_definition(self, modules):
		result = {'entries': []}
		for name in modules:
			_module = UDM_Module(name, ldap_connection=self.ldap_connection, ldap_position=self.ldap_position)
			result['entries'].append({
				'id': _module.name,
				'label': _module.title,
				#'object_name': _module.object_name,
				#'object_name_plural': _module.object_name_plural,
				#'help_link': _module.help_link,
				#'help_text': _module.help_text,
				#'columns': _module.columns,
				#'has_tree': _module.has_tree,
			})
			self.add_link(result, 'udm/relation/object-types', self.abspath(_module.name) + '/', name=_module.name, title=_module.title)
		self.add_caching(public=True)
		self.content_negotiation(result)


class LdapBase(Ressource):

	def get(self):
		result = {}
		url = self.abspath('container/dc', quote_dn(ucr['ldap/base']))
		self.add_link(result, '', url)
		self.set_header('Location', url)
		self.set_status(301)
		self.add_caching(public=True)
		self.content_negotiation(result)


class ObjectLink(Ressource):
	"""If the object-type is not known but only the DN, this resource redirects to the correct object."""

	def get(self, dn):
		dn = unquote_dn(dn)
		attrs = self.ldap_connection.get(dn)
		modules = udm_modules.objectType(None, self.ldap_connection, dn, attrs) or []
		if not modules:
			raise NotFound(None, dn)
		for module in modules:
			module = UDM_Module(module, ldap_connection=self.ldap_connection, ldap_position=self.ldap_position)
			if module.module:
				break
		url = self.abspath(module.name, quote_dn(dn))
		self.set_header('Location', url)
		self.set_status(301)
		self.add_caching(public=True)
		self.content_negotiation({})


class ObjectByUiid(ObjectLink):

	def get(self, uuid):
		try:
			dn = self.ldap_connection.searchDn(filter_format('entryUUID=%s', [uuid]))[0]
		except IndexError:
			raise NotFound()
		return super(ObjectByUiid, self).get(dn)


class ContainerQueryBase(Ressource):

	@tornado.gen.coroutine
	def _container_query(self, object_type, container, modules, scope):
		"""Get a list of containers or child objects of the specified container."""

		if not container:
			container = ucr['ldap/base']
			defaults = {}
			if object_type != 'navigation':
				defaults['$operations$'] = ['search', ],  # disallow edit
			if object_type in ('dns/dns', 'dhcp/dhcp'):
				defaults.update({
					'label': UDM_Module(object_type, ldap_connection=self.ldap_connection, ldap_position=self.ldap_position).title,
					'icon': 'udm-%s' % (object_type.replace('/', '-'),),
				})
			self.add_link({}, 'next', self.urljoin('?container=%s' % (quote(container))))
			raise tornado.gen.Return([dict({
				'id': container,
				'label': ldap_dn2path(container),
				'icon': 'udm-container-dc',
				'path': ldap_dn2path(container),
				'objectType': 'container/dc',
				'$operations$': UDM_Module('container/dc', ldap_connection=self.ldap_connection, ldap_position=self.ldap_position).operations,
				'$flags$': [],
				'$childs$': True,
				'$isSuperordinate$': False,
			}, **defaults)])

		result = []
		for xmodule in modules:
			xmodule = UDM_Module(xmodule, ldap_connection=self.ldap_connection, ldap_position=self.ldap_position)
			superordinate = univention.admin.objects.get_superordinate(xmodule.module, None, self.ldap_connection, container)  # TODO: should also better be in a thread
			try:
				ucr['directory/manager/web/sizelimit'] = ucr.get('ldap/sizelimit', '400000')
				items = yield self.pool.submit(xmodule.search, container, scope=scope, superordinate=superordinate)
				for item in items:
					module = UDM_Module(item.module, ldap_connection=self.ldap_connection, ldap_position=self.ldap_position)
					result.append({
						'id': item.dn,
						'label': item[module.identifies],
						'icon': 'udm-%s' % (module.name.replace('/', '-')),
						'path': ldap_dn2path(item.dn),
						'objectType': module.name,
						'$operations$': module.operations,
						'$flags$': item.oldattr.get('univentionObjectFlag', []),
						'$childs$': module.childs,
						'$isSuperordinate$': udm_modules.isSuperordinate(module.module),
					})
			except UDM_Error as exc:
				raise HTTPError(400, None, str(exc))

		raise tornado.gen.Return(result)


class Tree(ContainerQueryBase):
	"""GET udm/(dns/dns|dhcp/dhcp|)/tree/ (the tree content of navigation/DNS/DHCP)"""

	@sanitize_query_string(
		container=DNSanitizer(default=None)
	)
	@tornado.gen.coroutine
	def get(self, object_type):
		ldap_base = ucr['ldap/base']
		container = self.request.query_arguments['container']

		modules = container_modules()
		scope = 'one'
		if not container:
			# get the tree root == the ldap base
			scope = 'base'
		elif object_type != 'navigation' and container and ldap_base.lower() == container.lower():
			# this is the tree root of DNS / DHCP, show all zones / services
			scope = 'sub'
			modules = [object_type]

		containers = yield self._container_query(object_type, container, modules, scope)
		self.add_caching(public=False)
		self.content_negotiation(containers)


class MoveDestinations(ContainerQueryBase):

	@sanitize_query_string(
		container=DNSanitizer(default=None)
	)
	@tornado.gen.coroutine
	def get(self, object_type):
		scope = 'one'
		modules = container_modules()
		container = self.request.query_arguments['container']
		if not container:
			scope = 'base'

		containers = yield self._container_query(object_type, container, modules, scope)
		self.add_caching(public=False)
		self.content_negotiation(containers)


class Properties(Ressource):
	"""GET udm/users/user/properties (get properties of users/user object type)"""

	def get(self, object_type, dn=None):  # TODO: add link to DefaultValue
		result = {}
		if dn:
			dn = unquote_dn(dn)
		module = self.get_module(object_type)
		module.load(force_reload=True)  # reload for instant extended attributes

		self.add_link(result, 'up', self.urljoin('.'))
		properties = module.get_properties(dn)
		searchable = self.get_query_argument('searchable', False)
		if searchable:
			properties = [prop for prop in properties if prop.get('searchable', False)]
		result['properties'] = properties

		self.add_caching(public=True)
		self.content_negotiation(result)


class ReportingBase(Ressource):

	def initialize(self):
		self.reports_cfg = udr.Config()


class Report(ReportingBase):
	"""GET udm/users/user/report/$report_type?dn=...&dn=... (create a report of users)"""

	# i18n: translation for univention-directory-reports
	_('PDF Document')
	_('CSV Report')

	@tornado.gen.coroutine
	def get(self, object_type, report_type):
		dns = self.get_query_arguments('dn')
		yield self.create_report(object_type, report_type, dns)

	@tornado.gen.coroutine
	def post(self, object_type, report_type):
		dns = self.get_body_arguments('dn')
		yield self.create_report(object_type, report_type, dns)

	@tornado.gen.coroutine
	def create_report(self, object_type, report_type, dns):
		try:
			report_type in self.reports_cfg.get_report_names(object_type)
		except KeyError:
			raise NotFound(report_type)

		report = udr.Report(self.ldap_connection)
		try:
			report_file = yield self.pool.submit(report.create, object_type, report_type, dns)
		except udr.ReportError as exc:
			raise HTTPError(400, None, str(exc))

		with open(report_file) as fd:
			self.set_header('Content-Type', 'text/csv' if report_file.endswith('.csv') else 'application/pdf')
			self.set_header('Content-Disposition', 'attachment; filename="%s"' % (os.path.basename(report_file).replace('\\', '\\\\').replace('"', '\\"')))
			self.finish(fd.read())
		os.remove(report_file)


class NextFreeIpAddress(Ressource):
	"""GET udm/networks/network/$DN/next-free-ip-address (get the next free IP in this network)"""

	def get(self, dn):  # TODO: threaded?! (might have caused something in the past in system setup?!)
		"""Returns the next IP configuration based on the given network object

		requests.options = {}
			'networkDN' -- the LDAP DN of the network object
			'increaseCounter' -- if given and set to True, network object counter for IP addresses is increased

		return: {}
		"""
		dn = unquote_dn(dn)
		obj = self.get_object('networks/network', dn)
		try:
			obj.refreshNextIp()
		except udm_errors.nextFreeIp:
			raise NoIpLeft(dn)

		result = {
			'ip': obj['nextIp'],
			'dnsEntryZoneForward': obj['dnsEntryZoneForward'],
			'dhcpEntryZone': obj['dhcpEntryZone'],
			'dnsEntryZoneReverse': obj['dnsEntryZoneReverse']
		}

		self.add_caching(public=False)
		self.content_negotiation(result)

		if self.get_query_argument('increaseCounter', False):
			# increase the next free IP address
			obj.stepIp()
			obj.modify()


class DefaultValue(Ressource):
	"""GET udm/users/user/properties/$property/default (get the default value for the specified property)
	Returns the default search pattern/value for the given object property"""

	def get(self, object_type, property_):
		module = self.get_module(object_type)
		result = module.get_default_values(property_)
		self.add_caching(public=False)
		self.content_negotiation(result)


class Objects(ReportingBase):

	@tornado.gen.coroutine
	def get(self, object_type):
		"""GET udm/users/user/ (nach Benutzern suchen)"""
		module = self.get_module(object_type)
		result = self._options(object_type)

		# TODO: allow to specify an own ldap filter?
		# TODO: add "opened" instead of giving property names?
		# TODO: rename fields in the response into "printable"?

		search = bool(self.request.query)
		container = self.request.query_arguments['position']
		objectProperty = self.request.query_arguments['property']
		objectPropertyValue = self.request.query_arguments['propertyvalue']
		scope = self.request.query_arguments['scope']
		hidden = self.request.query_arguments['hidden']
		fields = self.request.query_arguments['fields']
		fields = (set(fields) | set([objectProperty])) - set(['name', 'None', None, ''])
		properties = self.request.query_arguments['properties'][:]
		direction = self.request.query_arguments['dir']
		reverse = direction == 'DESC'
		by = self.request.query_arguments['by']
		page = self.request.query_arguments['page']
		items_per_page = self.request.query_arguments['pagesize']  # TODO: rename: items-per-page, pagelength, pagecount, pagesize

		# TODO: replace the superordinate concept with container
		superordinate = None
		if module.superordinate_names:
			superordinate = self.request.query_arguments['superordinate']
		if superordinate:
			mod = get_module(superordinate, superordinate, self.ldap_connection)
			if not mod:
				raise SuperordinateDoesNotExist(superordinate)
			superordinate = mod.get(superordinate)
			container = container or superordinate.dn

		entries = []
		objects = []
		if search:
			objects, last_page = yield self.search(module, container, objectProperty, objectPropertyValue, superordinate, scope, hidden, items_per_page, page, by, reverse)

		for obj in objects or []:
			if obj is None:
				continue
			module = get_module(object_type, obj.dn, self.ldap_connection)
			if module is None:
				# This happens when concurrent a object is removed between the module.search() and get_module() call
				# MODULE.warn('LDAP object does not exists %s (flavor: %s). The object is ignored.' % (obj.dn, request.flavor))
				continue

			entry = Object.get_representation(module, obj, properties, self.ldap_connection)
			entry.update({
				#'$childs$': module.childs,
				'name': module.obj_description(obj),
				'path': ldap_dn2path(obj.dn, include_rdn=False),
				'uri': self.urljoin(quote_dn(obj.dn)),
				'fields': {},  # TODO: wrap via encode_properties() instead of module.property_description() ?!
			})
			if '$value$' in fields:
				entry['$value$'] = [module.property_description(obj, column['name']) for column in module.columns]
			if '*' in fields or '*' in properties:
				obj.open()
				fields = set(obj.info.keys())
			for field in fields - set(module.password_properties) - set(entry.keys()):
				entry['fields'][field] = module.property_description(obj, field)
			entries.append(entry)

		if items_per_page:
			self.add_link(result, 'first', self.urljoin('', page='1'), title=_('First page'))
			if page > 1:
				self.add_link(result, 'prev', self.urljoin('', page=str(page - 1)), title=_('Previous page'))
			if not last_page:
				self.add_link(result, 'next', self.urljoin('', page=str(page + 1)), title=_('Next page'))
			else:
				self.add_link(result, 'last', self.urljoin('', page=str(last_page)), title=_('Last page'))

		for i, report_type in enumerate(sorted(self.reports_cfg.get_report_names(object_type)), 1):
			form = self.add_form(result, self.urljoin('report', quote(report_type)), 'POST', rel='udm/relation/report', name=report_type, id='report%d' % (i,))
			self.add_form_element(form, '', _('Create %s report') % _(report_type), type='submit')

		form = self.add_form(result, self.urljoin('multi-edit'), 'POST', name='multi-edit', rel='edit-form')
		self.add_form_element(form, '', _('Modify %s (multi edit)') % (module.object_name_plural,), type='submit')

		form = self.add_form(result, self.urljoin('move'), 'POST', name='move', rel='udm/relation/object/move')
		self.add_form_element(form, 'position', '')
		self.add_form_element(form, '', _('Move %s') % (module.object_name_plural,), type='submit')

		form = self.add_form(result, self.urljoin(''), 'GET', rel='search')
		self.add_form_element(form, 'position', container or '')
		if module.superordinate_names:
			self.add_form_element(form, 'superordinate', superordinate or '')
		self.add_form_element(form, 'property', objectProperty or '', element='select', options=[{'value': '', 'label': _('Defaults')}] + [{'value': prop['id'], 'label': prop['label']} for prop in module.properties(None) if prop.get('searchable')])
		self.add_form_element(form, 'propertyvalue', objectPropertyValue or (module.get_default_values(objectProperty) if objectProperty else '*'))
		self.add_form_element(form, 'scope', scope, element='select', options=[{'value': 'sub'}, {'value': 'one'}, {'value': 'base'}, {'value': 'base+one'}])
		self.add_form_element(form, 'hidden', '1', type='checkbox', checked=bool(hidden))
		#self.add_form_element(form, 'fields', list(fields))
		self.add_form_element(form, 'page', str(page or '1'), type='number')
		self.add_form_element(form, 'pagesize', str(items_per_page or '0'), type='number')
		self.add_form_element(form, 'by', by or '')
		self.add_form_element(form, 'dir', direction if direction in ('ASC', 'DESC') else 'ASC', element='select', options=[{'value': 'ASC', 'label': _('Ascending')}, {'value': 'DESC', 'label': _('Descending')}])
		self.add_form_element(form, '', _('Search'), type='submit')

		result['entries'] = entries  # TODO: is "entries" a good name? items, objects
		self.add_caching(public=False)
		self.content_negotiation(result)

	@tornado.gen.coroutine
	def search(self, module, container, prop, value, superordinate, scope, hidden, items_per_page, page, by, reverse):
		ctrls = {}
		serverctrls = []
		hashed = (self.request.user_dn, module.name, container or None, prop or None, value or None, superordinate or None, scope or None, hidden or None, items_per_page or None, by or None, reverse or None)
		session = self.search_sessions.get(hashed, {})
		last_cookie = session.get('last_cookie', '')
		current_page = session.get('page', 0)
		page_ctrl = SimplePagedResultsControl(True, size=items_per_page, cookie=last_cookie)  # TODO: replace with VirtualListViewRequest
		if module.supports_pagination:
			if items_per_page:
				serverctrls.append(page_ctrl)
			if by in ('uid', 'uidNumber', 'cn'):
				rule = ':caseIgnoreOrderingMatch' if by not in ('uidNumber',) else ''
				serverctrls.append(SSSRequestControl(ordering_rules=['%s%s%s' % ('-' if reverse else '', by, rule)]))
		objects = []
		# TODO: we have to store the results of the previous pages (or make them cacheable)
		# FIXME: we have to store the session across all processes
		ucr['directory/manager/web/sizelimit'] = ucr.get('ldap/sizelimit', '400000')
		last_page = page
		for i in range(current_page, page or 1):
			objects = yield self.pool.submit(module.search, container, prop or None, value, superordinate, scope=scope, hidden=hidden, serverctrls=serverctrls, response=ctrls)
			for control in ctrls.get('ctrls', []):
				if control.controlType == SimplePagedResultsControl.controlType:
					page_ctrl.cookie = control.cookie
			if not page_ctrl.cookie:
				self.search_sessions.pop(hashed, None)
				break
		else:
			self.search_sessions[hashed] = {'last_cookie': page_ctrl.cookie, 'page': page}
			last_page = 0
		raise tornado.gen.Return((objects, last_page))

	def get_html(self, response):
		if self.request.method in ('GET', 'HEAD'):
			r = response.copy()
			r.pop('errors', None)
			r.pop('entries', None)
			root = super(Objects, self).get_html(r)
		else:
			root = super(Objects, self).get_html(response)
		if self.request.method in ('GET', 'HEAD'):
			for thing in response.get('errors', response.get('entries', [])):
				if isinstance(thing, dict) and thing.get('uri'):
					x = thing.copy()
					a = ET.Element("a", href=x.pop('uri'), rel="udm/relation/object item")
					a.text = x.get('dn')
					pre = ET.Element("pre")
					pre.text = json.dumps(x, indent=4)
					root.append(ET.Element("br"))
					# There is a bug in chrome, so we cannot have form='report1 report2'. so, only 1 report is possible :-/
					root.append(ET.Element('input', type='checkbox', name='dn', value=x['dn'], form=' '.join([report['id'] for report in response['_forms'] if report['rel'] == 'udm/relation/report'][-1:])))
					root.append(a)
					root.append(pre)
					root.append(ET.Element("br"))
				else:
					pre = ET.Element("pre")
					pre.text = json.dumps(thing, indent=4)
					root.append(pre)
					root.append(ET.Element("br"))
		return root

	@sanitize_body_arguments(
		position=DNSanitizer(required=True),
		superordinate=DNSanitizer(required=False, allow_none=True),
		options=DefaultDictSanitizer({}, default_sanitizer=StringSanitizer()),
		policies=DefaultDictSanitizer({}, default_sanitizer=DNSanitizer()),
		properties=DictSanitizer({}),
	)
	@tornado.gen.coroutine
	def post(self, object_type):
		"""POST udm/users/user/ (Benutzer hinzufügen)"""
		module = self.get_module(object_type)
		container = self.get_body_argument('position')
		superordinate = self.get_body_argument('superordinate')
		options = self.get_body_arguments('options')
		policies = self.get_body_arguments('policies')
		properties = self.get_body_arguments('properties')

		ldap_position = univention.admin.uldap.position(self.ldap_position.getBase())
		if container:
			ldap_position.setDn(container)
		elif superordinate:
			ldap_position.setDn(superordinate)
		else:
			if hasattr(module.module, 'policy_position_dn_prefix'):
				container = '%s,cn=policies,%s' % (self.module.policy_position_dn_prefix, ldap_position.getBase())
			else:
				defaults = module.get_default_containers()
				container = defaults[0] if defaults else ldap_position.getBase()

			ldap_position.setDn(container)

		#if superordinate:
		#	mod = get_module(module.name, superordinate, ldap_connection)
		#	if not mod:
		#		MODULE.error('Superordinate module not found: %s' % (superordinate,))
		#		raise SuperordinateDoesNotExist(superordinate)
		#	MODULE.info('Found UDM module for superordinate')
		#	superordinate = mod.get(superordinate)

		obj = module.module.object(None, self.ldap_connection, ldap_position, superordinate=superordinate)
		obj.open()
		obj.options = [opt for opt, enabled in dict(options).items() if enabled]  # TODO: AppAttributes.data_for_module(self.name).iteritems() ?
		obj.policies = reduce(lambda x, y: x + y, policies, [])
		properties = dict((prop, properties[prop]) for prop in dict(obj.items()) if obj.has_property(prop) and prop in properties)  # FIXME: remove prop in properties?!
		properties = dict(encode_properties(module.name, properties, self.ldap_connection))

		try:
			for key, value in dict(properties.items()).items():  # UDM_Error: Value may not change. key=gidNumber old=5086 new=5086
				if not obj.descriptions[key].may_change:
					if obj[key] == value:
						properties.pop(key)

			module._map_properties(obj, properties)
			dn = yield self.pool.submit(obj.create)
		except udm_errors.objectExists:
			raise
		except udm_errors.base as exc:
			UDM_Error(exc).reraise()
		self.set_header('Location', self.urljoin(quote_dn(dn)))
		self.set_status(201)
		self.add_caching(public=False)
		self.content_negotiation({})

	def options(self, object_type):
		result = self._options(object_type)
		self.add_caching(public=False)
		self.content_negotiation(result)

	def _options(self, object_type):
		result = {}
		module = self.get_module(object_type)
		parent = self.get_parent_object_type(module)
		methods = ['GET', 'OPTIONS']
		self.add_link(result, 'udm/relation/object-modules', self.urljoin('../../'), title=_('All modules'))
		self.add_link(result, 'up', self.urljoin('../'), title=parent.object_name_plural)
		self.add_link(result, 'self', self.urljoin(''), title=module.object_name_plural)
		if 'search' in module.operations:
			self.add_link(result, 'search', self.urljoin(''), title=_('Search for %s') % (module.object_name_plural,))
		if 'add' in module.operations:
			methods.append('POST')
			self.add_link(result, 'create-form', self.urljoin('add'), title=_('Create a %s') % (module.object_name,))
		if module.help_link or module.help_text:
			self.add_link(result, 'help', module.help_link or '', title=module.help_text or module.help_link)
		self.add_link(result, 'icon', self.urljoin('favicon.ico'), type='image/x-icon')
		if module.has_tree:
			self.add_link(result, 'udm/relation/tree', self.urljoin('tree'), title=_('Object type tree'))
#		self.add_link(result, '', self.urljoin(''))
		self.set_header('Allow', ', '.join(methods))
		return result


class ObjectsMove(Ressource):

	@sanitize_body_arguments(
		position=DNSanitizer(required=True),
		dn=ListSanitizer(DNSanitizer(required=True)),
	)
	def post(self, object_type):
		# FIXME: this can only move objects of the same object_type but should move everything
		position = self.request.body_arguments['position']
		dns = self.request.body_arguments['dn']  # TODO: validate: moveable, etc.
		queue = Operations.queue.setdefault(self.request.user_dn, {})
		status = {
			'id': str(uuid.uuid4()),
			'finished': False,
			'errors': False,
			'moved': [],
		}
		queue[status['id']] = status
		self.set_status(201)
		self.set_header('Location', self.abspath('progress', status['id']))
		self.finish()
		try:
			for i, dn in enumerate(dns, 1):
				module = get_module(object_type, dn, self.ldap_connection)
				dn = yield self.pool.submit(module.move, dn, position)
				status['moved'].append(dn)
				status['progress'] = _('Moved %d of %d objects. Last object was: %s.') % (i, len(dns), dn)
		except:
			status['errors'] = True
			status['traceback'] = traceback.format_exc()  # FIXME: error handling
			raise
		else:
			status['uri'] = self.urljoin(dn)
		finally:
			status['finished'] = True


class Object(Ressource):

	@tornado.gen.coroutine
	def get(self, object_type, dn):
		"""GET udm/users/user/$DN (get all properties/values of the user)"""
		dn = unquote_dn(dn)
		props = {}
		copy = bool(self.get_query_argument('copy', None))  # TODO: move into own ressource: ./copy

		if object_type == 'users/self' and not self.ldap_connection.compare_dn(dn, self.request.user_dn):
			raise HTTPError(403)

		module = get_module(object_type, dn, self.ldap_connection)
		if module is None:
			raise NotFound(object_type, dn)

		obj = yield self.pool.submit(module.get, dn)
		if not obj:
			raise NotFound(object_type, dn)
		if object_type not in ('users/self', 'users/passwd') and not univention.admin.modules.recognize(object_type, obj.dn, obj.oldattr):
			raise NotFound(object_type, dn)

		self.add_link(props, 'udm/relation/object-modules', self.urljoin('../../'), title=_('All modules'))
		self.add_link(props, 'udm/relation/object-module', self.urljoin('../'), title=self.get_parent_object_type(module).object_name_plural)
		#self.add_link(props, 'udm/relation/object-types', self.urljoin('../'))
		self.add_link(props, 'up', self.urljoin('x/../'), name=module.name, title=module.object_name)
		self.add_link(props, 'self', self.urljoin(''), title=obj.dn)
		self.add_link(props, 'icon', self.urljoin('favicon.ico'), type='image/x-icon')
		self.add_link(props, 'udm/relation/object/remove', self.urljoin(''), method='DELETE')
		self.add_link(props, 'udm/relation/object/edit', self.urljoin(''), method='PUT')
#		for mod in module.child_modules:
#			mod = self.get_module(mod['id'])
#			if mod and set(mod.superordinate_names) & {module.name, }:
#				self.add_link(props, 'udm/relation/children-types', self.urljoin('../../%s/?superordinate=%s' % (quote(mod.name), quote(obj.dn))), name=mod.name, title=mod.object_name_plural)
		if module.childs:
			self.add_link(props, 'udm/relation/children-types', self.urljoin(quote(obj.dn), 'children-types/'), name=module.name, title=_('Sub object types of %s') % (module.object_name,))

		props['uri'] = self.urljoin(quote_dn(obj.dn))
		props.update(self.get_representation(module, obj, ['*'], self.ldap_connection, copy))
		if set(module.operations) & {'edit', 'move', 'remove', 'subtree_move'}:
			self.add_link(props, 'edit-form', self.urljoin(quote_dn(obj.dn), 'edit'), title=_('Modify, move or remove this %s' % (module.object_name,)))

		if module.name == 'networks/network':
			self.add_link(props, 'udm/relation/next-free-ip', self.urljoin(quote_dn(obj.dn), 'next-free-ip-address'), title=_('Next free IP address'))

		if obj.has_property('jpegPhoto'):
			self.add_link(props, 'udm/relation/user-photo', self.urljoin(quote_dn(obj.dn), 'properties/photo.jpg'), type='image/jpeg', title=_('User photo'))

	def set_metadata(self, obj):  # FIXME: move into UDM core!
		obj.oldattr.update(self.ldap_connection.get(obj.dn, attr=[b'+']))

	def set_entity_tags(self, obj):
		self.set_header('Etag', self.get_etag(obj))
		self.set_header('Last-Modified', last_modified(time.strptime(obj.oldattr['modifyTimestamp'][0].decode('utf-8', 'replace'), '%Y%m%d%H%M%SZ')))
		self.check_conditional_requests()

	def get_etag(self, obj):
		# generate as early as possible, to not cause side effects e.g. default values in obj.info. It must be the same value for GET and PUT
		if not obj._open:
			raise RuntimeError('Object was not opened!')
		etag = hashlib.sha1()
		etag.update(obj.dn.encode('utf-8', 'replace'))
		etag.update(obj.module.encode('utf-8', 'replace'))
		etag.update(b''.join(obj.oldattr.get('entryCSN', [])))
		etag.update(b''.join(obj.oldattr.get('entryUUID', [])))
		etag.update(json.dumps(obj.info, sort_keys=True).encode('utf-8'))
		return u'"%s"' % etag.hexdigest()

	@classmethod
	def get_representation(cls, module, obj, properties, ldap_connection, copy=False):
		def _remove_uncopyable_properties(obj):
			if not copy:
				return
			for name, p in obj.descriptions.items():
				if not p.copyable:
					obj.info.pop(name, None)

		# TODO: check if we really want to set the default values
		_remove_uncopyable_properties(obj)
		obj.set_defaults = True
		obj.set_default_values()
		_remove_uncopyable_properties(obj)
		values = {}
		if properties:
			values = obj.info.copy()
			for passwd in module.password_properties:
				values.pop(passwd, None)
			if '*' not in properties:
				for key in list(values.keys()):
					if key not in properties:
						values.pop(key)
			values = dict(decode_properties(module.name, values, ldap_connection))

		for key, value in list(values.items()):
			syntax = module.get_property(key).syntax
			if inspect.isclass(syntax):
				syntax = syntax()
			if isinstance(syntax, (udm_syntax.OkOrNot, udm_syntax.TrueFalseUp, udm_syntax.boolean)):
				if syntax.parse(True) == value:
					values[key] = True
				elif syntax.parse(False) == value:
					values[key] = False

		props = {}
		props['dn'] = obj.dn
		props['objectType'] = module.name
		props['id'] = '+'.join(explode_rdn(obj.dn, True))
		if module.superordinate_names:
			props['superordinate'] = obj.superordinate and obj.superordinate.dn
		props['position'] = ldap_connection.parentDn(obj.dn)
		props['properties'] = values
		props['options'] = dict((opt['id'], opt['value']) for opt in module.get_options(udm_object=obj))
		props['policies'] = {}
		if '*' in properties:
			for policy in obj.policies:
				pol_mod = get_module(None, policy, ldap_connection)
				if pol_mod and pol_mod.name:
					props['policies'].setdefault(pol_mod.name, []).append(policy)
			props['references'] = module.get_references(obj.dn)
		#props['$labelObjectType$'] = module.title
		#props['$labelObjectTypeSingular$'] = module.object_name
		#props['$labelObjectTypePlural$'] = module.object_name_plural
		props['flags'] = obj.oldattr.get('univentionObjectFlag', [])
		#props['$operations$'] = module.operations
		if copy:
			props.pop('dn')
		return props

	@sanitize_body_arguments(
		position=DNSanitizer(required=True),
		superordinate=DNSanitizer(required=False, allow_none=True),
		options=DefaultDictSanitizer({}, default_sanitizer=BooleanSanitizer()),
		policies=DefaultDictSanitizer({}, default_sanitizer=DNSanitizer()),
		properties=DictSanitizer({}),
	)
	@tornado.gen.coroutine
	def put(self, object_type, dn):
		"""PUT udm/users/user/$DN (Benutzer hinzufügen / modifizieren)"""
		dn = unquote_dn(dn)
		module = get_module(object_type, dn, self.ldap_connection)
		if not module:
			raise NotFound(object_type)  # FIXME: create

		position = self.get_body_arguments('position')
		if position and not self.ldap_connection.compare_dn(self.ldap_connection.parentDn(dn), position):
			yield self.move(module, dn, position)
			return
		else:
			obj = yield self.modify(module, None, dn)
			self.set_status(302)
			self.set_header('Location', self.urljoin(quote_dn(obj.dn)))

		self.add_caching(public=False)
		self.content_negotiation({})

	@sanitize_body_arguments(
		position=DNSanitizer(required=True),
		superordinate=DNSanitizer(required=False, allow_none=True),
		options=DefaultDictSanitizer({}, default_sanitizer=BooleanSanitizer(), required=True),
		policies=DefaultDictSanitizer({}, default_sanitizer=DNSanitizer(), required=True),
		properties=DictSanitizer({}),
	)
	@tornado.gen.coroutine
	def patch(self, object_type, dn):
		dn = unquote_dn(dn)
		module = get_module(object_type, dn, self.ldap_connection)
		if not module:
			raise NotFound(object_type)
		yield self.modify(module, self.request.body_arguments, dn)
		self.add_caching(public=False)
		self.content_negotiation({})

	@tornado.gen.coroutine
	def modify(self, module, properties, dn):
		obj = module.module.object(None, self.ldap_connection, self.ldap_position, dn)
		obj.open()
		obj.options = [opt for opt, enabled in dict(self.get_body_arguments('options')).items() if enabled]
		obj.policies = reduce(lambda x, y: x + y, self.get_body_arguments('policies'), [])
		if properties is None:
			properties = self.get_body_arguments('properties')
			properties = dict((prop, properties[prop]) for prop in dict(obj.items()) if obj.has_property(prop) and prop in properties)  # FIXME: remove prop in properties?!

		properties = dict(encode_properties(module.name, properties, self.ldap_connection))

		validation = yield self._validate(module, properties)
		if not all(x['valid'] if isinstance(x['valid'], bool) else all(x['valid']) for x in validation):
			raise HTTPError(422)

		try:
			for key, value in dict(properties.items()).items():  # UDM_Error: Value may not change. key=gidNumber old=5086 new=5086
				if not obj.descriptions[key].may_change:
					if obj[key] == value:
						properties.pop(key)

			module._map_properties(obj, properties)
			yield self.pool.submit(obj.modify)
		except udm_errors.base as exc:
			UDM_Error(exc).reraise()
		else:
			raise tornado.gen.Return(obj)

	@tornado.gen.coroutine
	def move(self, module, dn, position):
		queue = Operations.queue.setdefault(self.request.user_dn, {})
		status = {
			'id': str(uuid.uuid4()),
			'finished': False,
			'errors': False,
		}
		queue[status['id']] = status
		self.set_status(201)
		self.set_header('Location', self.abspath('progress', status['id']))
		self.add_caching(public=False)
		self.content_negotiation(status)
		try:
			dn = yield self.pool.submit(module.move, dn, position)
		except:
			status['errors'] = True
			status['traceback'] = traceback.format_exc()  # FIXME: error handling
			raise
		else:
			status['uri'] = self.urljoin(dn)
		finally:
			status['finished'] = True

	@sanitize_query_string(
		cleanup=BoolSanitizer(default=False),
		recursive=BoolSanitizer(default=False),
	)
	@tornado.gen.coroutine
	def delete(self, object_type, dn):
		"""DELETE udm/users/user/$DN (Benutzer löschen)"""
		dn = unquote_dn(dn)
		module = get_module(object_type, dn, self.ldap_connection)
		if not module:
			raise NotFound(object_type)

		cleanup = bool(self.request.query_arguments['cleanup'])
		recursive = bool(self.request.query_arguments['recursive'])
		yield self.pool.submit(module.remove, dn, cleanup, recursive)
		self.add_caching(public=False)
		self.content_negotiation({})

	def check_conditional_requests(self):
		last_modified = parsedate(self._headers.get('Last-Modified', ''))
		if last_modified is not None:
			last_modified = datetime.datetime(*last_modified[:6])
			date = parsedate(self.request.headers.get('If-Modified-Since', ''))
			if date is not None:
				if_since = datetime.datetime(*date[:6])
				if if_since >= last_modified:
					self.set_status(304)
					raise Finish()

			date = parsedate(self.request.headers.get('If-Unmodified-Since', ''))
			if date is not None:
				if_not_since = datetime.datetime(*date[:6])
				if last_modified > if_not_since:
					raise HTTPError(412, _('If-Unmodified-Since does not match Last-Modified.'))

		etag = self._headers.get("Etag", "")
		if not etag:
			return

		def wheak(x):
			return x[2:] if x.startswith(b'W/') else x
		etag_matches = re.compile(r'\*|(?:W/)?"[^"]*"')
		etags = etag_matches.findall(self.request.headers.get("If-None-Match", ""))
		if not etags:
			return
		if '*' in etags or wheak(etag) in map(wheak, etags):
			self.set_status(304)  # Not modified
			raise Finish()
		etags = etag_matches.findall(self.request.headers.get("If-Match", ""))
		if wheak(etag) not in map(wheak, etags):
			raise HTTPError(412, _('If-Match %s does not match entity tag(s) %s.') % (etag, ', '.join(etags)))  # precondition failed


class UserPhoto(Ressource):

	@tornado.gen.coroutine
	def get(self, object_type, dn):
		dn = unquote_dn(dn)
		module = get_module(object_type, dn, self.ldap_connection)
		if module is None:
			raise NotFound(object_type, dn)

		obj = yield self.pool.submit(module.get, dn)
		if not obj:
			raise NotFound(object_type, dn)

		if not obj.has_property('jpegPhoto'):
			raise NotFound(object_type, dn)

		data = obj.info.get('jpegPhoto', '').decode('base64')
		self.add_header('Last-Modified', last_modified(time.strptime(self.ldap_connection.getAttr(obj.dn, b'modifyTimestamp')[0].decode('utf-8'), '%Y%m%d%H%M%SZ')))
		self.set_header('Content-Type', 'image/jpeg')
		self.add_caching(public=False, max_age=2592000)
		self.finish(data)

	@tornado.gen.coroutine
	def post(self, object_type, dn):
		dn = unquote_dn(dn)
		module = get_module(object_type, dn, self.ldap_connection)
		if module is None:
			raise NotFound(object_type, dn)

		obj = yield self.pool.submit(module.get, dn)
		if not obj:
			raise NotFound(object_type, dn)

		if not obj.has_property('jpegPhoto'):
			raise NotFound(object_type, dn)

		photo = self.request.files['jpegPhoto'][0]['body']
		if len(photo) > 262144:
			raise HTTPError('too large: maximum: 262144 bytes')
		obj['jpegPhoto'] = photo.encode('base64')

		yield self.pool.submit(obj.modify)

		self.content_negotiation({})


class ObjectAdd(Ressource):
	"""GET a form containing information about all properties, methods, URLs to create a specific object"""

	@tornado.gen.coroutine
	def get(self, object_type):
		result = {}
		module = self.get_module(object_type)
		if 'add' not in module.operations:
			raise NotFound(object_type)

		self.add_link(result, 'icon', self.urljoin('favicon.ico'), type='image/x-icon')
		self.add_link(result, 'udm/relation/object-modules', self.urljoin('../../'), title=_('All modules'))
		self.add_link(result, 'udm/relation/object-module', self.urljoin('../'), title=self.get_parent_object_type(module).object_name_plural)
		self.add_link(result, 'udm/relation/object-type', self.urljoin('.'), title=module.object_name)
		self.add_link(result, 'self', self.urljoin(''), title=_('Add'))

		module.load(force_reload=True)  # reload for instant extended attributes
		result['layout'] = module.get_layout()
		result['properties'] = module.get_properties()
		meta_layout = {'layout': ['position', 'template', 'options'], 'advanced': False, 'description': _('Meta information'), 'label': _('Meta information'), 'is_app_tab': False}
		result['layout'].insert(0, meta_layout)

		for policy in module.policies:
			form = self.add_form(result, action=self.urljoin(policy['objectType']) + '/', method='GET', name=policy['objectType'], rel='udm/relation/policy-result')
			self.add_form_element(form, 'position', '', label=_('The container where the object is going to be created in'))
			self.add_form_element(form, 'policy', '', label=policy['label'], title=policy['description'])  # TODO: value should be the currently set policy!
			self.add_form_element(form, '', _('Policy result'), type='submit')

		obj = module.module.object(None, self.ldap_connection, self.ldap_position)
		obj.open()
		result['entry'] = Object.get_representation(module, obj, ['*'], self.ldap_connection)

		form = self.add_form(result, action=self.urljoin('.'), method='POST', layout=True)
		self.add_form_element(form, 'position', '', element='select', options=sorted(({'value': x, 'label': ldap_dn2path(x)} for x in module.get_default_containers()), key=lambda x: x['label'].lower()))
		if module.template:
			template = UDM_Module(module.template, ldap_connection=self.ldap_connection, ldap_position=self.ldap_position)
			templates = template.search(ucr.get('ldap/base'))
			self.add_form_element(form, 'template', '', element='select', options=[{'value': _obj.dn, 'label': _obj[template.identifies]} for _obj in templates])
		if module.superordinate_names:
			meta_layout['layout'].append('superordinate')
			self.add_form_element(form, 'superordinate', '')  # TODO: replace with <select>

		# FIXME: respect layout
		for prop in result['properties']:
			if prop['id'] in ('$dn$',):
				continue
			elif prop['id'] == '$options$':
				self.add_form_element(form, 'options', [opt['id'] for opt in prop['widgets'] if opt['value']], element='select', multiple='multiple', options=[{'value': opt['id'], 'label': opt['label']} for opt in prop['widgets']])
				continue
			self.add_form_element(form, 'properties[%s]' % prop['id'], '', label=prop.get('label', prop['id']), placeholder=prop.get('label', prop['id']), title=prop.get('description', ''))

		result['layout'].append({'layout': [], 'advanced': False, 'description': _('Policies'), 'label': _('Policies'), 'is_app_tab': False})
		for policy in module.policies:
			result['layout'][-1]['layout'].append('policies[%s]' % (policy['objectType'],))
			self.add_form_element(form, 'policies[%s]' % (policy['objectType']), 'FIXME', label=policy['label'])  # FIXME: value should be the currently set policy

		meta_layout['layout'].append('')
		self.add_form_element(form, '', _('Create %s') % (module.object_name,), type='submit')

		# TODO: wizard: first select position & template
		self.add_caching(public=True)
		self.content_negotiation(result)


class ObjectEdit(Ressource):
	"""GET a form containing ways to modify, remove, move a specific object"""

	@tornado.gen.coroutine
	def get(self, object_type, dn):
		dn = unquote_dn(dn)
		module = get_module(object_type, dn, self.ldap_connection)
		if module is None:
			raise NotFound(object_type, dn)

		if not set(module.operations) & {'remove', 'move', 'subtree_move', 'edit'}:
			# modification of this object type is not possible
			raise NotFound(object_type, dn)

		result = {}
		module.load(force_reload=True)  # reload for instant extended attributes

		obj = yield self.pool.submit(module.get, dn)
		if not obj:
			raise NotFound(object_type, dn)

		if object_type not in ('users/self', 'users/passwd') and not univention.admin.modules.recognize(object_type, obj.dn, obj.oldattr):
			raise NotFound(object_type, dn)

		self.add_link(result, 'icon', self.urljoin('../favicon.ico'), type='image/x-icon')
		self.add_link(result, 'udm/relation/object-modules', self.urljoin('../../../'), title=_('All modules'))
		self.add_link(result, 'udm/relation/object-module', self.urljoin('../../'), title=self.get_parent_object_type(module).object_name_plural)
		self.add_link(result, 'udm/relation/object-type', self.urljoin('../'), title=module.object_name)
		self.add_link(result, 'up', self.urljoin('..', quote_dn(obj.dn)), title=obj.dn)
		self.add_link(result, 'self', self.urljoin(''), title=_('Modify'))

		if 'remove' in module.operations:
			# TODO: add referring objects
			form = self.add_form(result, action=self.urljoin('.').rstrip('/'), method='DELETE')
			self.add_form_element(form, 'cleanup', '1', type='checkbox', checked=True)
			self.add_form_element(form, 'recursive', '1', type='checkbox', checked=True)
			self.add_form_element(form, '', _('Remove'), type='submit')

		if set(module.operations) & {'move', 'subtree_move'}:
			form = self.add_form(result, action=self.urljoin('.').rstrip('/'), method='PUT')
			self.add_form_element(form, 'position', self.ldap_connection.parentDn(obj.dn))  # TODO: replace with <select>
			self.add_form_element(form, '', _('Move'), type='submit')

		if 'edit' in module.operations:
			obj.open()
			result['layout'] = module.get_layout(dn if object_type != 'users/self' else None)
			meta_layout = {'layout': ['options', ''], 'advanced': False, 'description': _('Meta information'), 'label': _('Meta information'), 'is_app_tab': False}
			result['layout'].insert(0, meta_layout)
			result['properties'] = module.get_properties(dn)
			result['options'] = module.options.keys()
			result['synced'] = ucr.is_true('ad/member') and 'synced' in obj.oldattr.get('univentionObjectFlag', [])
			if result['synced']:
				result['active_directory_warning'] = _('The %s "%s" is part of the Active Directory domain.') % (module.object_name, obj[module.identifies])
				for prop in result['properties'].values():
					if prop['readonly_when_synced']:
						prop['disabled'] = True

			for policy in module.policies:
				form = self.add_form(result, action=self.urljoin(policy['objectType']) + '/', method='GET', name=policy['objectType'], rel='udm/relation/policy-result')
				self.add_form_element(form, 'policy', '', label=policy['label'], title=policy['description'])  # TODO: value should be the currently set policy!
				self.add_form_element(form, '', _('Policy result'), type='submit')

			if obj.has_property('jpegPhoto'):
				form = self.add_form(result, action=self.urljoin('properties/photo.jpg'), method='POST', enctype='multipart/form-data')
				self.add_form_element(form, 'jpegPhoto', '', type='file', accept='image/jpg')
				self.add_form_element(form, '', _('Upload user photo'), type='submit')

			# FIXME: respect layout
			form = self.add_form(result, action=self.urljoin('.').rstrip('/'), method='PUT', layout=True)
			for prop in result['properties']:
				if prop['id'] == '$options$':
					self.add_form_element(form, 'options', [opt['id'] for opt in prop['widgets'] if opt['value']], element='select', multiple='multiple', options=[{'value': opt['id'], 'label': opt['label']} for opt in prop['widgets']])

			# TODO: iterate over all properties instead of obj.info, add better labels, etc.
			password_properties = module.password_properties
			for prop in result['properties']:
				key = prop['id']
				if key.startswith('$'):
					continue
				value = dict(encode_properties(obj.module, {key: obj[key]}, self.ldap_connection))[key]
				input_type = 'input'
				if key in password_properties:
					value = ''
					input_type = 'password'
				self.add_form_element(form, 'properties[%s]' % (key,), value, label=key, placeholder=key, type=input_type)

			result['layout'].append({'layout': [], 'advanced': False, 'description': _('Policies'), 'label': _('Policies'), 'is_app_tab': False})
			for policy in module.policies:
				result['layout'][-1]['layout'].append('policies[%s]' % (policy['objectType'],))
				self.add_form_element(form, 'policies[%s]' % (policy['objectType']), 'FIXME', label=policy['label'])  # FIXME: value should be the currently set policy
			# TODO: add references

			self.add_form_element(form, '', _('Modify %s') % (module.object_name,), type='submit')

		self.add_caching(public=False)
		self.content_negotiation(result)


class PropertyChoices(Ressource):
	"""GET udm/users/user/$DN/property/$name/choices (get possible values/choices for that property)"""

	@tornado.gen.coroutine
	def get(self, object_type, dn, property_):
		dn = unquote_dn(dn)
		module = self.get_module(object_type)
		try:
			syntax = module.module.property_descriptions[property_].syntax
		except KeyError:
			raise NotFound(object_type, dn)
		request_body = {'syntax': syntax.name}  # FIXME
		choices = yield self.pool.submit(read_syntax_choices, _get_syntax(syntax.name), request_body, ldap_connection=self.ldap_connection, ldap_position=self.ldap_position)
		self.add_caching(public=False)
		self.content_negotiation(choices)


class PolicyResultBase(Ressource):
	"""get the possible policies of the policy-type for user objects located at the containter"""

	@run_on_executor(executor='pool')
	def _get(self, object_type, policy_type, dn, is_container=False):
		"""Returns a virtual policy object containing the values that
		the given object or container inherits"""

		policy_dn = self.request.query_arguments['policy']

		if is_container:
			# editing a new (i.e. non existing) object -> use the parent container
			obj = self.get_object(get_module(None, dn, self.ldap_connection).module, dn)
		else:
			# editing an exiting UDM object -> use the object itself
			obj = self.get_object(object_type, dn)

		if policy_dn:
			policy_obj = self.get_object(policy_type, policy_dn)
		else:
			policy_obj = self.get_module(policy_type).get(None)
		policy_obj.clone(obj)

		# There are 2x2x2 (=8) cases that may occur (c.f., Bug #31916):
		# (1)
		#   [edit] editing existing UDM object
		#   -> the existing UDM object itself is loaded
		#   [new]  virtually edit non-existing UDM object (when a new object is being created)
		#   -> the parent container UDM object is loaded
		# (2)
		#   [w/pol]   UDM object has assigend policies in LDAP directory
		#   [w/o_pol] UDM object has no policies assigend in LDAP directory
		# (3)
		#   [inherit] user request to (virtually) change the policy to 'inherited'
		#   [set_pol] user request to (virtually) assign a particular policy
		faked_policy_reference = None
		if not is_container and not policy_dn:
			# case: [edit; w/pol; inherit]
			# -> current policy is (virtually) overwritten with 'None'
			faked_policy_reference = [None]
		elif is_container and policy_dn:
			# cases:
			# * [new; w/pol; inherit]
			# * [new; w/pol; set_pol]
			# -> old + temporary policy are both (virtually) set at the parent container
			faked_policy_reference = obj.policies + [policy_dn]
		else:
			# cases:
			# * [new; w/o_pol; inherit]
			# * [new; w/o_pol; set_pol]
			# * [edit; w/pol; set_pol]
			# * [edit; w/o_pol; inherit]
			# * [edit; w/o_pol; set_pol]
			faked_policy_reference = [policy_dn]

		policy_obj.policy_result(faked_policy_reference)
		infos = copy.copy(policy_obj.polinfo_more)
		for key, value in infos.items():
			if key in policy_obj.polinfo:
				if isinstance(infos[key], (tuple, list)):
					continue
				infos[key]['value'] = policy_obj.polinfo[key]
		if policy_dn:
			self.add_link(infos, 'udm/relation/policy-edit', self.abspath(policy_obj.module, policy_dn), title=_('Click to edit the inherited properties of the policy'))
		return infos


class PolicyResult(PolicyResultBase):
	"""get the possible policies of the policy-type for user objects located at the containter
	GET udm/users/user/$userdn/policies/$policy_type/?policy=$dn (for a existing object)
	"""

	@sanitize_query_string(
		policy=DNSanitizer(required=False, default=None)
	)
	@tornado.gen.coroutine
	def get(self, object_type, dn, policy_type):
		dn = unquote_dn(dn)
		infos = yield self._get(object_type, policy_type, dn, is_container=False)
		self.add_caching(public=False, no_cache=True, must_revalidate=True, no_store=True)
		self.content_negotiation(infos)


class PolicyResultContainer(PolicyResultBase):
	"""get the possible policies of the policy-type for user objects located at the containter
	GET udm/users/user/policies/$policy_type/?policy=$dn&position=$dn (for a container, where a object should be created in)
	"""

	@sanitize_query_string(
		policy=DNSanitizer(required=False, default=None),
		position=DNSanitizer(required=True)
	)
	@tornado.gen.coroutine
	def get(self, object_type, policy_type):
		container = self.request.query_arguments['position']
		infos = yield self._get(object_type, policy_type, container, is_container=True)
		self.add_caching(public=False, no_cache=True, must_revalidate=True, no_store=True)
		self.content_negotiation(infos)


class Operations(Ressource):
	"""GET /udm/progress/$progress-id (get the progress of a started operation like move, report, maybe add/put?, ...)"""

	queue = {}

	def get(self, progress):
		progressbars = self.queue.get(self.request.user_dn, {})
		if progress not in progressbars:
			raise NotFound()
		result = progressbars[progress]
		if result.get('uri'):
			self.set_status(303)
			self.add_header('Location', result['uri'])
			self.add_link(result, 'self', result['uri'])
			self.queue.get(self.request.user_dn, {}).pop(progress, {})
		else:
			self.set_status(301)
			self.add_header('Location', self.urljoin(''))
			self.add_header('Retry-After', '1')
		self.add_caching(public=False, no_store=True, no_cache=True, must_revalidate=True)
		self.content_negotiation(result)

	def get_html(self, response):
		root = super(Operations, self).get_html(response)
		if isinstance(response, dict):
			if 'value' in response and 'max' in response:
				h1 = ET.Element('h1')
				h1.text = response.get('description', '')
				root.append(h1)
				root.append(ET.Element('progress', value=str(response['value']), max=str(response['max'])))
		return root


class LicenseRequest(Ressource):

	@sanitize_query_string(
		email=EmailSanitizer(required=True),
	)
	@tornado.gen.coroutine
	def get(self):
		data = {
			'email': self.request.query_arguments['email'],
			'licence': dump_license(),
		}
		if not data['licence']:
			raise HTTPError(500, _('Cannot parse License from LDAP'))

		# TODO: we should also send a link (self.request.full_url()) to the license server, so that the email can link to a url which automatically inserts the license:
		# self.request.urljoin('import', license=urllib.quote(zlib.compress(''.join(_[17:] for _ in open('license.ldif', 'rb').readlines() if _.startswith('univentionLicense')), 6)[2:-4].encode('base64').rstrip()))

		data = urllib.urlencode(data)
		url = 'https://license.univention.de/keyid/conversion/submit'
		http_client = tornado.httpclient.HTTPClient()
		try:
			yield http_client.fetch(url, method='POST', body=data, user_agent='UMC/AppCenter', headers={'Content-Type': 'application/x-www-form-urlencoded'})
		except tornado.httpclient.HTTPError as exc:
			error = str(exc)
			if exc.response.code >= 500:
				error = _('This seems to be a problem with the license server. Please try again later.')
			match = re.search('<span id="details">(?P<details>.*?)</span>', exc.response.body, flags=re.DOTALL)
			if match:
				error = match.group(1).replace('\n', '')
			# FIXME: use original error handling
			raise HTTPError(400, _('Could not request a license from Univention: %s') % (error,))

		# creating a new ucr variable to prevent duplicated registration (Bug #35711)
		handler_set(['ucs/web/license/requested=true'])
		self.add_caching(public=False, no_store=True, no_cache=True, must_revalidate=True)
		self.content_negotiation({'message': _('A new license has been requested and sent to your email address.')})


class LicenseCheck(Ressource):

	def get(self):
		message = _('The license is valid.')
		try:
			check_license(self.ldap_connection)
		except LicenseError as exc:
			message = str(exc)
		self.add_caching(public=False, max_age=120)
		self.content_negotiation(message)


class License(Ressource):

	def get(self):
		license_data = {}
		self.add_link(license_data, 'udm/relation/license-check', self.urljoin('check'), title=_('Check license status'))
		self.add_link(license_data, 'udm/relation/license-request', self.urljoin('request'))
		self.add_link(license_data, 'udm/relation/license-import', self.urljoin(''))

		form = self.add_form(license_data, self.urljoin('request'), 'GET', rel='udm/relation/license-request')
		self.add_form_element(form, 'email', '', type='email', label=_('E-Mail address'))
		self.add_form_element(form, '', _('Request new license'), type='submit')

		form = self.add_form(license_data, self.urljoin('import'), 'POST', rel='udm/relation/license-import', enctype='multipart/form-data')
		self.add_form_element(form, 'license', '', type='file', label=_('License file (ldif format)'))
		self.add_form_element(form, '', _('Import license'), type='submit')

		try:
			import univention.admin.license as udm_license
		except:
			license_data['licenseVersion'] = 'gpl'
		else:
			license_data['licenseVersion'] = udm_license._license.version
			if udm_license._license.version == '1':
				for item in ('licenses', 'real'):
					license_data[item] = {}
					for lic_type in ('CLIENT', 'ACCOUNT', 'DESKTOP', 'GROUPWARE'):
						count = getattr(udm_license._license, item)[udm_license._license.version][getattr(udm_license.License, lic_type)]
						if isinstance(count, basestring):
							try:
								count = int(count)
							except:
								count = None
						license_data[item][lic_type.lower()] = count

				if 'UGS' in udm_license._license.types:
					udm_license._license.types = filter(lambda x: x != 'UGS', udm_license._license.types)
			elif udm_license._license.version == '2':
				for item in ('licenses', 'real'):
					license_data[item] = {}
					for lic_type in ('SERVERS', 'USERS', 'MANAGEDCLIENTS', 'CORPORATECLIENTS'):
						count = getattr(udm_license._license, item)[udm_license._license.version][getattr(udm_license.License, lic_type)]
						if isinstance(count, basestring):
							try:
								count = int(count)
							except:
								count = None
						license_data[item][lic_type.lower()] = count
				license_data['keyID'] = udm_license._license.licenseKeyID
				license_data['support'] = udm_license._license.licenseSupport
				license_data['premiumSupport'] = udm_license._license.licensePremiumSupport

			license_data['licenseTypes'] = udm_license._license.types
			license_data['oemProductTypes'] = udm_license._license.oemProductTypes
			license_data['endDate'] = udm_license._license.endDate
			license_data['baseDN'] = udm_license._license.licenseBase
			free_license = ''
			if license_data['baseDN'] == 'Free for personal use edition':
				free_license = 'ffpu'
			if license_data['baseDN'] == 'UCS Core Edition':
				free_license = 'core'
			if free_license:
				license_data['baseDN'] = ucr.get('ldap/base', '')
			license_data['freeLicense'] = free_license
			license_data['sysAccountsFound'] = udm_license._license.sysAccountsFound
		self.add_caching(public=False, max_age=120)
		self.content_negotiation(license_data)


class LicenseImport(Ressource):

	def get(self):
		text = '''dn: cn=admin,cn=license,cn=univention,%(ldap/base)s
cn: admin
objectClass: top
objectClass: univentionLicense
objectClass: univentionObject
univentionObjectType: settings/license
''' % ucr
		for line in zlib.decompress(unquote(license).decode('base64'), -15).splitlines():
			text += 'univentionLicense%s\n' % (line.strip(),)

		self.import_license(io.BytesIO(text))

	def post(self):
		return self.import_license(io.BytesIO(self.request.files['license'][0]['body']))

	def import_license(self, fd):
		try:
				# check license and write it to LDAP
				importer = LicenseImporter(fd)
				importer.check(ucr.get('ldap/base', ''))
				importer.write(self.ldap_connection)
		except ldap.LDAPError as exc:
			# LDAPError e.g. LDIF contained non existing attributes
			raise HTTPError(400, _('Importing the license failed: LDAP error: %s.') % exc.args[0].get('info'))
		except (ValueError, AttributeError) as exc:
			# AttributeError: missing univentionLicenseBaseDN
			# ValueError raised by ldif.LDIFParser when e.g. dn is duplicated
			raise HTTPError(400, _('Importing the license failed: %s.') % (exc,))
		except LicenseError as exc:
			raise HTTPError(400, str(exc))
		self.content_negotiation({'message': _('The license was imported successfully.')})


def decode_properties(object_type, properties, lo, version=1):
	mod = univention.udm.UDM(lo, version).get(object_type)
	mod.connection = lo
	codecs = mod._udm_object_class.udm_prop_class._encoders
	for key, value in properties.items():
		if key in codecs:
			mod_obj = mod._udm_object_class()
			mod_obj._udm_module = mod
			mod_obj._lo = lo
			codec = mod_obj._init_encoder(codecs[key], property_name=key)
			value = codec.decode(value)
			if isinstance(codec, univention.udm.encoders.Base64BinaryPropertyEncoder):  # jpegPhoto
				value = value.encoded
			elif isinstance(value, datetime.date):  # birthday, userexpiry
				value = value.isoformat()
		yield key, value


def encode_properties(object_type, properties, lo, version=1):
	mod = univention.udm.UDM(lo, version).get(object_type)
	mod.connection = lo
	codecs = mod._udm_object_class.udm_prop_class._encoders
	for key, value in properties.items():
		if key in codecs:
			mod_obj = mod._udm_object_class()
			mod_obj._udm_module = mod
			mod_obj._lo = lo
			codec = mod_obj._init_encoder(codecs[key], property_name=key)
			if isinstance(codec, univention.udm.encoders.Base64BinaryPropertyEncoder):  # jpegPhoto
				value = codec.decode(value)
			if inspect.isclass(codec) and issubclass(codec, univention.udm.encoders.DatePropertyEncoder):  # birthday, userexpiry
				value = codec.decode(value)
			value = codec.encode(value)
		yield key, value


def quote_dn(dn):
	if isinstance(dn, unicode):
		dn = dn.encode('utf-8')
	return quote(dn)  # .replace('/', quote('/', safe=''))


def unquote_dn(dn):
	# tornado already decoded it (UTF-8)
	return dn


def last_modified(date):
	return '%s, %02d %s %04d %02d:%02d:%02d GMT' % (
		('Mon', 'Tue', 'Wed', 'Thu', 'Fri', 'Sat', 'Sun')[date.tm_wday],
		date.tm_mday,
		('Jan', 'Feb', 'Mar', 'Apr', 'May', 'Jun', 'Jul', 'Aug', 'Sep', 'Oct', 'Nov', 'Dec')[date.tm_mon - 1],
		date.tm_year, date.tm_hour, date.tm_min, date.tm_sec
	)


class Application(tornado.web.Application):

	def __init__(self, **kwargs):
		#module_type = '([a-z]+)'
		module_type = '(%s)' % '|'.join(re.escape(mod) for mod in Modules.mapping.keys())
		object_type = '([a-z]+/[a-z_]+)'
		policies_object_type = '(policies/[a-z_]+)'
		dn = '((?:[^/]+%s.+,)?%s)' % (self.multi_regex('='), self.multi_regex(ucr['ldap/base']),)
		# FIXME: with that dn regex, it is not possible to have urls like (/udm/$dn/foo/$dn/) because ldap-base at the end matches the last dn
		# Note: the ldap base is part of the url to support "/" as part of the DN. otherwise we can use: '([^/]+(?:=|%3d|%3D)[^/]+)'
		# Note: we cannot use .replace('/', '%2F') for the dn part as url-normalization could replace this and apache doesn't pass URLs with %2F to the ProxyPass without http://httpd.apache.org/docs/current/mod/core.html#allowencodedslashes
		property_ = '([^/]+)'
		super(Application, self).__init__([
			(r"/(?:udm/)?(favicon).ico", Favicon, {"path": "/var/www/favicon.ico"}),
			(r"/udm/(?:index.html)?", Modules),
			(r"/udm/swagger.json", Swagger),
			(r"/udm/relation/(.*)", Relations),
			(r"/udm/license/", License),
			(r"/udm/license/import", LicenseImport),
			(r"/udm/license/check", LicenseCheck),
			(r"/udm/license/request", LicenseRequest),
			(r"/udm/ldap/base/", LdapBase),
			(r"/udm/object/%s" % (dn,), ObjectLink),
			(r"/udm/object/([a-z0-9]{8}-[a-z0-9]{4}-[a-z0-9]{4}-[a-z0-9]{4}-[a-z0-9]{12})", ObjectByUiid),
			(r"/udm/%s/" % (module_type,), ObjectTypes),
			(r"/udm/(navigation)/tree", Tree),
			(r"/udm/(%s|navigation)/move-destinations/" % (object_type,), MoveDestinations),
			(r"/udm/navigation/children-types/", SubObjectTypes),
			(r"/udm/%s/" % (object_type,), Objects),
			(r"/udm/%s/add" % (object_type,), ObjectAdd),
			(r"/udm/%s/move" % (object_type,), ObjectsMove),
			(r"/udm/%s/tree" % (object_type,), Tree),
			(r"/udm/%s/properties" % (object_type,), Properties),
			(r"/udm/%s/favicon.ico" % (object_type,), Favicon, {"path": "/usr/share/univention-management-console-frontend/js/dijit/themes/umc/icons/16x16/"}),
			(r"/udm/%s/%s" % (object_type, dn), Object),
			(r"/udm/%s/%s/edit" % (object_type, dn), ObjectEdit),
			(r"/udm/%s/%s/children-types/" % (object_type, dn), SubObjectTypes),
			(r"/udm/%s/report/([^/]+)" % (object_type,), Report),
			(r"/udm/%s/%s/%s/" % (object_type, dn, policies_object_type), PolicyResult),
			(r"/udm/%s/%s/" % (object_type, policies_object_type), PolicyResultContainer),
			(r"/udm/%s/%s/properties/choices" % (object_type, dn), Properties),
			(r"/udm/%s/%s/properties/%s/choices" % (object_type, dn, property_), PropertyChoices),
			(r"/udm/%s/%s/properties/photo.jpg" % (object_type, dn), UserPhoto),
			(r"/udm/%s/properties/%s/default" % (object_type, property_), DefaultValue),
			(r"/udm/networks/network/%s/next-free-ip-address" % (dn,), NextFreeIpAddress),
			(r"/udm/progress/([a-z0-9]{8}-[a-z0-9]{4}-[a-z0-9]{4}-[a-z0-9]{4}-[a-z0-9]{12})", Operations),
			# TODO: decorator for dn argument, which makes sure no invalid dn syntax is used
		])

	def multi_regex(self, chars):
		# Bug in tornado: requests go against the raw url; https://github.com/tornadoweb/tornado/issues/2548, therefore we must match =, %3d, %3D
		return ''.join('(?:%s|%s|%s)' % (re.escape(c), re.escape(urllib.quote(c).lower()), re.escape(urllib.quote(c).upper())) if c in '=,' else re.escape(c) for c in chars)
