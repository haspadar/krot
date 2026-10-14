import datetime

import pytest

from fakes.indexing import FakeBingSubmission
from krot_index import night
from krot_index.engines.bing import Bing

SITE = "abendseite.de"
URL = "https://" + SITE

# Bing's days, UTC midnight: 2026-10-02, -03, -04.
FIRST, SECOND, THIRD = ("/Date(%d)/" % ms for ms in (1790899200000, 1790985600000, 1791072000000))


@pytest.fixture
def api():
    served = FakeBingSubmission()
    yield served
    served.close()


def counts(api, domain=SITE):
    return Bing("bing-units-key", endpoint=api.endpoint).index_counts(domain)


def test_each_day_carries_the_figure_bing_named(api):
    api.crawl_stats[URL] = [(FIRST, 2), (SECOND, 3)]
    assert counts(api) == [(datetime.date(2026, 10, 2), 2, None), (datetime.date(2026, 10, 3), 3, None)]


def test_excluded_pages_are_unknown_because_bing_never_says(api):
    api.crawl_stats[URL] = [(FIRST, 2)]
    assert [row[2] for row in counts(api)] == [None]


def test_a_measured_zero_stays_zero(api):
    api.crawl_stats[URL] = [(FIRST, 0)]
    assert counts(api) == [(datetime.date(2026, 10, 2), 0, None)]


def test_days_come_oldest_first_whatever_the_order_bing_used(api):
    api.crawl_stats[URL] = [(THIRD, 5), (FIRST, 2)]
    assert [row[0] for row in counts(api)] == [datetime.date(2026, 10, 2), datetime.date(2026, 10, 4)]


def test_day_is_read_in_the_zone_bing_names(api):
    # 2026-10-02 00:00 UTC is still the 1st at five in the evening, Pacific.
    api.crawl_stats[URL] = [("/Date(1790899200000-0700)/", 2)]
    assert counts(api)[0][0] == datetime.date(2026, 10, 1)


def test_a_day_without_a_readable_date_is_dropped_not_dated_today(api):
    api.crawl_stats[URL] = [("2026-10-02", 2), ("/Date(-62135596800000)/", 4), (None, 6), (FIRST, 3)]
    assert counts(api) == [(datetime.date(2026, 10, 2), 3, None)]


@pytest.mark.parametrize("date", ["/Date(999999999999999999999)/", "/Date(1790899200000+9999)/",
                                  "/Date(253402300800000)/"])
def test_a_date_beyond_the_calendar_is_dropped_and_the_next_day_still_read(api, date):
    api.crawl_stats[URL] = [(date, 5), (FIRST, 2)]
    assert counts(api) == [(datetime.date(2026, 10, 2), 2, None)]


@pytest.mark.parametrize("held", [None, "many", -1, 2.5, True])
def test_a_day_without_a_readable_figure_is_dropped_not_zeroed(api, held):
    api.crawl_stats[URL] = [(FIRST, held)]
    assert counts(api) == []


def test_site_with_no_days_yet_is_an_empty_list_not_a_refusal(api):
    api.crawl_stats[URL] = []
    assert counts(api) == []


def test_site_the_key_does_not_hold_is_an_ownership_refusal(api):
    with pytest.raises(night.Refused) as refused:
        counts(api, "nordseite.be")
    assert refused.value.ownership


def test_answer_that_is_not_json_is_a_refusal(api):
    api.stats_answer = 503, "<html>Service Unavailable</html>", {"Content-Type": "text/html"}
    with pytest.raises(night.Refused):
        counts(api)


def test_the_key_is_not_in_what_a_refusal_says(api):
    api.stats_answer = 503, "<html>Service Unavailable</html>", {"Content-Type": "text/html"}
    with pytest.raises(night.Refused) as refused:
        counts(api)
    assert "bing-units-key" not in str(refused.value)


def test_counting_asks_for_no_page_and_no_allowance(api):
    api.crawl_stats[URL] = [(FIRST, 2)]
    counts(api)
    assert [request.path.rsplit("/", 1)[1] for request in api.server.requests] == ["GetCrawlStats"]
