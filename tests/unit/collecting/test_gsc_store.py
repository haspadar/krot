"""Day replacement, snapshot export and additive upgrade against real PostgreSQL."""

import io
import json
import os
from datetime import date
from pathlib import Path

import pytest

from krot_collect.gsc_store import SearchStore

DSN = os.environ.get('KROT_TEST_POSTGRES')
pytestmark = pytest.mark.skipif(not DSN, reason='KROT_TEST_POSTGRES is not set')
SCHEMA = Path(__file__).resolve().parents[3] / 'roles/collecting/files/schema.sql'


@pytest.fixture
def db():
    import psycopg2
    connection = psycopg2.connect(DSN)
    connection.autocommit = True
    with connection.cursor() as cursor:
        cursor.execute('DROP SCHEMA IF EXISTS krot_collect CASCADE; CREATE SCHEMA krot_collect')
        cursor.execute(SCHEMA.read_text())
    yield connection
    connection.close()


@pytest.fixture
def store(db):
    import psycopg2
    result = SearchStore('unused', connect=lambda dbname: psycopg2.connect(DSN))
    yield result
    result.connection.close()


def rows(db, sql):
    with db.cursor() as cursor:
        cursor.execute(sql)
        return cursor.fetchall() if cursor.description else []


def replace(store, figures, dataset='page'):
    site, property, day = 'orchard.test', 'sc-domain:orchard.test', date(2026, 9, 10)
    attempt = store.start(site, property, day, dataset)
    store.replace(site, property, day, dataset, figures, attempt)


def page(url='/fruit', impressions=5):
    return dict(url=url, impressions=impressions, clicks=1, position=3.5)


def test_a_day_replacement_removes_rows_no_longer_reported(store, db):
    replace(store, [page('/pear'), page('/plum')])
    replace(store, [page('/pear', 9)])
    assert rows(db, 'SELECT url,impressions FROM krot_collect.search_page') == [('/pear', 9)]


def test_a_write_failure_restores_the_previous_day_and_marker(store, db):
    replace(store, [page()])
    with pytest.raises(Exception):
        replace(store, [page(impressions=-1)])
    assert rows(db, 'SELECT p.impressions,d.row_count FROM krot_collect.search_page p'
                ' JOIN krot_collect.search_day d USING(site,day,search_type)') == [(5, 1)]


def test_a_successful_empty_day_is_distinct_from_never_collected(store, db):
    replace(store, [])
    assert rows(db, 'SELECT row_count,finalized,pagination_complete,coverage_limited FROM krot_collect.search_day') == [
        (0, True, True, True)]


def test_long_unicode_keys_are_retained_without_index_failure(store, db):
    figures = dict(url='https://orchard.test/' + 'яблоко' * 700, query='осенний урожай' * 500,
                   impressions=12, clicks=2, position=4.0)
    replace(store, [figures], 'page_query')
    assert rows(db, 'SELECT url,query FROM krot_collect.search_page_query') == [(figures['url'], figures['query'])]


def test_duplicate_rows_do_not_inflate_marker_counts(store, db):
    replace(store, [page(), page(impressions=8)])
    assert rows(db, 'SELECT row_count FROM krot_collect.search_day') == [(1,)]


def test_attempt_success_is_committed_with_the_day(store, db):
    replace(store, [])
    assert rows(db, 'SELECT status,row_count FROM krot_collect.search_attempt') == [('success', 0)]


def test_two_collectors_cannot_replace_the_same_database_concurrently(store):
    import psycopg2
    second = SearchStore('unused', connect=lambda dbname: psycopg2.connect(DSN))
    try:
        with store.exclusive():
            with pytest.raises(RuntimeError):
                with second.exclusive():
                    pass
    finally:
        second.connection.close()


def test_the_export_contains_only_declared_sites(store, db):
    replace(store, [page()])
    rows(db, "INSERT INTO krot_collect.search_page(site,day,url,impressions,clicks,position)"
         " VALUES('other.test','2026-09-10','/private',1,0,2) RETURNING site")
    out = io.StringIO()
    store.export(['orchard.test'], date(2026, 9, 1), date(2026, 9, 20), out)
    records = [json.loads(line) for line in out.getvalue().splitlines()]
    assert (len(records), {record['row']['site'] for record in records}) == (3, {'orchard.test'})


def test_schema_reapply_preserves_crawler_history(db):
    rows(db, "INSERT INTO krot_collect.crawler_read(site,day) VALUES('birds.test','2026-09-01') RETURNING site")
    with db.cursor() as cursor:
        cursor.execute(SCHEMA.read_text())
    assert rows(db, 'SELECT site FROM krot_collect.crawler_read') == [('birds.test',)]


def test_gsc_refuses_an_unupgraded_projects_schema(store, db):
    from krot_collect.store import Missing
    rows(db, "UPDATE krot_collect.schema_version SET version=1 RETURNING version")
    with pytest.raises(Missing):
        store.check()


def test_version_one_upgrade_preserves_old_history_and_adds_search_tables(db):
    with db.cursor() as cursor:
        cursor.execute('DROP SCHEMA krot_collect CASCADE; CREATE SCHEMA krot_collect')
        cursor.execute("CREATE TABLE krot_collect.schema_version(version integer);"
                       " INSERT INTO krot_collect.schema_version VALUES(1);"
                       " CREATE TABLE krot_collect.crawler_read(site varchar(255) NOT NULL, day date NOT NULL,"
                       " collected_at timestamptz NOT NULL DEFAULT now(),PRIMARY KEY(site,day));"
                       " INSERT INTO krot_collect.crawler_read(site,day) VALUES('nest.test','2026-09-02')")
        cursor.execute(SCHEMA.read_text())
    assert rows(db, "SELECT site,version,to_regclass('krot_collect.search_page') IS NOT NULL"
                ' FROM krot_collect.crawler_read CROSS JOIN krot_collect.schema_version') == [('nest.test', 2, True)]


def test_attempts_keep_the_oldest_failed_day_in_the_repair_horizon(store):
    store.start('seed.test', 'sc-domain:seed.test', date(2026, 8, 1), 'query')
    assert store.horizon('seed.test', 'sc-domain:seed.test') == date(2026, 8, 1)


def test_imported_uncertified_rows_keep_the_old_history_horizon(store, db):
    rows(db, "INSERT INTO krot_collect.search_page_query(site,day,url,query,impressions,clicks,position)"
         " VALUES('grove.test','2026-01-01','/shade','tree',4,0,6) RETURNING site")
    assert store.horizon('grove.test', 'sc-domain:grove.test') == date(2026, 1, 1)


def test_export_does_not_require_writer_privileges(store, db):
    replace(store, [page('/harvest')])
    rows(db, "DO $$ BEGIN IF NOT EXISTS(SELECT FROM pg_roles WHERE rolname='gsc_export_reader')"
         " THEN CREATE ROLE gsc_export_reader; END IF; END $$")
    rows(db, 'GRANT USAGE ON SCHEMA krot_collect TO gsc_export_reader')
    rows(db, 'GRANT SELECT ON ALL TABLES IN SCHEMA krot_collect TO gsc_export_reader')
    store._run('SET ROLE gsc_export_reader')
    out = io.StringIO()
    store.export(['orchard.test'], date(2026, 9, 1), date(2026, 9, 30), out)
    assert len(out.getvalue().splitlines()) == 3
