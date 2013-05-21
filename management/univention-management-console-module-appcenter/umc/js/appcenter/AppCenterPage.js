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
/*global define require console*/

define([
	"dojo/_base/declare",
	"dojo/_base/lang",
	"dojo/_base/array",
	"dojo/when",
	"dojo/query",
	"dojo/dom-class",
	"dojo/store/Memory",
	"dojo/topic",
	"dojo/regexp",
	"dojo/Deferred",
	"dojox/image/LightboxNano",
	"umc/app",
	"umc/dialog",
	"umc/tools",
	"umc/modules/lib/server",
	"umc/widgets/Page",
	"umc/widgets/ProgressBar",
	"umc/widgets/ConfirmDialog",
	"umc/widgets/Text",
	"umc/widgets/ExpandingTitlePane",
	"umc/widgets/TitlePane",
	"umc/widgets/TextBox",
	"umc/widgets/CheckBox",
	"umc/widgets/ContainerWidget",
	"umc/widgets/LabelPane",
	"umc/widgets/Button",
	"umc/widgets/GalleryPane",
	"umc/i18n!umc/modules/appcenter"
], function(declare, lang, array, when, query, domClass, Memory, topic, regexp, Deferred, Lightbox, UMCApplication, dialog, tools, libServer, Page, ProgressBar, ConfirmDialog, Text, ExpandingTitlePane, TitlePane, TextBox, CheckBox, ContainerWidget, LabelPane, Button, GalleryPane, _) {

	var _SearchWidget = declare("umc.modules.appcenter._SearchWidget", [ContainerWidget], {

		category: null,

		style: 'overflow: auto;',

		buildRendering: function() {
			this.inherited(arguments);

			var widthContainer = new ContainerWidget();
			this._searchTextBox = new TextBox({
				label: _("Search term"),
				style: 'width: 135px;'
			});
			var searchLabel = new LabelPane({
				content: this._searchTextBox
			});
			widthContainer.addChild(searchLabel);
			this.addChild(widthContainer);

			this._categoryContainer = new ContainerWidget({
				label: _("Categories")
			});
			var categoryLabel = new LabelPane({
				content: this._categoryContainer
			});
			this.addChild(categoryLabel);
		},

		postCreate: function() {
			this.inherited(arguments);
			this._searchTextBox.on('keyup', lang.hitch(this, 'onSearch'));
		},

		_getValueAttr: function() {
			return this._searchTextBox.get('value');
		},

		_getCategoryAttr: function() {
			return this.category;
		},

		_setCategoriesAttr: function(categories) {
			// remove all existing categories
			array.forEach(this._categoryContainer.getChildren(), lang.hitch(this, function(category) {
				this._categoryContainer.removeChild(category);
				category.destroyRecursive();
			}));

			// add new categories
			this._categoryContainer.addChild(new Button({
				label: _('All'),
				callback: lang.hitch(this, function() {
					this.category = null;
					this._updateCss();
					this.onSearch();
				})
			}));
			array.forEach(categories, lang.hitch(this, function(category) {
				this._categoryContainer.addChild(new Button({
					label: category,
					callback: lang.hitch(this, function() {
						this.category = category;
						this._updateCss();
						this.onSearch();
					})
				}));
			}));

			this._updateCss();
		},

		_updateCss: function() {
			var categories = this._categoryContainer.getChildren();
			var label;
			array.forEach(categories, lang.hitch(this, function(category) {
				label = category.get('label');
				if (this.category == label || (! this.category && label == _('All'))) {
					domClass.add(category.domNode, 'umcCategorySelected');
				} else {
					domClass.remove(category.domNode, 'umcCategorySelected');
				}
			}));
		},

		onSearch: function() {
		}
	});

	return declare("umc.modules.appcenter.AppCenterPage", [ Page ], {

		_udm_accessible: false, // license depends on udm
		standby: null, // parents standby method must be passed. weird IE-Bug (#29587)
		autoStart: true, // get/user/preferences and updateApplications. Needed because it is used in apps.js as well
		showModuleUsage: false, // problems with dialog staying open

		// class name of the widget as CSS class
		'class': 'umcAppCenter',

		postMixInProperties: function() {
			this.inherited(arguments);

			lang.mixin(this, {
				title: _("App management"),
				headerText: _("Manage Applications for UCS"),
				helpText: _("This page lets you install and remove applications that enhance your UCS installation.")
			});
		},

		buildRendering: function() {
			this.inherited(arguments);

			this._progressBar = new ProgressBar();
			this.own(this._progressBar);

			this._initialCheckDeferred = new Deferred();
			this._buildRenderingDeferred = new Deferred();
			this.standby(true);
			tools.umcpCommand('appcenter/working').then(lang.hitch(this, function(data) {
				this.standby(false);
				var working = data.result;
				if (working) {
					// this._initialCheckDeferred is resolved there
					this._switch_to_progress_bar(_('Another package operation is in progress'), null, 'watching', false);
				} else {
					this._initialCheckDeferred.resolve();
				}
			}), lang.hitch(this, function() {
				this.standby(false);
				this._initialCheckDeferred.resolve();
			}));

			this._initialCheckDeferred.then(lang.hitch(this, function() {
				this._appCenterInformation =
					'<p>' + _('Univention App Center is the simplest method to install or uninstall applications on Univention Corporate Server.') + '</p>' +
					'<p>' + _('Univention always receives an estranged notification for statistical purposes upon installation and uninstallation of an application in Univention App Center that is only saved at Univention for data processing and will not be forwarded to any third party.') + '</p>' +
					'<p>' + _('Depending on the guideline of the respective application vendor an updated UCS license key with so-called key identification (Key ID) is required for the installation of an application. In this case, the Key ID will be sent to Univention together with the notification. As a result the application vendor receives a message from Univention with the following information:') +
						'<ul>' +
							'<li>' + _('Name of the installed application') + '</li>' +
							'<li>' + _('Registered email address') + '</li>' +
						'</ul>' +
					_('The description of every application includes a respective indication for such cases.') + '</p>' +
					'<p>' + _('If your UCS environment does not have such a key at it\'s disposal (e.g. UCS Free-for-personal-Use Edition) and the vendor requires a Key ID, you will be asked to request an updated license key directly from Univention. Afterwards the new key can be applied.') + '</p>' +
					'<p>' + _('The sale of licenses, maintenance or support for the applications uses the default processes of the respective vendor and is not part of Univention App Center.') + '</p>';

				this._searchWidget = new _SearchWidget({
					region: 'left'
				});
				this.addChild(this._searchWidget);

				var titlePane = new ExpandingTitlePane({
					title: _('Applications')
				});

				this._grid = new GalleryPane({
					baseClass: "umcAppCenter",

					style: 'height: 100%; width: 100%;',

					getIconClass: function(item) {
						return tools.getIconClass(item.icon, 50, 'umcAppCenter');
					},

					getStatusIconClass: function(item) {
						var iconClass = '';
						if (! item.can_update && item.candidate_version && item.cannot_update_reason != 'not_installed') {
							iconClass = tools.getIconClass('appcenter-cannot_update', 24, 'umcAppCenter');
						} else if (item.can_update) {
							iconClass = tools.getIconClass('appcenter-can_update', 24, 'umcAppCenter');
						} else if (item.is_installed) {
							iconClass = tools.getIconClass('appcenter-is_installed', 24, 'umcAppCenter');
						}
						return iconClass;
					}
				});

				titlePane.addChild(this._grid);
				this.addChild(titlePane);

				if (this.autoStart) {
					tools.getUserPreferences().then(lang.hitch(this, function(prefs) {
						if (tools.isTrue(prefs.appcenterSeen)) {
							// load apps
							this.updateApplications();
						} else {
							dialog.confirmForm({
								title: _('Univention App Center'),
								widgets: [
									{
										type: Text,
										name: 'help_text',
										content: '<div style="width: 535px">' + this._appCenterInformation + '</div>'
									},
									{
										type: CheckBox,
										name: 'show_again',
										label: _("Show this message again")
									}
								],
								buttons: [{
									name: 'submit',
									'default': true,
									label: _('Continue')
								}]
							}).then(
								lang.hitch(this, function(data) {
									tools.setUserPreference({appcenterSeen: data.show_again ? 'false' : 'true'});
									this.updateApplications();
								}),
								lang.hitch(this, function() {
									this.updateApplications();
								})
							);
						}
					}), lang.hitch(this, function() {
						this.updateApplications();
					}));
				}

				// register event handlers
				this._searchWidget.on('search', lang.hitch(this, 'filterApplications'));

				this.own(this._grid.on('.dgrid-row:click', lang.hitch(this, function(evt) {
					this._show_details(this._grid.row(evt));
					topic.publish('/umc/actions', this.moduleID, this.moduleFlavor, this._grid.row(evt).id, 'show');
				})));

				this._buildRenderingDeferred.resolve(); // for apps.js
			}));
		},

		formatTxt: function(txt) {
			// do not allow HTML
			txt = txt.replace(/</g, '&lt;');
			txt = txt.replace(/>/g, '&gt;');

			// insert links
			txt = txt.replace(/(https?:\/\/\S*)/g, '<a target="_blank" href="$1">$1</a>');

			// format line breakes
			txt = txt.replace(/\n\n\n/g, '\n<br>\n<br>\n<br>\n');
			txt = txt.replace(/\n\n/g, '\n<br>\n<br>\n');

			return txt;
		},

		// inspired by PackagesPage._show_details
		_show_details: function(app) {
			this.standby(true);

			tools.umcpCommand('appcenter/get', {'application': app.id}).then(
				lang.hitch(this, function(data) {
					this.standby(false);
					var app = data.result;
					var width = 550;        // mimic the default of dialog.confirm

					var label_style = 'vertical-align:top;text-align:right;padding-left:1em;padding-right:.5em;white-space:nowrap;font-weight:bold;';
					var data_style	= 'vertical-align:top;padding-bottom:.25em;';

					var txt = "<h1>" + _("Details for Application '%(name)s'", app) + "</h1>";
					txt += "<table>\n";
					var fields = this._detail_field_order();
					array.forEach(fields, lang.hitch(this, function(key) {
						var label = this._detail_field_label(key);
						var value = app[key];
						var detail_func = this['_detail_field_custom_' + key];
						if (detail_func) {
							value = lang.hitch(this, detail_func)(app);
						}
						if (!value) {
							return; // continue
						}
						if (label) {
							txt += "<tr>\n";
							txt += "<td style='" + label_style + "'>" + label + "</td>\n";
							txt += "<td style='" + data_style + "'>" + value + "</td>\n";
							txt += "</tr>\n";
						}
					}));
					txt += "</table>\n";
					var buttons = [];
					if (!app.allows_using && this._udm_accessible) {
						var label = app.can_update ? _('Upgrade') : _('Install'); // call it Install/Upgrade, although it is request
						buttons.push({
							name: 'request',
							label: label,
							callback: lang.hitch(this, function() {
								this._show_license_request();
							})
						});
					}
					if (app.allows_using && app.can_install) {
						buttons.push({
							name: 'install',
							label: _("Install"),
							callback: lang.hitch(this, function() {
								if (app.licenseagreement) {
									// before installing, user must agree on license terms
									var content = '<h1>' + _('License agreement') + '</h1>';
									content += '<div style="max-height:250px; overflow:auto;">' +
										this.formatTxt(app.licenseagreement) +
										'</div>';
									dialog.confirm(content, [{
										name: 'decline',
										label: _('Cancel'),
										'default': true
									}, {
										name: 'accept',
										label: _('Accept license')
									}], _('License agreement')).then(lang.hitch(this, function(response) {
										if (response == 'accept') {
											this._call_installer('install', app);
										}
									}));
								} else {
									this._call_installer('install', app);
								}
							})
						});
					}
					if (app.allows_using && app.can_update) {
						buttons.push({
							name: 'update',
							label: _("Upgrade"),
							callback: lang.hitch(this, function() {
								this.upgradeApp(app);
							})
						});
					}
					if (app.can_uninstall) {
						buttons.push({
							name: 'uninstall',
							label: _("Uninstall"),
							callback: lang.hitch(this, function() {
								this._call_installer('uninstall', app);
							})
						});
						if (UMCApplication.getModule(app.umc_module, app.umc_flavor)) {
							buttons.push({
								name: 'open',
								label: _("Open"),
								callback: lang.hitch(this, function() {
									topic.publish('/umc/modules/open', app.umc_module, app.umc_flavor);
								})
							});
						}
					}
					// always: a button to close the dialog.
					buttons.push({
						name: 'cancel',
						'default': true,
						label: _("Close")
					});

					var dialogText = new Text({
						'class': 'umcConfirmDialogText',
						content: txt
					});
					var confirmDialog = new ConfirmDialog({
						title: _('Application details'),
						message: dialogText,
						options: buttons
					});

					// decorate screenshot images with a Lightbox
					var lightbox;
					query('.umcScreenshot', confirmDialog.domNode).forEach(function(imgNode) {
						lightbox = new Lightbox({ href: imgNode.src }, imgNode);
						imgNode.onload = function() {
							confirmDialog.resize();
						};
					});

					// connect to 'onConfirm' event to close the dialog in any case
					confirmDialog.on('confirm', function() {
						confirmDialog.close();
					});

					// show the confirmation dialog
					confirmDialog.show();

				}),
				lang.hitch(this, function() {
					this.standby(false);
				})
			);
		},

		_package_changes_one: function(changes, label) {
			var txt = '';
			var details;
			if (changes === undefined || changes.length) {
				if (changes === undefined) {
					details = '<div>' + _('Unknown') + '</div>';
				} else {
					details = '<ul><li>' + changes.join('</li><li>') + '</li></ul>';
				}
				txt = '<p>' + label + details + '</p>';
			}
			return txt;
		},

		_package_changes: function(install, remove, broken, incompatible, opened, host) {
			var container = new ContainerWidget({});
			var txt = '';
			txt += this._package_changes_one(install, _('The following packages will be installed or upgraded:'));
			txt += this._package_changes_one(remove, _('The following packages will be removed:'));
			txt += this._package_changes_one(broken, _('This operation causes problems in the following packages that cannot be resolved:'));
			if (txt === '') {
				txt = '<p>' + _('No changes') + '</p>';
			}
			if (incompatible) {
				txt += '<div>' + _('The version of the remote App Center is <strong>incompatible</strong> with the local one. Please update your hosts.') + '</div>';
			}
			var install_count = install ? install.length : _('Unknown');
			var remove_count = remove ? (remove.length === 0 ? 0 : '<strong>' + remove.length + '</strong>') : _('Unknown');
			var broken_count = broken ? (broken.length === 0 ? 0 : '<strong>' + broken.length + '</strong>') : _('Unknown');
			var incompatible_headline = incompatible ? ', <strong>' + _('incompatible') : '</strong>';
			container.addChild(new Text({
				content: _('Software changes on %(host)s (installed/upgraded: %(installed)s, removed: %(removed)s, erroneous: %(erroneous)s%(incompatible)s)', {host: host, installed: install_count, removed: remove_count, erroneous: broken_count, incompatible: incompatible_headline})
			}));
			container.addChild(new TitlePane({
				title: _('Show details'),
				open: opened,
				content: txt
			}));
			return container;
		},

		_call_installer: function(func, app, force) {
			var verb = '';
			var verb1 = '';
			switch(func) {
			case 'install':
				verb = _("install");
				verb1 = _("Installing");
				break;
			case 'uninstall':
				verb = _("uninstall");
				verb1 = _("Uninstalling");
				break;
			case 'update':
				verb = _("upgrade");
				verb1 = _("Upgrading");
				break;
			default:
				console.warn(func, 'is not a known function');
				break;
			}

			if (!force) {
				topic.publish('/umc/actions', this.moduleID, this.moduleFlavor, app.id, func);
			}

			var command = 'appcenter/invoke';
			if (!force) {
				command = 'appcenter/invoke_dry_run';
			}
			var commandArguments = {
				'function': func,
				'application': app.id,
				'force': force === true
			};

			this._progressBar.reset(_('%s: Performing software tests on involved systems', app.name));
			this._progressBar._progressBar.set('value', Infinity);
			this.standby(true, this._progressBar);
			tools.umcpCommand(command, commandArguments).then(
				lang.hitch(this, function(data) {
					this.standby(false);
					var result = data.result;
					var confirmationRequired = false;
					var container = new ContainerWidget({});
					var label = '';
					var headline = '';
					var buttons = [];

					if (!result.can_continue) {
						confirmationRequired = true;
						var mayContinue = !result.serious_problems;
						var no_host_info = true;
						tools.forIn(result.hosts_info, function() {
							no_host_info = false;
							return false;
						});
						if (func == 'update') {
							container.addChild(new Text({
								content: _('These changes contain <strong>all package upgrades available</strong> and thus may <strong>include errata updates</strong>. If this is not intended, the corresponding components have to be temporarily deactivated first using the tab "%s" above.', _('Repository Settings')),
								style: {paddingBottom: '.25em'}
							}));
						}
						container.addChild(this._package_changes(result.install, result.remove, result.broken, false, no_host_info, _('this server')));
						tools.forIn(result.hosts_info, lang.hitch(this, function(host, host_info) {
							container.addChild(this._package_changes(host_info.result.install, host_info.result.remove, host_info.result.broken, !host_info.compatible_version, false, host));
						}));
						if (result.unreachable.length) {
							if (app.is_master) {
								label = _('The server tried to connect to DC Backups.');
							} else {
								label = _('The server tried to connect to DC Master and DC Backups.');
							}
							label += ' ' + _('The following hosts cannot be reached:');
							container.addChild(new Text({
								content: label + '<ul><li>' + result.unreachable.join('</li><li>') + '</li></ul>'
							}));
							if (!result.master_unreachable) {
								var cmdLine = lang.replace('univention-add-app {component_id} -m', {component_id: app.candidate_component_id || app.component_id});
								var commandHint = '<strong>' + _('Attention!') + '</strong>' + ' ' + _('This application requires an extension of the LDAP schema.') + ' ' + _('Be sure to execute the following command as root on all of these backup servers <em>after</em> installing the application.') + '</td></tr><tr><td colspan="2"><pre>' + cmdLine + '</pre>';
								container.addChild(new Text({
									content: commandHint
								}));
							}
						}
						if (mayContinue) {
							headline = _("Do you really want to %(verb)s %(ids)s?",
										{verb: verb, ids: app.name});
							buttons = [{
								name: 'cancel',
								'default': true,
								label: _("Cancel"),
								callback: lang.hitch(this, function() {
									topic.publish('/umc/actions', this.moduleID, this.moduleFlavor, app.id, 'user-cancel');
								})
							}, {
								name: 'submit',
								label: tools.capitalize(verb),
								callback: lang.hitch(this, function() {
									this._call_installer(func, app, true);
								})
							}];
						} else {
							topic.publish('/umc/actions', this.moduleID, this.moduleFlavor, app.id, 'cannot-continue');
							headline = _('You cannot continue');
							buttons = [{
								name: 'cancel',
								'default': true,
								label: _("Cancel")
							}];
						}
					}

					if (confirmationRequired) {
						dialog.confirm(container, buttons, headline);
					} else {
						var progressMessage = _("%(verb)s %(ids)s", {verb: verb1, ids: app.name});

						this._switch_to_progress_bar(progressMessage, app, func);
					}
				}),
				lang.hitch(this, function() {
					this.standby(false);
				})
			);
		},

		_detail_field_custom_usage: function(values) {
			var txts = [];
			var useractivationrequired = values.useractivationrequired;
			var webinterface = values.webinterface;
			var webinterfacename = values.webinterfacename || values.name;
			var umcmodulename = values.umcmodulename;
			var umcmoduleflavor = values.umcmoduleflavor;
			var module = UMCApplication.getModule(umcmodulename, umcmoduleflavor);
			if (useractivationrequired) {
				var domain_administration_link = _('Domain administration');
				if (values.is_installed && UMCApplication.getModule('udm', 'users/user')) {
					domain_administration_link = lang.replace('<a href="javascript:void(0)" onclick="require(\'umc/app\').openModule(\'udm\', \'users/user\')">{name}</a>', {name : domain_administration_link});
				}
				txts.push(_('Users need to be modified in the %s in order to use this service.', domain_administration_link));
			}
			if (module && this.showModuleUsage) {
				var module_link = lang.replace('<a href="javascript:void(0)" onclick="require(\'umc/app\').openModule(\'{umcmodulename}\', {umcmoduleflavor})">{name}</a>', {
					umcmodulename: umcmodulename,
					umcmoduleflavor: umcmoduleflavor ? '\'' + umcmoduleflavor + '\'' : 'undefined',
					name: module.name
				});
				txts.push(_('A module for the administration of the app is available: %s.', module_link));
			}
			if (values.is_installed && webinterface) {
				var webinterface_link = lang.replace('<a href="{webinterface}" target="_blank">{name}</a>', {
					webinterface: webinterface,
					name: webinterfacename
				});
				txts.push(_('The app provides a web interface: %s.', webinterface_link));
			}
			if (txts.length) {
				return txts.join(' ');
			}
		},

		_detail_field_custom_candidate_version: function(values) {
			var version = values.version;
			var candidate_version = values.candidate_version;
			var is_installed = values.is_installed;
			if (candidate_version) {
				return candidate_version;
			}
			if (! is_installed) {
				return version;
			}
		},

		_detail_field_custom_version: function(values) {
			var version = values.version;
			var is_installed = values.is_installed;
			if (is_installed) {
				return version;
			}
		},

		_detail_field_custom_website: function(values) {
			var name = values.name;
			var website = values.website;
			if (name && website) {
				return '<a href="' + website + '" target="_blank">' + name + '</a>';
			}
		},

		_detail_field_custom_vendor: function(values) {
			var vendor = values.vendor;
			var website = values.websitevendor;
			if (vendor && website) {
				return '<a href="' + website + '" target="_blank">' + vendor + '</a>';
			} else if (vendor) {
				return vendor;
			}
		},

		_detail_field_custom_maintainer: function(values) {
			var maintainer = values.maintainer;
			var vendor = values.vendor;
			if (vendor == maintainer) {
				return null;
			}
			var website = values.websitemaintainer;
			if (maintainer && website) {
				return '<a href="' + website + '" target="_blank">' + maintainer + '</a>';
			} else if (maintainer) {
				return maintainer;
			}
		},

		_detail_field_custom_contact: function(values) {
			var contact = values.contact;
			if (contact) {
				return '<a href="mailto:' + contact + '">' + contact + '</a>';
			}
		},

		_detail_field_custom_allows_using: function(values) {
			var allows_using = values.allows_using;
			if (!allows_using) {
				var txt = _('For the installation of this application an updated UCS license key with a so-called key identification (Key ID) is required.');
				if (!this._udm_accessible) {
					txt += ' ' + _('You need to have access to the Univention Directory Manager (UDM) module to fully use the App Center.');
				}
				return txt;
			}
		},

		_detail_field_custom_defaultpackagesmaster: function(values) {
			var master_packages = values.defaultpackagesmaster;
			var can_install = values.can_install;
			var can_update = values.can_update;
			var allows_using = values.allows_using;
			if (allows_using && values.cannot_install_reason == 'not_joined') {
				return '<strong>' + _('Attention!') + '</strong>' + ' ' + _('This application requires an extension of the LDAP schema.') + ' ' + _('The system has to join a domain before the application can be installed!');
			}
			// if (allows_using && (can_install || can_update) && master_packages && master_packages.length) {
			// 	// prepare a command with max 50 characters length per line
			// 	var MAXCHARS = 50;
			// 	var cmdLine = lang.replace('univention-add-app {component_id} ', {component_id: values.candidate_component_id || values.component_id});
			// 	var cmdLines = [];
			// 	array.forEach(master_packages, function(icmd) {
			// 		if (icmd.length + cmdLine.length > MAXCHARS) {
			// 			cmdLines.push(cmdLine);
			// 			cmdLine = '    ';
			// 		}
			// 		cmdLine += icmd + ' ';
			// 	});
			// 	if (cmdLine) {
			// 		cmdLines.push(cmdLine);
			// 	}
			// 	var commandStr = cmdLines.join('\\\n');

			// 	// print out note for master and backup servers
			// 	if (values.is_master) {
			// 		return '<strong>' + _('Attention!') + '</strong>' + ' ' + _('This application requires an extension of the LDAP schema.') + ' ' + _('Be sure to execute the following commands as root on all of your backup servers <em>after</em> installing the application on this DC master.') + '</td></tr><tr><td colspan="2"><pre>' + commandStr + '</pre>';
			// 	} else {
			// 		return '<strong>' + _('Attention!') + '</strong>' + ' ' + _('This application requires an extension of the LDAP schema.') + ' ' + _('Be sure to execute the following commands as root <em>first</em> on your DC master and <em>then</em> on all of your backup servers <em>prior</em> to installing the application on this system.') + '</td></tr><tr><td colspan="2"><pre>' + commandStr + '</pre>';
			// 	}
			// }
		},

		_detail_field_custom_cannot_update_reason: function(values) {
			var newValues = lang.mixin({}, values);
			newValues.cannot_install_reason = values.cannot_update_reason;
			newValues.cannot_install_reason_detail = values.cannot_update_reason_detail;
			newValues.serverrole = values.candidate_server_role;
			return this._detail_field_custom_cannot_install_reason(newValues);
		},

		_detail_field_custom_cannot_install_reason: function(values) {
			var cannot_install_reason = values.cannot_install_reason;
			var cannot_install_reason_detail = values.cannot_install_reason_detail;
			if (!values.allows_using) {
				return '';
			}

			var txt = '';
			if (cannot_install_reason == 'hardware_requirements') {
				return cannot_install_reason_detail;
			} else if (cannot_install_reason == 'conflict') {
				txt = _('This application conflicts with the following Applications/Packages. Uninstall them first.');
				txt += '<ul><li>' + cannot_install_reason_detail.join('</li><li>') + '</li></ul>';
			} else if (cannot_install_reason == 'wrong_serverrole') {
				txt = '<p>' + _('This application cannot be installed on the current server role (%(reason_detail)s). In order to install the application, one of the following roles is necessary: %(server_roles)s', {reason_detail: cannot_install_reason_detail, server_roles: values.serverrole.join(', ')}) + '</p>';
			}
			return txt;
		},

		_detail_field_custom_categories: function(values) {
			if (values.categories) {
				return values.categories.join(', ');
			}
		},

		_detail_field_custom_notifyvendor: function(values) {
			var maintainer = values.maintainer && values.maintainer != values.vendor;
			if (values.notifyvendor) {
				if (maintainer) {
					return _('This application will inform the maintainer if you (un)install it.');
				} else {
					return _('This application will inform the vendor if you (un)install it.');
				}
			} else {
				if (maintainer) {
					return _('This application will not inform the maintainer if you (un)install it.');
				} else {
					return _('This application will not inform the vendor if you (un)install it.');
				}
			}
		},

		_detail_field_custom_screenshot: function(values) {
			if (values.screenshot) {
				return lang.replace('<img src="{url}" style="max-width: 90%; height:200px;" class="umcScreenshot" />', {
					url: values.screenshot,
					id: this.id
				});
			}
		},

		_detail_field_order: function() {
			return [
				//'name',
				'vendor',
				'maintainer',
				'contact',
				'website',
				'version',
				'candidate_version',
				'categories',
				'longdescription',
				'screenshot',
				'usage',
				'defaultpackagesmaster',
				'cannot_install_reason',
				'cannot_update_reason',
				'notifyvendor',
				'allows_using'
			];
		},

		_detail_field_label: function(key) {
			var labels = {
				// 'name': _("Name"),
				'vendor': _("Vendor"),
				'maintainer': _("Maintainer"),
				'contact': _("Contact"),
				'website': _("Website"),
				'version': _('Installed version'),
				'candidate_version': _('Candidate version'),
				'categories': _("Section"),
				'longdescription': _("Description"),
				'screenshot': _("Screenshot"),
				'usage': _('Notes on using'),
				'defaultpackagesmaster': _("Packages for master system"),
				'cannot_install_reason': _("Installation not possible"),
				'cannot_update_reason': _("Upgrade not possible"),
				'notifyvendor': _("Email notification"),
				'allows_using': _("UCS License Key")
			};
			return labels[key];
		},

		upgradeApp: function(app) {
			if (app.candidate_readmeupdate) {
				// before updating, show update README file
				var content = '<h1>' + _('Upgrade information') + '</h1>';
				content += '<div style="max-height:250px; overflow:auto;">' +
					this.formatTxt(app.candidate_readmeupdate) +
					'</div>';
				dialog.confirm(content, [{
					name: 'decline',
					label: _('Cancel'),
					'default': true
				}, {
					name: 'update',
					label: _('Upgrade')
				}], _('Upgrade information')).then(lang.hitch(this, function(response) {
					if (response == 'update') {
						this._call_installer('update', app);
					}
				}));
			} else {
				this._call_installer('update', app);
			}
		},

		getApplications: function() {
			if (!this._applications) {
				return tools.umcpCommand('appcenter/query', {}).then(lang.hitch(this, function(data) {
					// sort by name
					this._applications = data.result;
					this._applications.sort(tools.cmpObjects({
						attribute: 'name',
						ignoreCase: true
					}));
					return this._applications;
				}));
			}
			return this._applications;
		},

		updateApplications: function() {
			// query all applications
			this._applications = null;
			this.standby(true);
			when(this.getApplications(),
				lang.hitch(this, function(applications) {
					this.standby(false);
					this._grid.set('store', new Memory({data: applications}));

					var categories = [];
					array.forEach(applications, function(application) {
						array.forEach(application.categories, function(category) {
							if (array.indexOf(categories, category) < 0) {
							     categories.push(category);
							}
						});
					});
					this._searchWidget.set('categories', categories.sort());
				}),
				lang.hitch(this, function() {
					this.standby(false);
				})
			);
		},

		filterApplications: function() {
			// sanitize the search pattern
			var searchPattern = lang.trim(this._searchWidget.get('value'));
			searchPattern = regexp.escapeString(searchPattern);
			searchPattern = searchPattern.replace(/\\\*/g, '.*');
			searchPattern = searchPattern.replace(/ /g, '\\s+');

			var regex  = new RegExp(searchPattern, 'i');
			var category = this._searchWidget.get('category');

			var query = {
				test: function(value, obj) {
					var string = lang.replace(
						'{name} {description} {categories}', {
							name: obj.name,
							description: obj.description,
							categories: category ? '' : obj.categories.join(' ')
						});
					return regex.test(string);
				}
			};
			this._grid.query.name = query;

			if (! category) {
				delete this._grid.query.categories;
			} else {
				this._grid.query.categories = {
					test: function(categories) {
						return (array.indexOf(categories, category) >= 0);
					}
				};
			}

			this._grid.refresh();
		},

		_show_license_request: function() {
			topic.publish('/umc/actions', this.moduleID, this.moduleFlavor, 'request-license');
			if (this._udm_accessible) {
				dialog.confirmForm({
					title: _('Request updated license key with identification'),
					widgets: [
						{
							type: Text,
							name: 'help_text',
							content: '<h2>' + _('Provision of an updated UCS license key') + '</h2><div style="width: 535px"><p>' + _('Please provide a valid email address such that an updated license can be sent to you. This may take a few minutes. You can then upload the updated license key directly in the following license dialog.') + '</p>'
						},
						{
							type: TitlePane,
							name: 'more_information',
							title: _('More information'),
							open: false,
							content: this._appCenterInformation
						},
						{
							type: TextBox,
							name: 'email',
							required: true,
							regExp: '.+@.+',
							label: _("Email address")
						}
					],
					autoValidate: true
				}).then(lang.hitch(this, function(values) {
					this.standby(true);
					tools.umcpCommand('appcenter/request_new_license', values).then(
						lang.hitch(this, function(data) {
							// cannot require in the beginning as
							// udm might be not installed
							this.standby(false);
							require(['umc/modules/udm/LicenseDialog'], function(LicenseDialog) {
								if (data.result) {
									var dlg = new LicenseDialog();
									dlg.show();
								}
							});
						}),
						lang.hitch(this, function() {
							this.standby(false);
						}));
				}));
			}
		},

		_switch_to_progress_bar: function(msg, app, func, keep_alive) {
			// One request needs to be active otherwise
			// module might be killed if user logs out
			// during installation: dpkg will be in a
			// broken state, Bug #30611.
			// dont handle any errors. a timeout is not
			// important. this command is just for the module
			// to stay alive
			if (keep_alive !== false) {
				tools.umcpCommand('appcenter/keep_alive', {}, false);
			}
			this.standby(true, this._progressBar);
			this._progressBar.reset(msg);
			this._progressBar.auto('appcenter/progress',
				{},
				lang.hitch(this, function() {
					this._initialCheckDeferred.resolve();
					if (func === 'install' && app.umc_module) {
						// hack it into favorites: the app is yet unknown
						UMCApplication.addFavoriteModule(app.umc_module, app.umc_flavor);
						UMCApplication._saveFavorites();
					}
					this._markupErrors();
				}),
				undefined,
				undefined,
				true
			);
		},

		_markupErrors: function() {
			var installMasterPackagesOnHostFailedRegex = (/Installing extension of LDAP schema for (.+) seems to have failed on (DC Master|DC Backup) (.+)/);
			var errors = array.map(this._progressBar._errors, function(error) {
				var match = installMasterPackagesOnHostFailedRegex.exec(error);
				if (match) {
					var component = match[1];
					var role = match[2];
					var host = match[3];
					error = '<p>' + _('Installing the extension of the LDAP schema on %s seems to have failed.', '<strong>' + host + '</strong>') + '</p>';
					if (role == 'DC Backup') {
						error += '<p>' + _('If everything else went correct and this is just a temporary network problem, you should execute %s as root on that backup system.', '<pre>univention-add-app ' + component + ' -m</pre>') + '</p>';
					}
					error += '<p>' + _('Further information can be found in the following log file on each of the involved systems: %s', '<br /><em>/var/log/univention/management-console-module-appcenter.log</em>') + '</p>';
				}
				return error;
			});
			this._progressBar._errors = errors;
			this._progressBar.stop(lang.hitch(this, '_restartOrReload'), undefined, true);
		},

		_restartOrReload: function() {
			// update the list of apps
			this.updateApplications();

			libServer.askRestart(_('A restart of the UMC server components may be necessary for the software changes to take effect.'));
		}
	});
});
