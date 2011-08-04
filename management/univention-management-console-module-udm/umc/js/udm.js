/*global console MyError dojo dojox dijit umc */

dojo.provide("umc.modules.udm");

dojo.require("dijit.Menu");
dojo.require("dijit.MenuItem");
dojo.require("dijit.layout.BorderContainer");
dojo.require("dijit.layout.ContentPane");
dojo.require("dojo.DeferredList");
dojo.require("umc.dialog");
dojo.require("umc.i18n");
dojo.require("umc.tools");
dojo.require("umc.widgets.ExpandingTitlePane");
dojo.require("umc.widgets.Grid");
dojo.require("umc.widgets.Module");
dojo.require("umc.widgets.Page");
dojo.require("umc.widgets.SearchForm");
dojo.require("umc.widgets.Tree");

dojo.require("umc.modules._udm.Template");
dojo.require("umc.modules._udm.NewObjectDialog");
dojo.require("umc.modules._udm.TreeModel");
dojo.require("umc.modules._udm.DetailPage");

dojo.declare("umc.modules.udm", [ umc.widgets.Module, umc.i18n.Mixin ], {
	// summary:
	//		Module to interface (Univention Directory Manager) UDM objects.
	// description:
	//		This class offers a GUI interface to query and manipulate the different types
	//		of UDM objects. UDM objects have different properties and functions, however,
	//		the way they are displayed is rudimentary similar across the different types.
	//		This class is meant to be used (a) either to interface a particular UDM type
	//		(users, groups, computers, ...) or (b) to display a navigation interface which
	//		shows the container hierarchy on the left side and existing UDM objects of
	//		any type on the search list. The class' behaviour is controlled by the moduleFlavor
	//		property (which is set automatically when available modules are queried during
	//		the initialization).

	// openObject: Object?
	//		If given, the module will open upon start the detail page for editing the given
	//		object (specified by its LDAP DN). This property is expected to be a dict with
	//		the properties 'objectType' and 'objectDN' (both as strings).
	openObject: null,

	// the property field that acts as unique identifier: the LDAP DN
	idProperty: 'ldap-dn',

	// internal reference to the search page
	_searchPage: null,

	// internal reference to the detail page for editing an UDM object
	_detailPage: null,

	// internal reference to the signal handle to umc.modules._udm.DetailPage.onClose
	_detailPageCloseHandle: null,

	// reference to a `umc.widgets.Tree` instance which is used to display the container
	// hierarchy for the UDM navigation module
	_tree: null,

	// reference to the last item in the navigation on which a context menu has been opened
	_navContextItem: null,

	buildRendering: function() {
		// call superclass method
		this.inherited(arguments);

		if ('navigation' == this.moduleFlavor) {
			// for the UDM navigation, we do not need to query
			this.renderSearchPage();
		}
		else {
			// render search page, we first need to query lists of containers/superodinates
			// in order to correctly render the search form
			(new dojo.DeferredList([
				this.umcpCommand('udm/containers'),
				this.umcpCommand('udm/superordinates')
			])).then(dojo.hitch(this, function(results) {
				var containers = results[0][0] ? results[0][1] : [];
				var superordinates = results[1][0] ? results[1][1] : [];
				this.renderSearchPage(containers.result, superordinates.result);
			}));
		}

		// check whether we need to open directly the detail page of a given object
		if (this.openObject) {
			this.createDetailPage(this.openObject.objectType, this.openObject.objectDN);
		}
	},

	renderSearchPage: function(containers, superordinates) {
		// summary:
		//		Render all GUI elements for the search formular, the grid, and the side-bar
		//		for the UMD navigation.

		// setup search page
		this._searchPage = new umc.widgets.Page({
			headerText: this.description,
			helpText: 'Lorem ipsum dolor sit amet, consetetur sadipscing elitr, sed diam nonumy eirmod tempor invidunt ut labore et dolore magna aliquyam erat, sed diam voluptua. At vero eos et accusam et justo duo dolores et ea rebum. Stet clita kasd gubergren, no sea takimata sanctus est Lorem ipsum dolor sit amet. Lorem ipsum dolor sit amet, consetetur sadipscing elitr, sed diam nonumy eirmod tempor invidunt ut labore et dolore magna aliquyam erat.'
		});
		this.addChild(this._searchPage);
		var titlePane = new umc.widgets.ExpandingTitlePane({
			title: this._('Entries'),
			design: 'sidebar'
		});
		this._searchPage.addChild(titlePane);

		//
		// add data grid
		//

		// define actions
		var actions = [{
			name: 'add',
			label: this._( 'Add' ),
			description: this._( 'Adding a new UDM object.' ),
			iconClass: 'dijitIconNewTask',
			isContextAction: false,
			isStandardAction: true,
			callback: dojo.hitch(this, 'showNewObjectDialog')
		}, {
			name: 'edit',
			label: this._( 'Edit' ),
			description: this._( 'Edit the UDM object.' ),
			iconClass: 'dijitIconEdit',
			isStandardAction: true,
			isMultiAction: false,
			callback: dojo.hitch(this, function(ids, items) {
				if (items.length && items[0].objectType) {
					this.createDetailPage(items[0].objectType, ids[0]);
				}
			})
		}, {
			name: 'delete',
			label: this._( 'Delete' ),
			description: this._( 'Deleting the selected UDM object.' ),
			isStandardAction: true,
			isMultiAction: true,
			iconClass: 'dijitIconDelete',
			callback: dojo.hitch(this, function(ids) {
				if (ids.length) {
					this.removeObjects(ids);
				}
			})
		}];

		// define grid columns
		var columns = [{
			name: 'name',
			label: this._( 'Name' ),
			description: this._( 'Name of the UDM object.' ),
			formatter: dojo.hitch(this, 'iconFormatter')
		}, {
			name: 'path',
			label: this._('Path'),
			description: this._( 'Path of the UDM object.' )
		}];

		// the navigation needs a slightly modified store that uses the UMCP query
		// function 'udm/nav/object/query'
		var store = this.moduleStore;
		if ('navigation' == this.moduleFlavor) {
			store = dojo.delegate(this.moduleStore, {
				storePath: 'udm/nav/object'
			});
		}

		// generate the data grid
		this._grid = new umc.widgets.Grid({
			region: 'center',
			actions: actions,
			columns: columns,
			moduleStore: store
		});
		titlePane.addChild(this._grid);

		//
		// add search widget
		//

		var umcpCmd = dojo.hitch(this, 'umcpCommand');
		var widgets = [];
		var layout = [];

		if ('navigation' == this.moduleFlavor) {
			// for the navigation we need a different search form
			widgets = [];
			layout = [];
		}
		else {
			// check whether we need to display containers or superordinates
			var objTypeDependencies = [];
			var objTypes = [];
			if (superordinates && superordinates.length) {
				// superordinates...
				widgets.push({
					type: 'ComboBox',
					name: 'superordinate',
					description: this._( 'The superordinate in which the search is carried out.' ),
					label: this._('Superordinate'),
					value: superordinates[0].id || superordinates[0],
					staticValues: superordinates,
					umcpCommand: umcpCmd
				});
				layout.push('superordinate');
				objTypeDependencies.push('superordinate');
			}
			else if (containers && containers.length) {
				// containers...
				containers.unshift({ id: 'all', label: this._( 'All containers' ) });
				widgets.push({
					type: 'ComboBox',
					name: 'container',
					description: this._( 'The container in which the query is executed.' ),
					label: this._('Container'),
					value: containers[0].id || containers[0],
					staticValues: containers,
					umcpCommand: umcpCmd
				});
				layout.push('container');
				objTypes.push({ id: this.moduleFlavor, label: this._( 'All types' ) });
			}

			// add remaining elements of the search form
			widgets = widgets.concat([{
				type: 'ComboBox',
				name: 'objectType',
				description: this._( 'The type of the UDM object.' ),
				label: this._('Object type'),
				value: objTypes.length ? this.moduleFlavor : undefined,
				staticValues: objTypes,
				dynamicValues: 'udm/types',
				umcpCommand: umcpCmd,
				depends: objTypeDependencies
			}, {
				type: 'ComboBox',
				name: 'objectProperty',
				description: this._( 'The object property on which the query is filtered.' ),
				label: this._( 'Object property' ),
				dynamicValues: 'udm/properties',
				dynamicOptions: { searchable: true },
				umcpCommand: umcpCmd,
				depends: 'objectType'
			}, {
				type: 'MixedInput',
				name: 'objectPropertyValue',
				description: this._( 'The value for the specified object property on which the query is filtered.' ),
				label: this._( 'Property value' ),
				dynamicValues: 'udm/values',
				umcpCommand: umcpCmd,
				depends: [ 'objectProperty', 'objectType' ]
			}]);
			layout = layout.concat([ 'objectType', 'objectProperty', 'objectPropertyValue' ]);
		}

		// generate the search widget
		this._searchWidget = new umc.widgets.SearchForm({
			region: 'top',
			widgets: widgets,
			layout: [ layout ],
			onSearch: dojo.hitch(this, 'filter')
		});
		titlePane.addChild(this._searchWidget);

		// generate the navigation pane for the navigation module
		if ('navigation' == this.moduleFlavor) {
			var model = new umc.modules._udm.TreeModel({
				umcpCommand: umcpCmd
			});
			this._tree = new umc.widgets.Tree({
				//style: 'width: auto; height: auto;',
				model: model,
				persist: false,
				// customize the method getIconClass()
				onClick: dojo.hitch(this, 'filter'),
				getIconClass: function(/*dojo.data.Item*/ item, /*Boolean*/ opened) {
					return umc.tools.getIconClass(item.icon || 'udm-container-cn');
				}
			});
			var treePane = new dijit.layout.ContentPane({
				content: this._tree,
				region: 'left',
				splitter: true,
				style: 'width: 200px;'
			});

			// add a context menu to edit/delete items
			var menu = dijit.Menu({});
			menu.addChild(new dijit.MenuItem({
				label: this._( 'Edit' ),
				iconClass: 'dijitIconEdit',
				onClick: dojo.hitch(this, function(e) {
					this.createDetailPage(this._navContextItem.objectType, this._navContextItem.id);
				})
			}));
			menu.addChild(new dijit.MenuItem({
				label: this._( 'Delete' ),
				iconClass: 'dijitIconDelete',
				onClick: dojo.hitch(this, function() {
					this.removeObjects(this._navContextItem.id);
				})
			}));
			menu.addChild(new dijit.MenuItem({
				label: this._( 'Reload' ),
				iconClass: 'dijitIconUndo',
				onClick: dojo.hitch(this, function() {
					this._tree.reload();
				})
			}));

			// when we right-click anywhere on the tree, make sure we open the menu
			menu.bindDomNode(this._tree.domNode);

			// remember on which item the context menu has been opened
			this.connect(menu, '_openMyself', function(e) {
				var el = dijit.getEnclosingWidget(e.target);
				if (el) {
					this._navContextItem = el.item;
				}
			});

			// encapsulate the current layout with a new BorderContainer in order to place
			// the tree navigation pane on the left side
			//var tmpContainer = new dijit.layout.BorderContainer({});
			//tmpContainer.addChild(treePane);
			//this._searchPage.region = 'center';
			//tmpContainer.addChild(this._searchPage);
			//this._searchPage = tmpContainer;
			titlePane.addChild(treePane);
		}

		this._searchPage.startup();
	},

	iconFormatter: function(value, rowIndex) {
		// summary:
		//		Formatter method that adds in a given column of the search grid icons
		//		according to the object types.

		// get the iconNamae
		var item = this._grid._grid.getItem(rowIndex);
		var iconName = item.objectType || '';
		iconName = iconName.replace('/', '-');

		// create an HTML image that contains the icon (if we have a valid iconName)
		var result = value;
		if (iconName) {
			result = dojo.string.substitute('<img src="images/icons/16x16/udm-${icon}.png" height="${height}" width="${width}" style="float:left; margin-right: 5px" /> ${value}', {
				icon: iconName,
				height: '16px',
				width: '16px',
				value: value
			});
		}
		return result;
	},

	filter: function(vals) {
		// summary:
		//		Send a new query with the given filter options as specified in the search form
		//		and (for the UDM navigation) the selected container.

		if ('navigation' == this.moduleFlavor) {
			var items = this._tree.get('selectedItems');
			if (items.length) {
				this._grid.filter({
					container: items[0].id
				});
			}
		}
		else {
			this._grid.filter(vals);
		}
	},

	removeObjects: function(/*String|String[]*/ _ids) {
		// summary:
		//		Remove the selected UDM objects.

		// get an array
		var ids = dojo.isArray(_ids) ? _ids : (_ids ? [ _ids ] : []);

		console.log('# removeObjects');
		console.log(dojo.toJson(_ids));
		console.log(dojo.toJson(ids));
		
		// ignore empty array
		if (!ids.length) {
			return;
		}
		console.log('# 1');

		// let user confirm deletion
		var msg = this._('Please confirm the removal of the %d selected objects!', ids.length);
		if (ids.length == 1) {
			msg = this._('Please confirm the removal of the selected object!');
		}
		umc.dialog.confirm(msg, [{
			label: this._('Delete'),
			callback: dojo.hitch(this, function() {
				// remove the selected elements via a transaction on the module store
				var transaction = this.moduleStore.transaction();
				dojo.forEach(ids, function(iid) {
					this.moduleStore.remove(iid);
				}, this);
				transaction.commit();
			})
		}, {
			label: this._('Cancel')
		}]);

	},

	showNewObjectDialog: function() {
		// summary:
		//		Open a user dialog for creating a new UDM object.

		// when we are in navigation mode, make sure the user has selected a container
		var selectedContainer = { id: '', label: '', path: '' };
		if ('navigation' == this.moduleFlavor) {
			var items = this._tree.get('selectedItems');
			if (items.length) {
				selectedContainer = items[0];
			}
			else {
				umc.dialog.alert(this._('Please select a container in the navigation bar. The new object will be placed at this location.'));
				return;
			}
		}

		// open the dialog
		var dialog = new umc.modules._udm.NewObjectDialog({
			umcpCommand: dojo.hitch(this, 'umcpCommand'),
			moduleFlavor: this.moduleFlavor,
			selectedContainer: selectedContainer,
			onDone: dojo.hitch(this, function(options) {
				// when the options are specified, create a new detail page
				options.objectType = options.objectType || this.moduleFlavor; // default objectType is the module flavor
				this.createDetailPage(options.objectType, undefined, options);
			})
		});
	},

	createDetailPage: function(objectType, ldapName, newObjOptions) {
		// summary:
		//		Creates and views the detail page for editing UDM objects.

		this._detailPage = new umc.modules._udm.DetailPage({
			umcpCommand: dojo.hitch(this, 'umcpCommand'),
			moduleStore: this.moduleStore,
			objectType: objectType,
			ldapName: ldapName,
			newObjectOptions: newObjOptions
		});
		this._detailPageCloseHandle = dojo.connect(this._detailPage, 'onClose', this, 'closeDetailPage');
		this.addChild(this._detailPage);
		this.selectChild(this._detailPage);
	},

	closeDetailPage: function() {
		// summary:
		//		Closes the detail page for editing UDM objects.

		this.selectChild(this._searchPage);
		if (this._detailPageCloseHandle) {
			dojo.disconnect(this._detailPageCloseHandle);
			this._detailPageCloseHandle = null;
		}
		if (this._detailPage) {
			this.removeChild(this._detailPage);
			this._detailPage.destroyRecursive();
			this._detailPage = null;
		}
	}
});



