import gzip
import io
import os
from datetime import date

import pytest

from krot_collect import logline
from krot_collect.agents import Agents
from krot_collect.crawl import GARBAGE_LINES, Collection
from krot_collect.logfiles import LogFiles, Unreadable
from krot_collect.ranges import Ranges
from krot_collect.sections import Sections
from krot_collect.tally import Tally

SITE = "a.example"
PATTERN = logline.FORMATS["time_first"]


class FakeStore:
    """Remembers what was stored; says the newest day it was told."""

    def __init__(self, newest=None):
        self.newest = newest
        self.stored = {}

    def newest_day(self, site):
        return self.newest

    def store(self, site, reading):
        self.stored[site] = reading


def line(day, agent="Googlebot/2.1"):
    return '[%02d/Aug/2026:10:00:00 +0300] 66.249.66.1 - a "GET / HTTP/1.1" 200 1 "-" "%s" rt=0.1\n' % (day, agent)


def write(directory, name, days, compress=False):
    path = os.path.join(directory, name)
    body = "".join(line(day) for day in days).encode()
    if compress:
        with gzip.open(path, "wb") as sink:
            sink.write(body)
    else:
        with open(path, "wb") as sink:
            sink.write(body)
    return path


def collect(directory, store):
    tally = Tally(Agents(), Ranges({}), Sections(), PATTERN)
    out, err = io.StringIO(), io.StringIO()
    ok = Collection(LogFiles(directory), tally, store, PATTERN, out, err).one(SITE)
    return ok, out.getvalue(), err.getvalue()


def test_rotations_are_ordered_by_number_not_by_name(tmp_path):
    for name in ("a.example-access.log.10.gz", "a.example-access.log.2.gz", "a.example-access.log",
                 "a.example-access.log.1"):
        (tmp_path / name).write_bytes(b"")
    assert [os.path.basename(p) for p in LogFiles(str(tmp_path)).of(SITE)] == [
        "a.example-access.log", "a.example-access.log.1", "a.example-access.log.2.gz", "a.example-access.log.10.gz"]


def test_a_truncated_archive_is_unreadable(tmp_path):
    path = write(str(tmp_path), "a.example-access.log.2.gz", [18, 19], compress=True)
    with open(path, "r+b") as handle:
        handle.truncate(os.path.getsize(path) - 10)
    with pytest.raises(Unreadable):
        list(LogFiles(str(tmp_path)).lines(path))


def test_a_whole_archive_reads(tmp_path):
    path = write(str(tmp_path), "a.example-access.log.2.gz", [18, 19], compress=True)
    assert len(list(LogFiles(str(tmp_path)).lines(path))) == 2


def test_a_site_without_a_log_is_said_and_not_failed(tmp_path):
    ok, out, _ = collect(str(tmp_path), FakeStore())
    assert (ok, "no log on disk" in out) == (True, True)


def test_a_first_run_reads_every_file(tmp_path):
    write(str(tmp_path), "a.example-access.log", [22])
    write(str(tmp_path), "a.example-access.log.1", [21])
    write(str(tmp_path), "a.example-access.log.2.gz", [20], compress=True)
    store = FakeStore()
    collect(str(tmp_path), store)
    assert store.stored[SITE].days == {date(2026, 8, 20), date(2026, 8, 21), date(2026, 8, 22)}


def test_the_newest_stored_day_is_read_again_and_older_ones_are_not(tmp_path):
    write(str(tmp_path), "a.example-access.log", [22])
    write(str(tmp_path), "a.example-access.log.1", [20, 21])
    write(str(tmp_path), "a.example-access.log.2.gz", [19], compress=True)
    store = FakeStore(newest=date(2026, 8, 21))
    collect(str(tmp_path), store)
    assert store.stored[SITE].days == {date(2026, 8, 21), date(2026, 8, 22)}


def test_the_walk_stops_after_the_file_that_reached_older_days(tmp_path):
    write(str(tmp_path), "a.example-access.log", [22])
    write(str(tmp_path), "a.example-access.log.1", [20, 21])
    broken = write(str(tmp_path), "a.example-access.log.2.gz", [19], compress=True)
    with open(broken, "r+b") as handle:
        handle.truncate(5)
    ok, _, _ = collect(str(tmp_path), FakeStore(newest=date(2026, 8, 21)))
    assert ok


def test_days_read_before_a_broken_archive_are_kept(tmp_path):
    write(str(tmp_path), "a.example-access.log", [22])
    write(str(tmp_path), "a.example-access.log.1", [21])
    broken = write(str(tmp_path), "a.example-access.log.2.gz", [19, 20], compress=True)
    with open(broken, "r+b") as handle:
        handle.truncate(os.path.getsize(broken) - 10)
    store = FakeStore()
    ok, _, err = collect(str(tmp_path), store)
    assert (ok, store.stored[SITE].days, "truncated" in err or "whole" in err) \
        == (False, {date(2026, 8, 21), date(2026, 8, 22)}, True)


def test_the_days_of_a_broken_archive_are_not_marked_read(tmp_path):
    write(str(tmp_path), "a.example-access.log", [22])
    broken = write(str(tmp_path), "a.example-access.log.1.gz", [21, 22], compress=True)
    with open(broken, "r+b") as handle:
        handle.truncate(os.path.getsize(broken) - 4)
    store = FakeStore()
    collect(str(tmp_path), store)
    # Day 22 is in both files and the broken one spoke for it too: it goes unstored.
    assert SITE not in store.stored


def test_a_file_that_cannot_be_opened_fails_the_site(tmp_path):
    path = write(str(tmp_path), "a.example-access.log", [22])
    os.chmod(path, 0)
    try:
        if os.access(path, os.R_OK):
            pytest.skip("running as a user that reads anything")
        ok, _, err = collect(str(tmp_path), FakeStore())
        assert (ok, "log group" in err) == (False, True)
    finally:
        os.chmod(path, 0o644)


def test_a_file_of_nothing_but_junk_fails_the_site(tmp_path):
    (tmp_path / "a.example-access.log").write_text("junk line\n" * GARBAGE_LINES)
    store = FakeStore()
    ok, _, err = collect(str(tmp_path), store)
    assert (ok, SITE in store.stored, "declared format" in err) == (False, False, True)


def test_a_few_junk_lines_are_a_quiet_day(tmp_path):
    (tmp_path / "a.example-access.log").write_text("junk line\n" * (GARBAGE_LINES - 1))
    ok, _, _ = collect(str(tmp_path), FakeStore())
    assert ok


def test_an_empty_readable_log_is_green(tmp_path):
    (tmp_path / "a.example-access.log").write_text("")
    ok, _, _ = collect(str(tmp_path), FakeStore())
    assert ok
