/*
 * Copyright 2013 Univention GmbH
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
/*global define require window*/

define([
	"dojo/topic",
	"dojo/_base/array",
	"umc/store",
	"umc/tools",
	"umc/dialog"
], function(topic, array, store, tools, dialog) {
	var _buildSiteTitle = function(parts) {
		var titleStr = [];
		array.forEach(parts, function(i) {
			if (i) {
				// ignore values that are: null, undefined, ''
				i = i + ''; // force element to be string...
				titleStr.push(i.replace(/\//g, '-'));
			}
		});

		// join elements with '/' -> such that a hierarchy can be recongnized by Piwik
		return titleStr.join('/');
	};

	var _disablePiwik = false;
	var piwikTracker = null;
	var sendAction = function() {
		//console.log('### sendAction');
		if (!piwikTracker || _disablePiwik) {
			//console.log('###   ', piwikTracker, _disablePiwik);
			return;
		}
		//console.log('###   ', arguments);
		piwikTracker.setDocumentTitle(_buildSiteTitle(arguments));
		piwikTracker.setCustomUrl(window.location.protocol + "//" + window.location.host);
		piwikTracker.trackPageView();
	};

	var disablePiwik = function(disable) {
		//console.log('### disablePiwik:', disable);
		// send that piwik has been disabled
		tools.status('piwikDisabled', disable);
		_disablePiwik = false;
		sendAction('piwik', disable ? 'disable' : 'enable');
		_disablePiwik = disable;

		if (!require('umc/modules/ucr')) {
			// UCR UMC module is not available
			return;
		}

		// set the UCR variable accordingly
		var ucrStore = store('key', 'ucr');
		if (disable) {
			// explicitely set UCR variable to false
			topic.publish('/umc/actions', 'menu-help', 'piwik');
			ucrStore.put({
				key: 'umc/web/piwik',
				value: 'false'
			});
		} else {
			// remove UCR variable to obtain the default behaviour
			ucrStore.remove('umc/web/piwik');
		}
	};

	var loadPiwik = function() {
		//console.log('### loadPiwik');
		require(["https://www.piwik.univention.de/piwik.js"], function() {
			// create a new tracker instance
			piwikTracker = Piwik.getTracker('https://www.piwik.univention.de/piwik.php', 14);
			piwikTracker.enableLinkTracking();

			// send login action
			topic.publish('/umc/actions', 'session', 'login');
		});
	};

	// subscribe to all topics containing interesting actions
	topic.subscribe('/umc/actions', sendAction)

	// subscribe for disabling piwik
	topic.subscribe('/umc/piwik/disable', disablePiwik)

	// check whether piwik is enabled
	tools.ucr([
		'umc/web/piwik',
		'license/base'
	]).then(function(result) {
		var piwikUcrv = result['umc/web/piwik'];
		var piwikUcrvIsSet = typeof piwikUcrv == 'string' && piwikUcrv !== '';
		var ffpuLicense = result['license/base'] == 'Free for personal use edition';
		if (tools.isTrue(result['umc/web/piwik']) || (!piwikUcrvIsSet && ffpuLicense)) {
			// use piwik for user action feedback if it is not switched off explicitely
			tools.status('piwikDisabled', false);
			loadPiwik();
		} else {
			tools.status('piwikDisabled', true);
		}
	});
});

