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
/*global umc,define,require,console,document,window,getQuery,setTimeout*/

define([
	"dojo/_base/declare",
	"dojo/_base/lang",
	"dojo/_base/kernel",
	"dojo/_base/array",
	"dojo/_base/window",
	"dojo/window",
	"dojo/on",
	"dojo/mouse",
	"dojo/touch",
	"dojox/gesture/tap",
	"dojo/aspect",
	"dojo/has",
	"dojo/Evented",
	"dojo/Deferred",
	"dojo/promise/all",
	"dojo/cookie",
	"dojo/topic",
	"dojo/io-query",
	"dojo/store/Memory",
	"dojo/store/Observable",
	"dojo/dom",
	"dojo/dom-attr",
	"dojo/dom-class",
	"dojo/dom-geometry",
	"dojo/dom-construct",
	"put-selector/put",
	"dojo/hash",
	"dojox/html/styles",
	"dojox/html/entities",
	"dojox/gfx",
	"dijit/registry",
	"umc/tools",
	"umc/auth",
	"umc/dialog",
	"umc/store",
	"dijit/_WidgetBase",
	"dijit/Menu",
	"dijit/MenuItem",
	"dijit/PopupMenuItem",
	"dijit/MenuSeparator",
	"dijit/Tooltip",
	"dijit/form/DropDownButton",
	"dijit/layout/StackContainer",
	"umc/widgets/TabController",
	"umc/widgets/LiveSearchSidebar",
	"umc/widgets/GalleryPane",
	"umc/widgets/ContainerWidget",
	"umc/widgets/Page",
	"umc/widgets/Form",
	"umc/widgets/Button",
	"umc/widgets/Text",
	"./widgets/LanguageSwitch",
	"umc/i18n/tools",
	"umc/i18n!",
	"dojo/sniff" // has("ie"), has("ff")
], function(declare, lang, kernel, array, baseWin, win, on, mouse, touch, tap, aspect, has,
		Evented, Deferred, all, cookie, topic, ioQuery, Memory, Observable,
		dom, domAttr, domClass, domGeometry, domConstruct, put, hash, styles, entities, gfx, registry, tools, auth, dialog, store,
		_WidgetBase, Menu, MenuItem, PopupMenuItem, MenuSeparator, Tooltip, DropDownButton, StackContainer,
		TabController, LiveSearchSidebar, GalleryPane, ContainerWidget, Page, Form, Button, Text, LanguageSwitch,
		i18nTools, _
) {
	// cache UCR variables
	var _ucr = {};
	var _favoritesDisabled = false;
	var _initialHash = decodeURIComponent(hash());

	// helper function for sorting, sort indeces with priority < 0 to be at the end
	var _cmpPriority = function(x, y) {
		if (y.priority == x.priority) {
			return x._orgIndex - y._orgIndex;
		}
		return y.priority - x.priority;
	};

	// "short" cut (well at least more verbose) for checking for favorite module
	var isFavorite = function(mod) {
		return array.indexOf(mod.categories, '_favorites_') >= 0;
	};

	var _OverviewPane = declare([GalleryPane], {
//		categories: null,

		constructor: function(props) {
			lang.mixin(this, props);
		},

		postMixInProperties: function() {
			this.queryOptions = {
				sort: [{
					attribute: 'categoryPriority',
					descending: true
				}, {
					attribute: 'category',
					descending: false
				}, {
					attribute: 'priority',
					descending: true
				}, {
					attribute: 'name',
					descending: false
				}]
			};
		},

		getIconClass: function(item) {
			if (item.icon) {
				var icon;
				if (/\.svg$/.test(item.icon)) {
					icon = item.icon.replace(/\.svg$/, '');
					return tools.getIconClass(icon, 'scalable', '', 'background-size: contain;');
				}

				// for backwards compatibility we need to support png
				icon = lang.replace('{icon}.png', item);
				return tools.getIconClass(icon, 50);
			}
			return '';
		},

		_createFavoriteIcon: function(categoryColor, parentNode) {
			var _createIcon = function(nodeClass, color) {
				var node = domConstruct.create('div', { 'class': nodeClass }, parentNode);
				var surface = gfx.createSurface(node, 10, 10);
				surface.createPolyline([
					{x: 0, y: 0},
					{x: 0, y: 10},
					{x: 5, y: 5.6},
					{x: 10, y: 10},
					{x: 10, y: 0}
				]).setFill(color);
			};

			_createIcon('umcFavoriteIconInverted', 'white');
			_createIcon('umcFavoriteIconDefault', categoryColor);
		},

		renderRow: function(item, options) {
			var div = this.inherited(arguments);
			var category_for_color = item.category_for_color;
			var className = lang.replace('umcGalleryCategory-{0}', [category_for_color]);
			domClass.add(div.firstElementChild, className);
			if (isFavorite(item)) {
				var cat = require('umc/app').getCategory(category_for_color);
				if (cat) {
					this._createFavoriteIcon(cat.color, div.firstElementChild);
				}
			}
			return div;
		},

		getItemDescription: function(item) {
			return item.description;
		},

		updateQuery: function(searchPattern, searchQuery, category) {
			var query = function(obj) {
				// sub conditions
				var allCategories = !category;
				var matchesPattern = !searchPattern ||
					// for a given pattern, ignore 'pseudo' entries in _favorites_ category
					(searchQuery.test(null, obj) && obj.category != '_favorites_');
				var matchesCategory = true;
				if (!allCategories) {
					matchesCategory = obj.category == category.id;
				}
				else if (obj.category == '_favorites_') {
					// don't show duplicated modules
					matchesCategory = false;
				}

				// match separators OR modules with a valid class
				return matchesPattern && matchesCategory;
			};

			// set query
			this.set('query', query);
		}
	});

	var _ModuleStore = declare([Memory], {
		data: null,
		modules: null,

		categories: null,

		favoritesDisabled: false,

		idProperty: '$id$',

		constructor: function(modules, categories) {
			this.categories = this._createCategoryList(categories);
			this.setData(this._createModuleList(modules));
			this._pruneEmptyCategories();
		},

		_createModuleList: function(_modules) {
			_modules = _modules.sort(_cmpPriority);
			var modules = [];
			array.forEach(_modules, function(imod) {
				array.forEach(imod.categories || [], function(icat) {
					modules.push(this._createModuleItem(imod, icat));
				}, this);
			}, this);
			return modules;
		},

		_isNotShallowCopy: function(category){
			// to get the origin color of the category, we will ignore each
			// category that starts && ends with an underscore _
			// e.g. returns false for _favorites_ category
			var re = /^_.*_$/;
			return !re.test(category);
		},

		_isNotFavorites: function(cat) {
			return cat !== '_favorites_';
		},

		_createModuleItem: function(_item, categoryID) {
			// we need a uniqe ID for the store
			var item = lang.mixin({
				categories: []
			}, _item);
			item.$id$ = item.id + ':' + item.flavor;

			if (categoryID) {
				item.$id$ += '#' + categoryID;
				item.category = '' + categoryID;
				item.categoryPriority = lang.getObject('priority', false, this.getCategory(categoryID)) || 0;
			}
			else {
				item.category = '';
				item.categoryPriority = 0;
			}

			// by convention a link element has an url
			item.is_link = Boolean(item.url);
			item.is_shallow_copy = !this._isNotShallowCopy(item.category);
			item.category_for_color = item.category;
			if (item.is_shallow_copy && item.categories.length > 1) {
				item.category_for_color = array.filter(item.categories, this._isNotShallowCopy)[0] ||
					array.filter(item.categories, this._isNotFavorites)[0];
			}
			return item;
		},

		_createCategoryList: function(_categories) {
			var categories = array.map(_categories, function(icat, i) {
				return lang.mixin(icat, {
					_orgIndex: i,  // save the element's original index
					label: icat.name
				});
			});
			return categories.sort(_cmpPriority);
		},

		_pruneEmptyCategories: function() {
			var nonEmptyCategories = {'_favorites_': true};
			this.query().forEach(function(imod) {
				array.forEach(imod.categories, function(icat) {
					nonEmptyCategories[icat] = true;
				});
			});
			var categories = array.filter(this.categories, function(icat) {
				return nonEmptyCategories[icat.id] === true;
			});
			this.categories = categories;
		},

		setFavoritesString: function(favoritesStr) {
			favoritesStr = favoritesStr || '';
			array.forEach(lang.trim(favoritesStr).split(/\s*,\s*/), function(ientry) {
				this.addFavoriteModule.apply(this, ientry.split(':'));
			}, this);
		},

		_saveFavorites: function() {
			if (!tools.status('setupGui')) {
				return;
			}

			// get all favorite modules
			var modules = this.query({
				category: '_favorites_'
			});

			// save favorites as a comma separated list
			var favoritesStr = array.map(modules, function(imod) {
				return imod.flavor ? imod.id + ':' + imod.flavor : imod.id;
			}).join(',');

			// store updated favorites
			tools.setUserPreference({favorites: favoritesStr});
		},

		getCategories: function() {
			return this.categories; // Object[]
		},

		getCategory: function(/*String*/ id) {
			var res = array.filter(this.categories, function(icat) {
				return icat.id == id;
			});
			if (res.length <= 0) {
				return undefined; // undefined
			}
			return res[0];
		},

		getModules: function(/*String?*/ category) {
			var query = {};
			if (category) {
				query.categories = {
					test: function(categories) {
						return array.indexOf(categories, category) >= 0;
					}
				};
			}
			return this.query(query, {
				sort: _cmpPriority
			});
		},

		getModule: function(/*String?*/ id, /*String?*/ flavor, /*String?*/ category) {
			var query = {
				id: id,
				flavor: flavor || null,
				// by default, match categories != favorites category
				category: category || /^((?!_favorites_).)*$/
			};
			var res = this.query(query);
			if (res.length) {
				return res[0];
			}
			return undefined;
		},

		addFavoriteModule: function(/*String*/ id, /*String?*/ flavor) {
			var favoriteModule = this.getModule(id, flavor, '_favorites_');
			if (favoriteModule) {
				// module has already been added to the favorites
				return;
			}
			var _mod = this.getModule(id, flavor);
			if (_mod) {
				// add favorite to categories
				_mod.categories = _mod.categories.concat(['_favorites_']);
				this.put(_mod);
			}
			else {
				// module does not exist (on this server), we add a dummy module
				// (this is important when installing a new app which is automatically
				// added to the favorites)
				_mod = {
					id: id,
					flavor: flavor,
					name: id
				};
			}

			// add a module clone for favorite category
			var mod = this._createModuleItem(_mod, '_favorites_');
			this.add(mod);

			var favoritesButton = this.getCategory('_favorites_')._button;
			domClass.toggle(favoritesButton.domNode, 'favoritesHidden', (this.getModules('_favorites_').length === 0));

			// save settings
			this._saveFavorites();
		},

		removeFavoriteModule: function(/*String*/ id, /*String?*/ flavor) {
			// remove favorite module
			var favoriteModule = this.getModule(id, flavor, '_favorites_');
			if (favoriteModule) {
				this.remove(favoriteModule.$id$);
			}

			// remove favorites from categories
			var mod = this.getModule(id, flavor);
			if (mod && isFavorite(mod)) {
				mod.categories = array.filter(mod.categories, function(cat) { return cat !== '_favorites_'; });
				this.put(mod);
			}
			var favoritesButton = this.getCategory('_favorites_')._button;
			domClass.toggle(favoritesButton.domNode, 'favoritesHidden', (this.getModules('_favorites_').length === 0));
			// save settings
			this._saveFavorites();
		}
	});

	topic.subscribe('/umc/started', function() {

		var checkCertificateValidity = function() {
			var hostCert = parseInt(_ucr['ssl/validity/host'], 10);
			var rootCert = parseInt(_ucr['ssl/validity/root'], 10);
			var warning = parseInt(_ucr['ssl/validity/warning'], 10);
			var certExp = rootCert;
			var certType = _('SSL root certificate');
			if (rootCert >= hostCert) {
				certExp = hostCert;
				certType = _('SSL host certificate');
			}
			var today = new Date().getTime() / 1000 / 60 / 60 / 24; // now in days
			var days = certExp - today;
			if (days <= warning) {
				dialog.warn(_('The %(certificate)s will expire in %(days)d days and should be renewed!', {certificate: certType, days: days}));
			}
		};

		var checkShowStartupDialog = function() {
			var isUserAdmin = tools.status('username').toLowerCase() == 'administrator';
			var isUCRVariableEmpty = !Boolean(_ucr['umc/web/startupdialog']);
			var showStartupDialog = tools.isTrue(_ucr['umc/web/startupdialog']);
			var isDCMaster = _ucr['server/role'] == 'domaincontroller_master';
			if (!isDCMaster || !((isUCRVariableEmpty && tools.status('hasFreeLicense') && isUserAdmin) || (showStartupDialog && isUserAdmin))) {
				return;
			}

			require(["management/widgets/StartupDialog"], lang.hitch(this, function(StartupDialog) {
				var startupDialog = new StartupDialog({});
				startupDialog.on('hide', function() {
					// dialog is being closed
					// set the UCR variable to false to prevent any further popup
					var ucrStore = store('key', 'ucr');
					ucrStore.put({
						key: 'umc/web/startupdialog',
						value: 'false'
					});
					startupDialog.destroyRecursive();
				});
			}));
		};

		// run several checks
		checkCertificateValidity();
		checkShowStartupDialog();
	});

	var UmcHeader = declare([ContainerWidget], {

		// top tap bar (handed over upon instantiation)
		_tabController: null,
		_tabContainer: null,

		_headerRight: null,
		_mobileMenu: null,
		_hostInfo: null,
		_hostMenu: null,
		_menuMap: null,

		_resizeDeferred: null,
		_handleWindowResize: function() {
			if (this._resizeDeferred && !this._resizeDeferred.isFulfilled()) {
				this._resizeDeferred.cancel();
			}

			this._resizeDeferred = tools.defer(lang.hitch(this, function() {
				this.__updateHeaderAfterResize();
			}), 200);

			this._resizeDeferred.otherwise(function() { /* prevent logging of exception */ });
		},

		__updateHeaderAfterResize: function() {
			if (tools.status('overview') && !tools.status('singleModule')) {
				this._updateMoreTabsVisibility();
			}
		},

		setupGui: function() {
			// show the menu bar
			this.setupHeader();
			this.setupMenus();

			on(window, 'resize', lang.hitch(this, function() {
				this._handleWindowResize();
			}));
		},

		setupHeader: function() {
			if (tools.status('overview') && !tools.status('singleModule')) {
				this.setupBackToOverview();
				this._setupModuleTabs();
			}
			this._setupRightHeader();
		},

		_setupModuleTabs: function() {
			var Table = declare('Table', [ContainerWidget], {
				baseClass: 'table',
				buildRendering: function() {
					this.domNode = put('table');
					this.inherited(arguments);
				}
			});
			var TableRow = declare('TableRow', [ContainerWidget], {
				baseClass: 'tableRow',
				buildRendering: function() {
					this.domNode = put('tr');
					this.inherited(arguments);
				}
			});
			var TableCell = declare('TableCell', [_WidgetBase], {
				baseClass: 'tableCell',
				buildRendering: function() {
					this.domNode = put('td');
					this.inherited(arguments);
				},
				_setContentAttr: function(content) {
					this.domNode.innerHTML = content;
					this._set('content', content);
				}
			});

			this._moreTabsDropDownButton = new DropDownButton({
				'class': 'umcMoreTabsDropDownButton invisible',
				iconClass: '', // prevent 'dijitNoIcon' to be set
				dropDown: new Table({
					'class': 'umcMoreTabsDropDownMenuContent'
				})
			});
			aspect.after(this._moreTabsDropDownButton, 'openDropDown', lang.hitch(this, function(ret) {
				domClass.add(this._moreTabsDropDownButton.dropDown._popupWrapper, 'umcMoreTabsMenuPopupWrapper');
				return ret;
			}));

			var aspectHandlesMap = {};
			this._tabController.on('addChild', lang.hitch(this, function(module) {
				if (!module.isOverview) {
					var label = new TableCell({
						'class': 'label',
						content: module.title
					});
					var closeButton = new TableCell({
						'class': 'iconCell',
						content: '<div class="icon"></div>'
					});
					var menuItem = new TableRow({
						'class': 'dijitHidden',
						correspondingModuleID: module.id,
						_setLabelAttr: function(_label) {
							label.set('content', _label);
						}
					});

					label.on('click', lang.hitch(this._tabContainer, 'selectChild', module));
					closeButton.on('click', lang.hitch(this._tabContainer, 'removeChild', module));

					menuItem.addChild(label);
					menuItem.addChild(closeButton);
					this._moreTabsDropDownButton.dropDown.addChild(menuItem);

					this._updateMoreTabsVisibility();

					aspectHandlesMap[module.id] = aspect.after(module, '_setTitleAttr', lang.hitch(this, function(label) {
						var menuItemToUpdate = this._moreTabsDropDownButton.dropDown.getChildren().find(function(menuItem) {
							return menuItem.correspondingModuleID == module.id;
						});
						menuItemToUpdate.set('label', label);
						this._updateMoreTabsVisibility();
					}), true);
				}
			}));
			this._tabController.on('removeChild', lang.hitch(this, function(module) {
				aspectHandlesMap[module.id].remove();
				delete aspectHandlesMap[module.id];

				var menuItemToRemove = this._moreTabsDropDownButton.dropDown.getChildren().find(function(menuItem) {
					return menuItem.correspondingModuleID == module.id;
				});
				this._moreTabsDropDownButton.dropDown.removeChild(menuItemToRemove);
				this._updateMoreTabsVisibility();
			}));

			this.addChild(this._tabController);
			this.addChild(this._moreTabsDropDownButton);

			domClass.toggle(this._tabController.domNode, 'dijitHidden', tools.isTrue(tools.status('mobileView')));
			domClass.toggle(this._moreTabsDropDownButton.domNode, 'dijitHidden', tools.isTrue(tools.status('mobileView')));
		},

		_updateMoreTabsVisibility: function() {
			this._resetMoreTabsVisibility();

			// get available width for tabs and the width the tabs currently occupy
			var headerWidth = domGeometry.getContentBox(this.domNode).w;
			var moreTabsWidth = domGeometry.getMarginBox(this._moreTabsDropDownButton.domNode).w;
			var backToOverviewWidth = domGeometry.getMarginBox(this._backToOverviewButton.domNode).w;
			var headerRightWidth = domGeometry.getMarginBox(this._headerRight.domNode).w;
			var extraPadding = 10;
			var availableWidthForTabs = headerWidth - (headerRightWidth + backToOverviewWidth + moreTabsWidth + extraPadding);
			var tabsWidth = domGeometry.getMarginBox(this._tabController.domNode).w;

			// If tabs occupy more space than available hide one tab after another until
			// they occupy less space than available.
			// Also show a drop down button that opens a menu with all hidden tabs.
			var tabIndexOffset = 0;
			var tabs = this._tabController.getChildren();
			tabs.shift(); // remove the overview tab
			var extraTabs = this._moreTabsDropDownButton.dropDown.getChildren();
			var numOfTabs = extraTabs.length;
			while (tabsWidth > availableWidthForTabs && tabIndexOffset < numOfTabs) {
				tabIndexOffset++;
				domClass.add(tabs[numOfTabs - tabIndexOffset].domNode, 'dijitHidden');
				domClass.remove(extraTabs[numOfTabs - tabIndexOffset].domNode, 'dijitHidden');
				tabsWidth = domGeometry.getMarginBox(this._tabController.domNode).w;
			}
			if (tabIndexOffset > 0) {
				domClass.remove(this._moreTabsDropDownButton.domNode, 'invisible');
			}
		},

		_resetMoreTabsVisibility: function() {
			var tabs = this._tabController.getChildren();
			tabs.shift(); // remove the overview tab
			array.forEach(tabs, function(tab) {
				domClass.remove(tab.domNode, 'dijitHidden');
			});
			var extraTabs = this._moreTabsDropDownButton.dropDown.getChildren();
			array.forEach(extraTabs, function(tab) {
				domClass.add(tab.domNode, 'dijitHidden');
			});
			domClass.add(this._moreTabsDropDownButton.domNode, 'invisible');
		},

		_setupRightHeader: function() {
			this._headerRight = new ContainerWidget({
				'class': 'umcHeaderRight'
			});
			this.addChild(this._headerRight);

			if (tools.status('overview') && !tools.status('singleModule')) {
				this.setupSearchField();
			}
			this._menuMap = {};
			if (tools.status('overview')) {
				this._setupMenu();
			}
			this._headerRight.addChild(new ContainerWidget({
				'class': 'univentionLogo'
			}));
		},

		setupSearchField: function() {
			this._searchSidebarWrapper = new ContainerWidget({
				'class': 'umcLiveSearchSidebarWrapper collapsed'
			});
			this._searchSidebar = new LiveSearchSidebar({
				searchLabel: _('Module search')
			});

			this._searchSidebarWrapper.on('click', lang.hitch(this, function() {
				this._searchSidebar.focus();
				this._expandSearch();
			}));

			on(this._searchSidebar._searchTextBox.textbox, 'blur', lang.hitch(this, function() {
				if (!this._searchSidebar.get('value')) {
					this._collapseSearch();
				}
			}));

			this._searchSidebarWrapper.addChild(this._searchSidebar);
			this._headerRight.addChild(this._searchSidebarWrapper);
		},

		_expandSearch: function() {
			domClass.remove(this._searchSidebarWrapper.domNode, 'collapsed');
			this._updateMoreTabsVisibility();
		},

		_collapseSearch: function() {
			domClass.add(this._searchSidebarWrapper.domNode, 'collapsed');
		},

		_setupMenu: function() {
			this._setupMobileMenuToggleButton();
			this._setupMobileMenu();
		},

		_setupMobileMenuToggleButton: function() {
			var mobileMenuToggleButton = this._createMobileMenuToggleButton();
			this._headerRight.addChild(mobileMenuToggleButton);
		},

		_setupMobileMenu: function() {
			// function definitions (jump to 'start')
			var createBase = lang.hitch(this, function() {
				this._mobileMenu = new ContainerWidget({
					'class': 'mobileMenu hasPermaHeader',
					menuSlides: null,
					permaHeader: null,
					popupHistory: []
				});
			});

			var addMenuSlides = lang.hitch(this, function() {
				var menuSlides = new ContainerWidget({
					'class': 'menuSlides popupSlideNormalTransition'
				});
				this._mobileMenu.menuSlides = menuSlides;
				this._mobileMenu.addChild(menuSlides);
			});

			var addMobileMenuToggleButton = lang.hitch(this, function() {
				var mobileMenuToggleButton = this._createMobileMenuToggleButton();
				this._mobileMenu.addChild(mobileMenuToggleButton);
			});

			var addUserMenu = lang.hitch(this, function() {
				var userMenu = this._buildMenuSlide('umcMenuUsername', 'Menu');
				domClass.replace(userMenu.domNode, 'visibleSlide', 'hiddenSlide');
				this._mobileMenu.menuSlides.addChild(userMenu);
				this._menuMap[userMenu.id] = userMenu.menuSlideItemsContainer;
			});

			var addPermaHeader = lang.hitch(this, function() {
				//create permaHeader
				var permaHeader = new Text({
					content: 'Menu',
					'class': 'menuSlideHeader permaHeader fullWidthTile'
				});
				this._mobileMenu.permaHeader = permaHeader;
				this._mobileMenu.addChild(permaHeader);

				//add listeners
				this._mobileMenu.permaHeader.on(tap, lang.hitch(this, function() {
					var lastClickedPopupMenuItem = this._mobileMenu.popupHistory.pop();

					this._updateMobileMenuPermaHeaderForClosing(lastClickedPopupMenuItem);
					this._closeMobileMenuPopupFor(lastClickedPopupMenuItem);
				}));
			});

			var addCloseOverlay = lang.hitch(this, function() {
				this._mobileMenuCloseOverlay = new ContainerWidget({
					'class': 'mobileMenuCloseOverlay'
				});
				this._mobileMenuCloseOverlay.on(tap, lang.hitch(this, function() {
					this.closeMobileMenu();
				}));
				dojo.body().appendChild(this._mobileMenuCloseOverlay.domNode);
			});

			// start: building mobile menu
			createBase();
			addMenuSlides();
			addMobileMenuToggleButton();
			addUserMenu();
			addPermaHeader();
			addCloseOverlay();

			dojo.body().appendChild(this._mobileMenu.domNode);
		},

		_setupDesktopMenu: function() {
			// the host info and menu
			this._hostMenu = new Menu({});
			this._hostInfo = new DropDownButton({
				id: 'umcMenuHost',
				iconClass: 'umcServerIcon',
				label: tools.status('fqdn'),
				disabled: true,
				dropDown: this._hostMenu
			});
			this._headerRight.addChild(this._hostInfo);

			// display the username
			this._usernameButton = new DropDownButton({
				id: 'umcMenuUsername',
				'class': 'umcHeaderText',
				iconClass: 'umcUserIcon',
				label: tools.status('username'),
				dropDown: new Menu({})
			});
			this._headerRight.addChild(this._usernameButton);

			this._menuMap[this._usernameButton.id] = this._usernameButton.dropDown;
		},

		_buildMenuSlide: function(id, label, isSubMenu) {
			var headerClass = isSubMenu ? 'menuSlideHeader subMenu fullWidthTile' : 'menuSlideHeader fullWidthTile';
			var menuSlideHeader = new Text({
				content: label,
				'class': headerClass
			});
			var menuSlideItemsContainer = new ContainerWidget({
				'class': 'menuSlideItemsContainer'
			});

			var menuSlide = new ContainerWidget({
				id: id,
				'class': 'menuSlide hiddenSlide',
				menuSlideHeader: menuSlideHeader,
				menuSlideItemsContainer: menuSlideItemsContainer,
				popupMenuItem: null
			});
			menuSlide.addChild(menuSlideHeader);
			menuSlide.addChild(menuSlideItemsContainer);

			return menuSlide;
		},

		_handleDeprecatedMenuInstances: function(item) {
			if (item.isInstanceOf(PopupMenuItem)) {
				//create submneu
				var newSubmenu = {
					parentMenuId: item.$parentMenu$,
					priority: item.$priority$,
					label: item.label,
					popup: [],
					id: item.id
				};
				//add menu entries to submenu
				if (item.popup && item.popup.getChildren().length > 0) {
					menuEntries = item.popup.getChildren();
					array.forEach(menuEntries, function(menuEntry) {
						var newEntry = {
							priority: menuEntry.$priority$ || 0,
							label: menuEntry.label,
							onClick: menuEntry.onClick
						};
						newSubmenu.popup.push(newEntry);
					});
				}
				//destroy deprecated menu instance
				item.destroyRecursive();
				this.addSubMenu(newSubmenu);
			} else if (item.isInstanceOf(MenuItem)) {
				var newEntry = {
					parentMenuId: item.$parentMenu$ || "",
					priority: item.$priority$ || 0,
					id: item.id,
					label: item.label,
					onClick: item.onClick
				};
				item.destroyRecursive();
				this.addMenuEntry(newEntry);
			} else if (item.isInstanceOf(MenuSeparator)) {
				var newSeperator = {
					parentMenuId: item.$parentMenu$,
					priority: item.$priority$ || 0,
					id: item.id
				};
				item.destroyRecursive();
				this.addMenuEntry(newSeperator);
			}
		},

		addSubMenu: function(/*Object*/ item) {
			// adds a menu entry that when clicked opens a submenu.
			// Menu entries or other sub-menus can be added to this sub-menu.
			//
			// takes an object as paramter with the following properties:
			//	Required:
			//		label: String
			//		popup: Object[]
			//			Array of objects. Each object defines a menu entry that will be a child of
			//			this sub-menu.
			//			The objects needs to be in the format described at the 'addMenuEntry' method.
			//			Can be empty.
			//  Optional:
			//		priority: Number
			//			The priority affects at which position the MenuItem will be placed in the parent menu.
			//			The highest number is the first Menu entry, the lowest number the last.
			//			Defaults to 0.
			//		parentMenuId: String
			//			The id of the parentMenu as String. The Menu entry will be the child of that parent if it exists.
			//			Defaults to 'umcMenuUsername'.
			//		id: String


			//function definitions (jump to 'start')
			var _createPopupMenuItem = lang.hitch(this, function() {
				var _menuSlide = this._buildMenuSlide(item.id, item.label, true);
				var _parentSlide = registry.byId(item.parentMenuId || defaultParentMenu);
				var childItemsCounterNode = domConstruct.create('div', {
					'class': 'childItemsCounter'
				});
				popupMenuItem = new Text({
					priority: item.priority || 0,
					content: _(item.label),
					popup: _menuSlide,
					parentSlide: _parentSlide,
					childItemsCounter: 0,
					childItemsCounterNode: childItemsCounterNode,
					'class': 'dijitHidden menuItem popupMenuItem fullWidthTile'
				});
				//store a reference to the popupMenuItem in its popup
				popupMenuItem.popup.popupMenuItem = popupMenuItem;

				put(popupMenuItem.domNode,
						childItemsCounterNode,
						'+ div.popupMenuItemArrow' +
						'+ div.popupMenuItemArrowActive'
				);

				this._mobileMenu.menuSlides.addChild(popupMenuItem.popup);
				this._menuMap[popupMenuItem.popup.id] = popupMenuItem.popup.menuSlideItemsContainer;

				_addClickListeners();
			});

			var _addClickListeners = lang.hitch(this, function() {
				//open the popup of the popupMenuItem
				popupMenuItem.on(tap , lang.hitch(this, function() {
					this._openMobileMenuPopupFor(popupMenuItem);
					this._updateMobileMenuPermaHeaderForOpening(popupMenuItem);
				}));

				//close the popup of the popupMenuItem
				popupMenuItem.popup.menuSlideHeader.on(tap , lang.hitch(this, function() {
					var lastClickedPopupMenuItem = this._mobileMenu.popupHistory.pop();

					this._closeMobileMenuPopupFor(lastClickedPopupMenuItem);
					this._updateMobileMenuPermaHeaderForClosing(popupMenuItem);
				}));
			});

			var _addChildEntries = lang.hitch(this, function() {
				// add MenuEntries to the subMenu
				if (item.popup && item.popup.length > 0) {
					array.forEach(item.popup, lang.hitch(this, function(menuEntry) {
						menuEntry.parentMenuId = popupMenuItem.popup.id;
						if (menuEntry.popup) {
							this.addSubMenu(menuEntry);
						} else {
							this.addMenuEntry(menuEntry);
						}
					}));
				}
			});

			var _inserPopupMenuItem = lang.hitch(this, function() {
				// add the submenu at the correct position
				var menu = this._menuMap[item.parentMenuId || defaultParentMenu];

				// find the correct position for the entry
				var priorities = array.map(menu.getChildren(), function(ichild) {
					return ichild.priority || 0;
				});
				var itemPriority = item.priority || 0;
				var pos = 0;
				for (; pos < priorities.length; ++pos) {
					if (itemPriority > priorities[pos]) {
						break;
					}
				}
				menu.addChild(popupMenuItem, pos);
			});

			var _incrementPopupMenuItemCounter = function() {
				var parentMenu = registry.byId(item.parentMenuId || defaultParentMenu);
				if (parentMenu && parentMenu.popupMenuItem) {
					parentMenu.popupMenuItem.childItemsCounter++;
					parentMenu.popupMenuItem.childItemsCounterNode.innerHTML = parentMenu.popupMenuItem.childItemsCounter;
				}
			};

			//start: creating sub menu
			var defaultParentMenu = 'umcMenuUsername';
			var popupMenuItem;

			_createPopupMenuItem();
			_addChildEntries();
			_inserPopupMenuItem();
			_incrementPopupMenuItemCounter();
		},

		addMenuEntry: function(/*Object*/ item) {
			// takes an object as parameter with the following properties:
			//	Required:
			//		label: String
			//		onClick: Function
			//	Optional:
			//		priority: Number
			//			The priority affects at which position the MenuItem will be placed in the parent menu.
			//			The highest number is the first Menu entry, the lowest number the last.
			//			Defaults to 0.
			//		parentMenuId: String
			//			The id of the parentMenu as String. The Menu entry will be the
			//			child of that parent if it exists.
			//			Defaults to 'umcMenuUsername'
			//		id: String
			//
			//  To insert a Menu separator leave out the required parameters. Any or none optional parameters can still be passed.

			if (!tools.status('overview')) {
				return;
			}

			// handle old uses of addMenuEntry
			if (item.isInstanceOf &&
					(item.isInstanceOf(MenuItem) ||
					item.isInstanceOf(PopupMenuItem) ||
					item.isInstanceOf(MenuSeparator)) ) {
				this._handleDeprecatedMenuInstances(item);
				return;
			}

			//function definitions (jump to 'start')
			var _unhideParent = function() {
				// unhide the parent menu in case it is hidden
				if (parentMenu && parentMenu.popupMenuItem) {
					domClass.remove(parentMenu.popupMenuItem.domNode, 'dijitHidden');
				}
			};

			var _createMenuEntry = function() {
				if (!item.onClick && !item.label) {
					menuEntry = new Text({
						id: item.id,
						'class': 'menuItem separator fullWidthTile'
					});
				} else {
					menuEntry = new Text({
						priority: item.priority || 0,
						content: _(item.label),
						id: item.id,
						'class': 'menuItem fullWidthTile'

					});
					menuEntry.domNode.onclick = function() {
						item.onClick();
					};
				}
			};

			var _insertMenuEntry = lang.hitch(this, function() {
				// add the menuEntry to the correct menu
				var menu = this._menuMap[item.parentMenuId || defaultParentMenu];

				// find the correct position for the entry
				var priorities = array.map(menu.getChildren(), function(ichild) {
					return ichild.priority || 0;
				});
				var itemPriority = item.priority || 0;
				var pos = 0;
				for (; pos < priorities.length; ++pos) {
					if (itemPriority > priorities[pos]) {
						break;
					}
				}

				menu.addChild(menuEntry, pos);
			});

			var _incrementPopupMenuItemCounter = function() {
				//increase counter of the popupMenuItem
				if (!domClass.contains(menuEntry.domNode, 'separator')) {
					if (parentMenu && parentMenu.popupMenuItem) {
						parentMenu.popupMenuItem.childItemsCounter++;
						parentMenu.popupMenuItem.childItemsCounterNode.innerHTML = parentMenu.popupMenuItem.childItemsCounter;
					}
				}
			};

			//start: creating menu entry
			var defaultParentMenu = 'umcMenuUsername';
			var parentMenu = registry.byId(item.parentMenuId);
			var menuEntry;

			_unhideParent();
			_createMenuEntry();
			_insertMenuEntry();
			_incrementPopupMenuItemCounter();
		},

		addMenuSeparator: function(/*Object*/ item) {
			// takes an object as parameter with the following properties:
			//	Optional:
			//		priority: Number
			//			The priority affects at which position the MenuItem will be placed in the parent menu.
			//			The highest number is the first Menu entry, the lowest number the last.
			//			Defaults to 0.
			//		parentMenuId: String
			//			The id of the parentMenu as String. The Menu entry will be the
			//			child of that parent if it exists.
			//			Defaults to 'umcMenuUsername'
			//		id: String

			var _item = {
				priority: item ? item.priority : undefined,
				parentMenuId: item ? item.parentMenuId : undefined,
				id: item ? item.id : undefined
			};
			this.addMenuEntry(_item);
		},

		_openMobileMenuPopupFor: function(popupMenuItem) {
			domClass.remove(popupMenuItem.popup.domNode, 'hiddenSlide');
			domClass.add(popupMenuItem.domNode, 'menuItemActive menuItemActiveTransition');
			tools.defer(function() {
				domClass.replace(popupMenuItem.parentSlide.domNode, 'overlappedSlide', 'topLevelSlide');
				domClass.add(popupMenuItem.popup.domNode, 'visibleSlide topLevelSlide');
			}, 10);
		},

		_closeMobileMenuPopupFor: function(popupMenuItem) {
			if (!popupMenuItem) {
				return;
			}
			domClass.remove(popupMenuItem.popup.domNode, 'visibleSlide');
			domClass.remove(popupMenuItem.parentSlide.domNode, 'overlappedSlide');
			tools.defer(function() {
				domClass.replace(popupMenuItem.popup.domNode, 'hiddenSlide', 'topLevelSlide');
				domClass.add(popupMenuItem.parentSlide.domNode, 'topLevelSlide');
			}, 510);
			tools.defer(function() {
				domClass.remove(popupMenuItem.domNode, 'menuItemActive');
				tools.defer(function() {
					domClass.remove(popupMenuItem.domNode, 'menuItemActiveTransition');
				}, 400);
			}, 250);
		},

		_updateMobileMenuPermaHeaderForOpening: function(popupMenuItem) {
			this._mobileMenu.permaHeader.set('content', popupMenuItem.popup.menuSlideHeader.content);
			this._mobileMenu.popupHistory.push(popupMenuItem);
			domClass.toggle(this._mobileMenu.permaHeader.domNode, 'subMenu', domClass.contains(popupMenuItem.popup.menuSlideHeader.domNode, 'subMenu'));
		},

		_updateMobileMenuPermaHeaderForClosing: function(popupMenuItem) {
			if (!popupMenuItem) {
				return;
			}
			this._mobileMenu.permaHeader.set('content', popupMenuItem.parentSlide.menuSlideHeader.content);
			var isSubMenu = domClass.contains(popupMenuItem.parentSlide.menuSlideHeader.domNode, 'subMenu');
			domClass.toggle(this._mobileMenu.permaHeader.domNode, 'subMenu', isSubMenu);
		},

		setupBackToOverview: function() {
			this._backToOverviewButton = new Button({
				'class': 'umcBackToOverview',
				onClick: function() {
					require('umc/app').switchToOverview();
				}
			});
			this.addChild(this._backToOverviewButton);
		},

		toggleBackToOverviewVisibility: function(visible) {
			if (this._backToOverviewButton) {
				this._backToOverviewButton.set('visible', visible);
			}
		},

		_createMobileMenuToggleButton: function() {
			var mobileMenuToggleButton = new ContainerWidget({
				'class': 'umcMobileMenuToggleButton'
			});

			//create hamburger stripes
			put(mobileMenuToggleButton.domNode, 'div + div + div + div.umcMobileMenuToggleButtonTouchStyle');

			// add listeners
			if (has('touch')) {
				mobileMenuToggleButton.on(touch.press, function() {
					domClass.add(this, 'umcMobileMenuToggleButtonTouched');
				});
				mobileMenuToggleButton.on([touch.leave, touch.release], function() {
					tools.defer(lang.hitch(this, function() {
						domClass.remove(this, 'umcMobileMenuToggleButtonTouched');
					}), 300);
				});
			} else {
				mobileMenuToggleButton.on(mouse.enter, function() {
					domClass.add(this, 'umcMobileMenuToggleButtonHover');
				});
				var mobileToggleMouseLeave = on.pausable(mobileMenuToggleButton.domNode, mouse.leave, function() {
					domClass.remove(this, 'umcMobileMenuToggleButtonHover');
				});
			}
			mobileMenuToggleButton.on(tap, lang.hitch(this, function() {
				if (typeof mobileToggleMouseLeave !== 'undefined') {
					mobileToggleMouseLeave.pause();
				}
				tools.defer(function() {
					domClass.remove(mobileMenuToggleButton.domNode, 'umcMobileMenuToggleButtonHover');
				}, 510).then(function() {
					if (typeof mobileToggleMouseLeave !== 'undefined') {
						mobileToggleMouseLeave.resume();
					}
				});
				if (domClass.contains(dojo.body(), 'mobileMenuActive')) {
					this.closeMobileMenu();
				} else {
					this.openMobileMenu();
				}
			}));

			return mobileMenuToggleButton;
		},

		openMobileMenu: function() {
			domClass.toggle(dojo.body(), 'mobileMenuActive');
			tools.defer(function() {
				domClass.toggle(dojo.body(), 'mobileMenuToggleButtonActive');
			}, 510);
			this._moduleOpeningListener = this._tabController.on('selectChild', lang.hitch(this, function() {
				this.closeMobileMenu();
			}));
		},

		closeMobileMenu: function() {
			if (!domClass.contains(dojo.body(), 'mobileMenuActive')) {
				return;
			}
			domClass.remove(dojo.body(), 'mobileMenuActive');
			tools.defer(function() {
				domClass.toggle(dojo.body(), 'mobileMenuToggleButtonActive');
			}, 510);
			this._moduleOpeningListener.remove();
		},

		setupMenus: function() {
			// the settings context menu
			this.addMenuEntry(new PopupMenuItem({
				$parentMenu$: 'umcMenuUsername',
				$priority$: 60,
				label: _('Settings'),
				id: 'umcMenuSettings',
				popup: new Menu({}),
				'class': 'dijitHidden'
			}));

			this.addMenuEntry(new PopupMenuItem({
				$parentMenu$: 'umcMenuUsername',
				$priority$: 55,
				label: _('Switch language'),
				id: 'umcMenuLanguage',
				popup: LanguageSwitch()._languageMenu
			}));

			// the help context menu
			this.addMenuEntry(new PopupMenuItem({
				$parentMenu$: 'umcMenuUsername',
				$priority$: 50,
				label: _('Help'),
				id: 'umcMenuHelp',
				popup: new Menu({})
			}));

			// the logout button
			this.addMenuEntry(new MenuItem({
				$parentMenu$: 'umcMenuUsername',
				$priority$: -1,
				id: 'umcMenuLogout',
				label: _('Logout'),
				onClick: function() { require('umc/app').logout(); }
			}));

			this._setupHelpMenu();
			// TODO add into menu
			// this._setupHostInfoMenu();
		},

		_setupHelpMenu: function() {
			this.addMenuEntry(new MenuItem({
				$parentMenu$: 'umcMenuHelp',
				label: _('Help'),
				onClick: lang.hitch(this, 'showPageDialog', 'HelpPage', 'help', null, null)
			}));

			this.addMenuEntry(new MenuItem({
				$parentMenu$: 'umcMenuHelp',
				label: _('Feedback'),
				onClick: lang.hitch(this, '_showFeedbackPage')
			}));

			this._insertPiwikMenuItem();

			this.addMenuEntry(new MenuItem({
				$parentMenu$: 'umcMenuHelp',
				label: _('About UMC'),
				onClick: lang.hitch(this, 'showPageDialog', 'AboutPage!', 'about', null, null)
			}));

			this.addMenuEntry(new MenuSeparator({
				$parentMenu$: 'umcMenuHelp'
			}));

			this.addMenuEntry(new MenuItem({
				$parentMenu$: 'umcMenuHelp',
				label: _('UCS start site'),
				onClick: function() {
					topic.publish('/umc/actions', 'menu-help', 'ucs-start-site');
					var w = window.open('/ucs-overview?lang=' + kernel.locale, 'ucs-start-site');
					w.focus();
				}
			}));

			this.addMenuEntry(new MenuItem({
				$parentMenu$: 'umcMenuHelp',
				label: _('Univention Website'),
				onClick: function() {
					topic.publish('/umc/actions', 'menu-help', 'website');
					var w = window.open(_('umcUniventionUrl'), 'univention');
					w.focus();
				}
			}));
		},

		_insertPiwikMenuItem: function() {
			var isUserAdmin = tools.status('username').toLowerCase() == 'administrator';
			if (!(tools.status('hasFreeLicense') && isUserAdmin)) {
				return;
			}
			this.addMenuEntry(new MenuItem({
				$parentMenu$: 'umcMenuHelp',
				label: _('Usage statistics'),
				onClick: lang.hitch(this, 'showPageDialog', 'FeedbackPage', 'feedback', null, null)
			}));
		},

		_setupHostInfoMenu: function() {
			if (!this._hostInfo) {
				return;
			}
			// update the host information in the header
			var fqdn = tools.status('fqdn');
			tools.umcpCommand('get/hosts').then(lang.hitch(this, function(data) {
				var empty = data.result.length <= 1;
				empty = empty || data.result.length >= (parseInt(_ucr['umc/web/host_referrallimit'], 10) || 100);
				this._hostInfo.set('disabled', empty);

				var isIE89 = (has('ie') == 8 || has('ie') == 9);
				if (empty && isIE89) {
					// prevent IE displaying a disabled button with a shadowed text
					domAttr.set(this._hostInfo.focusNode, 'disabled', false);
				}

				if (empty) {
					return;
				}
				array.forEach(data.result, function(hostname) {
					this._hostMenu.addChild(new MenuItem({
						label: hostname,
						disabled: hostname === fqdn,
						onClick: lang.hitch(this, '_switchUMC', hostname)
					}));
				}, this);
			}));
		},

		_switchUMC: function(hostname) {
			topic.publish('/umc/actions', 'host-switch');
			tools.openRemoteSession(hostname);
		},

		showPageDialog: function(_PageRef, key, buttonsConf, additionCssClasses) {
			// publish action + set default values
			topic.publish('/umc/actions', 'menu-help', key);
			additionCssClasses = additionCssClasses || '';
			buttonsConf = buttonsConf || [{
				name: 'submit',
				'default': true,
				label: _('Close')
			}];

			// require given Page reference and display the dialog
			var deferred = new Deferred();
			require(["management/widgets/" + _PageRef], lang.hitch(this, function(_pageConf) {
				// prepare dict
				var pageConf = lang.mixin({
					'class': ''
				}, _pageConf);
				pageConf['class'] += ' ' + additionCssClasses;

				// create a new form to render the widgets
				var form = new Form(lang.mixin({
					region: 'main'
				}, pageConf));

				// create a page containing additional methods validate(),
				// _getValueAttr(), on() and onSubmit() in order to fake Form
				// behaviour for umc/dialog::confirmForm()
				var page = new Page(pageConf);
				page = lang.delegate(page, {
					validate: lang.hitch(form, 'validate'),
					_getValueAttr: lang.hitch(form, '_getValueAttr'),
					// fake call to on('submit', function)
					_callbacks: null,
					on: function(type, cb) {
						if (type == 'submit') {
							this._callbacks = this._callbacks || [];
							this._callbacks.push(cb);
						}
					},
					onSubmit: function(values) {
						array.forEach(this._callbacks, function(icb) {
							icb(values);
						});
					}
				});
				form.on('submit', lang.hitch(page, 'onSubmit'));

				// add elements to page
				page.addChild(form);
				page.addChild(new Text({
					'class': 'umcPageIcon',
					region: 'nav'
				}));

				// show dialog
				dialog.confirmForm({
					form: page,
					title: pageConf.headerText,
					'class': 'umcLargeDialog umcAppDialog',
					buttons: buttonsConf
				}).then(function(response) {
					deferred.resolve(response);
				}, function() {
					deferred.resolve(null);
				});
			}));
			return deferred;
		},

		_showFeedbackPage: function() {
			topic.publish('/umc/actions', 'menu-help', 'feedback');
			var url = _('umcFeedbackUrl') + '?umc=' + require('umc/app')._tabContainer.get('selectedChildWidget').title;
			var w = window.open(url, 'umcFeedback');
			w.focus();
		}
	});

	var app = new declare([Evented], {
		start: function(/*Object*/ props) {
			// summary:
			//		Start the UMC, i.e., render layout, request login for a new session etc.
			// props: Object
			//		The following properties may be given:
			//		* username, password: if both values are given, the UMC tries to directly
			//		  with these credentials.
			//		* module, flavor: if module is given, the module is started immediately,
			//		  flavor is optional.
			//		* overview: if false and a module is given for autostart, the overview and module header will
			//		  not been shown and the module cannot be closed

			// remove cookie from UCS 4.0 to prevent login problems
			cookie('UMCSessionId', null, {path: '/', expires: -1});
			cookie('UMCUsername', null, {path: '/', expires: -1});

			// save some config properties
			tools.status('overview', tools.isTrue(props.overview));
			// username will be overriden by final authenticated username
			tools.status('username', props.username || tools.getCookies().username);
			// password has been given in the query string... in this case we may cache it, as well
			tools.status('password', props.password);

			// check for mobile view
			if (win.getBox().w <= 550 || has('touch')) {
				tools.status('mobileView', true);
				domClass.add(dojo.body(), 'umcMobileView');
			}

			tools.status('app.loaded', new Deferred());

			if (typeof props.module == "string") {
				// a startup module is specified
				tools.status('autoStartModule', props.module);
				tools.status('autoStartFlavor', typeof props.flavor == "string" ? props.flavor : null);
			}

			topic.subscribe('/umc/authenticated', lang.hitch(this, '_authenticated'));
			auth.start();
		},

		_authenticated: function(username) {
			// save the username internally and as cookie
			tools.setUsernameCookie(username, { expires: 100, path: '/univention/' });
			tools.status('username', username);

			if (!tools.status('app.loaded').isFulfilled()) {
				// start the timer for session checking
				tools.checkSession(true);

				// setup static GUI part
				this.setupStaticGui();

				// load the modules
				return this.load().always(function() {
					tools.status('app.loaded').resolve();
				});
			}
		},

		_tabContainer: null,
		_topContainer: null,
		_overviewPage: null,
		_categoriesContainer: null,
		_setupStaticGui: false,
		_moduleStore: null,
		_categories: [],
		_loaded: false,
		_lastCategory: null,

		setupStaticGui: function() {
			// setup everything that can be set up statically

			// make sure that we have not build the GUI before
			if (this._setupStaticGui) {
				return;
			}

			if (has('touch')) {
				this.setupTouchDevices();
			}

			if (!tools.status('overview')) {
				domClass.toggle(baseWin.body(), 'umcHeadless', true);
			}

			// set up fundamental layout parts...

			this._topContainer = new ContainerWidget({
				id: 'umcTopContainer',
				domNode: dom.byId('umcTopContainer'),
				containerNode: dom.byId('umcTopContainer'),
				'class': 'umcTopContainer'
			});

			// module (and overview) container
			this._tabContainer = new StackContainer({
				'class': 'umcMainTabContainer dijitTabContainer dijitTabContainerTop'
			});

			// the tab bar
			this._tabController = new TabController({
				'class': 'umcMainTabController dijitTabContainer dijitTabContainerTop-tabs dijitHidden',
				containerId: this._tabContainer.id
			});

			// the header
			this._header = new UmcHeader({
				id: 'umcHeader',
				'class': 'umcHeader',
				_tabController: this._tabController,
				_tabContainer: this._tabContainer
			});

			this.registerTabSwitchHandling();

			// put everything together
			this._topContainer.addChild(this._header);
			this._topContainer.addChild(dialog.createNotificationMaster());
			this._topContainer.addChild(this._tabContainer);
			this._topContainer.startup();
			//this._updateScrolling();

			// subscribe to requests for opening modules and closing/focusing tabs
			topic.subscribe('/umc/modules/open', lang.hitch(this, 'openModule'));
			topic.subscribe('/umc/tabs/close', lang.hitch(this, 'closeTab'));
			topic.subscribe('/umc/tabs/focus', lang.hitch(this, 'focusTab'));

			var deferred = new Deferred();
			topic.subscribe('/umc/module/startup', function(callback) {
				deferred.then(callback);
			});
			on.once(this, 'ModulesLoaded', lang.hitch(this, function() {
				// run some checks (only if a overview page is available)
				deferred.resolve(tools.status('overview'));
				if (tools.status('overview')) {
					topic.publish('/umc/started');
				}
			}));

			this._setupStaticGui = true;
		},

		setupTouchDevices: function() {
			// add specific CSS class for touch devices (e.g., tablets)
			domClass.add(baseWin.body(), 'umcTouchDevices');
		},

		registerTabSwitchHandling: function() {
			// register events for closing and focusing
			this._tabContainer.watch('selectedChildWidget', lang.hitch(this, function(name, oldModule, newModule) {
				this._lastSelectedChild = oldModule;
				this._updateHeaderColor(oldModule, newModule);

				if (!newModule.moduleID) {
					// this is the overview page, not a module
					topic.publish('/umc/actions', 'overview');
					this._updateStateHash();
				} else {
					topic.publish('/umc/actions', newModule.moduleID, newModule.moduleFlavor, 'focus');
					this._updateStateHash();
				}
				var overviewShown = (newModule === this._overviewPage);
				this._header.toggleBackToOverviewVisibility(tools.status('numOfTabs') > 0);
				domClass.toggle(baseWin.body(), 'umcOverviewShown', overviewShown);
				domClass.toggle(baseWin.body(), 'umcOverviewNotShown', !overviewShown);
				if (!tools.status('mobileView')) {
					domClass.toggle(this._tabController.domNode, 'dijitHidden', (this._tabContainer.getChildren().length <= 1)); // hide/show tabbar
				}
				if (newModule.selectedChildWidget && newModule.selectedChildWidget._onShow) {
					newModule.selectedChildWidget._onShow();
				}
			}));
			aspect.before(this._tabContainer, 'removeChild', lang.hitch(this, function(module) {
				this._updateNumOfTabs(-1);
				topic.publish('/umc/actions', module.moduleID, module.moduleFlavor, 'close');
				this._header.toggleBackToOverviewVisibility(tools.status('numOfTabs') > 0);

				if (module == this._tabContainer.get('selectedChildWidget')) {
					if (array.indexOf(this._tabContainer.getChildren(), this._lastSelectedChild) !== -1) {
						this._tabContainer.selectChild(this._lastSelectedChild);
					} else {
						this.switchToOverview();
					}
				}
			}));
		},

		_updateHeaderColor: function(oldModule, newModule) {
			var headerColorCss;
			// remove color of oldModule if it was not the overview
			if (oldModule && oldModule.moduleID) {
				headerColorCss = lang.replace('headerColor-{categoryColor}', oldModule);
				domClass.remove(this._header.domNode, headerColorCss);
			}
			// add color of newModule if it is not the overview
			if (newModule.moduleID) {
				headerColorCss = lang.replace('headerColor-{categoryColor}', newModule);
				domClass.add(this._header.domNode, headerColorCss);
			}
		},

		switchToOverview: function() {
			if (array.indexOf(this._tabContainer.getChildren(), this._overviewPage) < 0) {
				return;  // overview is not displayed
			}
		//	topic.publish('/umc/actions', 'overview');
			this._tabContainer.selectChild(this._overviewPage);
		},

		load: function() {
			// make sure that we don't load the modules twice
			if (this._loaded) {
				return;
			}

			// load data dynamically
			var ucrDeferred = this._loadUcrVariables();
			var modulesDeferred = this._loadModules().then(lang.hitch(this, '_initModuleStore'));

			// wait for modules and the UCR variables to load
			return all([modulesDeferred, ucrDeferred]).then(lang.hitch(this, function() {
				this._loaded = true;
				this.onLoaded();
			}));
		},

		_loadUcrVariables: function() {
			return tools.ucr([
				'server/role',
				'system/setup/showloginmessage', // set to true when not joined
				'domainname',
				'hostname',
				'umc/web/feedback/mail',
				'umc/web/feedback/description',
				'umc/web/favorites/default',
				'umc/web/startupdialog',
				'umc/web/host_referrallimit',
				'umc/web/sso/newwindow',
				'umc/http/session/timeout',
				'ssl/validity/host',
				'ssl/validity/root',
				'ssl/validity/warning',
				'update/available',
				'update/reboot/required',
				'umc/web/piwik',
				'license/base',
				'uuid/license',
				'uuid/system',
				'version/releasename',
				'version/erratalevel',
				'version/patchlevel',
				'version/version'
			]).then(lang.hitch(this, function(res) {
				// save the ucr variables in a local variable
				lang.mixin(_ucr, res);
				tools.status('hasFreeLicense', tools.isFreeLicense(_ucr['license/base']));
				tools.status('uuidSystem', _ucr['uuid/system']);
				this._loadPiwik();
				this._saveVersionStatus();
				tools.status('umcWebSsoNewwindow', _ucr['umc/web/sso/newwindow']);
			}));
		},

		_loadPiwik: function() {
			var fakeUuid = '00000000-0000-0000-0000-000000000000';
			var isRealUuid = tools.status('uuidSystem') !== fakeUuid;
			var piwikUcrv = _ucr['umc/web/piwik'];
			var piwikUcrvIsSet = typeof piwikUcrv == 'string' && piwikUcrv !== '';
			var piwikAllowed = tools.isTrue(piwikUcrv) || (!piwikUcrvIsSet && tools.status('hasFreeLicense'));
			// use piwik for user action feedback if it is not switched off explicitely
			tools.status('piwikDisabled', !(piwikAllowed && isRealUuid));
			require(["umc/piwik"], function() {});
		},

		_saveVersionStatus: function() {
			tools.status('ucsVersion', lang.replace('{version/version}-{version/patchlevel} errata{version/erratalevel} ({version/releasename})', _ucr));
		},

		reloadModules: function() {
			tools.resetModules();
			return this._loadModules(true).then(lang.hitch(this, function(args) {
				var modules = args[0];
				var categories = args[1];

				this._grid.set('categories', categories);
				this._moduleStore.constructor(modules, categories);

				this._overviewPage.removeChild(this._categoryButtons);
				this.renderCategories();
				// select the previous selected category again (assuming it still exists after reload)
				this._updateQuery(this.category || {id: '_favorites_'});
			}));
		},

		_loadModules: function(reload) {
			var options = reload ? {reload: true} : null;
			var onlyLoadAutoStartModule = !tools.status('overview') && tools.status('autoStartModule');
			return all({
				modules: tools.umcpCommand('get/modules', options),
				categories: tools.umcpCommand('get/categories')
			}).then(lang.hitch(this, function(data) {
				// update progress
				var _modules = lang.getObject('modules.modules', false, data) || [];
				var _categories = lang.getObject('categories.categories', false, data) || [];

				if (onlyLoadAutoStartModule) {
					_modules = array.filter(_modules, function(imod) {
						var moduleMatched = tools.status('autoStartModule') == imod.id;
						var flavorMatched = !tools.status('autoStartFlavor') || tools.status('autoStartFlavor') == imod.flavor;
						return moduleMatched && flavorMatched;
					});
				}

				this._loadJavascriptModules(_modules);

				return [_modules, _categories];
			}));
		},

		_initModuleStore: function(args) {
			var modules = args[0];
			var categories = args[1];
			this._moduleStore = this._createModuleStore(modules, categories);
		},

		_createModuleStore: function(modules, categories) {
			return new Observable(new _ModuleStore(modules, categories));
		},

		_loadJavascriptModules: function(modules) {
			// register error handler
			require.on('error', function(err) {
				if (err.message == 'scriptError' && err.info[0].split("/").pop(-1) != 'piwik.js') {
					dialog.warn(_('Could not load module "%s".', err.info[0]));
					console.log('scriptError:', err);
				}
			});

			var loadedCount = [];

			tools.forEachAsync(modules, lang.hitch(this, function(imod) {
				var is_module = !Boolean(imod.url);
				if (is_module) {
					loadedCount.push(this._tryLoadingModule(imod));
				}
			})).then(lang.hitch(this, function() {
				all(loadedCount).always(lang.hitch(this, 'onModulesLoaded'));
			}));
		},

		_tryLoadingModule: function(module) {
			var deferred = new Deferred();
			deferred.then(null, function(msg) {
				if (msg) {
					console.warn(msg);
				}
			});
			try {
				var path = 'umc/modules/' + module.id;
				require([path], lang.hitch(this, function(baseClass) {
					if (typeof baseClass == "function" && tools.inheritsFrom(baseClass.prototype, 'umc.widgets._ModuleMixin')) {
						deferred.resolve(baseClass);
					} else if (baseClass === null) {
						deferred.cancel(lang.replace('Module could not be loaded: {0}', [path]));
					} else if (typeof baseClass === 'object') {
						require([lang.replace('{0}!{1}', [path, module.flavor || ''])], lang.hitch(this, function(baseClass) {
							if (typeof baseClass == "function" && tools.inheritsFrom(baseClass.prototype, 'umc.widgets._ModuleMixin')) {
								deferred.resolve(baseClass);
							} else {
								deferred.cancel(lang.replace('{0} is not a umc.widgets._ModuleMixin! (1}', [module.id, baseClass]));
							}
						}));
					} else {
						deferred.cancel(lang.replace('{0} is not a umc.widgets._ModuleMixin! (1}', [module.id, baseClass]));
					}
				}));
			} catch (err) {
				deferred.cancel(err);
			}
			return deferred;
		},

		onLoaded: function() {
			// updated status information from ucr variables
			tools.status('sessionTimeout', parseInt(_ucr['umc/http/session/timeout'], 10) || tools.status('sessionTimeout'));
			tools.status('feedbackAddress', _ucr['umc/web/feedback/mail'] || tools.status('feedbackAddress'));
			tools.status('feedbackSubject', _ucr['umc/web/feedback/description'] || tools.status('feedbackSubject'));

			var launchableModules = this._getLaunchableModules();
			tools.status('singleModule', launchableModules.length < 2);

			this.setupGui();

			var autoStartModule = tools.status('autoStartModule');
			var autoStartFlavor = tools.status('autoStartFlavor') || null;
			var props;
			if (autoStartModule && (launchableModules.length === 1 ? (launchableModules[0].id == autoStartModule && (launchableModules[0].flavor || null) == autoStartFlavor) : true)) {
				props = ioQuery.queryToObject(window.location.search.substring(1));
				array.forEach(['username', 'password', 'overview', 'lang', 'module', 'flavor'], function(key) {
					delete props[key];
				});
				props = {
					props: props
				};
			}

			if (!launchableModules.length) {
				dialog.alert(_('There is no module available for the authenticated user %s.', tools.status('username')));
			} else if (launchableModules.length === 1) {
				// if only one module exists open it
				var module = launchableModules[0];
				this.openModule(module.id, module.flavor, props);
			} else if (autoStartModule) {
				// if module is given in the query string, open it directly
				this.openModule(autoStartModule, autoStartFlavor, props);
			}
		},

		setupGui: function() {
			// make sure that we have not build the GUI before
			if (tools.status('setupGui')) {
				return;
			}

			// save hostname and domainname as status information
			tools.status('domainname', _ucr.domainname);
			tools.status('hostname', _ucr.hostname);
			tools.status('fqdn', _ucr.hostname + '.' + _ucr.domainname);

			window.document.title = lang.replace('{0} - {1}', [tools.status('fqdn'), window.document.title]);

			// setup menus
			this._header.setupGui();
			this._setupOverviewPage();
			this._setupStateHashing();

			// set a flag that GUI has been build up
			tools.status('setupGui', true);
			this.onGuiDone();
		},

		// return the index for the given module tab, i.e., the index regarding other
		// open tabs if the same module ID and flavor
		_getModuleTabIndex: function(tab) {
			var idx = 0;
			array.some(this._tabContainer.getChildren(), function(itab) {
				if (itab.id == tab.id) {
					return true;
				}
				if (itab.moduleID == tab.moduleID && itab.moduleFlavor == tab.moduleFlavor) {
					++idx;
				}
			}, this);
			return idx;
		},

		_updateStateHash: function() {
			tools.defer(lang.hitch(this, function() {
				var state = this._getStateHash();
				hash(state);
			}), 0);
		},

		_getStateHash: function() {
			var moduleTab = lang.getObject('_tabContainer.selectedChildWidget', false, this);
			var state = '';

			if (!moduleTab.isOverview) {
				// module tab
				state = 'module=' + lang.replace('{id}:{flavor}:{index}:{state}', {
					id: moduleTab.moduleID,
					flavor: moduleTab.moduleFlavor || '',
					index: this._getModuleTabIndex(moduleTab),
					state: moduleTab.moduleState
				});
			}
			else if (moduleTab.isOverview && this.category) {
				// overview tab with selected category
				state = 'category=' + this.category.id;
			}

			return decodeURIComponent(state);
		},

		_parseModuleStateHash: function(hash) {
			try {
				var allParts = hash.split(':');
				var mainParts = allParts.splice(0, 3);
				return {
					id: mainParts[0],
					flavor: mainParts[1] || undefined,
					index: mainParts[2] || 0,
					moduleState: allParts.join(':')
				};
			} catch(err) {
				return {};
			}
		},

		_reCategory: /^category=(.*)$/,
		_reModule: /^module=(.*)$/,
		_lastStateHash: '',
		_setupStateHashing: function() {
			topic.subscribe('/dojo/hashchange', lang.hitch(this, function(_hash) {
				var hash = decodeURIComponent(_hash);
				if (this._getStateHash() == hash || this._lastStateHash == hash) {
					// nothing to do
					this._lastStateHash = hash;
					return;
				}
				if (!hash) {
					// UMC overview page
					this.switchToOverview();
					return;
				}
				var match = hash.match(this._reModule);
				if (match) {
					// hash encodes module tab
					var state = this._parseModuleStateHash(match[1]);
					var similarModuleTabs = array.filter(this._tabContainer.getChildren(), function(itab) {
						return itab.moduleID == state.id && itab.moduleFlavor == state.flavor;
					});

					if (state.index < similarModuleTabs.length) {
						this.focusTab(similarModuleTabs[state.index]);
						similarModuleTabs[state.index].set('moduleState', state.moduleState);
					} else {
						this.openModule(state.id, state.flavor, {
							moduleState: state.moduleState
						});
					}
				}

				match = hash.match(this._reCategory);
				if (match) {
					// hash encodes a module category view
					this.switchToOverview();
					var category = this.getCategory(match[1]);
					if (category) {
						this._updateQuery(category);
					}
				}

				// save the called parameter
				this._lastStateHash = hash;
			}));

			if (_initialHash) {
				tools.defer(lang.partial(hash, _initialHash, true), 0);
			}
		},

		_setupOverviewPage: function() {
			if (!tools.status('overview')) {
				// no overview page is being displayed
				// (e.g., system setup in appliance scenario)
				return;
			}

			this._grid = new _OverviewPane({
				'class': 'umcOverviewPane',
//				categories: this.getCategories(),
				store: this._moduleStore,
				actions: [{
					name: 'open',
					label: _('Open module'),
					isDefaultAction: true,
					callback: lang.hitch(this, function(id, item) {
						if (!item.is_link) {
							this.openModule(item);
						}
					})
				}, {
					name: 'toggle_favorites',
					label: function(item) {
						return isFavorite(item) ? _('Remove from favorites') : _('Add to favorites');
					},
					callback: lang.hitch(this, function(id, item) {
						this._toggleFavoriteModule(item);
					})
				}]
			});

			this._overviewPage = new Page({
				noFooter: true,
				id: 'umcOverviewPage',
				title: 'Overview',
				isOverview: true,
				'class': 'umcOverviewContainer container'
			});

			this._searchText = new Text({
				'class': 'dijitHidden umcGalleryCategoryHeader'
			});

			this.renderCategories();
			this._overviewPage.addChild(this._searchText);
			this._overviewPage.addChild(this._grid);
			this._tabContainer.addChild(this._overviewPage, 0);
			this._tabController.hideChild(this._overviewPage);

			aspect.after(this._overviewPage, '_onShow', lang.hitch(this, '_focusSearchField'));
			this._registerGridEvents();

			// show the first visible category
			this._updateQuery(this._lastCategory);
		},

		renderCategories: function() {
			this._categoryButtons = new ContainerWidget({
				'class': 'umcCategoryBar'
			});
			this._overviewPage.addChild(this._categoryButtons, 0);
			array.forEach(this.getCategories(), lang.hitch(this, function(category) {
				var iconClass = '';
				if (category.icon) {
					iconClass = tools.getIconClass(category.icon, 70);
				}
				var color = category.color || 'white';
				if (has('touch')) {
					styles.insertCssRule(lang.replace('.umcGalleryWrapperItem .umcGalleryCategory-{id}.touched, .umcGalleryWrapperItem.umcGalleryItemActive .umcGalleryCategory-{id}', category), lang.replace('background-color: {0}; ', [color]));
				} else {
					styles.insertCssRule(lang.replace('.umcGalleryWrapperItem .umcGalleryCategory-{id}:hover, .umcGalleryWrapperItem.umcGalleryItemActive .umcGalleryCategory-{id}', category), lang.replace('background-color: {0}; ', [color]));
				}
				var button = new Button({
					label: category.label,
					'class': lang.replace('umcCategory-{id}', category),
					onClick: lang.hitch(this, function() {
						this._lastCategory = category;
						this._updateQuery(category);

						this._header._searchSidebar._searchTextBox._updateInlineLabelVisibility();
						this._header._collapseSearch();
						this._header._updateMoreTabsVisibility();
					}),
					color: color,
					categoryID: category.id,
					iconClass: iconClass
				});

				// add a node to the button for the colored circle
				put(button.iconNode, '-div.umcCategoryButtonCircleWrapper div.circle <', button.iconNode);
				styles.insertCssRule(lang.replace('.umcCategory-{id} .umcCategoryButtonCircleWrapper .circle', category), lang.replace('background-color: {0};', [color]));

				category._button = button;
				this._categoryButtons.addChild(button);
			}));

			// special treats for an empty favorites category
			var favoritesCategory = this.getCategory('_favorites_');
			var emptyFavorites = this.getModules('_favorites_').length === 0;
			domClass.toggle(favoritesCategory._button.domNode, 'favoritesHidden', emptyFavorites);

			// take the first visible category as fallback for the last selected one
			this._lastCategory = emptyFavorites ? array.filter(this.getCategories(), function(category) {return category.id != '_favorites_'; })[0] : this.getCategories()[0];

			// spread category buttons over whole width
			styles.insertCssRule('.umc .umcCategoryBar .dijitButton', lang.replace('width: {0}%', [100.0 / this.getCategories().length]));
		},

		_focusSearchField: function() {
			if (!this._header._searchSidebar) {
				return;
			}
			if (!has('touch') && !tools.status('mobileView')) {
				setTimeout(lang.hitch(this, function() {
					this._header._searchSidebar.focus();
				}, 0));
			}
		},

		_registerGridEvents: function() {
			if (!this._header._searchSidebar) {
				return;
			}
			this._header._searchSidebar.on('search', lang.hitch(this, function() {
				this.switchToOverview();
				this._updateQuery(null);
			}));
		},

		_updateQuery: function(category) {
			this.category = category;
			var searchPattern = '';
			var searchQuery = new RegExp('.*');

			if (!category) {
				searchPattern = lang.trim(this._header._searchSidebar.get('value'));
				searchQuery = this._header._searchSidebar.getSearchQuery(searchPattern);
			} else {
				if (this._header._searchSidebar) {
					this._header._searchSidebar.set('value', null);
				}
			}

			if (!category && !searchPattern) {
				// if search pattern is an empty string, resort back to the
				// last selected category
				category = this._lastCategory;
				category._button.set('selected', true);
			}

			// update the 'selected' state of all category buttons
			array.forEach(this._categoryButtons.getChildren(), function(ibutton) {
				ibutton.set('selected', category ? ibutton.categoryID == category.id : false);
			});

			this._grid.updateQuery(searchPattern, searchQuery, category);

			// update the search label
			domClass.toggle(this._searchText.domNode, 'dijitHidden', !!category);
			this._searchText.set('content', _('Search query ›%s‹', entities.encode(searchPattern)));

			// update the hash
			this._updateStateHash();
		},

		_updateNumOfTabs: function(offset) {
			// updated number of tabs
			offset = offset || 0;
			tools.status('numOfTabs', Math.max(0, this._tabContainer.getChildren().length - 1 + offset));
		},

		openModule: function(/*String|Object*/ module, /*String?*/ flavor, /*Object?*/ props) {
			// summary:
			//		Open a new tab for the given module.
			// description:
			//		This method is subscribed to the channel '/umc/modules/open' in order to
			//		open modules from other modules without requiring 'umc/app'.
			// module:
			//		Module ID as string
			// flavor:
			//		The module flavor as string.
			// props:
			//		Optional properties that are handed over to the module constructor.

			var deferred = new Deferred();
			// get the object in case we have a string
			if (typeof(module) == 'string') {
				module = this.getModule(module, flavor);
			}
			if (undefined === module) {
				deferred.reject();
				return deferred;
			}

			this._tryLoadingModule(module).then(lang.hitch(this, function(BaseClass) {
				// force any tooltip to hide
				if (Tooltip._masterTT) { Tooltip._masterTT.fadeOut.play(); }

				// create a new tab
				var tab = null; // will be the module
				if (BaseClass.prototype.unique || tools.status('mobileView')) {
					var sameModules = array.filter(this._tabContainer.getChildren(), function(i) {
						return i.moduleID == module.id && i.moduleFlavor == module.flavor;
					});
					if (sameModules.length) {
						tab = sameModules[0];
					}
				}
				if (!tab) {
					// module is not open yet, open it
					var params = lang.mixin({
						title: module.name,
						//iconClass: tools.getIconClass(module.icon),
						closable: tools.status('overview') && !tools.status('singleModule'),  // closing tabs is only enabled if the overview is visible
						moduleFlavor: module.flavor,
						moduleID: module.id,
						categoryColor: module.category_for_color,
						description: module.description
					}, props);

					tab = new BaseClass(params);
					tab.watch('moduleState', lang.hitch(this, '_updateStateHash'));
					this._tabContainer.addChild(tab);
					tab.startup();
					this._updateNumOfTabs();
					this.__insertTabStyles(tab, module);
					topic.publish('/umc/actions', module.id, module.flavor, 'open');
					tools.checkReloadRequired();
				}
				this._tabContainer.selectChild(tab, true);
				deferred.resolve(tab);
			})).otherwise(function(err) {
				console.warn('Error initializing module ' + module.id + ':', err);
				tools.checkReloadRequired();
				deferred.reject(err);
			});
			return deferred;
		},

		_insertedTabStyles: [],
		__insertTabStyles: function(tab, module) {
			var module_flavor_css = module.id;
			if (module.flavor) {
				module_flavor_css = lang.replace('{id}-{flavor}', module);
			}
			module_flavor_css = module_flavor_css.replace(/[^_a-zA-Z0-9\-]/g, '-');
			domClass.add(tab.controlButton.domNode, lang.replace('umcModuleTab-{0}', [module_flavor_css]));
			var menuTab = this._header._moreTabsDropDownButton.dropDown.getChildren().find(function(menuItem) {
				return menuItem.correspondingModuleID == tab.id;
			});
			domClass.add(menuTab.domNode, lang.replace('color-{0}', [module_flavor_css]));

			if (this._insertedTabStyles.includes(module_flavor_css)) {
				// do not insert the same styles more than once
				return;
			}

			this._insertedTabStyles.push(module_flavor_css);

			var color = this.__getModuleColor(module);
			var defaultClasses = '.umc .dijitTabContainerTop-tabs .dijitTab';
			var cssProperties = lang.replace('background-color: {0}; background-image: none; filter: none;', [color]);

			styles.insertCssRule(lang.replace('{0}.umcModuleTab-{1}.dijitHover', [defaultClasses, module_flavor_css]), cssProperties);
			styles.insertCssRule(lang.replace('{0}.umcModuleTab-{1}.dijitTabChecked', [defaultClasses, module_flavor_css]), cssProperties);
			styles.insertCssRule(lang.replace('.umc .headerColor-{0} .dijitTabContainerTop-tabs .dijitTab.umcModuleTab-{1}.dijitTabHover', [module.category_for_color, module_flavor_css]), 'background-color: rgba(0, 0, 0, 0.1)');
			styles.insertCssRule(lang.replace('.umcModuleHeader-{0}', [module_flavor_css]), cssProperties);
			styles.insertCssRule(lang.replace('.umc .umcHeader.headerColor-{0}', [module.category_for_color]), cssProperties);
			styles.insertCssRule(lang.replace('.umc .umcMoreTabsDropDownMenuContent tr.color-{0}:hover', [module_flavor_css]), lang.replace('background-color: {0}', [color]));
		},

		__getModuleColor: function(module) {
			var category = array.filter(this.getCategories(), lang.hitch(this, function(category) {
				return module.category_for_color === category.id;
			}));
			if (category.length) {
				return category[0].color;
			}
			return '';
		},

		focusTab: function(tab) {
			if (array.indexOf(this._tabContainer.getChildren(), tab) >= 0) {
				this._tabContainer.selectChild(tab, true);
			}
		},

		closeTab: function(tab, /*Boolean?*/ destroy) {
			destroy = destroy === undefined || destroy === true;
			tab.onClose();
			if (destroy) {
				this._tabContainer.closeChild(tab);
			} else {
				this._tabContainer.removeChild(tab);
			}
		},

		getModules: function(/*String?*/ category) {
			// summary:
			//		Get modules, either all or the ones for the specific category.
			//		The returned array contains objects with the properties
			//		{ BaseClass, id, title, description, categories }.
			// categoryID:
			//		Optional category name.a
			return this._moduleStore.getModules(category);
		},

		_getLaunchableModules: function() {
			return this._moduleStore.query(function(item) {
				return item.category !== '_favorites_';
			});
		},

		getModule: function(/*String?*/ id, /*String?*/ flavor, /*String?*/ category) {
			// summary:
			//		Get the module object for a given module ID.
			//		The returned object has the following properties:
			//		{ BaseClass, id, description, category, flavor }.
			// id:
			//		Module ID as string.
			// flavor:
			//		The module flavor as string.
			// category:
			//		Restricts the search only to the given category.
			return this._moduleStore.getModule(id, flavor, category);
		},

		getCategories: function() {
			// summary:
			//		Get all categories as an array. Each entry has the following properties:
			//		{ id, description }.
			return this._moduleStore.getCategories();
		},

		getCategory: function(/*String*/ id) {
			// summary:
			//		Get the category that corresponds to the given ID.
			return this._moduleStore.getCategory(id);
		},

		addFavoriteModule: function(/*String*/ id, /*String?*/ flavor) {
			if (!_favoritesDisabled) {
				this._moduleStore.addFavoriteModule(id, flavor);
			}
		},

		_toggleFavoriteModule: function(module) {
			if (isFavorite(module)) {
				// for the favorite category, remove the module from the favorites
				this._moduleStore.removeFavoriteModule(module.id, module.flavor);
				topic.publish('/umc/actions', 'overview', 'favorites', module.id, module.flavor, 'remove');
			}
			else {
				// for any other category, add the module to the favorites
				this._moduleStore.addFavoriteModule(module.id, module.flavor);
				topic.publish('/umc/actions', 'overview', 'favorites', module.id, module.flavor, 'add');
			}
		},

		addSubMenu: function(item) {
			if (this._header) {
				this._header.addSubMenu(item);
			}
		},

		addMenuEntry: function(item) {
			if (this._header) {
				this._header.addMenuEntry(item);
			}
		},

		addMenuSeparator: function(item) {
			if (this._header) {
				this._header.addMenuSeparator(item);
			}
		},

		showPageDialog: function() {
			return this._header.showPageDialog.apply(this, arguments);
		},

		registerOnStartup: function(/*Function*/ callback) {
			topic.publish('/umc/module/startup', callback);
		},

		logout: function() {
			this._askLogout().then(lang.hitch(this, function() {
				tools.checkSession(false);
				window.location = '/univention/logout';
			}));
		},

		relogin: function(username) {
			if (username === undefined) {
				return this.logout();
			}
			this._askLogout().then(function() {
				// TODO: we should do a real logout here. maybe the UMCUsername cookie can be set
				tools.checkSession(false);
				tools.closeSession();
				window.location.search = 'username=' + username;
			});
		},

		_askLogout: function() {
			var deferred = new Deferred();
			dialog.confirm(_('Do you really want to logout?'), [{
				label: _('Cancel'),
				callback: function() {
					deferred.cancel();
				}
			}, {
				label: _('Logout'),
				'default': true,
				callback: lang.hitch(this, function() {
					topic.publish('/umc/actions', 'session', 'logout');
					deferred.resolve();
				})
			}]);
			return deferred;
		},

		linkToModule: function(/*String*/ moduleId, /*String?*/ moduleFlavor, /*String?*/ linkName) {
			kernel.deprecated('umc/app:linkToModule()', 'use tools.linkToModule instead (different argument format)!');
			return tools.linkToModule({
				module: moduleId,
				flavor: moduleFlavor,
				linkName: linkName
			});
		},

		__openAllModules: function(category) {
			umc.app._moduleStore.query(function(m) {
				if (category) {
					return m.category == category;
				}
				return m.category && m.category !== '_favorites_';
			}).forEach(function(m) {
				umc.app.openModule(m.id, m.flavor);
			});
		},

		onModulesLoaded: function() {
			// event stub when all modules are loaded as Javascript files
		},

		onGuiDone: function() {
			// event stub
		}
	})();

	lang.setObject('umc.app', app);
	return app;
});
