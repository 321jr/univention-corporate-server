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
	"dojo/topic",
	"dojo/promise/all",
	"dijit/layout/BorderContainer",
	"dojox/html/entities",
	"umc/dialog",
	"umc/tools",
	"umc/app",
	"umc/widgets/ContainerWidget",
	"umc/widgets/ConfirmDialog",
	"umc/widgets/Module",
	"umc/widgets/Page",
	"umc/widgets/Text",
	"umc/widgets/ExpandingTitlePane",
	"umc/widgets/TextBox",
	"umc/widgets/PasswordBox",
	"umc/widgets/ProgressBar",
	"umc/modules/join/Form",
	"umc/modules/join/Grid",
	"umc/modules/lib/server",
	"umc/i18n!umc/modules/join"
], function(declare, lang, topic, all, BorderContainer, entities, dialog, tools, app, ContainerWidget, ConfirmDialog,
			Module, Page, Text, ExpandingTitlePane, TextBox, PasswordBox, ProgressBar, JoinForm, JoinGrid, Lib_Server, _) {

	var JoinPage = declare("umc.modules.join.JoinPage", [Page], {
		_titlePane: null,
		_form: null,
		_joining: null, // flag for the last executed action

		headerText: _("Initial system join"),

		buildRendering: function() {
			this.inherited(arguments);

			this._titlePane = new ExpandingTitlePane({
				title: _("credentials")
			});
			this.addChild(this._titlePane);

			this._form = new JoinForm({});
			this._titlePane.addChild(this._form);
		}
	});

	var StatusPage = declare("umc.modules.join.StatusPage", [Page], {
		_titlePane: null,
		_grid: null,

		headerText: _("Join status"),
		helpText: _("This page shows the status of all available join scripts on this system, along with all join-related actions."),

		buildRendering: function() {
			this.inherited(arguments);

			this._titlePane = new ExpandingTitlePane({
				title: _("Join status")
			});
			this.addChild(this._titlePane);

			this._grid = new JoinGrid({
				sortIndex: 2
			});
			this._titlePane.addChild(this._grid);
		}
	});

	var LogPage = declare("umc.modules.join.LogPage", [Page], {
		_titlePane: null,
		_logtext: null, // text widget that holds log

		headerText: _("Join log"),

		postMixInProperties: function() {
			this.inherited(arguments);
			this.footerButtons = [{
				name: 'close',
				label: _('Show Join status'),
				callback: lang.hitch(this, 'onShowGrid')
			}];
		},

		buildRendering: function() {
			this.inherited(arguments);

			this._titlePane = new ExpandingTitlePane({
				title: _("Join log")
			});
			this.addChild(this._titlePane);

			var container = new BorderContainer({gutters: false});
			this._titlePane.addChild(container);

			// temporary container for scrolling to the bottom
			var logContainer = new ContainerWidget({
				region:			'center',
				scrollable:		true
			});
			container.addChild(logContainer);

			// FIXME use a generic CSS class that requests a specific monospaced font
			this._logtext = new Text({
				region:			'center',
				content:		_('... loading log ...'),
				style:			'font-family:monospace;'
			});

			logContainer.addChild(this._logtext);
		},

		onShowGrid: function() {
			// event stub
		},

		setText: function(text) {
			this._logtext.set('content', text);
		},

		// fetches join log text.
		fetch_log_text: function() {
			// now really fetch log file contents.
			tools.umcpCommand('join/logview').then(lang.hitch(this, function(data) {
				var txt = entities.encode(data.result).replace(/\n/g, "<br/>\n");
				this.setText(txt);
			}));
		}
	});

	return declare("umc.modules.join", [ Module ], {

		standbyOpacity:		1,
		region: 			'center',

		_serverRole: null,

		_switchView: function(code) {
			var lastSelectedChild = this.selectedChildWidget;

			var child = {
				'grid': this._statuspage,
				'log': this._logpage,
				'join_form': this._joinpage
			}[code];
			if (child) {
				this.selectChild(child);
			}

			// update the layout if view changed
			if (lastSelectedChild != this.selectedChildWidget) {
				this.layout();
				// redo the status query for the grid
				this._statuspage._grid.reload_grid();
			}
		},

		buildRendering: function() {
			this.inherited(arguments);
			this.standby(true);

			this._progressBar = new ProgressBar();
			this.own(this._progressBar);

			this._joinpage = new JoinPage();
			this.addChild(this._joinpage);

			this._statuspage = new StatusPage();
			this.addChild(this._statuspage);

			this._logpage = new LogPage();
			this.addChild(this._logpage);

			// select the status page as default
			this.selectChild(this._statuspage);

			// join the system
			this._joinpage._form.on('submit', lang.hitch(this, function() {
				// trigger the join procedure
				var values = this._joinpage._form.get('value');
				this._joinpage._form._widgets.password.set('value', '');

				topic.publish('/umc/actions', this.moduleID, this.moduleFlavor, 'initial-join');
				this.join(values);
			}));

			// run join scripts
			this._statuspage._grid.on('runScripts', lang.hitch(this, function(scripts, force) {
				var txtscripts = '<ul style="max-height: 200px; overflow: auto;"><li>' + scripts.join('</li><li>') + '</ul>';
				if (this._serverRole == 'domaincontroller_master') {
					// we don't need credentials on DC master
					dialog.confirm(_('The following join scripts will be executed: ') + txtscripts, [{
						name: 'run',
						label: _('Run join scripts'),
						callback: lang.hitch(this, function() {
							this.runJoinScripts(scripts, force, {});
						})
					}, {
						name: 'cancel',
						label: 'Cancel',
						'default': true
					}]);
				} else {
					this.getCredentials(txtscripts).then(lang.hitch(this, function(credentials) {
						this.runJoinScripts(scripts, force, credentials);
					}));
				}
			}));

			// show the join logfile
			this._statuspage._grid.on('ShowLogfile', lang.hitch(this, function() {
				this._switchView('log');
				this._logpage.fetch_log_text();
			}));

			// rejoin the system
			this._statuspage._grid.on('Rejoin',  lang.hitch(this, function() {
//				this._switchView('join_form');
				dialog.confirmForm({form: new JoinForm({buttons: []}), submit: _('Rejoin system'), style: 'max-width: 350px;'}).then(lang.hitch(this, function(values) {
					this.join(values);
				}));
			}));

			this._logpage.on('ShowGrid', lang.hitch(this, function() {
				this._switchView('grid');
			}));

			all([
				this.umcpCommand('join/joined'),
				this.umcpCommand('join/running'),
				tools.ucr('server/role')
			]).then(lang.hitch(this, function(results) {
				var joined = results[0].result;
				var job_running = results[1].result;
				this._serverRole = results[2]['server/role'];

				this.standby(false);
				this.standbyOpacity = 0.75;  // set it back to semi transparent

				if (job_running) {
					// display the running progress
					this._joinpage.showProgressBar(_('A join process is already running...'), _('The join scripts have successfully been executed.'));
				}
				else if (!joined) {
					if (this._serverRole == 'domaincontroller_master') {
						dialog.alert(_('A DC master should be joined by the %s.', app.linkToModule('setup')));
						return;
					}
					this._switchView('join_form');
				} else {
					// grid view is selected by default... refresh the grid
					this._statuspage._grid.reload_grid();
				}
			}), lang.hitch(this, function() {
				this.standby(false);
			}));
		},

		// starts the join process and show progressbar
		join: function(dataObj) {
			this.standby(true);
			this.umcpCommand('join/join', {
				hostname: dataObj.hostname,
				username: dataObj.username,
				password: dataObj.password
			}, false).then(
				lang.hitch(this, function(data) {
					this._joining = true;
					this.showProgressBar();
				}), lang.hitch(this, function(error) {
					this._joining = false;
					this.handleError(error, _("Can't start join process:<br>"));
				})
			);
		},

		runJoinScripts: function(scripts, force, credentials) {
			this.standby(true);

			var values = { scripts: scripts, force: force };
			if (credentials.username) {
				values.username = credentials.username;
			}
			if (credentials.password) {
				values.password = credentials.password;
			}

			this.umcpCommand('join/run', values, false).then(
				lang.hitch(this, function(data) {
					this._joining = false;
					// Job is started. Now wait for its completion.
					this.showProgressBar();
				}),
				lang.hitch(this, function(error) {
					this._joining = false;
					this.handleError(error, _("Can't run join scripts:<br>"));
				})
			);
		},

		handleError: function(error, msg, title) {
			this.standby(false);
			if (error.response.status != 400 && error.response.status != 409) {
				return tools.handleErrorStatus(error.response, true);
			}
			var errormessage = '';
			// lol, we got HTTP errors which are exactly meant the other way round
			if (error.response.status == 400) {
				errormessage = msg;
				errormessage += error.response.data.result.error;
			} else if (error.response.status == 409) {
				errormessage = error.response.data.message + ':<br>';
				_('username'); _('password'); _('hostname');
				tools.forIn(error.response.data.result, function(key, value) {
					errormessage += key + ': ' + value + '<br>';
				});
			}
			dialog.alert(errormessage, title || _('Error'));
			this.reinit(false);
		},

		showProgressBar: function(title, successmsg) {
			this.standby(false);
			this.standby(true, this._progressBar);
			// Job is started. Now wait for its completion.
			this._progressBar.reset(title || _('Starting the join process...'));
			this._progressBar.auto(
				'join/progress',
				{},
				lang.hitch(this, function() {
					this.standby(false);
					var errors = this._progressBar.getErrors();
					if (errors.critical) {
						// invalid credentials... don't show the restart dialog
						dialog.alert(errors.errors[0], _('Join error'));
						this.reinit(false);
					} else if (errors.errors.length) {
						this._alert(errors.errors[0], _('Join error'), lang.hitch(this, function() {
							// reload and show restart dialog after user closed the pop up
							this.reinit(true);
						}));
					} else {
						dialog.notify(successmsg || _('The join process was successful.'));
						this.reinit(true);
					}
				}),
				undefined,
				undefined,
				true // let our callback handle errors
			);
		},

		// gets the current join status and switches display mode if needed.
		reinit: function(restart) {
			this.standby(true);
			return this.umcpCommand('join/joined').then(lang.hitch(this, function(data) {
				// update view
				var joined = data.result;
				if (joined) {
					// show grid with join status, else....
					this._switchView('grid');
				} else {
					// show affordance to join, nothing more.
					this._switchView('join_form');
				}

				if (restart) {
					// ask to restart / reboot
					if (this._joining && joined) {
						Lib_Server.askReboot(_('A reboot of the server is recommended after joining the system.'));
					} else {
						Lib_Server.askRestart(_('A restart of the UMC server components may be necessary for changes to take effect.'));
					}
				}

				this._joining = null;
				this._statuspage._grid.reload_grid();
				this.standby(false);
			}), lang.hitch(this, function(result) {
				this.standby(false);
				console.error("reinit ERROR " + result.message);
			}));
		},

		_alert: function(msg, title, callback) {
			var dialog = new ConfirmDialog({
				message: msg,
				title: title,
				style: 'max-width: 650px;',
				options: [{
					label: 'Ok',
					'default': true,
					callback: lang.hitch(this, function() {
						callback();
						dialog.hide();
					})
				}]
			});
			this.own(dialog);
			dialog.on('cancel', function() { callback(); });
			dialog.show();
			return dialog;
		},

		// pop up to ask for credentials when running join scripts
		getCredentials: function(scripts) {
			var msg = _('<p>Please enter credentials of an user account with administrator rights to run the selected join scripts.</p>') + scripts;
			var deferred = dialog.confirmForm({
				widgets: [{
					name: 'text',
					type: Text,
					content: msg
				}, {
					name: 'username',
					type: TextBox,
					label: _('Username'),
					value: tools.status('username')
				}, {
					name: 'password',
					type: PasswordBox,
					label: _('Password')
				}],
				layout: [ 'text', 'username', 'password' ],
				title: _('Run join scripts'),
				submit: _('Run'),
				style: 'max-width: 400px;'
			}).then(function(values) {
				if (!values.password || values.password.length === 0) {
					dialog.alert(_('The password may not be empty.'), _('Password invalid'));
					throw new Error();
				}
				if (!values.username || values.username.length === 0) {
					dialog.alert(_('The username may not be empty.'), _('Username invalid'));
					throw new Error();
				}
				return values;
			});

			return deferred;
		}

	});
});
