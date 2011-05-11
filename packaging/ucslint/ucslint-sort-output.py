#!/usr/bin/python
#
import sys, os, re

if len(sys.argv) < 2:
	print 'ucslint-sort-output.py <filename>'
	sys.exit(1)

reID = re.compile('^[UWEIS]:\d\d\d\d-\d+: ')

content = open( sys.argv[1], 'r' ).read()

tmplines = []
eventlist = []

for line in content.splitlines():
	if reID.match(line):
		if tmplines:
			eventlist.append( '\n'.join(tmplines) )
		tmplines = []
	tmplines.append(line)
if tmplines:
	eventlist.append( '\n'.join(tmplines) )

eventlist.sort()

for event in eventlist:
	print event
