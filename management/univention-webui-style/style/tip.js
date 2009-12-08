var mx,my,pid,lay_id;
var version=parseInt(navigator.appVersion.charAt (0));

function warte(lay){ // Delayfunction für Tooltip

	lay_id=lay;
	pid = window.setTimeout('showTip()',1000);
}

function showTip(){ // Zeigt Tooltip an

	if(navigator.appName=="Microsoft Internet Explorer")
	{
		if(window.lay_id) eval(lay_id+".style.visibility = 'visible'");
	}  
	if(navigator.appName=="Netscape")
	{
		if(document.getElementById(lay_id) != undefined)
		document.getElementById(lay_id).style.visibility = 'visible';
	}

}

function hideTip(){ // Verbirgt Tooltip

	window.clearTimeout(pid);

	if(navigator.appName=="Microsoft Internet Explorer")
	{
		if(window.lay_id) eval(lay_id+".style.visibility = 'hidden'");
	}
	if(navigator.appName=="Netscape")
	{
		if(document.getElementById(lay_id) != undefined)
		document.getElementById(lay_id).style.visibility = 'hidden';
	}

}

function sendForm(id,value){ // Formular mit Link senden und Button auf pressed setzen
   /* 
      https://forge.univention.org/bugzilla/show_bug.cgi?id=13035

      We have to select all members in the mmselect widget before
      the form will be submitted.
   */

	mmselect_objects=document.getElementsByTagName("div");
	for (var i = 0; i < mmselect_objects.length; i++) {
		if (mmselect_objects[i].id=='mmselect') {
			box = mmselect_objects[i].getElementsByTagName("select")[0];
			for (var j = 0; j < box.options.length; j++) {
				box.options[j].selected = true;
			}
		}
	}

   if(!value)value='pressed';
   document.forms['cache'].elements['cache'].value=id;
   document.getElementById(id).value=value;
   document.forms['content'].submit();
}

function sendForm2(id){ // Formular mit Link senden und Button auf pressed setzen
   document.forms['cache'].elements['cache'].value=id;
   document.getElementById(id).value="pressed";
   document.forms['menu'].submit();
}

function setBG(id, status){ // Ändert Background der Menüelemente für IE
/*
if(navigator.appName=="Microsoft Internet Explorer"){
	if(status)
	document.getElementById(id).style.backgroundColor = "#cc0033";
	else
	document.getElementById(id).style.backgroundColor = "#cccccc";
	}
*/
}
function clear_cached(){
  if(document.forms['cache'].elements['cache'].value)
   document.getElementById(document.forms['cache'].elements['cache'].value).value="";
  if(!document.forms['content'].elements['is_js'].value)
   document.forms['content'].elements['is_js'].value=1;
  if( document.forms['menu'] != undefined )
   if(!document.forms['menu'].elements['is_js'].value)
    document.forms['menu'].elements['is_js'].value=1;
}

function doReload(){
  document.forms['content'].submit();
}
function doRefresh(refresh){
  window.setTimeout("doReload()",refresh);
}
