"""The store against a real Postgres: the questions here are about the database itself.

Runs where KROT_TEST_POSTGRES holds a libpq connection string — CI sets it and
starts the server. Skipped otherwise, which is why CI must set it.
"""

import os
from datetime import date

import pytest

from krot_collect import logline
from krot_collect.agents import Agents
from krot_collect.prefix import read
from krot_collect.ranges import Ranges
from krot_collect.sections import Sections
from krot_collect.store import Missing, PostgresStore, months_before
from krot_collect.tally import Tally

DSN = os.environ.get("KROT_TEST_POSTGRES")
SCHEMA = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "..", "..", "roles", "collecting", "files",
                      "schema.sql")

pytestmark = pytest.mark.skipif(not DSN, reason="KROT_TEST_POSTGRES is not set")

SITE = "a.example"
DAY = date(2026, 8, 22)


@pytest.fixture
def psycopg2():
    return pytest.importorskip("psycopg2")


@pytest.fixture
def admin(psycopg2):
    connection = psycopg2.connect(DSN)
    connection.autocommit = True
    with connection.cursor() as cursor:
        cursor.execute("DROP SCHEMA IF EXISTS krot_collect CASCADE")
        cursor.execute("CREATE SCHEMA krot_collect")
        with open(SCHEMA) as source:
            cursor.execute(source.read())
    yield connection
    connection.close()


@pytest.fixture
def store(admin, psycopg2):
    return PostgresStore("ignored", connect=lambda dbname: psycopg2.connect(DSN))


def rows(admin, sql):
    with admin.cursor() as cursor:
        cursor.execute(sql)
        return cursor.fetchall()


def reading(lines):
    return Tally(Agents(), Ranges({}), Sections(), logline.FORMATS["time_first"], ai_paths=True).of(lines)


def line(day=22, agent="Googlebot/2.1", tail=" rt=0.100"):
    return '[%02d/Aug/2026:10:00:00 +0300] 66.249.66.1 - a "GET /x HTTP/1.1" 200 7 "-" "%s"%s' % (day, agent, tail)


def test_the_schema_at_this_version_passes(store):
    store.check()


def test_a_second_version_row_is_refused(store, admin):
    rows(admin, "INSERT INTO krot_collect.schema_version VALUES (2) RETURNING version")
    with pytest.raises(Missing):
        store.check()


def test_a_day_is_replaced_whole_not_added_to(store, admin):
    store.store(SITE, reading([line(), line()]))
    store.store(SITE, reading([line()]))
    assert rows(admin, "SELECT requests FROM krot_collect.crawler_day") == [(1,)]


def test_a_day_of_people_alone_has_a_marker_and_no_figures(store, admin):
    store.store(SITE, reading([line(agent="Mozilla/5.0 Chrome/120")]))
    assert (rows(admin, "SELECT count(*) FROM krot_collect.crawler_read")[0][0],
            rows(admin, "SELECT count(*) FROM krot_collect.crawler_day")[0][0]) == (1, 0)


def test_the_newest_day_comes_from_the_markers(store):
    store.store(SITE, reading([line(day=21), line(day=22, agent="Mozilla/5.0 Chrome/120")]))
    assert store.newest_day(SITE) == DAY


def test_the_response_time_keeps_its_decimals(store, admin):
    store.store(SITE, reading([line(tail=" rt=0.001")]))
    assert str(rows(admin, "SELECT rt_sum FROM krot_collect.request_day")[0][0]) == "0.001"


def test_a_readers_path_is_stored(store, admin):
    store.store(SITE, reading([line(agent="ChatGPT-User/1.0")]))
    assert rows(admin, "SELECT family, path FROM krot_collect.crawler_path") == [("chatgpt-user", "/x")]


def test_forgetting_sweeps_every_table_and_counts_them_all(store, admin):
    store.store(SITE, reading([line(day=1, agent="ChatGPT-User/1.0")]))
    assert store.forget_older_than(date(2027, 11, 1)) == 5


def test_a_sources_ranges_are_replaced_whole(store, admin):
    store.store_ranges("s", ["googlebot"], [read("10.0.0.0/24"), read("10.0.1.0/24")], None)
    store.store_ranges("s", ["googlebot"], [read("10.0.2.0/24")], None)
    assert rows(admin, "SELECT prefix FROM krot_collect.bot_range") == [("10.0.2.0/24",)]


def test_a_family_named_twice_does_not_break_the_source(store, admin):
    store.store_ranges("s", ["googlebot", "googlebot"], [read("10.0.0.0/24")], None)
    assert rows(admin, "SELECT count(*) FROM krot_collect.bot_range") == [(1,)]


def test_sources_no_longer_listed_are_dropped(store, admin):
    store.store_ranges("old", ["googlebot"], [read("10.0.0.0/24")], None)
    store.store_ranges("s", ["googlebot"], [read("10.0.1.0/24")], None)
    store.forget_sources_other_than(["s"])
    assert rows(admin, "SELECT source FROM krot_collect.bot_range") == [("s",)]


def test_an_empty_list_forgets_nothing(store, admin):
    store.store_ranges("s", ["googlebot"], [read("10.0.0.0/24")], None)
    assert store.forget_sources_other_than([]) == 0


def test_stored_ranges_are_read_back(store):
    store.store_ranges("s", ["googlebot"], [read("10.0.0.0/24")], None)
    assert store.range_rows() == [("googlebot", "10.0.0.0/24")]


def test_months_before_clamps_to_the_months_end():
    assert months_before(date(2027, 4, 30), 14) == date(2026, 2, 28)
