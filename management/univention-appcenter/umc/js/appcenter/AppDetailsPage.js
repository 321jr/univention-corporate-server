/*
 * Copyright 2013-2015 Univention GmbH
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
/*global define console window*/

define([
	"dojo/_base/declare",
	"dojo/_base/lang",
	"dojo/_base/kernel",
	"dojo/_base/array",
	"dojo/promise/all",
	"dojo/when",
	"dojo/query",
	"dojo/io-query",
	"dojo/topic",
	"dojo/Deferred",
	"dojo/dom-construct",
	"dojo/dom-class",
	"dojo/dom-style",
	"dojo/store/Memory",
	"dojo/store/Observable",
	"dojox/image/LightboxNano",
	"umc/app",
	"umc/tools",
	"umc/dialog",
	"umc/widgets/TitlePane",
	"umc/widgets/ContainerWidget",
	"umc/widgets/ProgressBar",
	"umc/widgets/Page",
	"umc/widgets/Text",
	"umc/widgets/Grid",
	"umc/widgets/Tooltip",
	"umc/modules/appcenter/AppCenterGallery",
	"umc/modules/appcenter/App",
	"umc/modules/appcenter/Carousel",
	"umc/i18n!umc/modules/appcenter"
], function(declare, lang, kernel, array, all, when, query, ioQuery, topic, Deferred, domConstruct, domClass, domStyle, Memory, Observable, Lightbox, UMCApplication, tools, dialog, TitlePane, ContainerWidget, ProgressBar, Page, Text, Grid, Tooltip, AppCenterGallery, App, Carousel, _) {

	var adaptedGrid = declare([Grid], {
		_updateContextActions: function() {
			this.inherited(arguments);
			domStyle.set(this._contextActionsToolbar.domNode, 'visibility', 'visible');
		}
	});

	return declare("umc.modules.appcenter.AppDetailsPage", [ Page ], {
		appLoadingDeferred: null,
		standbyDuring: null, // parents standby method must be passed. weird IE-Bug (#29587)
		'class': 'umcAppDetailsPage',
		standby: null,

		title: _("App management"),
		noFooter: true,
		getAppCommand: 'appcenter/get',

		navBootstrapClasses: 'col-xs-12 col-sm-12 col-md-12 col-lg-12',
		mainBootstrapClasses: 'col-xs-12 col-sm-12 col-md-12 col-lg-12',
		_initialBootstrapClasses: 'col-xs-12 col-sm-12 col-md-12 col-lg-12',

		backLabel: _('Back to overview'),
		detailsDialog: null,
		configDialog: null,
		isSubPage: false,

		appCenterInformation:
			'<p>' + _('Univention App Center is the simplest method to install or uninstall applications on Univention Corporate Server.') + '</p>' +
			'<p>' + _('Univention always receives an estranged notification for statistical purposes upon installation and uninstallation of an application in Univention App Center that is only saved at Univention for data processing and will not be forwarded to any third party.') + '</p>' +
			'<p>' + _('Depending on the guideline of the respective application vendor an updated UCS license key with so-called key identification (Key ID) is required for the installation of an application. In this case, the Key ID will be sent to Univention together with the notification. As a result the application vendor receives a message from Univention with the following information:') +
				'<ul>' +
					'<li>' + _('Name of the installed application') + '</li>' +
					'<li>' + _('Registered email address') + '</li>' +
				'</ul>' +
			_('The description of every application includes a respective indication for such cases.') + '</p>' +
			'<p>' + _('If your UCS environment does not have such a key at it\'s disposal (e.g. UCS Free-for-personal-Use Edition) and the vendor requires a Key ID, you will be asked to request an updated license key directly from Univention. Afterwards the new key can be applied.') + '</p>' +
			'<p>' + _('The sale of licenses, maintenance or support for the applications uses the default processes of the respective vendor and is not part of Univention App Center.') + '</p>',

		postMixInProperties: function() {
			this.inherited(arguments);

			this.appLoadingDeferred = new Deferred();
			this._progressBar = new ProgressBar({});
			this.own(this._progressBar);
			this._grid = new AppCenterGallery({});
			this.own(this._grid);

			this.headerButtons = [{
				name: 'close',
				iconClass: this.isSubPage ? 'umcArrowLeftIconWhite' : 'umcCloseIconWhite',
				label: this.backLabel,
				align: 'left',
				callback: lang.hitch(this, 'onBack')
			}];
		},

		_setAppAttr: function(app) {
			this._set('app', app);
			if (this.appLoadingDeferred.isFulfilled()) {
				this.appLoadingDeferred = new Deferred();
			}
			var appLoaded = app;
			if (!app.fully_loaded) {
				// app is just {id: '...'}!
				// we need to ask the server,
				// it is not yet known!
				appLoaded = tools.umcpCommand(this.getAppCommand, {'application': app.id}).then(function(data) {
					return data.result;
				});
			}
			when(appLoaded).then(lang.hitch(this, function(loadedApp) {
				if (loadedApp === null) {
					this.onBack();
					this.appLoadingDeferred.reject();
					return;
				}
				var app = new App(loadedApp, this);
				this._set('app', app);
				this.hostDialog.set('app', app);
				this.detailsDialog.set('app', app);
				this.configDialog.set('app', app);
				this.set('headerText', app.name);
				//this.set('helpText', app.longDescription);
				this.buildInnerPage();
				this.appLoadingDeferred.resolve();
			}));
		},

		_appIsInstalledInDomain: function() {
			return this._appCountInstallations() > 0;
		},

		_appCountInstallations: function() {
			var sum = 0;
			array.forEach(this.app.installationData, function(item) {
				sum += item.isInstalled;
			});
			return sum;
		},

		reloadPage: function() {
			// reset same app, but only pass the id => loads new from server
			this.set('app', {id: this.app.id});
			return this.appLoadingDeferred;
		},

		getButtons: function() {
			var buttons = [];
			if (this.app.canOpen() && this.app.isInstalled) {
				buttons.push({
					name: 'open',
					label: this.app.getOpenLabel(),
					defaultButton: true,
					'class': 'umcAppButton umcAppButtonFirstRow',
					callback: lang.hitch(this, function() {
						this.app.open();
					})
				});
			} else if (this.app.canInstall) {
				buttons.push({
					name: 'install',
					label: _('Install'),
					'class': 'umcAppButton',
					isStandardAction: true,
					isContextAction: false,
					iconClass: 'umcIconAdd',
					callback: lang.hitch(this.app, 'install')
				});
			}

			if (this.app.useShop) {
				buttons.push({
					name: 'shop',
					label: _('Buy'),
					iconClass: 'umcShopIcon',
					'class': 'umcAppButton umcAppButtonFirstRow',
					callback: lang.hitch(this, 'openShop')
				});
			}
			return buttons;
		},

		getActionButtons: function() {
			var buttons = [];
			if (this.app.canInstall) {
				buttons.push({
					name: 'install',
					label: _('Install'),
					'class': 'umcAppButton',
					isStandardAction: true,
					isContextAction: false,
					iconClass: 'umcIconAdd',
					callback: lang.hitch(this.app, 'install')
				});
			}
			if (this.app.canOpenInDomain()) {
				buttons.push({
					name: 'open',
					label: this.app.getOpenLabel(),
					'class': 'umcAppButton umcAppButtonFirstRow',
					isContextAction: true,
					isStandardAction: true,
					canExecute: lang.hitch(this, function(app) {
						return app.data.canOpen();
					}),
					callback: lang.hitch(this, function(host, app) {
						app[0].data.open();
					})
				});
			}
			if (this.app.canDisableInDomain()) {
				buttons.push({
					name: 'disable',
					label: _('Continue using'),
					'class': 'umcAppButton umcAppButtonFirstRow',
					isContextAction: true,
					isStandardAction: true,
					canExecute: lang.hitch(this, function(app) {
						return app.data.canDisable();
					}),
					callback: lang.hitch(this, 'disableApp')
				});
			}
			if (this.app.isDocker) {
				buttons.push({
					name: 'configure',
					label: _('Configuration'),
					align: 'right',
					canExecute: lang.hitch(this, function(app) {
						return app.data.canConfigure();
					}),
					callback: lang.hitch(this, 'configureApp')
				});
			}
			if (this.app.canUninstallInDomain()) {
				buttons.push({
					name: 'uninstall',
					label: _('Uninstall'),
					isContextAction: true,
					isStandardAction: true,
					'class': 'umcAppButton',
					canExecute: lang.hitch(this, function(app) {
						return app.data.canUninstall();
					}),
					callback: lang.hitch(this, function(host, app) {
						app[0].data.uninstall();
					})
				});
			}
			if (this.app.canUpgradeInDomain()) {
				buttons.push({
					name: 'update',
					label: _('Upgrade'),
					isContextAction: true,
					isStandardAction: true,
					canExecute: lang.hitch(this, function(app) {
						return app.data.canUpgrade();
					}),
					callback: lang.hitch(this, function(host, app) {
						app[0].data.upgrade();
					})
				});
			}
			return buttons;
		},

		buildInnerPage: function() {
			if (this._icon) {
				this.removeChild(this._icon);
				this._icon.destroyRecursive();
				this._icon = null;
			}
			var suffix = this.app.logoDetailPage ? '-detailpage' : '';
			var icon_class = this._grid.getIconClass(this.app, suffix);
			if (icon_class) {
				this._icon = new ContainerWidget({
					region: 'nav',
					'class': icon_class + ' icon',
				});
				this.addChild(this._icon, 0);
			}

			if (this._navHeaderButtonContainer) {
				this.removeChild(this._navHeaderButtonContainer);
				//TODO fix
				//this._navHeaderButtonContainer.destroyRecursive();
				this._navHeaderButtonContainer = null;
			}
			this._navHeaderButtonContainer = new ContainerWidget({
				region: 'nav',
				'class': 'navHeaderButton'
			});

			this._navHeaderButtonContainer.addChild(this._headerTextPane, 0);

			var vendor = this._detailFieldCustomVendor();
			if (vendor) {
				var _vendorTextPane = new Text({
					content: vendor
				});
				this._navHeaderButtonContainer.addChild(_vendorTextPane);
			}

			if (this.app.isInstalled || this.app.getHosts().length) {
				var installedText = new Text({
					content: _('Installed')
				});
				this._navHeaderButtonContainer.addChild(installedText);
			} else {
				var categoryButtons = this._detailFieldCustomCategories();
				if (categoryButtons) {
					this._navHeaderButtonContainer.domNode.appendChild(categoryButtons);
				}
			}

			this.set('navButtons', this.getButtons());
			this._navButtons.set('style', {'margin-left': '-0.2em', 'margin-top': '1em'});
			this._navHeaderButtonContainer.addChild(this._navButtons);

			this.addChild(this._navHeaderButtonContainer);
			this.own(this._navHeaderButtonContainer);

			if (this._navHeaderRatingContainer) {
				this.removeChild(this._navHeaderRatingContainer);
				this._navHeaderRatingContainer.destroyRecursive();
				this._navHeaderRatingContainer = null;
			}
			this._navHeaderRatingContainer = new ContainerWidget({
				region: 'nav',
				'class': 'navHeaderRating'
			});
			this.addChild(this._navHeaderRatingContainer);
			this.own(this._navHeaderRatingContainer);
			array.forEach(this.app.rating, lang.hitch(this, function(rating) {
				var ratingText = new Text({
					content: rating.label,
					'class': 'umcAppRating' + rating.value
				});
				this._navHeaderRatingContainer.addChild(ratingText);
				var tooltip = new Tooltip({
					label: rating.description,
					connectId: [ ratingText.domNode ]
				});
				this._navHeaderRatingContainer.own(tooltip);
			}));

			if (this._mainRegionContainer) {
				this.removeChild(this._mainRegionContainer);
				this._mainRegionContainer.destroyRecursive();
				this._mainRegionContainer = null;
			}
			this._mainRegionContainer = new ContainerWidget({});
			this.addChild(this._mainRegionContainer);
			this.own(this._mainRegionContainer);

			if (this.app.isInstalled || this.app.getHosts().length > 0) {
				var usage = this.app.readme;
				if (usage) {
					usage = lang.replace(usage, this.app);
				} else {
					usage = this._detailFieldCustomUsage();
				}
				if (usage) {
					usageHeader = new Text({
						content: _('First steps'), 
						'class': 'mainHeader'
					});
					this._mainRegionContainer.addChild(usageHeader);

					var usagePane = new Text({
						content: usage,
						'class': 'usage'
					});
					this._mainRegionContainer.addChild(usagePane);
				}

				var gridHeader = new Text({
					content: _('Manage domain wide installations'),
					'class': 'mainHeader'
				});
				this._mainRegionContainer.addChild(gridHeader);

				var actions = this.getActionButtons();

				var columns = [{
					name: 'server',
					label: _('Server')
				}, {
					name: 'appStatus',
					label: _('Status')
				}];

				var myStore = new Observable(new Memory({
					data: this.app.getHosts()
				}));
				this._installedAppsGrid = new adaptedGrid({
					'class': 'appDetailsPageGrid',
					actions: actions,
					columns: columns,
					moduleStore: myStore,
					gridOptions: {
						'class': 'appDetailsPageGridContent'
					}
				});
				this._mainRegionContainer.addChild(this._installedAppsGrid);
			}

			this._detailsContainer = new ContainerWidget({
				'class': 'detailsContainer'
			});

			var descriptionContainerClass = 'descriptionContainer';
			descriptionContainerClass += this.app.longDescription.length > 360 ? ' longText' : '';
			var descriptionContainer = new ContainerWidget({
				'class': descriptionContainerClass
			});
			domConstruct.create('div', {
				innerHTML: this.app.longDescription
			}, descriptionContainer.domNode);
			this._detailsContainer.addChild(descriptionContainer);

			if (this.app.screenshot) {
				var styleContainer = new ContainerWidget({
					'class': 'carouselWrapper'
				});

				this.carousel = new Carousel({
					items: [{src: this.app.screenshot}]
				});
				styleContainer.addChild(this.carousel);
				this._detailsContainer.addChild(styleContainer);
			}

			// for an uninstalled app show details (open TitlePane) at the top of main
			// otherwise close the Titlepane and move it under the grid
			var isOpen = true;
			if (this.app.isInstalled || this.app.getHosts().length) {
				isOpen = false;
			}
			var detailsPane = new TitlePane({
				open: isOpen,
				//class: 'installedAppDetailsPane',
				title: _('Details'),
				content: this._detailsContainer,
				'class': 'appDetailsPane'
			});
			this._mainRegionContainer.addChild(detailsPane, isOpen ? 0 : null);

			//footer
			//TODO just for testing
			domConstruct.empty(this._footer.domNode);
			domStyle.set(this._footer.domNode, 'margin-bottom', '9em');

			domConstruct.create('span', {
				innerHTML: _('More information'),
				'class': 'mainHeader'
			}, this._footer.domNode);

			var footerLeft = new ContainerWidget({
				'class': 'appDetailsFooter'
			});
			this._footer.own(footerLeft);
			this._footer.addChild(footerLeft);
			var footerRight = new ContainerWidget({
				'class': 'appDetailsFooter'
			});
			this._footer.own(footerRight);
			this._footer.addChild(footerRight);


			this._detailsTable = domConstruct.create('table', {
				style: {borderSpacing: '1em 0.1em'}
			});
			if (this.app.hasMaintainer()) {
				this.addToDetails(_('Vendor'), 'Vendor');
				this.addToDetails(_('App provider'), 'Maintainer');
			} else {
				this.addToDetails(_('App provider'), 'Vendor');
			}
			this.addToDetails(_('Contact'), 'Contact');
			this.addToDetails(_('More information'), 'Website');
			this.addToDetails(_('Support'), 'SupportURL');
			this.addToDetails(_('Installed version'), 'Version');
			this.addToDetails(_('Candidate version'), 'CandidateVersion');
			this.addToDetails(_('Categories'), 'Categories');
			this.addToDetails(_('End of life'), 'EndOfLife');

			domConstruct.place(this._detailsTable, footerLeft.domNode);

			if (this._detailFieldCustomNotifyVendor()) {
				var notificationHeader = new Text({
					content: _('Notification'),
					style: 'font-weight: bold'
				});
				footerRight.addChild(notificationHeader);
				var notificationText = new Text({
					content: this._detailFieldCustomNotifyVendor()
				});
				footerRight.addChild(notificationText);
			}

			domStyle.set(document.querySelectorAll('.umcModule[id^="umc_modules_app"] .umcModuleContent')[0], 'overflow', 'visible');
			domStyle.set(this._main.domNode, 'margin-bottom', '2em');
		},

		openShop: function() {
			var shopUrl = this.app.shopURL || 'https://shop.univention.com';
			var w = window.open(shopUrl, '_blank');
			tools.umcpCommand('appcenter/buy', {application: this.app.id}).then(
				function(data) {
					var params = data.result;
					params.locale = kernel.locale.slice( 0, 2 ).toLowerCase();
					w.location = shopUrl + '?' + ioQuery.objectToQuery(params);
					w.focus();
				},
				function() {
					w.close();
				}
			);
		},

		disableApp: function(host, app) {
			var action = tools.umcpCommand('appcenter/enable_disable_app', {application: app[0].data.id, enable: false}).then(lang.hitch(this, 'reloadPage'));
			this.standbyDuring(action);
		},

		configureApp: function() {
			this.configDialog.showUp();
		},

		uninstallApp: function(host) {
			// before installing, user must read uninstall readme
			this.showReadme(this.app.readmeUninstall, _('Uninstall Information'), _('Uninstall')).then(lang.hitch(this, function() {
				this.callInstaller('uninstall', host).then(
					lang.hitch(this, function() {
						this.showReadme(this.app.readmePostUninstall, _('Uninstall Information')).then(lang.hitch(this, 'markupErrors'));
					}), lang.hitch(this, function() {
						this.markupErrors();
					})
				);
			}));
		},


		installAppDialog: function() {
			if (this.app.installationData) {
				var hosts = [];
				var removedDueToInstalled = [];
				var removedDueToRole = [];
				array.forEach(this.app.installationData, function(item) {
					if (item.canInstall()) {
						if (item.isLocal()) {
							hosts.unshift({
								label: item.displayName,
								id: item.hostName
							});
						} else {
							hosts.push({
								label: item.displayName,
								id: item.hostName
							});
						}
					} else {
						if (item.isInstalled) {
							removedDueToInstalled.push(item.displayName);
						} else if (!item.hasFittingRole()) {
							removedDueToRole.push(item.displayName);
						}
					}
				});
				var title =_("Do you really want to %(verb)s %(ids)s?",
					{verb: _('install'), ids: this.app.name});
				this.hostDialog.reset(title, hosts, removedDueToInstalled, removedDueToRole);
				this.hostDialog.showUp().then(lang.hitch(this, function(values) {
					this.installApp(values.host);
				}));
			} else {
				this.installApp();
			}
		},

		installApp: function(host) {
			this.showReadme(this.app.licenseAgreement, _('License agreement'), _('Accept license')).then(lang.hitch(this, function() {
				this.showReadme(this.app.readmeInstall, _('Install Information'), _('Install')).then(lang.hitch(this, function() {
					this.callInstaller('install', host).then(
						lang.hitch(this, function() {
							// put dedicated module of this app into favorites
							UMCApplication.addFavoriteModule('apps', this.app.id);
							this.showReadme(this.app.readmePostInstall, _('Install Information')).then(lang.hitch(this, 'markupErrors'));
						}), lang.hitch(this, function() {
							this.markupErrors();
						})
					);
				}));
			}));
		},

		upgradeApp: function(host) {
			// before installing, user must read update readme
			this.showReadme(this.app.candidateReadmeUpdate, _('Upgrade Information'), _('Upgrade')).then(lang.hitch(this, function() {
				this.callInstaller('update', host).then(
					lang.hitch(this, function() {
						this.showReadme(this.app.candidateReadmePostUpdate, _('Upgrade Information')).then(lang.hitch(this, 'markupErrors'));
					}), lang.hitch(this, function() {
						this.markupErrors();
					})
				);
			}));
		},

		showReadme: function(readme, title, acceptButtonLabel) {
			var readmeDeferred = new Deferred();
			if (!readme) {
				readmeDeferred.resolve();
			} else {
				var buttons;
				if (acceptButtonLabel) {
					buttons = [{
						name: 'no',
						label: _('Cancel'),
						'default': true
					}, {
						name: 'yes',
						label: acceptButtonLabel
					}];
				} else {
					buttons = [{
						name: 'yes',
						label: _('Continue'),
						'default': true
					}];
				}
				var content = '<h1>' + title + '</h1>';
				content += '<div style="max-height:250px; overflow:auto;">' +
						readme +
					'</div>';
				dialog.confirm(content, buttons, title).then(function(response) {
					if (response == 'yes') {
						readmeDeferred.resolve();
					} else {
						readmeDeferred.reject();
					}
				});
			}
			return readmeDeferred;
		},

		callInstaller: function(func, host, force, deferred, values) {
			deferred = deferred || new Deferred();
			var nonInteractive = new Deferred();
			deferred.then(lang.hitch(nonInteractive, 'resolve'));
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
				topic.publish('/umc/actions', this.moduleID, this.moduleFlavor, this.app.id, func);
			}

			var command = 'appcenter/invoke';
			if (!force) {
				command = 'appcenter/invoke_dry_run';
			}
			if (this.app.isDocker) {
				command = 'appcenter/docker/invoke';
			}
			var commandArguments = {
				'function': func,
				'application': this.app.id,
				'app': this.app.id,
				'host': host || '',
				'force': force === true,
				'values': values || {}
			};

			this._progressBar.reset(_('%s: Performing software tests on involved systems', this.app.name));
			this._progressBar._progressBar.set('value', Infinity); // TODO: Remove when this is done automatically by .reset()
			var invokation;
			if (this.app.isDocker) {
				invokation = tools.umcpProgressCommand(this._progressBar, command, commandArguments).then(
						undefined,
						undefined,
						lang.hitch(this, function(result) {
							var errors = array.map(result.intermediate, function(res) {
								if (res.level == 'WARNING' || res.level == 'ERROR' || res.level == 'CRITICAL') {
									return res.message;
								}
							});
							this._progressBar._addErrors(errors);
						})
				);
			} else {
				invokation = tools.umcpCommand(command, commandArguments);
			}
			invokation = invokation.then(lang.hitch(this, function(data) {
				if (!('result' in data)) {
					data = {'result': data};
				}
				var result = data.result;
				var headline = '';
				var actionLabel = tools.capitalize(verb);
				var mayContinue = true;

				if ('success' in result) {
					if (result.success) {
						deferred.resolve();
					} else {
						deferred.reject();
					}
				} else if (!result.can_continue) {
					mayContinue = !result.serious_problems;
					if (mayContinue) {
						headline = _("Do you really want to %(verb)s %(ids)s?",
									{verb: verb, ids: this.app.name});
					} else {
						topic.publish('/umc/actions', this.moduleID, this.moduleFlavor, this.app.id, 'cannot-continue');
						headline = _('You cannot continue');
					}
					this.detailsDialog.reset(mayContinue, headline, actionLabel);
					if (this.app.isDocker && mayContinue) {
						this.detailsDialog.showConfiguration(func);
					}
					this.detailsDialog.showHardRequirements(result.invokation_forbidden_details, this);
					this.detailsDialog.showSoftRequirements(result.invokation_warning_details, this);
					if (result.software_changes_computed) {
						if (result.unreachable.length) {
							this.detailsDialog.showUnreachableHint(result.unreachable, result.master_unreachable);
						}
						var noHostInfo = tools.isEqual({}, result.hosts_info);
						if (func == 'update') {
							this.detailsDialog.showErrataHint();
						}
						this.detailsDialog.showPackageChanges(result.install, result.remove, result.broken, false, noHostInfo, host);
						tools.forIn(result.hosts_info, lang.hitch(this, function(host, host_info) {
							this.detailsDialog.showPackageChanges(host_info.result.install, host_info.result.remove, host_info.result.broken, !host_info.compatible_version, false, host);
						}));
					}
					nonInteractive.reject();
					this.detailsDialog.showUp().then(
						lang.hitch(this, function(values) {
							this.callInstaller(func, host, true, deferred, values);
						}),
						function() {
							deferred.reject();
						}
					);
				} else {
					var progressMessage = _("%(verb)s %(ids)s on %(host)s", {verb: verb1, ids: this.app.name, host: host || _('this host')});

					this.switchToProgressBar(progressMessage).then(
						function() {
							deferred.resolve();
						}, function() {
							deferred.reject();
						}
					);
				}
			}));
			this.standbyDuring(all([invokation, deferred, nonInteractive]), this._progressBar);
			return deferred;
		},

		showLicenseRequest: function(action) {
			topic.publish('/umc/actions', this.moduleID, this.moduleFlavor, 'request-license');
			if (this.udmAccessible) {
				topic.publish('/umc/license/activation');
			} else {
				// UDM is not present. Either because this is
				// not the DC Master or because the user is no
				// Administrator
				var msg;
				if (this.app.isMaster) {
					var loginAsAdminTag = '<a href="javascript:void(0)" onclick="require(\'umc/app\').relogin(\'Administrator\')">Administrator</a>';
					msg =
						'<p>' + _('You need to request and install a new license in order to use the Univention App Center.') + '</p>' +
						'<p>' + _('To do this please log in as %s and repeat the steps taken until this dialog. You will be guided through the installation.', loginAsAdminTag) + '</p>';
				} else {
					var hostLink;
					if (tools.status('username') == 'Administrator') {
						hostLink = '<a href="javascript:void(0)" onclick="require(\'umc/tools\').openRemoteSession(\'' + this.app.hostMaster + '\')">' + this.app.hostMaster + '</a>';
					} else {
						hostLink = '<a target="_blank" href="https://' + this.app.hostMaster + '/univention-management-console">' + this.app.hostMaster + '</a>';
					}
					var dialogName = _('Activation of UCS');
					msg =
						'<p>' + _('You need to request and install a new license in order to use the Univention App Center.') + '</p>' +
						'<p>' + _('To do this please log in on %(host)s as an administrator. Click on the gear-wheel symbol in the top right line of the screen and choose "%(dialogName)s". There you can request the new license.', {host: hostLink, dialogName: dialogName}) + '</p>' +
						'<p>' + _('After that you can "%(action)s" "%(app)s" here on this system.', {action: action, app: this.app.name}) + '</p>';
				}
				dialog.alert(msg);
			}
		},

		switchToProgressBar: function(msg, keepAlive) {
			var deferred = new Deferred();
			// One request needs to be active otherwise
			// module might be killed if user logs out
			// during installation: dpkg will be in a
			// broken state, Bug #30611.
			// dont handle any errors. a timeout is not
			// important. this command is just for the module
			// to stay alive
			if (keepAlive !== false) {
				tools.umcpCommand('appcenter/keep_alive', {}, false);
			}
			msg = msg || _('Another package operation is in progress.');
			var callback = lang.hitch(this, function() {
				if (this._progressBar.getErrors().errors.length) {
					deferred.reject();
				} else {
					deferred.resolve();
				}
			});
			this._progressBar.reset(msg);
			this._progressBar.auto('appcenter/progress',
				{},
				callback,
				undefined,
				undefined,
				true
			);
			return deferred;
		},

		markupErrors: function() {
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
			this._progressBar.stop(lang.hitch(this, 'restartOrReload'), undefined, true);
		},

		updateApplications: function() {
			// Is overwritten with AppCenterPage.updateApplications
			var deferred = new Deferred();
			deferred.resolve();
			return deferred;
		},

		restartOrReload: function() {
			tools.defer(lang.hitch(this, function() {
				// update the list of apps
				var deferred = tools.renewSession().then(lang.hitch(this, function() {
					var reloadPage = this.updateApplications().then(lang.hitch(this, 'reloadPage'));
					var reloadModules = UMCApplication.reloadModules();
					return all([reloadPage, reloadModules]).then(function() {
						tools.checkReloadRequired();
					});
				}));

				// show standby animation
				this._progressBar.reset(_('Updating session and module data...'));
				this._progressBar._progressBar.set('value', Infinity); // TODO: Remove when this is done automatically by .reset()
				this.standbyDuring(deferred, this._progressBar);
			}), 100);
		},

		_detailFieldCustomUsage: function() {
			var txts = [];
			var is_installed = this.app.isInstalled;
			var useractivationrequired = this.app.userActivationRequired;
			if (is_installed && useractivationrequired) {
				var domain_administration_link = _('Domain administration');
				if (UMCApplication.getModule('udm', 'users/user')) {
					domain_administration_link = lang.replace('<a href="javascript:void(0)" onclick="require(\'umc/app\').openModule(\'udm\', \'users/user\')">{name}</a>', {name : domain_administration_link});
				}
				txts.push(_('Users need to be modified in the %s in order to use this service.', domain_administration_link));
			}
			var moduleLink = this.app.getModuleLink();
			if (moduleLink) {
				txts.push(_('A module for the administration of the app is available: %s.', moduleLink));
			}
			var webInterface = this.app.getWebInterfaceTag();
			if (webInterface) {
				txts.push(_('The app provides a web interface: %s.', webInterface));
			}
			if (this.app.isDocker) {
				txts.push(_('%s uses a container technology for enhanced security and compatibility.', this.app.name));
			}
			if (txts.length) {
				return txts.join(' ');
			}
		},

		_detailFieldCustomCandidateVersion: function() {
			var version = this.app.version;
			var candidate_version = this.app.candidateVersion;
			var is_installed = this.app.isInstalled;
			if (candidate_version) {
				return candidate_version;
			}
			if (! is_installed) {
				return version;
			}
		},

		_detailFieldCustomVersion: function() {
			var version = this.app.version;
			var is_installed = this.app.isInstalled;
			if (is_installed) {
				return version;
			}
		},

		_detailFieldCustomWebsite: function() {
			var name = this.app.name;
			var website = this.app.website;
			if (name && website) {
				return '<a href="' + website + '" target="_blank">' + name + '</a>';
			}
		},

		_detailFieldCustomSupportURL: function() {
			var supportURL = this.app.supportURL;
			if (supportURL) {
				if (supportURL == 'None') {
					return _('No support option provided');
				}
				return '<a href="' + supportURL + '" target="_blank">' + _('Available support options') + '</a>';
			} else {
				return _('Please contact the provider of the application');
			}
		},

		_detailFieldCustomVendor: function() {
			var vendor = this.app.vendor;
			var website = this.app.websiteVendor;
			if (vendor && website) {
				return '<a href="' + website + '" target="_blank">' + vendor + '</a>';
			} else if (vendor) {
				return vendor;
			}
		},

		_detailFieldCustomMaintainer: function() {
			if (!this.app.hasMaintainer()) {
				return null;
			}
			var maintainer = this.app.maintainer;
			var website = this.app.websiteMaintainer;
			if (maintainer && website) {
				return '<a href="' + website + '" target="_blank">' + maintainer + '</a>';
			} else if (maintainer) {
				return maintainer;
			}
		},

		_detailFieldCustomContact: function() {
			var contact = this.app.contact;
			if (contact) {
				return '<a href="mailto:' + contact + '">' + contact + '</a>';
			}
		},

		_detailFieldCustomNotifyVendor: function() {
			if (this.app.withoutRepository) {
				// without repository: Uses UCS repository:
				//   strictly speaking, we get the information
				//   about installation by some access logs
				//   (although this is not sent on purpose)
				return null;
			}
			if (this.app.notifyVendor) {
				return _('This application will inform the app provider about (un)installation. The app provider may contact you.');
			} else {
				return _('This application will not inform the app provider about (un)installation.');
			}
		},

		_detailFieldCustomEndOfLife: function() {
			if (this.app.endOfLife) {
				var warning = _('This application will not get any further updates. We suggest to uninstall %(app)s and search for an alternative application.', {app: this.app.name});
				if (this.app.isCurrent) {
					warning += ' ' + _('Click on "%(button)s" if you want to continue running this application at your own risk.', {button: _('Continue using')});
				}
				return warning;
			}
		},

		_detailFieldCustomScreenshot: function() {
			if (this.app.screenshot) {
				return lang.replace('<img src="{url}" style="max-width: 90%; height:200px;" class="umcScreenshot" />', {
					url: this.app.screenshot
				});
			}
		},

		_detailFieldCustomCategories: function() {
			if (this.app.categories) {
				var categoriesContainerNode = domConstruct.create('div', {
					'class': 'categoryContainer'
				});
				this.app.categories.forEach(lang.hitch(this, function(category) {
					var categoryButton = domConstruct.create('button', {
						textContent: _(category),
						onclick: lang.hitch(this, function() { this.onBack(category); }),
						'class': 'categoryButton'
					});
					domConstruct.place(categoryButton, categoriesContainerNode);
				}));
				return categoriesContainerNode;
			}
		},

		addToDetails: function(label, attribute) {
			var value;
			var detailFunc = this['_detailFieldCustom' + attribute];
			if (detailFunc) {
				value = lang.hitch(this, detailFunc)();
			}
			if (! value) {
				return;
			}
			var tr = domConstruct.create('tr', {}, this._detailsTable);
			domConstruct.create('td', {innerHTML: label, style: {verticalAlign: 'top'}}, tr);
			if (typeof value == 'string') {
				domConstruct.create('td', {innerHTML: value}, tr);
			} else {
				// value is a DOM node
				var td = domConstruct.create('td', {}, tr);
				domConstruct.place(value, td, 'only');
			}
		},

		onBack: function() {
		}
	});
});

