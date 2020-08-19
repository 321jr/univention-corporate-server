#!/usr/bin/python2.7
# -*- coding: utf-8 -*-
#
# Copyright 2020 Univention GmbH
#
# https://www.univention.de/
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
# <https://www.gnu.org/licenses/>.
#

ANYTHING = object()


def assert_called_with(mock, *argss):
	assert mock.call_count == len(argss)
	for call, (args, kwargs) in zip(mock.call_args_list, argss):
		call = call.call_list()
		assert len(call[0][0]) == len(args)
		assert len(call[0][1]) == len(kwargs)
		for call_arg, assert_arg in zip(call[0][0], args):
			if assert_arg is ANYTHING:
				continue
			assert call_arg == assert_arg
		for key, assert_arg in kwargs.items():
			call_arg = call[0][1][key]
			if assert_arg is ANYTHING:
				continue
			assert call_arg == assert_arg


def test_resolve(mocked_ucr, custom_apps, appcenter_umc_instance, umc_request):
	custom_apps.load('unittests/inis/umc/')
	umc_request.options = {'apps': ['riot'], 'action': 'install'}
	appcenter_umc_instance.resolve(umc_request)
	assert 'apps' in umc_request.result
	assert len(umc_request.result['apps']) == 1
	assert umc_request.result['apps'][0]['id'] == 'riot'
	assert 'autoinstalled' in umc_request.result
	assert [] == umc_request.result['autoinstalled']
	assert 'errors' in umc_request.result
	assert isinstance(umc_request.result['errors'], dict)
	assert 'warnings' in umc_request.result
	assert isinstance(umc_request.result['warnings'], dict)


def test_run(mocked_ucr, custom_apps, appcenter_umc_instance, umc_request, mocker):
	custom_apps.load('unittests/inis/umc/')
	localhost = '{hostname}.{domainname}'.format(**mocked_ucr)
	settings = {'riot/default/base_url': '/riot', 'riot/default/server_name': localhost}
	umc_request.options = {'apps': ['riot'], 'action': 'install', 'auto_installed': [], 'hosts': {'riot': localhost}, 'settings': {'riot': settings}, 'dry_run': True}
	mock = mocker.patch.object(appcenter_umc_instance, '_run_local_dry_run')
	mocker.patch.object(appcenter_umc_instance, '_run_local')
	mocker.patch.object(appcenter_umc_instance, '_run_remote_dry_run')
	mocker.patch.object(appcenter_umc_instance, '_run_remote')
	appcenter_umc_instance.run(umc_request)
	umc_request.progress(appcenter_umc_instance.progress)
	assert_called_with(mock, [(custom_apps.find('riot'), 'install', settings), {}])
