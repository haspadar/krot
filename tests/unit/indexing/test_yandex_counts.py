import datetime

import pytest

from fakes.indexing import FakeYandexRecrawl
from krot_index import night
from krot_index.engines.yandex import Yandex

SITE = "steppenseite.kz"
HOST = "https:steppenseite.kz:443"
TODAY = datetime.date(2026, 10, 14)


@pytest.fixture
def api():
    served = FakeYandexRecrawl()
    served.held(SITE)
    yield served
    served.close()


def counts(api, domain=SITE):
    return Yandex("yandex-units-token", api=api.api, sleep=lambda seconds: None).index_counts(domain, TODAY)


def test_points_are_dated_as_yandex_dated_them(api):
    api.in_search[HOST] = [("2026-09-19T10:00:11.592+03:00", 0), ("2026-09-23T10:00:05.948+03:00", 4005)]
    assert counts(api)[:2] == [(datetime.date(2026, 9, 19), 0, None), (datetime.date(2026, 9, 23), 4005, None)]


def test_a_measured_zero_stays_zero(api):
    api.in_search[HOST] = [("2026-09-19T10:00:11.592+03:00", 0)]
    assert counts(api)[0][1] == 0


def test_no_day_is_invented_between_points(api):
    api.in_search[HOST] = [("2026-09-19T10:00:00.000+03:00", 1), ("2026-09-23T10:00:00.000+03:00", 5)]
    assert [row[0] for row in counts(api) if row[1] is not None] == [datetime.date(2026, 9, 19),
                                                                    datetime.date(2026, 9, 23)]


def test_last_point_of_a_day_wins(api):
    api.in_search[HOST] = [("2026-09-19T14:00:00.000+03:00", 9), ("2026-09-19T10:00:00.000+03:00", 7)]
    assert counts(api)[0][1] == 9


def test_excluded_pages_are_todays_figure_and_no_earlier_days(api):
    api.in_search[HOST] = [("2026-09-19T10:00:00.000+03:00", 3)]
    api.excluded[HOST] = 41
    assert counts(api) == [(datetime.date(2026, 9, 19), 3, None), (TODAY, None, 41)]


def test_excluded_pages_share_the_row_of_a_point_dated_today(api):
    api.in_search[HOST] = [("2026-10-14T10:00:00.000+03:00", 3)]
    api.excluded[HOST] = 41
    assert counts(api) == [(TODAY, 3, 41)]


def test_zero_excluded_pages_is_a_figure(api):
    api.excluded[HOST] = 0
    assert counts(api) == [(TODAY, None, 0)]


@pytest.mark.parametrize("value", [None, "7", -1, True, 1.5])
def test_a_point_without_a_whole_figure_is_dropped(api, value):
    api.in_search[HOST] = [("2026-09-19T10:00:00.000+03:00", value), ("2026-09-20T10:00:00.000+03:00", 8)]
    assert [row[:2] for row in counts(api) if row[1] is not None] == [(datetime.date(2026, 9, 20), 8)]


def test_a_point_without_a_date_is_dropped(api):
    api.in_search[HOST] = [("not a date", 3), (None, 4), ("2026-09-20T10:00:00.000+03:00", 8)]
    assert [row[:2] for row in counts(api) if row[1] is not None] == [(datetime.date(2026, 9, 20), 8)]


def test_points_none_of_which_can_be_read_are_a_refusal_not_an_empty_site(api):
    api.in_search[HOST] = [("not a date", 3), ("2026-09-19T10:00:00.000+03:00", "many")]
    with pytest.raises(night.Refused):
        counts(api)


def test_a_young_site_with_an_empty_list_of_points_has_no_days(api):
    api.in_search[HOST] = []
    api.excluded[HOST] = 0
    assert [row[1] for row in counts(api)] == [None]


@pytest.mark.parametrize("body", [{}, {"history": None}, {"history": "none"}, {"points": []}])
def test_a_history_without_its_list_is_a_refusal_not_no_data(api, body):
    api.stats_body["history"] = body
    with pytest.raises(night.Refused):
        counts(api)


@pytest.mark.parametrize("body", [{}, {"excluded_pages_count": None}, {"excluded_pages_count": "41"},
                                  {"excluded_pages_count": -1}, {"excluded_pages_count": True}])
def test_a_summary_without_its_figure_is_a_refusal(api, body):
    api.stats_body["summary"] = body
    with pytest.raises(night.Refused):
        counts(api)


@pytest.mark.parametrize("code", ["HOST_NOT_LOADED", "HOST_NOT_INDEXED"])
def test_a_site_yandex_has_not_walked_yet_is_no_data_not_a_refusal(api, code):
    api.stats_error = 404, {"error_code": code, "error_message": "not yet"}
    with pytest.raises(night.NoData):
        counts(api)


def test_unverified_host_is_an_ownership_refusal(api):
    api.stats_error = 404, {"error_code": "HOST_NOT_VERIFIED", "error_message": "no"}
    with pytest.raises(night.Refused) as refused:
        counts(api)
    assert refused.value.ownership


def test_rejected_token_names_what_to_repair(api):
    api.stats_error = 401, {"error_code": "INVALID_OAUTH_TOKEN", "error_message": "no"}
    with pytest.raises(night.Refused) as refused:
        counts(api)
    assert "OAuth" in refused.value.repair


def test_site_the_account_does_not_hold_is_an_ownership_refusal(api):
    with pytest.raises(night.Refused) as refused:
        counts(api, "steppenseite.uz")
    assert refused.value.ownership


def test_counting_never_touches_the_recrawl_queue(api):
    api.in_search[HOST] = [("2026-09-19T10:00:00.000+03:00", 3)]
    counts(api)
    assert (api.queued, {request.method for request in api.server.requests}) == ([], {"GET"})
