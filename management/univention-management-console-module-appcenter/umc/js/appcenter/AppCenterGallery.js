/*
 * Copyright 2013-2014 Univention GmbH
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
/*global define*/

define([
	"dojo/_base/declare",
	"umc/tools",
	"umc/widgets/GalleryPane"
], function(declare, tools, GalleryPane) {
	return declare("umc.modules.appcenter.AppCenterGallery", [ GalleryPane ], {
		region: 'center',

		style: 'height: 100%; width: 100%;',

		getIconClass: function(item) {
			return tools.getIconClass(item.icon, 50, 'umcAppCenter');
		},

		getStatusIconClass: function(item) {
			var iconClass = '';
			if (item.endoflife) {
				iconClass = tools.getIconClass('appcenter-warning', 24, 'umcAppCenter');
			} else if (item.is_installed && item.candidate_version) {
				iconClass = tools.getIconClass('appcenter-can_update', 24, 'umcAppCenter');
			} else if (item.is_installed) {
				iconClass = tools.getIconClass('appcenter-is_installed', 24, 'umcAppCenter');
			}
			return iconClass;
		}
	});
});
