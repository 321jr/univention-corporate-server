/*
 * Copyright 2011-2017 Univention GmbH
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
	"umc/app",
	"umc/menu",
	"umc/tools",
	"umc/dialog",
	"umc/modules/lib/server",
	"dijit/MenuItem",
	"dijit/Menu",
	"dijit/PopupMenuItem",
	"umc/i18n!umc/modules/reboot"
], function(app, menu, tools, dialog, libServer, MenuItem, Menu, PopupMenuItem, _) {

	var addRebootMenu = function() {
		menu.addEntry(new PopupMenuItem({
			$priority$: 70,
			label: _('Server'),
			id: 'umcMenuServer',
			popup: new Menu({})
		}));
		menu.addEntry(new MenuItem({
			$parentMenu$: 'umcMenuServer',
			id: 'umcMenuShutdown',
			iconClass: 'icon24-umc-menu-shutdown',
			label: _('Shutdown server'),
			onClick: function() {
				libServer.askShutdown();
			}
		}));
		menu.addEntry(new MenuItem({
			$parentMenu$: 'umcMenuServer',
			id: 'umcMenuReboot',
			iconClass: 'icon24-umc-menu-reboot',
			label: _('Reboot server'),
			onClick: function() {
				libServer.askReboot();
			}
		}));
	};

	var checkRebootRequired = function() {
		tools.ucr(['update/reboot/required']).then(function(_ucr) {
			if (tools.isTrue(_ucr['update/reboot/required'])) {
				dialog.notify(_('This system has been updated recently. Please reboot this system to finish the update.'));
			//	libServer.askReboot(_('This system has been updated recently. Please reboot this system to finish the update.'));
			}
		});
	};

	app.registerOnStartup(function() {
		addRebootMenu();
		checkRebootRequired();
	});

	return null;
});
