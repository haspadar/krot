"""Sites in another Yandex Webmaster account are offered and read with that account's key.

The key belongs to the account: its allowance, its throttle and the cut-off after three sites it
cannot answer. Walked with the project's key, a site of another account is refused every night.
"""

import datetime
import io
import json

import pytest

from fakes.indexing import FakeStore
from krot_index import cli, counts, store as stores

DAY = datetime.date(2026, 11, 10)
OWN = {"domain": "own.test", "sitemap_url": "https://own.test/s.xml"}
KEPT = {"domain": "kept.test", "sitemap_url": "https://kept.test/s.xml", "yandex_account": "alternate"}
ALSO = {"domain": "also.test", "sitemap_url": "https://also.test/s.xml", "yandex_account": "alternate"}


class Answering:
    """A database with the schema at this program's version."""

    autocommit = False
    rowcount = -1

    def __call__(self, **kwargs):
        return self

    def cursor(self):
        return self

    def __enter__(self):
        return self

    def __exit__(self, *args):
        return False

    def execute(self, sql, args=()):
        self.rows = [(1,)]

    def fetchall(self):
        return self.rows


class Walked:
    """A walk that only remembers which engine it was given and which sites it was handed."""

    walks = []

    def __init__(self, engine, *args, **kwargs):
        self.engine = engine

    def over(self, sites):
        Walked.walks.append((self.engine, [site["domain"] for site in sites]))
        return 0


class Counting:
    def __init__(self, answers):
        self.answers = answers
        self.asked = []

    def index_counts(self, domain, today):
        self.asked.append(domain)
        return self.answers[domain]


class Checked(FakeStore):
    def check(self, oldest=1):
        return None


def write(tmp_path, sites, engines=("yandex",)):
    path = tmp_path / "first.json"
    path.write_text(json.dumps({"project": "first", "database": "first", "engines": list(engines),
                                "sites": sites}))
    return str(path)


def night(path, build):
    err = io.StringIO()
    code = cli.main(["--config", path, "--engine", "yandex"], connect=Answering(), engines=build,
                    out=io.StringIO(), err=err)
    return code, err.getvalue()


def reading(path, build):
    err = io.StringIO()
    code = counts.main(["--config", path], engines=build, store=Checked(), out=io.StringIO(), err=err)
    return code, err.getvalue()


@pytest.fixture(autouse=True)
def walked(monkeypatch):
    Walked.walks = []
    monkeypatch.setattr(cli, "Walk", Walked)


@pytest.fixture
def keys(monkeypatch):
    monkeypatch.setenv("KROT_INDEX_YANDEX_TOKEN", "own-key")
    monkeypatch.setenv("KROT_INDEX_YANDEX_TOKEN_ALTERNATE", "account-key")


def test_sites_are_grouped_by_the_account_they_name():
    assert [(account, [site["domain"] for site in group]) for account, group in cli.accounts("yandex", [OWN, KEPT, ALSO])] == [
        (None, ["own.test"]), ("alternate", ["kept.test", "also.test"])]


def test_google_does_not_have_accounts():
    assert [account for account, _ in cli.accounts("google", [OWN, KEPT])] == [None]


def test_an_account_has_its_own_key_variable():
    assert (cli.key_variable("yandex"), cli.key_variable("yandex", "alternate"), cli.key_variable("google", "alternate")) == (
        "KROT_INDEX_YANDEX_TOKEN", "KROT_INDEX_YANDEX_TOKEN_ALTERNATE", "KROT_INDEX_GOOGLE_KEY_FILE")


def test_each_account_is_walked_with_an_engine_built_from_its_own_key(tmp_path, keys):
    code, _ = night(write(tmp_path, [OWN, KEPT, ALSO]), lambda name, key: key)
    assert (code, Walked.walks) == (cli.OK, [("own-key", ["own.test"]), ("account-key", ["kept.test", "also.test"])])


def test_a_project_whose_sites_are_all_in_an_account_needs_no_key_of_its_own(tmp_path, monkeypatch):
    monkeypatch.delenv("KROT_INDEX_YANDEX_TOKEN", raising=False)
    monkeypatch.setenv("KROT_INDEX_YANDEX_TOKEN_ALTERNATE", "account-key")
    code, _ = night(write(tmp_path, [KEPT, ALSO]), lambda name, key: key)
    assert (code, Walked.walks) == (cli.OK, [("account-key", ["kept.test", "also.test"])])


