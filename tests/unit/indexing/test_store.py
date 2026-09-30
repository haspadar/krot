"""The store against a real Postgres: the questions here are about the database itself.

Runs where KROT_TEST_POSTGRES holds a libpq connection string — CI sets it and
starts the server. Without it the module is skipped, which is why CI must set it:
skipped, these would pass by never running.
"""

import os

import pytest

from krot_index import night
from krot_index.store import SCHEMA_VERSION, Missing, PostgresStore

DSN = os.environ.get("KROT_TEST_POSTGRES")
SCHEMA = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "..", "..", "roles", "indexing", "files",
                      "schema.sql")

pytestmark = pytest.mark.skipif(not DSN, reason="KROT_TEST_POSTGRES is not set")

SITE = "rufnummer.de"
HOME = "https://rufnummer.de/"


@pytest.fixture
def psycopg2():
    return pytest.importorskip("psycopg2")


@pytest.fixture
def admin(psycopg2):
    connection = psycopg2.connect(DSN)
    connection.autocommit = True
    with connection.cursor() as cursor:
        cursor.execute("DROP SCHEMA IF EXISTS krot_index CASCADE")
        cursor.execute("DROP SCHEMA IF EXISTS krot CASCADE")
        cursor.execute("CREATE SCHEMA krot_index")
        with open(SCHEMA) as source:
            cursor.execute(source.read())
    yield connection
    connection.close()


@pytest.fixture
def store(admin, psycopg2):
    opened = PostgresStore("krot_units", connect=lambda **kwargs: psycopg2.connect(DSN))
    yield opened
    opened.connection.close()


def sql(admin, statement, args=()):
    with admin.cursor() as cursor:
        cursor.execute(statement, args)
        return cursor.fetchall() if cursor.description else None


def test_fresh_schema_passes_the_check(store):
    store.check()


def test_schema_of_another_version_is_refused(store, admin):
    sql(admin, "UPDATE krot_index.schema_version SET version = %s", (SCHEMA_VERSION + 1,))
    with pytest.raises(Missing):
        store.check()


def test_absent_schema_is_refused(store, admin):
    sql(admin, "DROP SCHEMA krot_index CASCADE")
    with pytest.raises(Missing):
        store.check()


def test_the_schema_under_its_name_before_7_is_read_until_renamed(store, admin):
    sql(admin, "ALTER SCHEMA krot_index RENAME TO krot")
    store.remember(SITE, "google", HOME, night.KNOWN)
    assert sql(admin, "SELECT url FROM krot.page_index") == [(HOME,)]


def test_the_renamed_schema_is_read_over_the_old_name(store, admin):
    sql(admin, "CREATE SCHEMA krot")
    sql(admin, "CREATE TABLE krot.page_index (LIKE krot_index.page_index)")
    store.remember(SITE, "google", HOME, night.KNOWN)
    assert sql(admin, "SELECT count(*) FROM krot_index.page_index") == [(1,)]


def test_schema_applied_twice_holds_one_version(admin):
    with open(SCHEMA) as source:
        sql(admin, source.read())
    assert sql(admin, "SELECT version FROM krot_index.schema_version") == [(SCHEMA_VERSION,)]


def test_offer_keeps_what_the_engine_said(store):
    store.remember(SITE, "google", HOME, night.KNOWN)
    store.offered(SITE, "google", HOME)
    assert store._rows("SELECT state FROM krot_index.page_index") == [("known",)]


def test_offer_to_an_unasked_engine_creates_its_row(store):
    store.offered(SITE, "bing", HOME)
    assert store.ever_offered(SITE, "bing") == 1


def test_offer_of_last_week_is_still_held(store, admin):
    store.offered(SITE, "bing", HOME)
    sql(admin, "UPDATE krot_index.page_index SET submitted_at = now() - interval '13 days'")
    assert store.offered_recently(SITE, "bing") == [HOME]


def test_offer_of_fifteen_days_ago_is_no_longer_held(store, admin):
    store.offered(SITE, "bing", HOME)
    sql(admin, "UPDATE krot_index.page_index SET submitted_at = now() - interval '15 days'")
    assert store.offered_recently(SITE, "bing") == []


def test_longest_ago_asked_comes_first(store, admin):
    store.remember(SITE, "google", HOME, night.INDEXED)
    store.remember(SITE, "google", HOME + "vorwahl", night.INDEXED)
    sql(admin, "UPDATE krot_index.page_index SET asked_at = now() - interval '3 days' WHERE url = %s", (HOME + "vorwahl",))
    assert store.asked(SITE, "google") == [HOME + "vorwahl", HOME]


def test_dropped_page_is_forgotten_for_every_engine(store):
    store.remember(SITE, "google", HOME + "alt", night.INDEXED)
    store.offered(SITE, "bing", HOME + "alt")
    store.forget_gone(SITE, [HOME])
    assert store._rows("SELECT count(*) FROM krot_index.page_index") == [(0,)]


def test_forgetting_leaves_other_sites_alone(store):
    store.remember("vorwahl.at", "google", "https://vorwahl.at/", night.INDEXED)
    store.forget_gone(SITE, [HOME])
    assert store._rows("SELECT site FROM krot_index.page_index") == [("vorwahl.at",)]


def test_empty_list_forgets_nothing(store):
    store.remember(SITE, "google", HOME, night.INDEXED)
    store.forget_gone(SITE, [])
    assert store._rows("SELECT count(*) FROM krot_index.page_index") == [(1,)]


def test_second_night_row_of_a_day_replaces_the_first(store):
    store.record(night.Spending(SITE, "google", night.Offer({"unknown": 4}, submitted=[HOME], attempted=1), 66, True))
    store.record(night.Spending(SITE, "google", night.Offer({"unknown": 4}, submitted=[], attempted=2), 66, True))
    assert store._rows("SELECT attempted FROM krot_index.index_run") == [(2,)]


def test_unreadable_night_is_stored_with_no_queue(store):
    store.record(night.Spending(SITE, "google", night.Offer.unreadable(), 66, True))
    assert store._rows("SELECT held, waiting, refusal FROM krot_index.index_run") == [(None, None, "unreadable")]


def test_refused_night_row_is_said_not_raised(store, admin, capsys):
    sql(admin, "DROP TABLE krot_index.index_run")
    store.record(night.Spending(SITE, "google", night.Offer({"unknown": 1}), 66, True))
    assert "not recorded" in capsys.readouterr().err
