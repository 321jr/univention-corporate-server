/*
 * Copyright 2011-2013 Univention GmbH
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
/*global define console*/

define([
	"dojo/_base/declare",
	"dojo/_base/lang",
	"dojo/_base/array",
	"dojo/aspect",
	"umc/tools",
	"umc/widgets/Page",
	"umc/widgets/StandbyMixin",
	"umc/widgets/TextBox",
	"umc/widgets/MultiInput",
	"umc/widgets/Form",
	"umc/modules/setup/InterfaceGrid",
	"umc/modules/setup/types",
	"umc/i18n!umc/modules/setup",
	"umc/modules/setup/InterfaceWizard"
], function(declare, lang, array, aspect, tools, Page, StandbyMixin, TextBox, MultiInput, Form, InterfaceGrid, types, _) {
	return declare("umc.modules.setup.NetworkPage", [ Page, StandbyMixin ], {
		// summary:
		//		This class renderes a detail page containing subtabs and form elements
		//		in order to edit network interfaces.

		// system-setup-boot
		wizard_mode: false,

		// __systemsetup__ user is logged in at local firefox session
		local_mode: false,

		umcpCommand: tools.umcpCommand,

		// internal reference to the formular containing all form widgets of an UDM object
		_form: null,

		// dicts of the original IPv4/v6 values
		_orgValues: null,

		_currentRole: null,

		physical_interfaces: [],

		postMixInProperties: function() {
			this.title = _('Network');
			this.headerText = _('Network settings');
			this.helpText = _('In the <i>network settings</i>, IP addresses (IPv4 and IPv6) as well as name servers, gateways, and HTTP proxies may be specified.');

			this.inherited(arguments);
		},

		buildRendering: function() {
			this.inherited(arguments);

			var widgets = [{
				type: InterfaceGrid,
				name: 'interfaces',
				label: ''
			}, {
				type: TextBox,
				name: 'interfaces/primary',
				label: _('primary network interface')
//				depends: ['interfaces', 'gateway']
//				dynamicValues: lang.hitch(this, function(values) {
//					// The primary interface can be of any type
//					return array.map(values.interfaces, function(iface) {
//						return {id: iface.name, label: iface.name};
//					});
//				})
			}, {
				type: TextBox,
				name: 'gateway',
				label: _('Gateway (IPv4)')
			}, {
				type: TextBox,
				name: 'ipv6/gateway',
				label: _('Gateway (IPv6)')
			}, {
				type: MultiInput,
				subtypes: [{ type: TextBox }],
				name: 'nameserver',
				label: _('Domain name server (max. 3)'),
				max: 3
			}, {
				type: MultiInput,
				subtypes: [{ type: TextBox }],
				name: 'dns/forwarder',
				label: _('External name server (max. 3)'),
				max: 3
			}, {
				type: TextBox,
				name: 'proxy/http',
				label: _('HTTP proxy')
			}];

			var layout = [{
				label: _('IP network devices'),
				layout: ['interfaces']
			}, {
				label: _('Global network settings'),
				layout: [ ['gateway', 'ipv6/gateway'], 'nameserver', 'dns/forwarder', 'proxy/http']
			}];

			this._form = new Form({
				widgets: widgets,
				layout: layout,
				scrollable: true
			});
			this._form.on('submit', lang.hitch(this, 'onSave'));

			this.addChild(this._form);

			// FIXME: as the grid is a border container it has to be resized manually if it is used as form element
			this.own(aspect.after(this, 'resize', lang.hitch(this, function() {
					this._form._widgets.interfaces.resize();
			})));
		},

		postCreate: function() {
			this.inherited(arguments);

			// The grid contains changes if a DHCP request was made
			this._form._widgets.interfaces.watch('gateway', lang.hitch(this, function(name, old, value) {
				// set gateway from dhcp request
				this._form._widgets.gateway.set('value', value);
			}));

			this._form._widgets.interfaces.watch('nameserver', lang.hitch(this, function(name, old, value) {
				// read nameserver or dns/forwarder
				var nameserverWidget;
				if (this._form.getWidget('nameserver').get('visible')) {
					nameserverWidget = this._form.getWidget('nameserver');
				} else {
					// if nameserver is not visible, set dns/forwarder
					nameserverWidget = this._form.getWidget('dns/forwarder');
				}
				// set nameserver from dhcp request
				nameserverWidget.set('value', value);
			}));

			this.own(this._form._widgets.interfaces.watch('interfaces/primary', lang.hitch(this, function(name, old, value) {
				// set new primary interface
				this._form._widgets['interfaces/primary'].set('value', value);
			})));
		},

		setValues: function(_vals) {

			// save a copy of all original values that may be lists
			var r = /^(interfaces\/.*|nameserver[1-3]|dns\/forwarder[1-3])$/;
			this._orgValues = {};
			tools.forIn(_vals, function(ikey, ival) {
				if (r.test(ikey)) {
					this._orgValues[ikey] = ival;
				}
			}, this);

			// set all available interfaces
			this.physical_interfaces = _vals.physical_interfaces;

			// copy values that do not change in their name
			var vals = {};
			array.forEach(['gateway', 'ipv6/gateway', 'proxy/http', 'interfaces/primary'], function(ikey) {
				vals[ikey] = _vals[ikey];
			});

			// sort the keys such that the interface order is correct
			var sortedKeys = [];
			tools.forIn(_vals, function(ikey) {
				sortedKeys.push(ikey);
			});
			sortedKeys.sort();

			// copy lists of nameservers/forwarders
			vals.nameserver = [];
			vals['dns/forwarder'] = [];
			array.forEach(sortedKeys, function(ikey) {
				array.forEach(['nameserver', 'dns/forwarder'], function(jname) {
					if (0 === ikey.indexOf(jname)) {
						vals[jname].push(_vals[ikey]);
					}
				});
			});

			vals.interfaces = {};
			tools.forIn(_vals.interfaces, function(iname, iface) {
				vals.interfaces[iface.name] = types.getDevice(iface);
			});

			// set all physical interfaces for the grid here, the info does not exists on grid creation
			this._form._widgets.interfaces.set('physical_interfaces', this.physical_interfaces);

			this._form._widgets.interfaces.set('interfaces/primary', vals['interfaces/primary']);

			// only show forwarder for master, backup, and slave
			this._currentRole = _vals['server/role'];
			var showForwarder = this._currentRole == 'domaincontroller_master' || this._currentRole == 'domaincontroller_backup' || this._currentRole == 'domaincontroller_slave';
			this._form.getWidget('dns/forwarder').set('visible', showForwarder);

			// hide domain nameserver on master when using system setup boot
			this._form.getWidget('nameserver').set('visible', ! ( this.wizard_mode && this._currentRole == 'domaincontroller_master' ) );

			// set values
			this._form.setFormValues(vals);

			this.clearNotes();

			// show a note if interfaces changes
			if (!this.wizard_mode) {
				// only show notes in an joined system in productive mode
				var handler = this._form._widgets.interfaces.watch('value', lang.hitch(this, function() {
					// TODO: only show it when IP changes??
					this.addNote(_('Changing IP address configurations may result in restarting or stopping services. This can have severe side-effects when the system is in productive use at the moment.'));
					handler.unwatch();
				}));
				this.own(handler);
			}
		},

		getValues: function() {
			var _vals = this._form.get('value');
			var vals = {};

			// copy values that do not change in their name
			array.forEach(['gateway', 'ipv6/gateway', 'proxy/http', 'interfaces/primary'], function(ikey) {
				vals[ikey] = _vals[ikey];
			});

			vals.interfaces = {};
			array.forEach(_vals.interfaces, function(iface) {
				vals.interfaces[iface.name] = iface.toObject();
			});

			// copy lists of nameservers/forwarders
			array.forEach(['nameserver', 'dns/forwarder'], function(iname) {
				array.forEach(_vals[iname], function(jval, j) {
					vals[iname + (j + 1)] = jval;
				});
			});

			// add empty entries for all original entries that are not used anymore
			tools.forIn(this._orgValues, function(ikey, ival) {
				if (!(ikey in vals)) {
					vals[ikey] = '';
				}
			});

			return vals;
		},

		getSummary: function() {
			// a list of all components with their labels

			var vals = this._form.get('value');

			var network_summary = '';
			array.forEach(vals.interfaces, function(iface) {
				var summary = iface.getSummary();
				if (summary) {
					network_summary += summary + '<br>';
				}
			});

			// create a verbose list of all settings
			return [{
				variables: ['gateway'],
				description: _('Gateway (IPv4)'),
				values: vals['gateway']
			}, {
				variables: ['ipv6/gateway'],
				description: _('Gateway (IPv6)'),
				values: vals['ipv6/gateway']
			}, {
				variables: [(/nameserver.*/)],
				description: _('Domain name server'),
				values: vals['nameserver'].join(', ')
			}, {
				variables: [(/dns\/forwarder.*/)],
				description: _('External name server'),
				values: vals['dns/forwarder'].join(', ')
			}, {
				variables: ['proxy/http'],
				description: _('HTTP proxy'),
				values: vals['proxy/http']
			}, {
				variables: ['interfaces'],
				description: _('Network devices'),
				values: network_summary
			}, {
				variables: ['interfaces/primary'],
				description: _('Primary network interface'),
				values: vals['interfaces/primary']
			}];
		},

		onSave: function() {
			// event stub
		}
	});
});
