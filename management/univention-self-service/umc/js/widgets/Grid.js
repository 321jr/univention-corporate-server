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
/*global define, require, setTimeout, clearTimeout*/

define([
	"dojo/_base/declare",
	"dojo/_base/lang",
	"dojo/_base/array",
	"dojo/_base/kernel",
	"dojo/_base/window",
	"dojo/dom-construct",
	"dojo/dom-attr",
	"dojo/dom-geometry",
	"dojo/dom-style",
	"dojo/dom-class",
	"dojo/topic",
	"dojo/aspect",
	"dojo/on",
	"dojo/window",
	"dijit/Destroyable",
	"dijit/Menu",
	"dijit/MenuItem",
	"dijit/form/DropDownButton",
	"dgrid/OnDemandGrid",
	"dgrid/Selection",
	"dgrid/extensions/DijitRegistry",
	"dgrid/Selector",
	"dstore/legacy/StoreAdapter",
	"dstore/Memory",
	"./Button",
	"./Text",
	"./ContainerWidget",
	"./StandbyMixin",
	"./Tooltip",
	"./_RegisterOnShowMixin",
	"../tools",
	"../render",
	"../i18n!",
], function(declare, lang, array, kernel, win, construct, attr, geometry, style, domClass,
		topic, aspect, on, dojoWindow, Destroyable, Menu, MenuItem, DropDownButton,
		OnDemandGrid, Selection, DijitRegistry, Selector, StoreAdapter, Memory, Button, Text, ContainerWidget,
		StandbyMixin, Tooltip, _RegisterOnShowMixin, tools, render, _) {

	var _Grid = declare([OnDemandGrid, Selection, Selector, DijitRegistry, Destroyable], {
		getItem: function(item) {
			// For legacy dojox grid compability
			// e.g. formaters that expect to be working with a dojox grid
			return item;
 		}
 	});

	var _DropDownButton = declare([DropDownButton], {
		_onClick: function(evt) {
			// dont propagate any event here - otherwise dropDown gets closed.
			// this has something to do with the dropdown losing focus in favor
			// of the underlying td-node. it triggers _HasDropDown's _onBlur
			this.inherited(arguments);
			evt.stopPropagation();
		}
	});

	return declare("umc.widgets.Grid", [ContainerWidget, StandbyMixin, _RegisterOnShowMixin], {
		// summary:
		//		Encapsulates a complex grid with store, UMCP commands and action buttons;
		//		offers easy access to select items etc.

		// actions: Object[]
		//		Array of config objects that specify the actions that are going to
		//		be used in the grid.
		//		'canExecute': function that specifies whether an action can be excuted for
		//		              a particular item; the function receives a dict of all item
		//		              properties as parameter
		//		'tooltipClass': specifies a different tooltip class than umc/widgets/Tooltip
		//		'isContextAction': specifies that the action requires a selection
		//		'isStandardAction': specifies whether the action is displayed as own button or in the "more" menu
		//		'isMultiAction': specifies whether this action can be executed for multiple items
		//		'enablingMode': for multi actions; 'all' (default value) will require all selected items
		//		                to be executable, 'some' only requires at least one item in the selection
		//		                to be executable
		//		TODO: explain also the 'adjust' value for columns
		//		TODO: iconClass, label -> may be of type string or function
		//		      they are called either per item (with a dict as parameter) or
		//		      once as column caption (without any parameters)
		actions: [],

		// columns: Object[]
		//		Array of config objects that specify how the listing is rendered in
		//		the grid. Each element represents a column of the grid:
		//		'name': property that is going to be rendered in the column;
		//		'label': label of the column;
		//		'description': text for tooltip;
		//		'type': defaults to string, otherwise checkbox, icon, ...???;
		//		'editable': whether or not the field can be edited by the user;
		columns: null,

		// query: Object?
		//		The initial query for the data grid. If not specified no query will be executed
		//		when the module has loaded.
		query: null,

		// moduleStore: store.UmcpModuleStore
		//		Object store for module requests using UMCP commands.
		moduleStore: null,

		// footerFormatter: Function?
		//		Function that is called with two parameters: the number of selected objects,
		//		total number of objects. The function is expected to return a string that
		//		will be displayed in the grid footer.
		footerFormatter: null,

		// sortIndex: Number
		//		Controls which column is used for default sorting (values < 0 indicated
		//		sorting in descending order)
		sortIndex: 1,

		// use the framework wide translation file
		i18nClass: 'umc.app',

		// turn an labels for action columns by default
		actionLabel: true,

		// turn off gutters by default
		gutters: false,

		// defaultAction: Function/String a default action that is executed
		//		when clicking on the column defined in defaultActionColumn (if set) or in the first column.
		defaultAction: 'edit',

		// defaultActionColumn:
		//
		//
		defaultActionColumn: '',

		// gridOptions: options for the inner grid
		gridOptions: null,

		baseClass: 'umcGrid',

		_widgetList: [],
		own: function() {
			array.forEach(arguments, function(iarg) {
				this._widgetList.push(iarg);
			}, this);
			return this.inherited(arguments);
		},

		disabled: false,

		_contextMenu: null,

		// temporary div elements to estimate width of text for columns
		_tmpCell: null,
		_tmpCellHeader: null,

		// ContainerWidget that holds all buttons
		_toolbar: null,

		_header: null,
		_gridInfo: null,

		_gridInfoLegend: null,

		// internal list of all disabled items... when data has been loaded, we need to
		// disable these items again
		_disabledIDs: null,

		_selectionChangeTimeout: null,

		_resizeDeferred: null,

		// internal adapter to the module store
		_store: null,
		collection: null,

		_iconFormatter: function(valueField, iconField) {
			// summary:
			//		Generates a formatter functor for a given value and icon field.

			return lang.hitch(this, function(value, item) {
				// get the iconName
				var iconName = item[iconField];

				// create an HTML image that contains the icon
				var html = lang.replace('<img src="{url}/umc/icons/16x16/{icon}.png" height="{height}" width="{width}" style="float:left; margin-right: 5px" /> {value}', {
					icon: iconName, //dojo.moduleUrl("dojo", "resources/blank.gif").toString(),
					height: '16px',
					width: '16px',
					value: value,
					url: require.toUrl('dijit/themes')
				});
				return html;
			});
		},

		_parentModule: undefined,
		_parentModuleTries: 0,
		_publishPrefix: null,
		_getParentModule: function() {
			if (!this._parentModule && this._parentModuleTries < 5) {
				++this._parentModuleTries;
				this._parentModule = tools.getParentModule(this);
			}
			return this._parentModule;
		},

		_publishAction: function(action) {
			var mod = this._getParentModule();
			if (mod) {
				topic.publish('/umc/actions', mod.moduleID, mod.moduleFlavor, this._publishPrefix, 'grid', action);
			}
		},

		_onScroll: function() {
			var isActiveTab = !!document.getElementById(this.id).offsetParent;
			if (!isActiveTab) {
				return;
			}
			var viewPortHeight = dojoWindow.getBox().h;
			var atBottom = (window.pageYOffset + viewPortHeight) === win.body().clientHeight;
			if (atBottom) {
				this._heightenGrid(2 * viewPortHeight);
			}
		},

		_heightenGrid: function(extension) {
			var gridHeight = style.get(this._grid.domNode, "height");
			var newMaxGridHeight = gridHeight + extension;
			style.set(this._grid.domNode, "max-height", newMaxGridHeight + 'px');
			this._grid.resize();
			var gridIsFullyRendered = this._grid.domNode.scrollHeight < newMaxGridHeight;
			if (gridIsFullyRendered) {
				this._statusMessage.set('content', _('Done'));
				this._scrollSignal.remove();
				return;
			}
		},

		_setInitialGridHeight: function() {
			if (this._scrollSignal) {
				this._scrollSignal.remove();
			}
			this._scrollSignal = on(win.doc, 'scroll', lang.hitch(this, '_onScroll'));
			this.own(this._scrollSignal);
			var viewPortHeight = dojoWindow.getBox().h;
			var gridHeight = Math.round(viewPortHeight + viewPortHeight / 3);
			this._heightenGrid(gridHeight);
		},

		_selectAll: function() {
			this._grid.collection.fetch().forEach(lang.hitch(this, function(item){
				var row = this._grid.row(item);
				this._grid.select(row);
			}));
		},

		_updateGridSorting: function() {
			if (typeof this.sortIndex === "number" && this.sortIndex !== 0) {
				var column = this.columns[Math.abs(this.sortIndex) - 1];
				this._grid.set('sort', [{property: column.name, descending: this.sortIndex < 0 }]);
			}
		},

		postMixInProperties: function() {
			this.inherited(arguments);

			this._disabledIDs = {};
			this._store = new StoreAdapter({
				objectStore: this.moduleStore,
				isUmcpCommandStore: typeof(this.moduleStore.umcpCommand) === "function",
				idProperty: this.moduleStore.idProperty
			});
			if (this._store.isUmcpCommandStore) {
				this.own(this.moduleStore.on('Change', lang.hitch(this, function() {
					this.filter(this.query);
				})));
			} else if (this.moduleStore.query().observe) {
				this.moduleStore.query().observe(lang.hitch(this, function() {
					this.filter(this.query);
				}));
			}
			this.collection = new Memory({
				idProperty: this._store.idProperty
			});
		},

		buildRendering: function() {
			this.inherited(arguments);

			this._header = new ContainerWidget({
				baseClass: 'umcGridHeader'
			});
			this.addChild(this._header);
			
			this._gridInfo = new ContainerWidget({
				baseClass: 'umcGridFooter'
			});
			this._createGridInfo();
			this.addChild(this._gridInfo);

			this._grid = new _Grid(lang.mixin({
				collection: this.collection,
				className: 'dgrid-autoheight',
				bufferRows: 0,
				_refresh: lang.hitch(this, '_refresh'),
				selectionMode: 'extended',
				allowSelectAll: true,
				allowSelect: lang.hitch(this, 'allowSelect'),
				_selectAll: lang.hitch(this, '_selectAll'),
				update: lang.hitch(this, 'update'),
				selectAll: function() {
					this.inherited(arguments);
					this._selectAll(); //Bug: dgrid #1198
				}
			}, this.gridOptions || {}));

			this._updateGridSorting();

			this._contextMenu = new Menu({
				targetNodeIds: [this._grid.domNode]
			});
			this.own(this._contextMenu);
			this._statusMessage = new Text({
				content: _("Please perform a search")
			});
			this.own(this._statusMessage);

			this.setColumnsAndActions(this.columns, this.actions);

			this.addChild(this._grid);
			this.addChild(this._statusMessage);

			//
			// register event handler
			//

			this._grid.on('dgrid-select', lang.hitch(this, '_selectionChanged', true));
			this._grid.on('dgrid-deselect', lang.hitch(this, '_selectionChanged', false));

			this._grid.on(".dgrid-row:contextmenu", lang.hitch(this, '_updateContextItem'));

			this.on('filterDone', lang.hitch(this, '_updateGlobalCanExecute'));

			this._grid.on('dgrid-refresh-complete', lang.hitch(this, '_cleanupWidgets'));

			if (this.query) {
				this.filter(this.query);
			}

		},

		_updateGlobalCanExecute: function() {
			var items = this.getAllItems();
			array.forEach(this._getGlobalActions(), lang.hitch(this, function(action) {
				if (action.canExecute) {
					var enabled = action.canExecute(items);
					array.forEach(this._toolbar.getChildren(), function(button) {
						if (button.name === action.name) {
							button.set('disabled', !enabled);
						}
					});
				}
			}));
		},

		_cleanupWidgets: function() {
			this._widgetList = array.filter(this._widgetList, function(iwidget) {
				if ((iwidget.isInstanceOf && !iwidget.isInstanceOf(Menu))
						&& (iwidget.id && !document.getElementById(iwidget.id))
						&& !iwidget._destroyed
						&& iwidget.destroy) {
					iwidget.destroy();
					return false;
				}
				if (iwidget._destroyed) {
					return false;
				}
				return true;
			}, this);
		},

		startup: function() {
			this.inherited(arguments);

			this._registerAtParentOnShowEvents(lang.hitch(this._grid, 'resize'));
		},

		setColumnsAndActions: function(columns, actions) {
			this._setActionsAttr(actions, false);
			this._setColumnsAttr(columns);
		},

		_setColumnsAttr: function (columns) {
			tools.assert(columns instanceof Array, 'The property columns needs to be defined for umc/widgets/Grid as an array.');
			this.columns = columns;

			if (!this._grid) {
				// grid not yet defined
				return;
			}

			// create the layout for the grid columns
			var gridColumns = array.map(columns, function(icol, colNum) {
				tools.assert(icol.name !== undefined && icol.label !== undefined, 'The definition of grid columns requires the properties \'name\' and \'label\'.');

				// set common properties
				var col = lang.mixin({
//					width: 'auto',
//					editable: false,
//					description: ''
				}, icol, {
					field: icol.name
				});
//				delete col.label;

				// default action
				var defaultActionExists = this.defaultAction && (typeof this.defaultAction === "function" || array.indexOf(array.map(this.actions, function(iact) { return iact.name; }), this.defaultAction) !== -1);
				var isDefaultActionColumn = (!this.defaultActionColumn && colNum === 0) || (this.defaultActionColumn && col.name === this.defaultActionColumn);

				if (defaultActionExists && isDefaultActionColumn) {
					col.renderCell = lang.hitch(this, function(item, value, node, options) {
						value = icol.formatter ? icol.formatter(value, item) : value;

						var defaultAction = this._getDefaultActionForItem(item);

						if (!defaultAction) {
							if (value && value.domNode) {
								this.own(value);
							}
							return value.domNode;
						}

						var container = null;

						if (value && value.domNode) {
							container = new ContainerWidget({
								baseClass: 'umcGridDefaultAction',
							});
							container.addChild(value);
							container.own(value);
						} else {
							container = new Text({
								content: value,
								baseClass: 'umcGridDefaultAction',
							});
						}
						this.own(container);
						container.on('click', lang.hitch(this, function() {
							var idProperty = this.moduleStore.idProperty;
							defaultAction.callback([item[idProperty]], [item]);
						}));
						return container.domNode;
					});
				}

				// check whether the width shall be computed automatically
				if ('adjust' === col.width) {
					col.width = (this._getHeaderWidth(col.label) + 10) + 'px';
				}

				if (icol.formatter) {
					col.formatter = function(name, columnValue) {
						var colContent = icol.formatter(name, columnValue, columnValue);
						if (colContent && colContent.domNode) {
							return colContent.domNode.outerHTML;
						} else {
							return colContent;
						}
					};
				}
				// check for an icon
				if (icol.iconField) {
					// we need to specify a formatter
					col.formatter = this._iconFormatter(icol.name, icol.iconField);
				}

				return col;
			}, this);

			var selectionColumn = {
				selector: 'checkbox',
				label: 'Selector',
				width: '30px'
			};
			gridColumns.unshift(selectionColumn);

			// set new grid structure
			this._grid.set('columns', gridColumns);
			array.forEach(gridColumns, lang.hitch(this, function(column, id) {
				this._grid.styleColumn(id, 'width: ' + column.width);
			}));
		},

		layout: function() {
			this.resize();
		},

		resize: function() {
			if (this._grid) {
				this._grid.resize();
			}
		},

		_getHeaderWidth: function(text) {
			// if we do not have a temporary cell yet, create it
			if (!this._tmpCell && !this._tmpCellHeader) {
				this._tmpCellHeader = construct.create('div', { 'class': 'dgrid-header dijitOffScreen' });
				this._tmpCell = construct.create('div', { 'class': 'dgrid-cell' });
				construct.place(this._tmpCell, this._tmpCellHeader);
				construct.place(this._tmpCellHeader, win.body());
			}

			// set the text
			attr.set(this._tmpCell, 'innerHTML', text);

			// get the width of the cell
			return geometry.getMarginBox(this._tmpCell).w;
		},

		_setActionsAttr: function(actions, /*Boolean?*/ doSetColumns) {
			tools.assert(actions instanceof Array, 'The property actions needs to be defined for umc/widgets/Grid as an array.');
			this.actions = actions;

			// clear old actions
			array.forEach([this._header, this._contextMenu], function(iobj) {
				array.forEach(iobj.getChildren(), function(ichild) {
					iobj.removeChild(ichild);
					ichild.destroyRecursive();
				}, this);
			}, this);
			delete this._contextMenu.focusedChild;

			this._setGlobalActions();
			this._setContextActions();

			domClass.toggle(this._header.domNode, 'dijitHidden', !this.actions.length);
			if (this._toolbar.getChildren().length) {
				this._header.addChild(this._toolbar);
			}
			this._header.addChild(this._contextActionsToolbar);
			style.set(this._contextActionsToolbar.domNode, 'visibility', 'hidden');

			// redraw the columns
			if (doSetColumns !== false) {
				this._setColumnsAttr(this.columns);
			}
		},

		_getContextActions: function() {
			return array.filter(this.actions, function(iaction) { return (false !== iaction.isContextAction); });
		},

		_setContextActions: function() {
			this._contextActionsToolbar = new ContainerWidget({ style: 'float: left' });
			this._contextActionsMenu = new Menu({});
			this.own(this._contextActionsToolbar);
			this.own(this._contextActionsMenu);

			array.forEach(this._getContextActions(), function(iaction) {
				var getCallback = lang.hitch(this, function(prefix) {
					if (!iaction.callback) {
						return {};
					}
					return {
						onClick: lang.hitch(this, function() {
							this._publishAction(prefix + iaction.name);
							var ids = this.getSelectedIDs();
							var items = this.getSelectedItems();
							if (iaction.enablingMode === 'some') {
								items = array.filter(items, function(iitem) {
									return typeof iaction.canExecute === "function" ? iaction.canExecute(iitem) : true;
								});
								ids = array.map(items, function(iitem) {
									return this._dataStore.getValue(iitem, this.moduleStore.idProperty);
								}, this);
							}
							iaction.callback(ids, items);
						})
					};
				});
				// get icon and label (these properties may be functions)
				var iiconClass = typeof iaction.iconClass === "function" ? iaction.iconClass() : iaction.iconClass;
				var ilabel = typeof iaction.label === "function" ? iaction.label() : iaction.label;

				var props = { iconClass: iiconClass, label: ilabel, _action: iaction };

				if (iaction.isStandardAction) {
					// add action to the context toolbar
					var btn = new Button(lang.mixin(props, getCallback(''), { iconClass: props.iconClass || 'umcIconNoIcon' }));
					if (iaction.description) {
						try {
						var idescription = typeof iaction.description === "function" ? iaction.description(undefined) : iaction.description;
						var tooltip = new (iaction.tooltipClass || Tooltip)({
							label: idescription,
							connectId: [btn.domNode]
						});
						if (iaction.onShowDescription) {
							tooltip = lang.mixin(tooltip, { onShow: function(target) { iaction.onShowDescription(target, undefined); }});
						}
						if (iaction.onHideDescription) {
							tooltip = lang.mixin(tooltip, { onHide: function() { iaction.onHideDescription(undefined); }});
						}
						btn.own(tooltip);
						} catch (error) {}
					}
					this._contextActionsToolbar.addChild(btn);
				} else {
					// add action to the more menu
					this._contextActionsMenu.addChild(new MenuItem(lang.mixin(props, getCallback('multi-'))));
				}

				// add action to the context menu
				this._contextMenu.addChild(new MenuItem(lang.mixin(props, getCallback('menu-'))));
			}, this);

			// add more menu to toolbar
			if (this._contextActionsMenu.getChildren().length) {
				this._contextActionsToolbar.addChild(new _DropDownButton({
					baseClass: _DropDownButton.prototype.baseClass + ' umcGridMoreMenu',
					iconClass: 'umcIconNoIcon',
					label: _('more'),
					dropDown: this._contextActionsMenu
				}));
			}
		},

		_getGlobalActions: function() {
			return array.filter(this.actions, function(iaction) { return (false === iaction.isContextAction); });
		},

		_setGlobalActions: function() {
			//
			// toolbar for global actions
			//

			// add a toolbar which contains all non-context actions
			this._toolbar = new ContainerWidget({
				style: 'float: left',
				baseClass: 'umcGridToolBar'
			});
			this.own(this._toolbar);

			var buttonsCfg = array.map(this._getGlobalActions(), function(iaction) {
				var jaction = iaction;
				if (iaction.callback) {
					jaction = lang.mixin({}, iaction); // shallow copy

					// call custom callback with selected values
					jaction.callback = lang.hitch(this, function() {
						this._publishAction(iaction.name);
						iaction.callback(this.getSelectedIDs(), this.getSelectedItems());
					});
				}
				return jaction;
			}, this);

			// render buttons
			var buttons = render.buttons(buttonsCfg);

			// add buttons to toolbar
			array.forEach(buttons.$order$, function(ibutton) {
				this._toolbar.addChild(ibutton);
				ibutton.on('click', lang.hitch(this, function() {
					this._publishAction(ibutton.name);
				}));
			}, this);
		},

		_selectionChanged: function() {
			if (this._selectionChangeTimeout) {
				clearTimeout(this._selectionChangeTimeout);
			}

			this._selectionChangeTimeout = setTimeout(lang.hitch(this, function() {
				this._updateContextActions();

				this._updateGridInfoContent();
			}), 50);
		},

		_getContextActionItems: function() {
			return this._contextActionsToolbar.getChildren().concat(this._contextMenu.getChildren()).concat(this._contextActionsMenu.getChildren());
		},

		_updateContextActions: function() {
			var nItems = this.getSelectedIDs().length;

			array.forEach(this._getContextActionItems(), function(item) {
				if ((item instanceof Button || item instanceof MenuItem) && item._action) {
					var enabled = nItems !== 0;
					if (nItems > 1) {
						// when more than 1 row is selected:
						// disable actions which are no multiactions
						enabled = item._action.isMultiAction;
					}
					// disable multiaction if one of the selected items can not be executed
					var enablingFunction = array.every;
					if (item._action.enablingMode === 'some') {
						enablingFunction = array.some;
					}
					enabled = enabled && enablingFunction(this.getSelectedItems(), function(iitem) { return item._action.canExecute ? item._action.canExecute(iitem) : true; });
					item.set('disabled', !enabled);
				}
			}, this);

			// don't show context actions if they are not available
			var visibility = nItems === 0 ? 'hidden' : 'visible';
			style.set(this._contextActionsToolbar.domNode, 'visibility', visibility);
		},

		_updateContextItem: function(evt) {
			// when opening the context menu...
//TODO
//			var rowDisabled = this._grid.rowSelectCell.disabled(evt.rowIndex);
//			if (rowDisabled) {
//				return;
//			}

			var hasClickedOnDefaultAction = (evt.target != evt.cellNode);
			var id = this._grid.row(evt).id;
			var isSelected = this._grid.get('selection')[id];
			if (!isSelected || hasClickedOnDefaultAction) {
				var newSelection = lang.mixin({}, this._grid.get('selection'));
				newSelection[id] = true;
				this._grid.set('selection', newSelection);
			}
		},

		_getDefaultActionForItem: function(item) {
			// returns the default action for a specified item if the action exists and can be executed
			var identity = item[this.moduleStore.idProperty];
			var defaultAction = typeof this.defaultAction === "function" ?
				this.defaultAction([identity], [item]) : this.defaultAction;

			if (defaultAction) {
				var action;
				array.forEach(this.actions, function(iaction) {
					if (iaction.name === defaultAction) {
						action = iaction;
						return false;
					}
				}, this);
				if (action && action.callback) {
					var isExecutable = typeof action.canExecute === "function" ? action.canExecute(item) : true;
					if (isExecutable && !this.getDisabledItem(identity)) {
						return action;
					}
				}
			}
		},

		_setDisabledAttr: function(disabled) {
			this.disabled = disabled;

			// disable items
			this._grid.collection.fetch().forEach(lang.hitch(this, function(item) {
				var id = item[this.moduleStore.idProperty];
				this.setDisabledItem(id, disabled);
			}));
			// re-disable explicitly disabled items
			//this._updateDisabledItems();

			// disable all actions
			array.forEach(this._toolbar.getChildren().concat(this._contextActionsToolbar), lang.hitch(this, function(widget) {
				if (widget instanceof Button || widget instanceof _DropDownButton) {
					widget.set('disabled', disabled);
				}
			}));
		},

		_createGridInfo: function() {
			// add a legend that states how many objects are currently selected
			this._gridInfoLegend = new Text({
				content: _('No object selected'),
				style: 'padding-left: 5px'
			});
			this._gridInfo.addChild(this._gridInfoLegend);

			this._gridInfo.startup();

			// redo the layout since we added elements
			this.layout();

			return true;
		},

		_updateGridInfoContent: function() {
			var nItems = this.getSelectedIDs().length;
			this._grid.collection.fetch().totalLength.then(lang.hitch(this, function(nItemsTotal) {
				var msg = '';
				if (typeof this.footerFormatter === "function") {
					msg = this.footerFormatter(nItems, nItemsTotal);
				}
				else {
					msg = _('%(num)d entries of %(total)d selected', {num: nItems, total: nItemsTotal});
					if (0 === nItemsTotal) {
						msg = _('No entries could be found');
					}
					else if (1 === nItems) {
						msg = _('1 entry of %d selected', nItemsTotal);
					}
				}
				this._gridInfoLegend.set('content', msg);
			}));
		},

		_refresh: function() {
			this.filter(this.query);
		},

		update: function() {
			var updateNotPaused = false;
			if (this.getSelectedIDs().length === 0) {
				updateNotPaused = true;
				this._filter(this.query);
			}
			return updateNotPaused;
		},

		uninitialize: function() {
			// remove the temporary cell from the DOM
			if (this._tmpCellHeader) {
				construct.destroy(this._tmpCellHeader);
			}
			if (this._tmpCell) {
				construct.destroy(this._tmpCell);
			}
		},

		filter: function(query, options) {
			this._statusMessage.set('content', _('Please wait...'));
			this.standby(true);
			style.set(this._grid.domNode, 'max-height', '1px');
			this._filter(query, options).then(lang.hitch(this, function() {
				this.standby(false);
				this._setInitialGridHeight();
			}));
		},

		_filter: function(query, options) {
			var onSuccess = lang.hitch(this, function(result) {
				this.collection.setData(result);
				this._grid.refresh();
				this._updateGridInfoContent();
				this.onFilterDone(true);
			});
			var onError = lang.hitch(this, function(error) {
				if (error && error.response && error.response.text) {
					this._statusMessage.set('content', JSON.parse(error.response.text).message);
				} else {
					this._statusMessage.set('content', _('Could not load search results'));
				}
				this._grid.set('collection', new Memory());
				this._updateGridInfoContent();
			});
			// store the last query
			this.query = query;
			// umcpCommand doesn't know a range option -> need to cache
			// StoreAdapter doesn't work with fetchSync -> need to cache
			return this._store.filter(query, options).fetch().then(
					onSuccess,
					onError
			);
		},

		getAllItems: function() {
			// summary:
			//		Returns a list of all items
			var items = this._grid.collection.fetchSync();
			return items;
		},

		getSelectedItems: function() {
			// summary:
			//		Return the currently selected items.
			//		Filters disabled items.
			// returns:
			//		An array of dictionaries with all available properties of the selected items.
			var ids = this.getSelectedIDs();
			var filter = new this._grid.collection.Filter();
			var selectedItemsFilter = filter.in(this.moduleStore.idProperty, ids);
			var items = this._grid.collection.filter(selectedItemsFilter).fetchSync();
			return items;
		},

		getSelectedIDs: function() {
			// summary:
			//		Return the currently selected items.
			// returns:
			//		An array of id strings (as specified by moduleStore.idProperty).
			return array.filter(Object.keys(this._grid.selection), function(id) {
				return this._grid.selection[id];
			}, this);
		},

		getRowValues: function(row) {
			return row;
		},

		getItemIndex: function(id) {
			// summary:
			//		Returns the index of the given item specified by its ID.
			//		In case the item could not be resolved, returns -1.
			// id: String

			var item = this.getItem(id);
			if (!item) {
				return -1;
			}
			return id;
		},

		getItem: function(id) {
			// summary:
			//		Returns the item for a given ID.
			// id: String

			var item = array.filter(this._grid._lastCollection || [], function(iitem) {
				return iitem[this.moduleStore.idProperty] === id;
			}, this);
			if (item.length) {
				return item[0];
			}
			return null;
		},

		//_updateDisabledItems: function() {
		//    // see how many items are disabled
		//    var nDisabledItems = 0;
		//    tools.forIn(this._disabledIDs, function() {
		//        ++nDisabledItems;
		//    });
		//    if (!nDisabledItems) {
		//        // nothing to do
		//        return;
		//    }

		//    // walk through all elements and make sure that their disabled state
		//    // is correctly set
		//    var idx, iitem, iid, disabled;
		//    for (idx = 0; idx < this._grid.rowCount; ++idx) {
		//        iitem = this._grid.getItem(idx);
		//        iid = iitem[this.moduleStore.idProperty];
		//        disabled = this._disabledIDs[iid] === true;
		//        if (disabled === (!this._grid.rowSelectCell.disabled(idx))) {
		//            this._grid.rowSelectCell.setDisabled(idx, disabled);
		//        }
		//    }
		//},

		allowSelect: function(row) {
			if (this._disabledIDs[row.id]) {
				return false;
			} else {
				return true;
			}
		},

		setDisabledItem: function(_ids, disable) {
			// summary:
			//		Disables the specified items.
			// ids: String|String[]
			//		Item ID or list of IDs.
			// disable: Boolean?
			//		Disable or enable the specified items.

			var ids = tools.stringOrArray(_ids);
			disable = undefined === disable ? true : disable;
			array.forEach(ids, function(id) {
				this._disabledIDs[id] = !!disable;
				if (this._disabledIDs[id]) {
					this._grid.deselect(id);
				}
				var selectorColumn = '0';
				var selectorCell = this._grid.cell(id, selectorColumn);
				if (selectorCell.element) {
					var checkboxNode = selectorCell.element.firstChild;
					attr.set(checkboxNode, 'disabled', disable);
				}
			}, this);
		},

		getDisabledItem: function(_ids) {
			// summary:
			//		Returns an array (if input is an array) of Boolean or Boolean.
			//		If an item could not be resolved, returns null.
			// ids: String|String[]
			//		Item ID or list of IDs.

			var ids = tools.stringOrArray(_ids);
			var result = array.map(ids, function(id) {
				if (this._grid.row(id).element) {
					return this._grid.allowSelect(id);
				}
				return null;
			}, this);

			// return Boolean or array depending on the input
			if (!(_ids instanceof Array)) {
				return result[0]; // Boolean
			}
			return result; // Boolean[]
		},

		clearDisabledItems: function(/*Boolean?*/ doRendering) {
			// summary:
			//		Enables all previously disabled items and clears internal cache.

			// enable all disabled items
			for (var id in this._disabledIDs) {
				if (this._disabledIDs[id] === true) {
					this.setDisabledItem(id, false);
				}
			}

			// perform rendering if requested
			if (undefined === doRendering || doRendering) {
				this._grid.refresh();
			}
		},

		canExecuteOnSelection: function(/* String|Object */action, /* Object[] */items) {
			// summary:
			//		returns a subset of the given items that are available for the action according to the canExecute function
			var actionObj = null;
			var executableItems = [];

			if (typeof action === "string") {
				var tmpActions = array.filter(this.actions, function(iaction) {
					return iaction.isMultiAction && iaction.name === action;
				});
				if (!tmpActions.length) {
					throw 'unknown action ' + action;
				}
				actionObj = tmpActions[0];
			}
			executableItems = array.filter(items, function(iitem) {
				return typeof actionObj.canExecute === "function" ? actionObj.canExecute(iitem) : true;
			});

			return executableItems;
		},

		onFilterDone: function(success) {
			// event stub
		}
	});
});
