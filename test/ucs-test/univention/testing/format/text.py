# vim: set fileencoding=utf-8 ft=python sw=4 ts=4 et :
"""Format UCS Test results as simple text report."""
import sys
from univention.testing.data import TestFormatInterface, TestCodes
import curses
import time
from weakref import WeakValueDictionary
import re

__all__ = ['Text']


class _Term(object):  # pylint: disable-msg=R0903
    """Handle terminal formatting."""
    __ANSICOLORS = "BLACK RED GREEN YELLOW BLUE MAGENTA CYAN WHITE".split()
    # vt100.sgr0 contains a delay in the form of '$<2>'
    __RE_DELAY = re.compile(r'\$<\d+>[/*]?')

    def __init__(self, term_stream=sys.stdout):
        self.COLS = 80  # pylint: disable-msg=C0103
        self.LINES = 25  # pylint: disable-msg=C0103
        self.NORMAL = ''  # pylint: disable-msg=C0103
        for color in self.__ANSICOLORS:
            setattr(self, color, '')
        if not term_stream.isatty():
            return
        try:
            curses.setupterm()
        except TypeError:
            return
        self.COLS = curses.tigetnum('cols') or 80
        self.LINES = curses.tigetnum('lines') or 25
        self.NORMAL = _Term.__RE_DELAY.sub('', curses.tigetstr('sgr0') or '')
        set_fg_ansi = curses.tigetstr('setaf')
        for color in self.__ANSICOLORS:
            i = getattr(curses, 'COLOR_%s' % color)
            val = set_fg_ansi and curses.tparm(set_fg_ansi, i) or ''
            setattr(self, color, val)


class Text(TestFormatInterface):
    """
    Create simple text report.
    """
    __term = WeakValueDictionary()

    def __init__(self, stream=sys.stdout):
        super(Text, self).__init__(stream)
        try:
            self.term = Text.__term[self.stream]
        except KeyError:
            self.term = Text.__term[self.stream] = _Term(self.stream)

    def begin_run(self, environment, count=1):
        """Called before first test."""
        super(Text, self).begin_run(environment, count)
        now = time.strftime('%Y-%m-%d %H:%M:%S', time.localtime())
        print >> self.stream, "Starting %s ucs-test at %s to %s" % \
                (count, now, environment.log.name)

    def begin_section(self, section):
        """Called before each secion."""
        super(Text, self).begin_section(section)
        if section:
            header = " Section '%s' " % (section,)
            line = header.center(self.term.COLS, '=')
            print >> self.stream, line

    def begin_test(self, case, prefix=''):
        """Called before each test."""
        super(Text, self).begin_test(case, prefix)
        title = case.description or case.uid
        title = prefix + title.splitlines()[0]

        cols = self.term.COLS - TestCodes.MAX_MESSAGE_LEN - 1
        if cols < 1:
            cols = self.term.COLS
        while len(title) > cols:
            print >> self.stream, title[:cols]
            title = title[cols:]
        ruler = '.' * (cols - len(title))
        print >> self.stream, '%s%s' % (title, ruler),
        self.stream.flush()

    def end_test(self, result):
        """Called after each test."""
        reason = result.reason
        msg = TestCodes.MESSAGE.get(reason, reason)

        colorname = TestCodes.COLOR.get(result.reason, 'BLACK')
        color = getattr(self.term, colorname.upper(), '')

        print >> self.stream, '%s%s%s' % (color, msg, self.term.NORMAL)
        super(Text, self).end_test(result)

    def end_section(self):
        """Called after each secion."""
        if self.section:
            print >> self.stream
        super(Text, self).end_section()

    def format(self, result):
        """
        >>> from univention.testing.data import TestCase, TestEnvironment, \
                TestResult
        >>> te = TestEnvironment()
        >>> tc = TestCase()
        >>> tc.uid = 'python/data.py'
        >>> tr = TestResult(tc, te)
        >>> tr.success()
        >>> Text().format(tr)
        """
        self.begin_run(result.environment)
        self.begin_section('')
        self.begin_test(result.case)
        self.end_test(result)
        self.end_section()
        self.end_run()

if __name__ == '__main__':
    import doctest
    doctest.testmod()
