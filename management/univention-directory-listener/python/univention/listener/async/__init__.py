# -*- coding: utf-8 -*-
#
# Copyright 2017-2018 Univention GmbH
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
# you and Univention.
#
# This program is provided in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE. See the
# GNU Affero General Public License for more details.
#
# You should have received a copy of the GNU Affero General Public
# License with the Debian GNU/Linux or Univention distribution in file
# /usr/share/common-licenses/AGPL-3; if not, see
# <http://www.gnu.org/licenses/>.


"""
Asynchronous (optionally parallel) listener module API

To create a listener module (LM) with this API, create a Python file in
/usr/lib/univention-directory-listener/system/ which includes:

1. a subclass of AsyncListenerModuleHandler
2. with an inner class "Configuration" that has at least the class attributes
   "name", "description", "ldap_filter" and "run_asynchronously = True"

See /usr/share/doc/univention-directory-listener/examples/ for an example.

Then run:
# service celery-worker-async-listener-modules update-config
# service celery-worker-async-listener-modules start
# service univention-directory-listener restart

When the listener module code changes, restart
celery-worker-async-listener-modules, not
univention-directory-listener.
"""

from __future__ import absolute_import
from univention.listener.async.async_handler import AsyncListenerModuleHandler
from univention.listener.async.async_api_adapter import AsyncListenerModuleAdapter

# This will make sure the app is always imported when a listener module is
# loaded, so that shared_task will use this app:
from univention.listener.async.celery import app as celery_app

__all__ = ['AsyncListenerModuleHandler', 'AsyncListenerModuleAdapter', 'celery_app']
