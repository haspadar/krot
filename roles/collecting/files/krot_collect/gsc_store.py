"""Durable independent GSC reports, successful days and failed attempts."""

import json
from contextlib import contextmanager
from datetime import date

from krot_collect.store import Missing, PostgresStore, SCHEMA_VERSION

DATASETS = {
    "query": ("query", "country", "device"),
    "page": ("url",),
    "page_query": ("url", "query"),
}
METRICS = ("impressions", "clicks", "position")


class SearchStore(PostgresStore):
    def check(self):
        super().check()
        if self._rows("SELECT version FROM krot_collect.schema_version") != [(SCHEMA_VERSION,)]:
            raise Missing("GSC needs schema version %d — run the collecting role for this project" % SCHEMA_VERSION)

    @contextmanager
    def exclusive(self):
        locked = self._rows("SELECT pg_try_advisory_lock(hashtext('krot_collect.gsc'), hashtext(current_database()))")[0][0]
        if not locked:
            raise RuntimeError("another GSC collection is running in this database")
        try:
            yield
        finally:
            self._rows("SELECT pg_advisory_unlock(hashtext('krot_collect.gsc'), hashtext(current_database()))")

    def markers(self, site, property):
        return {(day, dataset) for day, dataset in self._rows(
            "SELECT day, dataset FROM krot_collect.search_day WHERE site = %s AND property = %s"
            " AND search_type = 'web' AND finalized AND pagination_complete IS TRUE", (site, property))}

    def start(self, site, property, day, dataset):
        if dataset not in DATASETS:
            raise ValueError("unknown GSC dataset")
        return self._rows(
            "INSERT INTO krot_collect.search_attempt (site, property, day, dataset) VALUES (%s,%s,%s,%s)"
            " RETURNING attempt_id", (site, property, day, dataset))[0][0]

    def finish(self, attempt, status, error=""):
        if status not in ("failed", "unavailable"):
            raise ValueError("unsuccessful attempt needs a failure status")
        self._run("UPDATE krot_collect.search_attempt SET status=%s, error=%s, finished_at=now()"
                  " WHERE attempt_id=%s AND status='running'", (status, error, attempt))

    def replace(self, site, property, day, dataset, figures, attempt):
        fields = DATASETS[dataset] + METRICS
        table = "krot_collect.search_" + dataset
        statements = [("DELETE FROM %s WHERE site=%%s AND day=%%s AND search_type='web'" % table, (site, day))]
        columns = ",".join(("site", "day") + fields)
        slots = ",".join(["%s"] * (2 + len(fields)))
        # Duplicated source keys replace rather than inflate or abort a whole day.
        keys = {"query": "query_hash,country,device", "page": "url_hash", "page_query": "url_hash,query_hash"}[dataset]
        update = ",".join("%s=EXCLUDED.%s" % (name, name) for name in METRICS)
        sql = "INSERT INTO %s (%s) VALUES (%s) ON CONFLICT (site,day,search_type,%s) DO UPDATE SET %s" % (
            table, columns, slots, keys, update)
        for row in figures:
            statements.append((sql, (site, day) + tuple(row[name] for name in fields)))
        statements.append((
            "INSERT INTO krot_collect.search_day (site,property,day,dataset,row_count,pagination_complete)"
            " SELECT %s,%s,%s,%s,count(*),true FROM " + table + " WHERE site=%s AND day=%s AND search_type='web'"
            " ON CONFLICT (site,day,search_type,dataset) DO UPDATE SET property=EXCLUDED.property,"
            " row_count=EXCLUDED.row_count,collected_at=now(),pagination_complete=true,coverage_limited=true,"
            " finalized=true,provenance='api'", (site, property, day, dataset, site, day)))
        statements.append((
            "UPDATE krot_collect.search_attempt SET status='success',finished_at=now(),"
            " row_count=(SELECT row_count FROM krot_collect.search_day"
            " WHERE site=%s AND day=%s AND search_type='web' AND dataset=%s) WHERE attempt_id=%s AND status='running'",
            (site, day, dataset, attempt)))
        self.transaction(statements)

    def latest(self, site, property, dataset):
        return self._rows("SELECT max(day) FROM krot_collect.search_day WHERE site=%s AND property=%s"
                          " AND dataset=%s AND search_type='web' AND finalized AND pagination_complete IS TRUE",
                          (site, property, dataset))[0][0]

    def forget(self, sites, cutoff):
        statements = []
        # Only sites this inventory owns; another project on the database is left alone.
        for dataset in (*DATASETS, "day", "attempt"):
            statements.append(("DELETE FROM krot_collect.search_%s WHERE site=ANY(%%s) AND day < %%s" % dataset,
                               (list(sites), cutoff)))
        self.transaction(statements)

    def export(self, sites, start, end, out):
        # A coherent snapshot, allowed to read but never to modify a table.
        self._run("BEGIN TRANSACTION ISOLATION LEVEL REPEATABLE READ READ ONLY")
        try:
            with self.connection.cursor() as cursor:
                for dataset in (*DATASETS, "day", "attempt"):
                    table = "krot_collect.search_" + dataset
                    cursor.execute("SELECT * FROM %s WHERE site=ANY(%%s) AND day BETWEEN %%s AND %%s ORDER BY site,day" % table,
                                   (list(sites), start, end))
                    columns = [one[0] for one in cursor.description]
                    while True:
                        rows = cursor.fetchmany(1000)
                        if not rows:
                            break
                        for values in rows:
                            record = {"contract_version": 1, "dataset": dataset, "row": dict(zip(columns, values))}
                            print(json.dumps(record, default=lambda value: value.isoformat()
                                             if isinstance(value, date) else str(value)), file=out)
            self._run("COMMIT")
        except BaseException:
            self._run("ROLLBACK")
            raise
