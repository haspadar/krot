import pytest

from fakes.indexing import FakeEngine, FakeStore
from krot_index.night import Refused
from krot_index.submission import Submission, what_to_ask_about

SITE = "rufnummer.de"


def page(path):
    return "https://rufnummer.de" + path


def listings(count):
    return {page("/vorwahl/%03d" % number): False for number in range(count)}


def cards(count):
    return {page("/nummer/%05d" % number): True for number in range(count)}


def test_page_the_engine_does_not_know_is_offered():
    engine = FakeEngine(quota=10)
    Submission(engine, FakeStore()).of(SITE, {page("/"): False})
    assert engine.submitted == [page("/")]


def test_page_the_engine_has_indexed_is_not_offered():
    engine = FakeEngine(quota=10)
    engine.knows[page("/")] = "indexed"
    Submission(engine, FakeStore()).of(SITE, {page("/"): False})
    assert engine.submitted == []


def test_asking_stops_at_half_again_the_share():
    engine = FakeEngine(quota=4)
    Submission(engine, FakeStore()).of(SITE, listings(20))
    assert len(engine.inspected) == 6


def test_share_divides_a_project_allowance_between_sites():
    engine = FakeEngine(quota=200)
    Submission(engine, FakeStore(), sharing=3).of(SITE, listings(100))
    assert len(engine.submitted) == 66


def test_cards_keep_a_quarter_of_the_window_among_many_listings():
    asked = what_to_ask_about([page("/l%d" % n) for n in range(40)], [page("/c%d" % n) for n in range(40)], [], 20)
    assert sum(1 for url in asked if "/c" in url) == 5


def test_listings_take_what_cards_leave_unused():
    asked = what_to_ask_about([page("/l%d" % n) for n in range(40)], [page("/c0")], [], 20)
    assert len(asked) == 20


def test_never_asked_pages_come_before_long_asked_ones():
    asked = what_to_ask_about([page("/alt"), page("/neu")], [], [page("/alt")], 1)
    assert asked == [page("/neu")]


def test_second_night_asks_about_pages_the_first_did_not_reach():
    engine = FakeEngine(quota=2)
    engine.knows.update({url: "indexed" for url in listings(6)})
    store = FakeStore()
    Submission(engine, store).of(SITE, listings(6))
    first = list(engine.inspected)
    store.tick(days=1)
    engine.inspected.clear()
    Submission(engine, store).of(SITE, listings(6))
    assert not set(first) & set(engine.inspected)


def test_page_offered_last_week_is_held():
    engine = FakeEngine(quota=10)
    store = FakeStore()
    Submission(engine, store).of(SITE, {page("/"): False})
    store.tick(days=7)
    engine.submitted.clear()
    Submission(engine, store).of(SITE, {page("/"): False})
    assert engine.submitted == []


def test_page_offered_a_fortnight_and_a_day_ago_is_offered_again():
    engine = FakeEngine(quota=10)
    store = FakeStore()
    Submission(engine, store).of(SITE, {page("/"): False})
    store.tick(days=15)
    engine.submitted.clear()
    Submission(engine, store).of(SITE, {page("/"): False})
    assert engine.submitted == [page("/")]


def test_silence_does_not_overwrite_yesterdays_answer():
    engine = FakeEngine(quota=10)
    engine.knows[page("/")] = "indexed"
    store = FakeStore()
    Submission(engine, store).of(SITE, {page("/"): False})
    engine.silent = True
    Submission(engine, store).of(SITE, {page("/"): False})
    assert store.state(SITE, "google", page("/")) == "indexed"


def test_unasked_engine_is_offered_listings_before_cards():
    engine = FakeEngine(slug="bing", quota=1, per_site=True, asking=False)
    Submission(engine, FakeStore()).of(SITE, {page("/nummer/1"): True, page("/vorwahl"): False})
    assert engine.submitted == [page("/vorwahl")]


def test_unasked_engine_is_never_questioned():
    engine = FakeEngine(slug="bing", quota=5, per_site=True, asking=False)
    Submission(engine, FakeStore()).of(SITE, listings(3))
    assert engine.inspected == []


def test_offer_to_an_unasked_engine_is_held_too():
    engine = FakeEngine(slug="indexnow", quota=10, per_site=True, asking=False)
    store = FakeStore()
    Submission(engine, store).of(SITE, {page("/"): False})
    store.tick(days=1)
    engine.submitted.clear()
    Submission(engine, store).of(SITE, {page("/"): False})
    assert engine.submitted == []


def test_offer_keeps_the_answer_google_gave():
    engine = FakeEngine(quota=10)
    engine.knows[page("/")] = "known"
    store = FakeStore()
    store.remember(SITE, "google", page("/"), "known")
    Submission(engine, store).of(SITE, {page("/"): False})
    assert store.state(SITE, "google", page("/")) == "known"


def test_site_serving_nothing_reports_no_states():
    offer = Submission(FakeEngine(slug="bing", per_site=True, asking=False), FakeStore()).of(SITE, {})
    assert offer.states == {}


def test_unreadable_site_leaves_its_rows_alone():
    store = FakeStore()
    store.remember(SITE, "google", page("/"), "indexed")
    Submission(FakeEngine(), store).of(SITE, None)
    assert store.state(SITE, "google", page("/")) == "indexed"


def test_page_the_site_dropped_is_forgotten_for_every_engine():
    store = FakeStore()
    store.remember(SITE, "google", page("/alt"), "indexed")
    store.offered(SITE, "bing", page("/alt"))
    Submission(FakeEngine(), store).of(SITE, {page("/"): False})
    assert [key for key in store.pages if key[2] == page("/alt")] == []


def test_unwritten_offer_stops_the_night():
    store = FakeStore()
    store.offer_fails = True
    with pytest.raises(RuntimeError):
        Submission(FakeEngine(quota=10), store).of(SITE, {page("/"): False})


def test_count_says_how_much_of_the_site_is_answered():
    offer = Submission(FakeEngine(quota=2), FakeStore()).of(SITE, listings(10))
    assert offer.covered() == (3, 10)


class RunsOutAfterOne(FakeEngine):
    """Takes the first page of a batch, then says the day is spent."""

    def submit_all(self, domain, urls):
        refusal = Refused("Quota exceeded", exhausted=True)
        refusal.accepted = urls[:1]
        raise refusal


def test_pages_taken_before_a_refusal_are_held():
    store = FakeStore()
    Submission(RunsOutAfterOne(quota=10), store).of(SITE, listings(2))
    assert store.offered_recently(SITE, "google") == [page("/vorwahl/000")]
