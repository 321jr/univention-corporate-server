/*
 * Python Heimdal
 *	Bindings for the encryption API of heimdal
 *
 * Copyright 2003-2010 Univention GmbH
 *
 * http://www.univention.de/
 *
 * All rights reserved.
 *
 * The source code of this program is made available
 * under the terms of the GNU Affero General Public License version 3
 * (GNU AGPL V3) as published by the Free Software Foundation.
 *
 * Binary versions of this program provided by Univention to you as
 * well as other copyrighted, protected or trademarked materials like
 * Logos, graphics, fonts, specific documentations and configurations,
 * cryptographic keys etc. are subject to a license agreement between
 * you and Univention and not subject to the GNU AGPL V3.
 *
 * In the case you use this program under the terms of the GNU AGPL V3,
 * the program is provided in the hope that it will be useful,
 * but WITHOUT ANY WARRANTY; without even the implied warranty of
 * MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE. See the
 * GNU Affero General Public License for more details.
 *
 * You should have received a copy of the GNU Affero General Public
 * License with the Debian GNU/Linux or Univention distribution in file
 * /usr/share/common-licenses/AGPL-3; if not, see
 * <http://www.gnu.org/licenses/>.
 */

#include <Python.h>
#include <krb5.h>

typedef struct {
	PyObject_HEAD
	krb5_context context;
	krb5_enctype enctype;
} krb5EnctypeObject;

PyTypeObject krb5EnctypeType;

krb5EnctypeObject *enctype_new(PyObject *unused, PyObject *args);
krb5EnctypeObject *enctype_from_enctype(krb5_context context, krb5_enctype enctype);
