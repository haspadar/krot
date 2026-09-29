import io
import json

import pytest

from krot_index import cli


class Unreachable:
    """A database that is not there: every connection refused."""

    def __call__(self, **kwargs):
        raise OSError("could not connect to server: No such file or directory")


class Schemaless:
    """A database that answers, without the krot schema in it."""

    autocommit = False

    def __call__(self, **kwargs):
        return self

    def cursor(self):
        return self

    def __enter__(self):
        return self

    def __exit__(self, *args):
        return False

    def execute(self, sql, args=()):
        raise RuntimeError('relation "krot.schema_version" does not exist')


@pytest.fixture
def config(tmp_path):
    path = tmp_path / "gudok.json"
    path.write_text(json.dumps({"project": "gudok", "database": "gudok", "engines": ["google"],
                                "sites": [{"domain": "rufnummer.de",
                                           "sitemap_url": "https://rufnummer.de/sitemap.xml"}]}))
    return str(path)


@pytest.fixture
def key(tmp_path, monkeypatch):
    path = tmp_path / "google.json"
    path.write_text("{}")
    monkeypatch.setenv("KROT_INDEX_GOOGLE_KEY_FILE", str(path))
    return str(path)


def run(argv, **kwargs):
    err = io.StringIO()
    code = cli.main(argv, err=err, out=io.StringIO(), **kwargs)
    return code, err.getvalue()


def test_misspelt_engine_is_named_as_misspelt(config):
    assert "no engine named 'gogle'" in run(["--config", config, "--engine", "gogle"])[1]


def test_engine_the_project_did_not_declare_is_red(config, tmp_path):
    path = tmp_path / "other.json"
    path.write_text(json.dumps({"project": "busel", "database": "stats", "engines": [], "sites": []}))
    assert run(["--config", str(path), "--engine", "google"])[0] == cli.FAILED


def test_empty_key_is_red(config, monkeypatch):
    monkeypatch.setenv("KROT_INDEX_GOOGLE_KEY_FILE", "")
    assert run(["--config", config, "--engine", "google"])[0] == cli.FAILED


def test_malformed_key_is_red_without_quoting_it(config, key):
    code, said = run(["--config", config, "--engine", "google"])
    assert (code, "{}" in said) == (cli.FAILED, False)


def test_missing_schema_names_the_role(config, key):
    code, said = run(["--config", config, "--engine", "google"], connect=Schemaless(),
                     engines=lambda name, key: object())
    assert (code, "run the indexing role" in said) == (cli.FAILED, True)


def test_unreachable_database_is_red(config, key):
    code, said = run(["--config", config, "--engine", "google"], connect=Unreachable(),
                     engines=lambda name, key: object())
    assert (code, "cannot be reached" in said) == (cli.FAILED, True)
