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
