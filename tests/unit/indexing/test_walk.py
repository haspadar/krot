import io

from fakes.indexing import FakeEngine, FakeStore
from krot_index.night import Refused
from krot_index.walk import Walk


class Sitemaps:
    """What each site serves, by its sitemap address; None where it cannot be read."""

    def __init__(self, served):
        self.served = served
        self.read = []

    def pages(self, url, cards_path=None, cards_sitemap=None):
        self.read.append(url)
        return self.served.get(url)


SITES = [
    {"domain": "rufnummer.de", "sitemap_url": "https://rufnummer.de/sitemap.xml"},
    {"domain": "vorwahl.at", "sitemap_url": "https://vorwahl.at/sitemap.xml"},
]
SERVED = {
    "https://rufnummer.de/sitemap.xml": {"https://rufnummer.de/": False},
    "https://vorwahl.at/sitemap.xml": {"https://vorwahl.at/": False},
}


def walk(engine, store=None, served=None):
    sitemaps = Sitemaps(dict(SERVED, **(served or {})))
    out, err = io.StringIO(), io.StringIO()
    runner = Walk(engine, store or FakeStore(), sitemaps, out=out, err=err)
    return runner, sitemaps, out, err


def test_healthy_night_needs_nobody():
    runner, _, _, _ = walk(FakeEngine())
    assert runner.over(SITES) == 0


def test_spent_project_day_stops_the_walk():
    engine = FakeEngine()
    engine.refuse_with = Refused("Quota exceeded", exhausted=True)
    runner, sitemaps, _, _ = walk(engine)
    runner.over(SITES)
    assert sitemaps.read == ["https://rufnummer.de/sitemap.xml"]


def test_spent_site_day_walks_on():
    engine = FakeEngine(slug="bing", per_site=True, asking=False)
    engine.refuse_with = Refused("quota", exhausted=True)
    runner, sitemaps, _, _ = walk(engine)
    runner.over(SITES)
    assert len(sitemaps.read) == 2


def test_spent_day_needs_nobody():
    engine = FakeEngine()
    engine.refuse_with = Refused("Quota exceeded", exhausted=True)
    runner, _, _, _ = walk(engine)
    assert runner.over(SITES) == 0


def test_unreadable_site_needs_somebody():
    runner, _, _, _ = walk(FakeEngine(), served={"https://vorwahl.at/sitemap.xml": None})
    assert runner.over(SITES) == 1


def test_every_site_leaves_a_night_row():
    store = FakeStore()
    runner, _, _, _ = walk(FakeEngine(), store)
    runner.over(SITES)
    assert [row.site for row in store.runs] == ["rufnummer.de", "vorwahl.at"]


def test_night_row_holds_the_sites_share():
    store = FakeStore()
    runner, _, _, _ = walk(FakeEngine(quota=200), store)
    runner.over(SITES)
    assert store.runs[0].allowance == 100


def test_unwritten_night_row_does_not_stop_the_walk():
    store = FakeStore()
    store.record_fails = True
    runner, sitemaps, _, _ = walk(FakeEngine(), store)
    runner.over(SITES)
    assert len(sitemaps.read) == 2


def test_every_line_names_the_engine():
    runner, _, out, err = walk(FakeEngine(slug="google"))
    runner.over(SITES)
    lines = (out.getvalue() + err.getvalue()).splitlines()
    assert lines and all(line.startswith("google ") for line in lines)


def test_guessed_allowance_is_said_out_loud():
    engine = FakeEngine(slug="bing", per_site=True, asking=False)
    engine.quota_named = False
    runner, _, _, err = walk(engine)
    runner.over(SITES)
    assert "could not ask" in err.getvalue()
