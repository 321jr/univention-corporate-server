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
/*global define */

define([
	"dojo/_base/declare",
	"dojo/_base/lang",
	"dojo/_base/array",
	"dojo/Deferred",
	"dojo/promise/all",
	"dijit/form/Button",
	"umc/tools",
	"umc/render",
	"umc/widgets/ContainerWidget",
	"umc/widgets/_FormWidgetMixin",
	"umc/widgets/LabelPane"
], function(declare, lang, array, Deferred, all, Button, tools, render, ContainerWidget, _FormWidgetMixin, LabelPane) {
	return declare("umc.widgets.MultiInput", [ ContainerWidget, _FormWidgetMixin ], {
		// summary:
		//		Widget for a small list of simple and complex entries. An entry can be one or
		//		multiple input fields (TextBox, ComboBox, etc.).

		// subtypes: Object[]
		//		Essentially an array of object that describe the widgets for one element
		//		of the MultiInput widget, the 'name' needs not to be specified, this
		//		property is passed to render.widgets().
		subtypes: null,

		// max: Number
		//		Maximal number of elements.
		max: Infinity,

		// the widget's class name as CSS class
		'class': 'umcMultiInput',

		depends: null,

		name: '',

		value: null,

		delimiter: '',

		disabled: false,

		_widgets: null,

		_nRenderedElements: 0,

		_rowContainers: null,

		_newButton: null,

		_lastDepends: null,

		_valuesLoaded: false,

		// deferred for overall process (built + loaded dependencies)
		_readyDeferred: null,

		// deferred for built process
		_allWidgetsBuiltDeferred: null,

		_startupDeferred: null,

		_blockChangeEvents: false,

		_hasSubtypeLabel: false,

		_createHandler: function(ifunc) {
			// This handler will be called by all subwidgets of the MultiInput widget.
			// When the first request comes in, we will execute the function to compute
			// the dynamic values. Request within a small time interval will get the
			// same result in order to have a caching mechanism for multiple queries.
			var _valueOrDeferred = null;
			var _lastCall = 0;
			var _lastOptions = undefined;

			return function(iname, options) {
				// current timestamp
				var currentTime = (new Date()).getTime();
				var elapsedTime = Math.abs(currentTime - _lastCall);
				var optionsChanged = !tools.isEqual(options, _lastOptions);
				_lastCall = currentTime;
				_lastOptions = options;

				// if the elapsed time is too big, or we have not a Deferred object (i.e., value
				// are directly computed by a function without AJAX calls), execute the function
				if (elapsedTime > 100 || !(lang.getObject('then', false, _valueOrDeferred) && lang.getObject('cancel', false, _valueOrDeferred)) || optionsChanged) {
					_valueOrDeferred = ifunc(options);
				}
				//console.log('# new deferred: ', iname, ' elapsedTime: ', elapsedTime, ' options: ', json.stringify(options), ' values: ', _valueOrDeferred);

				// return the value
				return _valueOrDeferred;
			};
		},

		postMixInProperties: function() {
			this.inherited(arguments);

			// delete the size class
			this.sizeClass = null;

			// the _readyDeferred is being resolved as soon as everything has been set up
			this._readyDeferred = new Deferred();

			this._startupDeferred = new Deferred();
			this._allWidgetsBuiltDeferred = new Deferred();

			// check the property 'subtypes'
			tools.assert(this.subtypes instanceof Array,
					'umc/widgets/ContainerWidget: The property subtypes needs to be a string or an array of strings: ' + this.subtypes);

			this._hasSubtypeLabel = array.some(this.subtypes, function(iwidget) {
				return iwidget.label;
			});

			// initiate other properties
			this._rowContainers = [];
			this._widgets = [];

			// we need to rewire the dependencies through this widget to the row widgets
			this.depends = [];
			array.forEach(this.subtypes, function(iwidget) {
				// gather all dependencies so form can notify us
				array.forEach(tools.stringOrArray(iwidget.depends), function(idep) {
					if (array.indexOf(this.depends, idep) < 0) {
						this.depends.push(idep);
					}
				}, this);

				// parse the dynamic value function and create a handler
				var ifunc = tools.stringOrFunction(iwidget.dynamicValues, this.umcpCommand || tools.umcpCommand);
				var handler = lang.hitch(this, this._createHandler(ifunc));

				// replace the widget handler for dynamicValues with our version
				iwidget.dynamicValues = handler;

				if (iwidget.dynamicValuesInfo) {
					// UDM syntax/choices/info
					var jfunc = tools.stringOrFunction(iwidget.dynamicValuesInfo, this.umcpCommand || tools.umcpCommand);
					var thresholdHandler = lang.hitch(this, this._createHandler(jfunc));
					iwidget.dynamicValuesInfo = thresholdHandler;
				}
			}, this);
		},

		startup: function() {
			this.inherited(arguments);

			this._startupDeferred.resolve();
		},

		buildRendering: function() {
			this.inherited(arguments);

			// add empty element
			this._appendRows();
		},

		_loadValues: function(depends) {
			// delegate the call to _loadValues to all widgets
			this._lastDepends = depends;
			array.forEach(this._widgets, function(iwidgets) {
				array.forEach(iwidgets, function(jwidget) {
					if (jwidget && '_loadValues' in jwidget) {
						jwidget._loadValues(depends);
					}
				});
			});
		},

		_setAllValues: function(_valList) {
			var _valList = lang.clone(_valList);
			this._blockChangeEvents = true;
			var valList = _valList;
			if (!(valList instanceof Array)) {
				valList = [];
			}

			// adjust the number of rows
			var diff = valList.length - this._nRenderedElements;
			if (diff > 0) {
				this._appendRows(diff);
			}
			else if (diff < 0) {
				this._popElements(-diff);
			}

			this._allWidgetsBuiltDeferred.then(lang.hitch(this, function() {
				// set all values
				array.forEach(valList, function(ival, irow) {
					if (irow >= this._widgets.length) {
						return;
					}

					var rowVals = [];
					if (typeof ival == "string") {
						// entry is string .. we need to parse it if we have a delimiter
						if (this.delimiter) {
							rowVals = ival.split(this.delimiter);
						}
						else {
							rowVals = [ ival ];
						}
					}
					else if (ival instanceof Array) {
						rowVals = ival;
					}

					// set values
					for (var j = 0; j < this.subtypes.length; ++j) {
						var val = j >= rowVals.length ? '' : rowVals[j];
						this._widgets[irow][j].set('value', val);

						// for dynamic combo boxes, we need to save the value as "initial value"
						if (this._widgets[irow][j].setInitialValue) {
							this._widgets[irow][j].setInitialValue(val, false);
						}
					}
				}, this);
				this._blockChangeEvents = false;
			}));
		},

		_setValueAttr: function(_vals) {
			// remove all empty elements
			var vals = array.filter(_vals, function(ival) {
				return (typeof ival == "string" && '' !== ival) || (ival instanceof Array && ival.length);
			});

			// append an empty element
			vals.push([]);

			// set the values
			this._setAllValues(vals);
			this._set('value', this.get('value'));
		},

		_setDisabledAttr: function ( value ) {
			this._allWidgetsBuiltDeferred.then(lang.hitch(this, function() {
				var i;
				for ( i = 0; i < this._rowContainers.length; ++i) {
					var irow = this._rowContainers[i];
					array.forEach( irow ? irow.getChildren() : [], function( widget ) {
						widget.set('disabled', value);
					} );
				}
			}));
			this._set('disabled', value);
		},

		_getAllValues: function() {
			var i, j, jwidget, val, isSet, vals = [], rowVals = [];
			for (i = 0; i < this._widgets.length; ++i) {
				rowVals = [];
				isSet = false;
				for (j = 0; j < this._widgets[i].length; ++j) {
					jwidget = this._widgets[i][j];
					if (!jwidget) {
						continue;
					}
					val = jwidget.get('value');
					isSet = isSet || ('' !== val);
					if (!tools.inheritsFrom(this._widgets[i][j], 'umc.widgets.Button')) {
						rowVals.push(val);
					}
				}
				if (this.delimiter) {
					// delimiter is given, represent rows as strings
					// ... and empty rows as empty string
					vals.push(isSet ? rowVals.join(this.delimiter) : '');
				}
				else {
					// delimiter is not given, represent rows as arrays
					// ... and empty rows as empty array
					vals.push(isSet ? rowVals : []);
				}
			}
			return vals;
		},

		_getValueAttr: function() {
			// only return non-empty entries
			var vals = [];
			array.forEach(this._getAllValues(), function(ival) {
				if (typeof ival == "string" && '' !== ival) {
					vals.push(ival);
				}
				else if (ival instanceof Array && ival.length) {
					// if we only have one subtype, do not use arrays as representation
					vals.push(1 == ival.length ? ival[0] : ival);
				}
			});
			return vals;
		},

		_renderNewButton: function() {
			if (this._newButton) {
				this._newButton.destroy();
				this._newButton = null;
			}

			// add the 'new' button to the last row
			if (this._nRenderedElements < 1 || this._nRenderedElements >= this.max) {
				return;
			}

			// create 'new' button
			var btn = this.own(new Button({
				disabled: this.disabled,
				iconClass: 'umcIconAdd',
				onClick: lang.hitch(this, '_appendRows', 1),
				'class': 'umcMultiInputAddButton'
			}))[0];

			// wrap a button with a LabelPane
			this._newButton = this.own(new LabelPane({
				content: btn,
				label: this._nRenderedElements === 1 && this._hasSubtypeLabel ? '&nbsp;' : '' // only keep the label for the first row
			}))[0];

			// add button to last row
			this._allWidgetsBuiltDeferred.then(lang.hitch(this, function() {
				this._rowContainers[this._rowContainers.length - 1].addChild(this._newButton);
			}));
		},

		_updateReadyDeferred: function() {
			// check all current elements whether they are ready
			var nReady = 0;
			var nNoReadyElements = 0; // num of elements that do not have a ready method
			var nElements = 0;
			var nBuiltElements = 0;
			var i, j;
			for (i = 0; i < this._widgets.length; ++i) {
				for (j = 0; j < this._widgets[i].length; ++j, ++nElements) {
					var jwidget = this._widgets[i][j];
					nBuiltElements += jwidget ? 1 : 0;
					var jreadyDeferred = jwidget && jwidget.ready ? jwidget.ready() : null;
					if (!jreadyDeferred) {
						++nNoReadyElements;
					}
					else if (jreadyDeferred.isFulfilled()) {
						++nReady;
					}
					else {
						// deferred has not yet been resolved -> re-trigger _updateReadyDeferred() upon resolution
						jreadyDeferred.then(lang.hitch(this, '_updateReadyDeferred'));
					}
				}
			}


			// initiate new Deferred objects if none is pending
			var overallProcess = (nReady + nBuiltElements) / (2 * nElements - nNoReadyElements);
			if (overallProcess < 1 && this._readyDeferred.isFulfilled()) {
				this._readyDeferred = new Deferred();
			}
			if (nBuiltElements < nElements && this._allWidgetsBuiltDeferred.isFulfilled()) {
				this._allWidgetsBuiltDeferred = new Deferred();
			}

			// update the deferred's progress
			if (!this._readyDeferred.isFulfilled()) {
				this._readyDeferred.progress({
					percentage: 100 * overallProcess
				});
			}

			if (overallProcess >= 1 && !this._readyDeferred.isFulfilled()) {
				// all elements are ready
				this._readyDeferred.resolve();
				this.onValuesLoaded();
			}

			if (nBuiltElements == nElements && !this._allWidgetsBuiltDeferred.isFulfilled()) {
				// all elements have been built
				this._allWidgetsBuiltDeferred.resolve();
			}
		},

		__appendRow: function(irow) {
			var order = [], widgetConfs = [];
			array.forEach(this.subtypes, function(iwidget, i) {
				// add the widget configuration dict to the list of widgets
				var iname = '__' + this.name + '-' + irow + '-' + i;
				var iconf = lang.mixin({}, iwidget, {
					disabled: this.disabled,
					threshold: this.threshold, // for UDM-threshold
					name: iname,
					value: '',
					dynamicValues: lang.partial(iwidget.dynamicValues, iname)
				});
				if (iwidget.dynamicValuesInfo) {
					iconf.dynamicValuesInfo = lang.partial(iwidget.dynamicValuesInfo, iname);
				}
				widgetConfs.push(iconf);

				// add the name of the widget to the list of widget names
				order.push(iname);
			}, this);


			// render the widgets
			var widgets = render.widgets(widgetConfs, this);

			// if we have a button, we need to pass the value and index of the
			// current element
			tools.forIn(widgets, function(ikey, iwidget) {
				var myrow = irow;
				if (tools.inheritsFrom(iwidget, 'umc.widgets.Button') && typeof iwidget.callback == "function") {
					var callbackOrg = iwidget.callback;
					iwidget.callback = lang.hitch(this, function() {
						callbackOrg(this.get('value')[myrow], myrow);
					});
				}
			}, this);

			// layout widgets
			var visibleWidgets = array.map(order, function(iname) {
				return widgets[iname];
			});
			var rowContainer = this.own(new ContainerWidget({}))[0];
			array.forEach(order, function(iname) {
				// add widget to row container (wrapped by a LabelPane)
				// only keep the label for the first row
				var iwidget = widgets[iname];
				var label = irow !== 0 ? '' : iwidget.label;
				if (tools.inheritsFrom(iwidget, 'umc.widgets.Button')) {
					label = irow !== 0 ? '' : '&nbsp;';
				}
				rowContainer.addChild(new LabelPane({
					disabled: this.disabled,
					content: iwidget,
					label: label
				}));

				// register to value changes
				this.own(iwidget.watch('value', lang.hitch(this, function() {
					if (!this._blockChangeEvents) {
						this._set('value', this.get('value'));
					}
				})));
			}, this);

			// add a 'remove' button at the end of the row
			var button = this.own(new Button({
				disabled: this.disabled,
				iconClass: 'umcIconDelete',
				onClick: lang.hitch(this, '_removeElement', irow),
				'class': 'umcMultiInputRemoveButton'
			}))[0];
			rowContainer.addChild(new LabelPane({
				content: button,
				label: irow === 0 && this._hasSubtypeLabel ? '&nbsp;' : '' // only keep the label for the first row
			}));

			// add row
			this._widgets[irow] = visibleWidgets;
			this._rowContainers[irow] = rowContainer;
			this._startupDeferred.then(lang.hitch(rowContainer, 'startup'));
			this.addChild(rowContainer);

			// call the _loadValues method by hand
			array.forEach(order, function(iname) {
				var iwidget = widgets[iname];
				if ('_loadValues' in iwidget) {
					iwidget._loadValues(this._lastDepends);
				}
			}, this);

			// update the ready deferred know and when the widget itself is ready
			this._updateReadyDeferred();
			var allReady = [];
			tools.forIn(widgets, function(ikey, iwidget) {
				allReady.push(iwidget.ready ? iwidget.ready() : null);
			});
			all(allReady).then(lang.hitch(this, '_updateReadyDeferred'));
		},

		_appendRows: function(n) {
			n = n || 1;
			if (n < 1) {
				return;
			}

			var nFinal = this._nRenderedElements + n;
			var newRows = [];
			for (var irow = this._nRenderedElements; irow < nFinal && irow < this.max; ++irow, ++this._nRenderedElements) {
				newRows.push(irow);

				// allocate indeces in 2D array _widget this allows _updateReadyDeferred()
				// to know how many entries there will be at the end
				this._rowContainers[irow] = null;
				this._widgets[irow] = [];
				for (var jsubWidget = 0; jsubWidget < this.subtypes.length; ++jsubWidget) {
					this._widgets[irow][jsubWidget] = null;
				}
			}

			// force the ready deferred to be updated
			this._updateReadyDeferred();

			// perform adding rows asynchronously
			tools.forEachAsync(newRows, lang.hitch(this, '__appendRow')).then(lang.hitch(this, function() {
				// all elements have been added to the DOM
				// add the new button
				this._renderNewButton();
				this._updateReadyDeferred();
			}));
		},

		_popElements: function(n) {
			if (n < 1) {
				return;
			}

			for (var irow = this._nRenderedElements - 1; irow >= this._nRenderedElements - n; --irow) {
				// destroy the row container
				this._rowContainers[irow].destroyRecursive();

				// clean up internal arrays
				this._rowContainers.pop();
				this._widgets.pop();
			}

			// update the number of render elements
			this._nRenderedElements -= n;


			// add the new button
			this._renderNewButton();
		},

		_removeElement: function(idx) {
			var vals = this._getAllValues();
			vals.splice(idx, 1);

			// add an empty line in case we removed the last element
			if (!vals.length) {
				vals.push('');
			}
			this._setAllValues(vals);
		},

		isValid: function() {
			var areValid = true;
			var i, j;
			for (i = 0; i < this._widgets.length; ++i) {
				for (j = 0; j < this._widgets[i].length; ++j) {
					areValid = areValid && (!this._widgets[i][j].isValid || this._widgets[i][j].isValid());
				}
			}
			return areValid;
		},

		setValid: function(/*Boolean|Boolean[]*/ areValid, /*String?|String[]?*/ messages) {
			// summary:
			//		Set all child elements to valid/invalid.
			//		Parameters can be either simple values (Boolean/String) or arrays.
			//		Arrays indicate specific states for each element
			var i, j;
			for (i = 0; i < this._widgets.length; ++i) {
				var imessage = messages instanceof Array ? messages[i] : messages;
				var iisValid = areValid instanceof Array ? areValid[i] : areValid;
				for (j = 0; j < this._widgets[i].length; ++j) {
					this._widgets[i][j].setValid(iisValid, imessage);
				}
			}
		},

		_setBlockOnChangeAttr: function(/*Boolean*/ value) {
			// execute the inherited functionality in the widget's scope
			if (this._widget) {
				tools.delegateCall(this, arguments, this._widget);
			}
		},

		_getBlockOnChangeAttr: function(/*Boolean*/ value) {
			// execute the inherited functionality in the widget's scope
			if (this._widget) {
				tools.delegateCall(this, arguments, this._widget);
			}
		},

		onValuesLoaded: function(values) {
			// summary:
			//		This event is triggered when all values (static and dynamic) have been loaded.
			// values:
			//		Array containing all dynamic and static values.
		},

		// ready:
		//		Similiar to `umc/widgets/_FormWidgetMixin:ready`.
		ready: function() {
			return this._readyDeferred;
		}
	});
});

