"""The krot_index schema of a project's database: what each engine said and what was sent.

A port of an earlier PHP implementation's stores. The one departure is what a
failed write does: the earlier one swallowed only the night's summary, and so does this one —
a lost page row is raised, because that row is what holds the page out of
tomorrow's offer.
"""

import sys

# The version of schema.sql this program was written against. The role writes
# it; the program only reads it.
SCHEMA_VERSION = 1

# The schema the role makes, and its name before 7.0.0 — read until the role has
# renamed it in this database.
SCHEMA = "krot_index"
LEGACY_SCHEMA = "krot"

# How long an offer counts for: long enough that a page still in the engine's
# queue is not offered again, short enough that one it dropped comes round.
OFFER_HOLDS_DAYS = 14


def first_line(failure):
    """The first line of what went wrong, or its type where it said nothing.

    Inside an except that must not raise: an empty message would otherwise turn
    "say it and carry on" into an IndexError that ends the walk.
    """
    lines = str(failure).strip().splitlines()
    return lines[0] if lines else type(failure).__name__


class Missing(Exception):
    """The schema is absent or at another version — something only the role repairs."""


class PostgresStore:
    def __init__(self, database, connect=None):
        self.database = database
        if connect is None:
            # Imported here so the rest of the program, and its tests, need no driver.
            import psycopg2

            connect = psycopg2.connect
        # Peer over the local socket: no password exists to leak or rotate.
        self.connection = connect(dbname=database)
        # ⚠️ Every statement its own transaction. On Postgres a failed statement
        # aborts the transaction around it, and one refused write would take every
        # later query of the night down with it.
        self.connection.autocommit = True
        # ⚠️ Tables by search path, not by a schema written into each statement:
        # krot, the name before 7.0.0, is read while krot_index is not there yet. The
        # program's directory is one per machine and the rename one per database —
        # another project's database is renamed only by that project's own run, and
        # its timer runs this code in between. Postgres skips a schema of the path
        # that does not exist; pg_catalog is searched first regardless.
        self._run("SET search_path TO %s, %s" % (SCHEMA, LEGACY_SCHEMA))

    def _rows(self, sql, args=()):
        with self.connection.cursor() as cursor:
            cursor.execute(sql, args)
            return cursor.fetchall()

    def _run(self, sql, args=()):
        with self.connection.cursor() as cursor:
            cursor.execute(sql, args)
            return cursor.rowcount

    def check(self):
        """Raises Missing unless the schema is here and at this program's version."""
        try:
            rows = self._rows("SELECT version FROM schema_version")
        except Exception as failure:
            raise Missing("no krot_index schema in database %s (%s) — run the indexing role"
                          % (self.database, first_line(failure)))
        versions = [row[0] for row in rows]
        if versions != [SCHEMA_VERSION]:
            raise Missing("krot_index schema in database %s is at version %s, this program expects %d — run the indexing role"
                          % (self.database, versions or "none", SCHEMA_VERSION))

    def remember(self, site, engine, url, state):
        self._run(
            "INSERT INTO page_index (site, engine, url, state, asked_at) VALUES (%s, %s, %s, %s, now())"
            " ON CONFLICT (site, engine, url) DO UPDATE SET state = EXCLUDED.state, asked_at = now()",
            (site, engine, url, state))

    def offered(self, site, engine, url):
        # Inserts as well as updates: an engine that is never asked has no row
        # until this one, and an UPDATE alone would forget every page it sent.
        # An existing row keeps its state — that is what the engine SAID.
        self._run(
            "INSERT INTO page_index (site, engine, url, state, submitted_at) VALUES (%s, %s, %s, 'unknown', now())"
            " ON CONFLICT (site, engine, url) DO UPDATE SET submitted_at = now()",
            (site, engine, url))

    def offered_recently(self, site, engine):
        return [row[0] for row in self._rows(
            "SELECT url FROM page_index WHERE site = %s AND engine = %s"
            " AND submitted_at > now() - %s * interval '1 day'",
            (site, engine, OFFER_HOLDS_DAYS))]

    def asked(self, site, engine):
        """The site's pages this engine answered about, longest ago first."""
        return [row[0] for row in self._rows(
            "SELECT url FROM page_index WHERE site = %s AND engine = %s ORDER BY asked_at, url",
            (site, engine))]

    def ever_offered(self, site, engine):
        return self._rows(
            "SELECT count(*) FROM page_index WHERE site = %s AND engine = %s AND submitted_at IS NOT NULL",
            (site, engine))[0][0]

    def forget_gone(self, site, serving):
        """Drops rows of pages the site no longer serves — by site, for every engine at once."""
        if not serving:
            # Never on an empty list: the caller reads an unreadable site as None
            # and never gets here, so empty can only be a mistake — and deleting
            # on it would empty the site's history.
            return 0
        return self._run("DELETE FROM page_index WHERE site = %s AND NOT (url = ANY(%s))",
                         (site, list(serving)))

    def record(self, spending):
        """Writes the night down, or says it could not and carries on.

        The summary is the side errand; offering pages is the work. A refused
        write here costs one row, not a walk over every site.
        """
        try:
            self._run(
                "INSERT INTO index_run (site, engine, day, allowance, floor, attempted, accepted, held, waiting,"
                " refusal, ran_at) VALUES (%s, %s, current_date, %s, %s, %s, %s, %s, %s, %s, now())"
                " ON CONFLICT (site, engine, day) DO UPDATE SET allowance = EXCLUDED.allowance,"
                " floor = EXCLUDED.floor, attempted = EXCLUDED.attempted, accepted = EXCLUDED.accepted,"
                " held = EXCLUDED.held, waiting = EXCLUDED.waiting, refusal = EXCLUDED.refusal, ran_at = now()",
                (spending.site, spending.engine, spending.allowance, spending.floor, spending.attempted,
                 spending.accepted, spending.held, spending.waiting, spending.refusal))
        except Exception as failure:
            # Said once per site, to the journal: the earlier one said nothing, and a
            # summary missing for a month was then found only from the screen.
            print("warning: %s %s: the night was not recorded: %s"
                  % (spending.engine, spending.site, first_line(failure)), file=sys.stderr)
