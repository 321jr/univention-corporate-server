/*
 * Copyright 2012-2014 Univention GmbH
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
/*global define require*/

define([
	"dojo/_base/declare",
	"dojo/_base/lang",
	"dojo/_base/event",
	"dojo/dom-construct",
	"dojo/on",
	"dojo/keys",
	"dojo/topic",
	"dijit/form/ComboBox",
	"umc/widgets/TextBox",
	"umc/i18n!umc/modules/setup"
], function(declare, lang, dojoEvent, domConstruct, on, keys, topic, DijitComboBox, TextBox, _) {
	return declare('umc.modules.setup.LiveSearch', [DijitComboBox, TextBox], {
		searchAttr: 'label',
		hasDownArrow: false,
		autoComplete: false,
		highlightMatch: 'none',
		store: null,
		_searchNode: null,
		_searchingNode: null,
		_currentNode: null,
		inlineLabel: _('e.g., Boston...'),

		buildRendering: function() {
			this.inherited(arguments);

			this._currentNode = this._buttonNode;

			this._searchNode = lang.clone(this._buttonNode);
			this._searchNode.style.display = '';
			this._searchNode.childNodes[0].style.backgroundImage = 'url("' + require.toUrl('umc/modules/setup/search-icon.png') + '")';
			this._searchNode.childNodes[0].style.backgroundPosition = 'center';
			this.own(on(this._searchNode, 'click', lang.hitch(this, 'loadDropDown')));

			this._searchingNode = lang.clone(this._searchNode);
			this._searchingNode.childNodes[0].style.backgroundImage = 'url("' + require.toUrl('dijit/themes/umc/form/images/loading.gif') + '")';

			this._setState('search');
		},

		postCreate: function() {
			this.inherited(arguments);

			this.store.on('searching', lang.hitch(this, '_setState', 'searching'));
			this.store.on('searchFinished', lang.hitch(this, '_setState', 'search'));
		},

		_setState: function(state) {
			var newNode = this._currentNode;
			if (state == 'searching') {
				newNode = this._searchingNode;
			}
			else {
				newNode = this._searchNode;
			}
			domConstruct.place(newNode, this._currentNode, 'replace');
			this._currentNode = newNode;
		},

		loadDropDown: function() {
			this._startSearch(this.get('value'));
		},

		_onKey: function(evt) {
			var lastResult = this.store.lastResult;
			if (evt.keyCode == keys.ENTER) {
				if (this.state != 'searching' && lastResult.length && this._opened) {
					// select first item
					this.set('item', lastResult[0]);
					this.closeDropDown();
					dojoEvent.stop(evt);
					return;
				}
				if (this.state == 'searching' || !this.get('item')) {
					// ignore key event
					dojoEvent.stop(evt);
					return;
				}
			}
			this.inherited(arguments);
		}
	});
});
