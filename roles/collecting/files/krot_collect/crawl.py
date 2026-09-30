"""Walks a project's sites and collects what crawled each of them.

Sequential and local: the logs are files on this machine, with no API to be
polite to. What needs care is memory, hence lines read one at a time.
"""

from krot_collect import logline
from krot_collect.logfiles import Unreadable

# ⚠️ A file of at least this many lines of which NOT ONE parsed is a failure, not
# a quiet day: the log's format has drifted from the program's, and storing the
# day would write "nobody came" for every site on the machine. New in this
# program — the earlier one skipped such lines silently. Zero parsed rather than a
# share: a half-written vhost fills a live file with junk for a while, and a share
# would redden over that, while a live site in the right format never has twenty
# lines and none of them readable.
GARBAGE_LINES = 20


class Garbage(Unreadable):
    """A file that read whole and held no line in the declared format."""


class Collection:
    def __init__(self, files, tally, store, pattern, out, err):
        self.files = files
        self.tally = tally
        self.store = store
        self.pattern = pattern
        self.out = out
        self.err = err

    def collect(self, domains):
        """Collects every site and returns how many failed.

        A failure on one site does not stop the others: a log made unreadable by a
        permission change on one domain must not cost the night for the rest.
        """
        failed = 0
        for domain in domains:
            if not self.one(domain):
                failed += 1
        return failed

    def one(self, domain):
        paths = self.files.of(domain)
        if not paths:
            # A site declared without a log on disk: closed, or not yet serving.
            # Said, not failed — a log that exists and cannot be read is the red one.
            print("%s: no log on disk" % domain, file=self.out)
            return True

        walk = Walk(self.files, self.pattern, self.store.newest_day(domain))
        # ⚠️ What the walk read before a file refused is STILL stored. Files come
        # newest first, so a corrupt archive refuses after the recent days were
        # read to their end. Discarding them was the earlier implementation's own
        # defect: `rotate 14` keeps a bad archive a fortnight, and one truncated
        # file blinded its site for two weeks — the outage the collection exists
        # to notice, made invisible by the collection.
        reading = self.tally.of(walk.lines(paths)).without(walk.spoiled)
        if reading.days:
            self.store.store(domain, reading)

        requests = sum(figures[0] for figures in reading.crawlers.values())
        if walk.failure is not None:
            print("%s: %s" % (domain, walk.failure), file=self.err)
            if reading.days:
                print("%s: kept %d days read before it, %d crawler requests"
                      % (domain, len(reading.days), requests), file=self.out)
            return False
        print("%s: %d days, %d rows, %d crawler requests" % (domain, len(reading.days), len(reading.crawlers),
                                                             requests), file=self.out)
        return True


class Walk:
    """The lines worth reading for one site: everything since the newest day stored."""

    def __init__(self, files, pattern, newest):
        self.files = files
        self.pattern = pattern
        # ⚠️ Re-read, not skipped. The live file holds part of today, and on a
        # rotation morning part of yesterday sits in two files; re-reading is free
        # because a day is replaced whole, while skipping would leave whatever
        # arrived after the last run uncounted for good.
        self.newest = newest
        self.failure = None
        # The days of the file that refused: they arrived incomplete.
        self.spoiled = set()

    def lines(self, paths):
        for path in paths:
            reached_older = False
            from_this_file = set()
            count = 0
            parsed = 0
            try:
                for text in self.files.lines(path):
                    count += 1
                    one = logline.read(text, self.pattern)
                    if one is not None:
                        parsed += 1
                        if self.newest is not None and one.day < self.newest:
                            reached_older = True
                            continue
                        from_this_file.add(one.day)
                    yield text
                if count >= GARBAGE_LINES and parsed == 0:
                    raise Garbage("%s holds %d lines and none in the declared format — the log format has "
                                  "drifted from the program's" % (path, count))
            except Unreadable as refusal:
                # The walk ends here. This file's own days do not stand: a truncated
                # archive is found only at its end, after its lines were counted —
                # an undercount indistinguishable from a quiet day.
                self.failure = str(refusal)
                self.spoiled = from_this_file
                return
            # Per file rather than per line: nginx writes in completion order, so a
            # slow request started before midnight lands after one that finished
            # later. Reading a whole file removes the question.
            if reached_older:
                return