def test_an_account_without_its_key_is_red_and_named_while_the_others_are_still_walked(tmp_path, monkeypatch):
    monkeypatch.setenv("KROT_INDEX_YANDEX_TOKEN", "own-key")
    monkeypatch.delenv("KROT_INDEX_YANDEX_TOKEN_ALTERNATE", raising=False)
    code, said = night(write(tmp_path, [OWN, KEPT]), lambda name, key: key)
    assert (code, "KROT_INDEX_YANDEX_TOKEN_ALTERNATE is empty" in said, "account alternate" in said, Walked.walks) == (
        cli.FAILED, True, True, [("own-key", ["own.test"])])


def test_an_account_whose_key_cannot_be_used_is_red_without_quoting_it(tmp_path, monkeypatch):
    monkeypatch.setenv("KROT_INDEX_YANDEX_TOKEN", "own-key")
    monkeypatch.setenv("KROT_INDEX_YANDEX_TOKEN_ALTERNATE", "account-secret")

    def build(name, key):
        if key == "account-secret":
            raise ValueError("not a key")
        return key

    code, said = night(write(tmp_path, [OWN, KEPT]), build)
    assert (code, "account-secret" in said, "of account alternate" in said, len(Walked.walks)) == (
        cli.FAILED, False, True, 1)


def test_a_row_that_cannot_be_written_stops_the_night_before_the_next_account(tmp_path, keys, monkeypatch):
    class Failing(Walked):
        def over(self, sites):
            Walked.walks.append((self.engine, [site["domain"] for site in sites]))
            raise RuntimeError("permission denied for table page_index")

    monkeypatch.setattr(cli, "Walk", Failing)
    code, said = night(write(tmp_path, [OWN, KEPT]), lambda name, key: key)
    assert (code, "stopped" in said, Walked.walks) == (cli.FAILED, True, [("own-key", ["own.test"])])


def test_a_key_that_cannot_be_used_is_red_for_the_counts_without_stopping_the_other_account(tmp_path, keys):
    own = Counting({"own.test": [(DAY, 3, None)]})

    def build(name, key):
        if key == "account-key":
            raise ValueError("not a key")
        return own

    code, said = reading(write(tmp_path, [OWN, KEPT]), build)
    assert (code, "account alternate" in said, own.asked) == (1, True, ["own.test"])


def test_the_counts_read_each_account_with_its_own_key_and_only_its_sites(tmp_path, keys):
    own = Counting({"own.test": [(DAY, 3, None)]})
    account = Counting({"kept.test": [(DAY, 9, None)]})
    code, _ = reading(write(tmp_path, [OWN, KEPT]), lambda name, key: {"own-key": own, "account-key": account}[key])
    assert (code, own.asked, account.asked) == (0, ["own.test"], ["kept.test"])


def test_the_counts_of_an_account_without_its_key_are_red_while_the_other_is_still_read(tmp_path, monkeypatch):
    monkeypatch.setenv("KROT_INDEX_YANDEX_TOKEN", "own-key")
    monkeypatch.delenv("KROT_INDEX_YANDEX_TOKEN_ALTERNATE", raising=False)
    own = Counting({"own.test": [(DAY, 3, None)]})
    code, said = reading(write(tmp_path, [OWN, KEPT]), lambda name, key: own)
    assert (code, "KROT_INDEX_YANDEX_TOKEN_ALTERNATE is empty" in said, own.asked) == (1, True, ["own.test"])


def test_real_yandex_engines_keep_user_and_host_caches_separate(tmp_path, keys):
    from krot_index.engines.yandex import Yandex

    def call(method, url, headers, **kwargs):
        own = headers["Authorization"] == "OAuth own-key"
        user, domain = ("owner", "own.test") if own else ("archivist", "kept.test")
        if url.endswith("/user"):
            return 200, json.dumps({"user_id": user})
        assert url.endswith("/user/" + user + "/hosts")
        return 200, json.dumps({"hosts": [{"host_id": user + "-host", "ascii_host_url": "https://" + domain}]})

    code, _ = night(write(tmp_path, [OWN, KEPT]), lambda name, key: Yandex(key, call=call))
    assert code == cli.OK and [(engine.host(domains[0]), engine.user) for engine, domains in Walked.walks] == [
        ("owner-host", "owner"), ("archivist-host", "archivist")]
