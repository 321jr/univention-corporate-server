<?php
$this->data['header'] = $this->t($this->data['dictTitle']);

$this->data['head'] = <<<EOF
<meta name="robots" content="noindex, nofollow" />
<meta name="googlebot" content="noarchive, nofollow" />
EOF;

$this->includeAtTemplateBase('includes/header.php');
?>

<script type="text/javascript">
	//<!--
		require(["umc/dialog", "umc/tools", "dojo/json", "dojox/html/entities", "umc/i18n!management"], function(dialog, tools, json, entities, _) {
			setTimeout(function() { /* dependency problem umc/dialog is not yet require()d in umc/tools*/
				var data = <?php
$title = $this->t($this->data['dictTitle']);
$message = $this->t($this->data['dictDescr'], $this->data['parameters']) . " (Tracking-ID: " . $this->data['error']['trackId'] . ")";
$traceback = $this->data['showerrors'] ? $title . "\n\n" . $message . "\n\n" . $this->data['error']['exceptionMsg'] : "";
echo json_encode(array(
	"status" => 500,
	"title" => $title,
	"message" => $message,
	"traceback" => $traceback,
));
				?>;
				var info = tools.parseError(data);
				info.title = info.title || _('HTTP Error %s', info.status);
				tools.getErrorHandler({ force401Display: true, hideInformVendor: true, hideInformVendorViaMail: true }).displayError(info).then().always(function() {
					setTimeout(function() {
						window.location.href = data.location || '/univention/management/';
					}, 1000);
				});
			}, 1000);
		});
	//-->
</script>

<noscript>
    <h2><?php echo $this->t($this->data['dictTitle']); ?></h2>
<?php
echo htmlspecialchars($this->t($this->data['dictDescr'], $this->data['parameters']));

// include optional information for error
if (isset($this->data['includeTemplate'])) {
    $this->includeAtTemplateBase($this->data['includeTemplate']);
}
?>
    <div class="trackidtext">
        <p><?php echo $this->t('report_trackid'); ?></p>
        <div class="input-group" style="width: 1em;">
            <pre id="trackid" class="input-left"><?php echo $this->data['error']['trackId']; ?></pre>
            <!--<button data-clipboard-target="#trackid" id="btntrackid" class="btnaddonright">
                <img src="/<?php echo $this->data['baseurlpath'].'resources/icons/clipboard.svg'; ?>"
                     alt="Copy to clipboard" />
            </button>-->
        </div>
    </div>
<?php
// print out exception only if the exception is available
if ($this->data['showerrors']) {
?>
    <h2><?php echo $this->t('debuginfo_header'); ?></h2>
    <p><?php echo $this->t('debuginfo_text'); ?></p>

    <div style="border: 1px solid #eee; padding: 1em; font-size: x-small">
        <p style="margin: 1px"><?php echo htmlspecialchars($this->data['error']['exceptionMsg']); ?></p>
        <pre style="padding: 1em; font-family: monospace;"><?php
            echo htmlspecialchars($this->data['error']['exceptionTrace']); ?></pre>
    </div>
<?php
}

/* Add error report submit section if we have a valid technical contact. 'errorreportaddress' will only be set if
 * the technical contact email address has been set.
 */
if (isset($this->data['errorReportAddress'])) {
?>
    <h2><?php echo $this->t('report_header'); ?></h2>
    <form action="<?php echo htmlspecialchars($this->data['errorReportAddress']); ?>" method="post">
        <p><?php echo $this->t('report_text'); ?></p>
        <p><?php echo $this->t('report_email'); ?>
            <input type="email" size="25" name="email" value="<?php echo htmlspecialchars($this->data['email']); ?>" />
        </p>
        <p>
            <textarea class="metadatabox" name="text" rows="6" cols="50" style="width: 100%; padding: 0.5em;"><?php
                echo $this->t('report_explain'); ?></textarea>
        </p>
        <p>
            <input type="hidden" name="reportId" value="<?php echo $this->data['error']['reportId']; ?>"/>
            <button type="submit" name="send" class="btn"><?php echo $this->t('report_submit'); ?></button>
        </p>
    </form>
    <?php
}
?>
    <h2 style="clear: both"><?php echo $this->t('howto_header'); ?></h2>
    <p><?php echo $this->t('howto_text'); ?></p>
</noscript>
<?php
$this->includeAtTemplateBase('includes/footer.php');
