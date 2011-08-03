/*global console MyError dojo dojox dijit umc */

dojo.provide("umc.modules.top");

dojo.require("dojox.string.sprintf");
dojo.require("umc.dialog");
dojo.require("umc.i18n");
dojo.require("umc.widgets.ExpandingTitlePane");
dojo.require("umc.widgets.Module");
dojo.require("umc.widgets.Page");
dojo.require("umc.widgets.SearchForm");

dojo.declare("umc.modules.top", [ umc.widgets.Module, umc.i18n.Mixin ], {

	_grid: null,
	_store: null,
	_searchWidget: null,
	_contextVariable: null,
	_page: null,

	i18nClass: 'umc.modules.top',
	idProperty: 'pid',

	killProcesses: function(signal, pids) {
		var params = {
			signal: signal,
			pid: pids
		};
		this.umcpCommand('top/kill', params).then(dojo.hitch(this, function(data) {
			umc.dialog.notify(this._('Processes killed successfully'));
		}));
	},

	killProcesses: function(signal, pids) {
		var params = {
			signal: signal,
			pid: pids
		};
		this.umcpCommand('top/kill', params).then(dojo.hitch(this, function(data) {
			umc.dialog.notify(this._('Processes killed successfully'));
		}));
	},

	buildRendering: function() {
		this.inherited(arguments);

		this._page = new umc.widgets.Page({
			headerText: this._('Process overview'),
			helpText: this._('This module generates an overview of all running processes. The search function can reduce the number of results. Specifig processes can be selected and terminated. If a process can\'t be normally terminated (using SIGTERM signal), the termination can be forced (using SIGKILL signal).')
		});
		this.addChild(this._page);

		var titlePane = new umc.widgets.ExpandingTitlePane({
			title: this._('Entries')
		});
		this._page.addChild(titlePane);

		var actions = [{
			name: 'terminate',
			label: this._('Terminate processes'),
			iconClass: 'dijitIconDelete',
			callback: dojo.hitch(this, 'killProcesses', 'SIGTERM')
		}, {
			name: 'kill',
			label: this._('Kill processes'),
			iconClass: 'dijitIconDelete',
			callback: dojo.hitch(this, 'killProcesses', 'SIGKILL')
		}];

		var columns = [{
			name: 'user',
			label: this._('User'),
            width: '100px'
		}, {
			name: 'pid',
			label: this._('PID'),
            width: '75px'
		}, {
			name: 'cpu',
			label: this._('CPU (%)'),
            width: '50px'
		}, {
			name: 'vsize',
			label: this._('Virtual size (MB)'),
            width: '125px',
			formatter: function(value) {
				return dojox.string.sprintf('%.1f', value);
			}
		}, {
			name: 'rssize',
			label: this._('Resident set size (MB)'),
            width: '150px',
			formatter: function(value) {
				return dojox.string.sprintf('%.1f', value);
			}
		}, {
			name: 'mem',
			label: this._('Memory (%)'),
            width: '80px'
		}, {
			name: 'command',
			label: this._('Command'),
            width: 'auto'
		}];

		this._grid = new umc.widgets.Grid({
			region: 'center',
			actions: actions,
			columns: columns,
			moduleStore: this.moduleStore,
			query: {
                category: 'all',
                filter: '*'
            }
		});
		titlePane.addChild(this._grid);

		var widgets = [{
			type: 'ComboBox',
			name: 'category',
			value: 'all',
			label: this._('Category'),
			staticValues: [
				{id: 'all', label: this._('All')},
				{id: 'user', label: this._('User')},
				{id: 'pid', label: this._('PID')},
				{id: 'command', label: this._('Command')}
			]
		}, {
			type: 'TextBox',
			name: 'filter',
			value: '*',
			label: this._('Keyword')
		}];

		this._searchWidget = new umc.widgets.SearchForm({
			region: 'top',
			widgets: widgets,
			layout: [['category', 'filter']],
			onSearch: dojo.hitch(this._grid, 'filter')
		});

		titlePane.addChild(this._searchWidget);

		this._page.startup();
    }
});
