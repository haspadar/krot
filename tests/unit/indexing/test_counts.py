import datetime
import io
import json

import pytest

from fakes.indexing import FakeStore
from krot_index import counts, night, store as stores

DAY = datetime.date(2026, 10, 2)
SITES = [{"domain": "abendseite.de", "sitemap_url": "https://abendseite.de/sitemap.xml"},
         {"domain": "nordseite.be", "sitemap_url": "https://nordseite.be/sitemap.xml"}]


class FakeCounting:
    """An engine that answers what it was told per domain: a list of days, or an exception."""

    def __init__(self, answers):
        self.answers = answers
        self.asked = []

    def index_counts(self, domain, today):
        self.asked.append((domain, today))
        answer = self.answers[domain]
        if isinstance(answer, Exception):
            raise answer
        return answer


class Checked(FakeStore):
    """Remembers what the program asked of the schema's version."""

    def __init__(self):
        super().__init__()
        self.oldest = None
        self.missing = None

    def check(self, oldest=1):
        self.oldest = oldest
        if self.missing:
            raise stores.Missing(self.missing)


@pytest.fixture
def config(tmp_path):
    def write(engines=("bing", "yandex"), sites=SITES):
        path = tmp_path / "first.json"
        path.write_text(json.dumps({"project": "first", "database": "first", "engines": list(engines),
                                    "sites": list(sites)}))
        return str(path)

    return write


@pytest.fixture
def keys(monkeypatch):
    monkeypatch.setenv("KROT_INDEX_BING_KEY", "bing-key")
    monkeypatch.setenv("KROT_INDEX_YANDEX_TOKEN", "yandex-token")


def run(config_path, store, engines):
    out, err = io.StringIO(), io.StringIO()
    code = counts.main(["--config", config_path], engines=lambda name, key: engines[name], out=out, err=err, store=store)
    return code, out.getvalue(), err.getvalue()


def test_each_day_the_engine_named_is_written_for_its_site(config, keys):
    store = Checked()
    bing = FakeCounting({"abendseite.de": [(DAY, 2, None)], "nordseite.be": [(DAY, 7, None)]})
    code, _, _ = run(config(["bing"]), store, {"bing": bing})
    assert (code, store.counts) == (0, {("abendseite.de", "bing", DAY): {"in_index": 2, "not_in_index": None},
                                        ("nordseite.be", "bing", DAY): {"in_index": 7, "not_in_index": None}})


def test_a_measured_zero_is_written_as_zero(config, keys):
    store = Checked()
    run(config(["bing"], SITES[:1]), store, {"bing": FakeCounting({"abendseite.de": [(DAY, 0, None)]})})
    assert store.counts[("abendseite.de", "bing", DAY)]["in_index"] == 0


def test_a_day_read_again_keeps_the_figure_the_engine_no_longer_gives(config, keys):
    store = Checked()
    store.count("abendseite.de", "yandex", DAY, 5, 9)
    run(config(["yandex"], SITES[:1]), store, {"yandex": FakeCounting({"abendseite.de": [(DAY, None, 11)]})})
    assert store.counts[("abendseite.de", "yandex", DAY)] == {"in_index": 5, "not_in_index": 11}


def test_a_day_read_again_replaces_the_figure_it_had(config, keys):
    store = Checked()
    store.count("abendseite.de", "bing", DAY, 5, None)
    run(config(["bing"], SITES[:1]), store, {"bing": FakeCounting({"abendseite.de": [(DAY, 6, None)]})})
    assert store.counts[("abendseite.de", "bing", DAY)]["in_index"] == 6


def test_only_the_engines_the_project_declares_are_read(config, keys):
    store = Checked()
    yandex = FakeCounting({"abendseite.de": [(DAY, 1, None)]})
    run(config(["google", "yandex"], SITES[:1]), store, {"yandex": yandex})
    assert {key[1] for key in store.counts} == {"yandex"}


def test_a_site_the_engine_has_not_walked_yet_is_green(config, keys):
    store = Checked()
    bing = FakeCounting({"abendseite.de": night.NoData("not yet"), "nordseite.be": [(DAY, 7, None)]})
    code, out, _ = run(config(["bing"]), store, {"bing": bing})
    assert (code, "nothing to write yet" in out, len(store.counts)) == (0, True, 1)


def test_a_site_with_no_days_yet_is_green_and_writes_nothing(config, keys):
    store = Checked()
    code, _, _ = run(config(["bing"], SITES[:1]), store, {"bing": FakeCounting({"abendseite.de": []})})
    assert (code, store.counts) == (0, {})


def test_a_refused_site_is_red_and_the_others_are_still_read(config, keys):
    store = Checked()
    bing = FakeCounting({"abendseite.de": night.Refused("not held", ownership=True, repair="add the site"),
                         "nordseite.be": [(DAY, 7, None)]})
    code, _, err = run(config(["bing"]), store, {"bing": bing})
    assert (code, "add the site" in err, len(store.counts)) == (1, True, 1)


def test_a_refused_write_is_red_and_the_other_sites_are_still_written(config, keys):
    class Odd(Checked):
        def count(self, site, engine, day, in_index, not_in_index):
            if site == "abendseite.de":
                raise RuntimeError("permission denied for table index_count")
            super().count(site, engine, day, in_index, not_in_index)

    store = Odd()
    bing = FakeCounting({"abendseite.de": [(DAY, 2, None)], "nordseite.be": [(DAY, 7, None)]})
    code, _, err = run(config(["bing"]), store, {"bing": bing})
    assert (code, "not recorded" in err, len(store.counts)) == (1, True, 1)


def test_one_engine_refusing_does_not_stop_the_other(config, keys):
    store = Checked()
    engines = {"bing": FakeCounting({"abendseite.de": night.Refused("down")}),
               "yandex": FakeCounting({"abendseite.de": [(DAY, 3, None)]})}
    code, _, _ = run(config(sites=SITES[:1]), store, engines)
    assert (code, list(store.counts)) == (1, [("abendseite.de", "yandex", DAY)])


def test_counting_needs_the_schema_that_has_the_table(config, keys):
    store = Checked()
    run(config(["bing"], SITES[:1]), store, {"bing": FakeCounting({"abendseite.de": []})})
    assert store.oldest == stores.SCHEMA_VERSION


def test_a_schema_that_is_too_old_is_red_and_asks_for_the_role(config, keys):
    store = Checked()
    store.missing = "krot_index schema is at version 1 — run the indexing role"
    code, _, err = run(config(["bing"], SITES[:1]), store, {"bing": FakeCounting({})})
    assert (code, "run the indexing role" in err) == (1, True)


def test_the_day_asked_for_is_the_machines(config, keys):
    store = Checked()
    bing = FakeCounting({"abendseite.de": []})
    run(config(["bing"], SITES[:1]), store, {"bing": bing})
    assert bing.asked == [("abendseite.de", store.today())]


def test_a_missing_key_is_red_and_the_engine_is_not_built(config, monkeypatch):
    monkeypatch.delenv("KROT_INDEX_BING_KEY", raising=False)
    store = Checked()
    code, _, err = run(config(["bing"], SITES[:1]), store, {})
    assert (code, "KROT_INDEX_BING_KEY is empty" in err) == (1, True)


def test_a_project_declaring_neither_counted_engine_is_refused(config, keys):
    code, _, err = run(config(["google", "indexnow"]), Checked(), {})
    assert (code, "declares neither" in err) == (1, True)
