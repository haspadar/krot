import io
import json

from krot_collect import cli


def config(tmp_path, **extra):
    path = tmp_path / "project.json"
    path.write_text(json.dumps(dict({"project": "p", "database": "p", "sites": [{"domain": "a.example"}]}, **extra)))
    return str(path)


def run(argv, connect):
    out, err = io.StringIO(), io.StringIO()
    code = cli.main(argv, connect=connect, out=out, err=err)
    return code, err.getvalue()


def unreachable(dbname):
    raise OSError("no socket")


def test_a_project_without_sites_fails(tmp_path):
    code, err = run(["--config", config(tmp_path, sites=[]), "crawl"], unreachable)
    assert (code, "declares no sites" in err) == (1, True)


def test_an_unreachable_database_fails_and_says_which(tmp_path):
    code, err = run(["--config", config(tmp_path), "crawl"], unreachable)
    assert (code, "database p cannot be reached" in err) == (1, True)


class NoSchema:
    autocommit = False

    def cursor(self):
        raise RuntimeError('relation "krot_collect.schema_version" does not exist')


def test_a_missing_schema_sends_the_reader_to_the_role(tmp_path):
    code, err = run(["--config", config(tmp_path), "crawl"], lambda dbname: NoSchema())
    assert (code, "run the collecting role" in err) == (1, True)


def test_crawl_passes_configured_path_families_to_the_existing_tally(tmp_path):
    from datetime import date

    class MemoryStore:
        def __init__(self):
            self.readings = {}

        def range_rows(self):
            return []

        def newest_day(self, domain):
            return None

        def store(self, domain, reading):
            self.readings[domain] = reading

        def forget_older_than(self):
            return 0

    (tmp_path / 'pages.test-access.log').write_text(
        '[13/Oct/2026:12:00:00 +0300] 66.249.66.1 - pages.test "GET /berlin HTTP/1.1" '
        '200 32 "-" "Googlebot/2.1" cf=DE rt=0.1\n')
    memory = MemoryStore()
    cli.run_crawl({'database': 'unused', 'sites': [{'domain': 'pages.test'}],
                   'logs': {'directory': str(tmp_path)}, 'crawl': {'path_families': ['googlebot']}},
                  memory, io.StringIO(), io.StringIO())
    assert memory.readings['pages.test'].paths == {(date(2026, 10, 13), 'googlebot', '/berlin'): 1}
