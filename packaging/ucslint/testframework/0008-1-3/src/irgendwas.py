#!/usr/bin/python
_ = lambda s: s
def main():
	print 'Boing'
	print _('Dieser Test ist ok')
	print _('Hier lieg auch %d Problem vor') % 0
	x = 'hier'
	print _('Aber %s knallts' % x)
	# _('Im Kommentar %s aber nicht' % x)
	print _('foo %s bar' % x)
	print _('foo %s \'bar' % x)
	print _("foo %s bar" % x)
	print _("foo %s \"bar" % x)
	print _('''foo %s bar''' % x)
	print _("""foo %s bar""" % x)
	print _('''foo %s \'''bar''' % x)
	print _("""foo %s \"""bar""" % x)

main()
