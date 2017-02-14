<?php

/**
 * Support the htmlinject hook, which allows modules to change header, pre and post body on all pages.
 */
$this->data['htmlinject'] = array(
	'htmlContentPre' => array(),
	'htmlContentPost' => array(),
	'htmlContentHead' => array(),
);


$jquery = array();
if (array_key_exists('jquery', $this->data)) $jquery = $this->data['jquery'];

if (array_key_exists('pageid', $this->data)) {
	$hookinfo = array(
		'pre' => &$this->data['htmlinject']['htmlContentPre'],
		'post' => &$this->data['htmlinject']['htmlContentPost'],
		'head' => &$this->data['htmlinject']['htmlContentHead'],
		'jquery' => &$jquery, 
		'page' => $this->data['pageid']
	);
		
	SimpleSAML_Module::callHooks('htmlinject', $hookinfo);
}

/**
 * Do not allow to frame simpleSAMLphp pages from another location.
 * This prevents clickjacking attacks in modern browsers.
 *
 * If you don't want any framing at all you can even change this to
 * 'DENY', or comment it out if you actually want to allow foreign
 * sites to put simpleSAMLphp in a frame. The latter is however
 * probably not a good security practice.
 */
header('X-Frame-Options: SAMEORIGIN');

// read and sort available languages and prepare an array to later display them
$jsonfile = file_get_contents('/var/www/univention/languages.json');
$json = json_decode($jsonfile, true);
if ($json != NULL) {
	function sort_by_label($a, $b) {
		return strcasecmp($a['label'], $b['label']);
	}
	// hardcode english
	$en_us_found = false;
	foreach ($json as $entry) {
		if ($entry['id'] === 'en-US') {
			$en_us_found = true;
		}
	}
	if (!$en_us_found) {
		$json[] = array ('id' => 'en-US', 'label' => 'English');
	}
	// sort entries and prepare html code
	usort($json, "sort_by_label");
	foreach ($json as $entry) {
		$splitarray = explode('-', $entry['id']);
		$langstring = $splitarray[0];
		$langlinkarray[] = array(
			"id" => $entry['id'],
			"label" => $entry['label'],
			"href" => SimpleSAML_Utilities::addURLparameter(SimpleSAML_Utilities::selfURL(), array($this->languageParameterName => $langstring))
		);
	}
}
?><!DOCTYPE html>
<html>
	<head>
		<title>Univention Corporate Server Single-Sign-On</title>
		<meta http-equiv="Content-Type" content="text/html; charset=utf-8" />
		<meta http-equiv="X-UA-Compatible" content="IE=edge" />
		<meta name="viewport" content="target-densitydpi=device-dpi, width=device-width, height=device-height, initial-scale=1.0" />
		<meta name="robots" content="noindex, nofollow" />
		<link rel="shortcut icon" href="/favicon.ico" type="image/icon"/>
		<link rel="stylesheet" href="/univention/js/dijit/themes/umc/umc.css" type="text/css"/>
		<link rel="stylesheet" href="/univention/management/style.css">
<?php
if ($this->isLanguageRTL()) {
	echo '<link rel="stylesheet" type="text/css" href="/' . $this->data['baseurlpath'] . 'resources/default-rtl.css" />';
}
if(array_key_exists('head', $this->data)) {
	echo '<!-- head -->' . $this->data['head'] . '<!-- /head -->';
}
?>
		<script type="text/javascript">
			var availableLocales = <?php echo json_encode($langlinkarray); ?>;
		</script>
		<script type="text/javascript" src="/univention/js/config.js"></script>
		<script type="text/javascript" src="/univention/login/config.js"></script>
		<script type="text/javascript">
<?php
/** don't display language switcher when e.g. forms were sent */
if ($_SERVER['REQUEST_METHOD'] === 'POST') {
	echo 'umcConfig.allowLanguageSwitch = false;';
}
?>
		</script>
		<script type="text/javascript" async src="/univention/js/dojo/dojo.js"></script>
	</head>
	<body class="umc">
		<div class="umcHeader">
			<div class="umcHeaderRight">
				<div id="umcMenu" data-dojo-type="umc/Menu"></div>
				<div class="univentionLogo"></div>
			</div>
		</div>
