# Loosely inspired by
# https://github.com/stripe/datadog-checks/blob/master/checks.d/oom.py but with
# journald instead of kern.log, and as a count rather than a system check (so we
# can investigate distribution of OOMs over time rather than just declare the
# machine broken).

import re
import json

from utils.subprocess_output import get_subprocess_output
from checks import AgentCheck

# Note that this does *not* include processes being killed for outgrowing a
# memory control group, which is a slightly different error message.
oomRE = re.compile(
    r'^Out of memory: Kill process (?P<pid>\d+) \((?P<pname>.*?)\) ' +
    r'score (?P<score>.*?) or sacrifice child')


class OOM(AgentCheck):

    def __init__(self, name, init_config, agentConfig):
        AgentCheck.__init__(self, name, init_config, agentConfig)
        self.cursor = self.cursor_for_end_of_journal()

    def cursor_for_end_of_journal(self):
        # Note that for some reason it's important that this cursor be specific
        # to the filters we're using: if we get a cursor without the
        # _TRANSPORT=kernel PRIORITY=3 it somehow seems to sometimes skip the
        # next line when you pass it to --after-cursor.
        entries = self.journalctl_entries(['-n', '1'])
        if len(entries) == 0:
            # The kernel hasn't had any errors yet. That's fine, we'll start at
            # the beginning next time.
            return None
        if len(entries) > 1:
            self.log.error(
                'Too many results ({0}) for cursor_for_end_of_journal',
                len(entries))
            self.increment('oom.errors.cfeoj.empty')
            return None
        entry = entries[0]
        if '__CURSOR' not in entry:
            self.log.error('Missing __CURSOR for cursor_for_end_of_journal')
            self.increment('oom.errors.cfeoj.nocursor')
            return None
        return entry['__CURSOR']

    def journalctl_entries(self, args):
        out, err, exitCode = get_subprocess_output(
            ['journalctl',
             # One JSON object per line per entry.
             '-o', 'json',
             # No reason to look at non-system logs.
             '--system',
             # Kernel logs.
             '_TRANSPORT=kernel',
             # A the "error" level.
             'PRIORITY=3'] + args, self.log)
        if exitCode != 0:
            self.log.error('journalctl failed, code {0}: {1}'.format(
                exitCode, err))
            self.increment('oom.errors.je.failure')
            return []
        try:
            return [json.loads(line) for line in out.splitlines()]
        except:
            self.log.exception('json parsing failed')
            self.increment('oom.errors.je.jsonfail')
            return []

    def check(self, instance):
        args = []
        if self.cursor is not None:
            args = ['--after-cursor', self.cursor]
        entries = self.journalctl_entries(args)

        # Nothing at all happened? Great.
        if not entries:
            self.log.debug('Got nothing!')
            return

        self.log.debug('Got entries: %s' % entries)
        for entry in entries:
            # Start after this next time (whether or not it's an OOM).
            self.cursor = entry['__CURSOR']

            match = oomRE.match(entry['MESSAGE'])
            if not match:
                continue
            groups = match.groupdict()
            self.log.info('Detected OOM! {0}'.format(groups))
            self.increment('oom.killed',
                           tags=['pname:{0}'.format(groups['pname'])])
