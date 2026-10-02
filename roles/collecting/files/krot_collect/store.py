"""The krot_collect schema of a project's database."""

from datetime import datetime, timezone

# The version of schema.sql this program was written against. The role writes it;
# the program only reads it.
SCHEMA_VERSION = 2

# How long crawler figures are kept. Nothing here is personal — a crawler is a
# machine — so the limit is only what a screen can compare: a year answers "is
# this normal for August", two months more give the comparison a margin. nginx
# keeps a fortnight; everything past that exists only here.
KEEP_MONTHS = 14

# Swept together, with one window: a marker outliving its figures would claim the
# day was read and held nothing, and a table outliving another leaves a day whose
# halves disagree.
CRAWLER_TABLES = ("crawler_day", "crawler_read", "crawler_section", "request_day", "crawler_path")


def first_line(failure):
    lines = str(failure).strip().splitlines()
    return lines[0] if lines else type(failure).__name__


class Missing(Exception):
    """The schema is absent or at another version — something only the role repairs."""


def months_before(day, months):
    """The same day `months` earlier, clamped to the month's end as PHP's modify() is not.

    PHP rolls 31 March minus one month over to 3 March; a clamp cuts one or two days
    later at a month's end, which a fourteen-month window does not feel.
    """
    total = day.year * 12 + day.month - 1 - months
    year, month = divmod(total, 12)
    month += 1
    for last in (31, 30, 29, 28):
        try:
            return day.replace(year=year, month=month, day=min(day.day, last))
        except ValueError:
            continue
    raise ValueError(day)


class PostgresStore:
    def __init__(self, database, connect=None):
        self.database = database
        if connect is None:
            # Imported here, so the rest of the program and its tests need no driver.
            import psycopg2

            connect = psycopg2.connect
        # Peer over the local socket: no password exists to leak or rotate.
        self.connection = connect(dbname=database)
        # ⚠️ Every statement its own transaction, except where one is opened on
        # purpose: on Postgres a failed statement aborts the transaction around it.
        self.connection.autocommit = True

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
            rows = self._rows("SELECT version FROM krot_collect.schema_version")
        except Exception as failure:
            raise Missing("no krot_collect schema in database %s (%s) — run the collecting role"
                          % (self.database, first_line(failure)))
        versions = [row[0] for row in rows]
        if versions not in ([1], [SCHEMA_VERSION]):
            raise Missing("krot_collect schema in database %s is at version %s, this program expects %d — run the "
                          "collecting role" % (self.database, versions or "none", SCHEMA_VERSION))

    def transaction(self, statements):
        """Runs (sql, args) pairs in one transaction, all or nothing."""
        with self.connection.cursor() as cursor:
            cursor.execute("BEGIN")
            try:
                for sql, args in statements:
                    cursor.execute(sql, args)
            except BaseException:
                cursor.execute("ROLLBACK")
                raise
            cursor.execute("COMMIT")

    def newest_day(self, site):
        """The newest day read, from the markers — not the start of an unbroken run.

        From the markers: a day of people alone has one and no figures, and measured
        on the figures it would be re-read every night forever. The plain newest:
        a rotated log is gone, and a hole in the middle cannot be filled.
        """
        return self._rows("SELECT max(day) FROM krot_collect.crawler_read WHERE site = %s", (site,))[0][0]

    def store(self, site, reading):
        """Replaces each read day whole, figures and marker, in one transaction.

        Whole rather than added to: rotation puts one day in two files, and a store
        that added would inflate every figure it re-read, in the direction that
        looks like growth.
        """
        statements = []
        for day in sorted(reading.days):
            for table in ("crawler_day", "crawler_section", "request_day", "crawler_path"):
                statements.append(("DELETE FROM krot_collect.%s WHERE site = %%s AND day = %%s" % table, (site, day)))
            statements.append((
                "INSERT INTO krot_collect.crawler_read (site, day, collected_at) VALUES (%s, %s, now())"
                " ON CONFLICT (site, day) DO UPDATE SET collected_at = now()", (site, day)))
        for (day, family), (requests, size, errors) in sorted(reading.crawlers.items()):
            statements.append((
                "INSERT INTO krot_collect.crawler_day (site, family, day, requests, bytes, errors)"
                " VALUES (%s, %s, %s, %s, %s, %s)", (site, family, day, requests, size, errors)))
        for (day, family, section, status_class), requests in sorted(reading.sections.items()):
            statements.append((
                "INSERT INTO krot_collect.crawler_section (site, family, day, section, status_class, requests)"
                " VALUES (%s, %s, %s, %s, %s, %s)", (site, family, day, section, status_class, requests)))
        for day, served in sorted(reading.requests.items()):
            statements.append((
                "INSERT INTO krot_collect.request_day (site, day, requests, human, errors_5xx, rt_sum, rt_count,"
                " slow, robots_5xx, sitemap_5xx, home_5xx) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)",
                (site, day, served["requests"], served["human"], served["errors_5xx"],
                 # Spelled out with its decimals: the column is numeric(12,3).
                 "%.3f" % served["rt_sum"], served["rt_count"], served["slow"],
                 served["robots_5xx"], served["sitemap_5xx"], served["home_5xx"])))
        for (day, family, path), requests in sorted(reading.paths.items()):
            statements.append((
                "INSERT INTO krot_collect.crawler_path (site, family, day, path, requests)"
                " VALUES (%s, %s, %s, %s, %s)", (site, family, day, path, requests)))
        self.transaction(statements)

    def forget_older_than(self, today=None):
        """Drops days past the window from every crawler table; the rows gone, summed.

        ⚠️ Every table's count added up, not the first one's: an understated figure
        printed as "forgot N rows" would go on looking plausible from the one table
        still swept.
        """
        cutoff = months_before(today or datetime.now(timezone.utc).date(), KEEP_MONTHS)
        return sum(self._run("DELETE FROM krot_collect.%s WHERE day < %%s" % table, (cutoff,))
                   for table in CRAWLER_TABLES)

    def range_rows(self):
        """Every stored (family, prefix).

        ⚠️ Nothing, rather than an exception, where they cannot be read: the
        crawl then leaves every family unconfirmed, exactly as before ranges
        existed, instead of losing the night's figures over a table that only
        refines them.
        """
        try:
            return self._rows("SELECT family, prefix FROM krot_collect.bot_range")
        except Exception:
            return []

    def store_ranges(self, source, families, ranges, published):
        """Replaces one source's rows whole: a withdrawn range has to disappear."""
        statements = [("DELETE FROM krot_collect.bot_range WHERE source = %s", (source,))]
        written = set()
        for family in families:
            for one in ranges:
                # Deduplicated here too: a source naming one family twice would
                # repeat every row and fail the whole transaction.
                if (family, one.text) in written:
                    continue
                written.add((family, one.text))
                statements.append((
                    "INSERT INTO krot_collect.bot_range (source, family, prefix, published_at, collected_at)"
                    " VALUES (%s, %s, %s, %s, now())", (source, family, one.text, published)))
        self.transaction(statements)

    def forget_sources_other_than(self, names):
        # Never on an empty list: wiping the table would unverify every family at once.
        if not names:
            return 0
        return self._run("DELETE FROM krot_collect.bot_range WHERE NOT (source = ANY(%s))", (list(names),))
