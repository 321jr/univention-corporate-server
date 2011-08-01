#!/bin/sh
# -*- coding: utf-8 -*-
#
# Univention Lib
#  shell function for creating UMC operation and acl objects
#
# Copyright 2011 Univention GmbH
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

eval "$(ucr shell ldap/base)"

BIND_ARGS="$@"

umc_init () {
	# containers
	udm container/cn create $BIND_ARGS --ignore_exists --position cn=univention,$ldap_base --set name=UMC
	udm container/cn create $BIND_ARGS --ignore_exists --position cn=policies,$ldap_base --set name=UMC --set policyPath=1
	udm container/cn create $BIND_ARGS --ignore_exists --position cn=UMC,cn=univention,$ldap_base --set name=acls
	udm container/cn create $BIND_ARGS --ignore_exists --position cn=UMC,cn=univention,$ldap_base --set name=operations

	# default policies
	udm policies/console_access create $BIND_ARGS --ignore_exists --set name=default-admin \
		--position cn=UMC,cn=policies,$ldap_base

	# link default admin policy to the domain admins
	udm groups/group modify $BIND_ARGS --ignore_exists --dn "cn=Domain Admins,cn=groups,$ldap_base" \
		--policy-reference="cn=default-admin,cn=UMC,cn=policies,$ldap_base"
}

umc_operation_create () {
	# example: umc_operation_create "udm" "UDM" "udm/*"
	name=$1; shift
	description=$1; shift
	operations=""
	for oper in "$@"; do
		operations="$operations --append operation=$oper "
	done
	udm settings/console_operation create $BIND_ARGS --ignore_exists \
		--position cn=operations,cn=UMC,cn=univention,$ldap_base \
		--set name="$name" \
		--set description="$description" $operations
}

umc_acl_create () {
	# example: umc_acl_create "udm-all" "UDM" "All UDM operations" "udm/*"
	name=$1; shift
	category=$1; shift
	description=$1; shift
	commands=""
	for cmd in "$@"; do
		commands="$commands --append command=$cmd "
	done

	command=$1
	udm settings/console_acl create $BIND_ARGS --ignore_exists --position cn=acls,cn=UMC,cn=univention,$ldap_base \
		--set name="$name" \
		--set category="$category" \
		--set description="$description" \
		--set ldapbase="$ldap_base" $commands
}

umc_policy_append () {
	# example: umc_policy_append "default-admin" "udm-all" "udm-users"
	policy="$1"; shift

	acls=""
	for acl in "$@"; do
		acls="$acls --append allow=cn=$acl,cn=acls,cn=UMC,cn=univention,$ldap_base "
	done

	udm policies/console_access modify $BIND_ARGS --ignore_exists \
		--dn "cn=$policy,cn=UMC,cn=policies,$ldap_base" $acls
}
