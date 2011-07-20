/*global dojo dijit dojox umc console window */

dojo.provide("umc.widgets.CategoryPane");

dojo.require("dijit.layout.ContentPane");
dojo.require("dijit._Contained");
dojo.require("dijit._Container");
dojo.require("dijit.TitlePane");
dojo.require("umc.tools");
dojo.require("umc.widgets.Tooltip");

//TODO: don't use float, use display:inline-block; we need a hack for IE7 here, see:
//      http://robertnyman.com/2010/02/24/css-display-inline-block-why-it-rocks-and-why-it-sucks/
dojo.declare( "umc.widgets._CategoryItem", [dijit.layout.ContentPane, dijit._Contained], {
	modID: '',
	modIcon: '',
	label: '',
	description: '',

	postMixInProperties: function() {
		this.inherited(arguments);
		dojo.mixin(this, {
			baseClass: 'modLaunchButton',
			'class': umc.tools.getIconClass(this.modIcon, 64),
			content: '<div>' + this.label + '</div>'
		});
	},

	postCreate: function() {
		this.inherited(arguments);

		// add a tooltip
		var tooltip = new umc.widgets.Tooltip({
			label: this.description,
			connectId: [ this.domNode ]
		});

		//this.domNode.innerHtml = '<div>' + this.description + '</div>';
		this.connect(this, 'onMouseOver', function(evt) {
			dojo.addClass(this.domNode, 'modLaunchButtonHover');
		});
		this.connect(this, 'onMouseOut', function(evt) {
			dojo.removeClass(this.domNode, 'modLaunchButtonHover');
		});
		this.connect(this, 'onMouseDown', function(evt) {
			dojo.addClass(this.domNode, 'modLaunchButtonClick');
		});
		this.connect(this, 'onMouseUp', function(evt) {
			dojo.removeClass(this.domNode, 'modLaunchButtonClick');
		});
	}
});

dojo.declare( "umc.widgets.CategoryPane", [dijit.TitlePane, dijit._Container], {
	// summary:
	//		Widget that displays an overview of all modules belonging to a 
	//		given category along with their icon and description.

	// modules: Array
	//		Array of modules in the format {id:'...', title:'...', description:'...'}
	modules: [],

	// title: String
	//		Title of category for which the modules shall be displayed
	title: '',

	postMixInProperties: function() {
		this.inherited(arguments);
	},

	buildRendering: function() {
		// summary:
		//		Render a list of module items for the given category.

		this.inherited(arguments);

		// iterate over all modules
		dojo.forEach(this.modules, dojo.hitch(this, function(imod) {
			// create a new button widget for each module
			var modWidget = new umc.widgets._CategoryItem({
				modID: imod.id,
				modIcon: imod.icon,
				label: imod.name,
				description: imod.description
			});

			// hook to the onClick event of the module
			this.connect(modWidget, 'onClick', function(evt) {
				this.onOpenModule(imod);
			});

			// add module widget to the container
			this.addChild(modWidget);
		}));

		// we need to add a <br> at the end, otherwise we will get problems 
		// with the visualizaton
		//this.containerNode.appendChild(dojo.create('br', { clear: 'all' }));
	},

	onOpenModule: function(imod) {
		// event stub
	}
});


