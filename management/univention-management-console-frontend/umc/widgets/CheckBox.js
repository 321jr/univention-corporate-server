/*global dojo dijit dojox umc console */

dojo.provide("umc.widgets.CheckBox");

dojo.require("dijit.form.CheckBox");

dojo.declare("umc.widgets.CheckBox", dijit.form.CheckBox, {
	// by default, the checkbox is turned off
	value: 'false', 

	_setValueAttr: function(newValue) {
		this.set('checked', newValue == '0' || newValue == 'false' || newValue == 'FALSE' || !newValue ? false : true);
	},

	_getValueAttr: function() {
		return this.get('checked');
	}
});



