import pytest

from fakes.indexing import FakeBingSubmission
from krot_index import night
from krot_index.engines.bing import QUOTA_WHEN_UNASKED, Bing

SITE = "abendseite.de"


@pytest.fixture
def api():
    served = FakeBingSubmission()
    yield served
    served.close()


def bing(api, key="bing-units-key"):
    return Bing(key, endpoint=api.endpoint)


def test_allowance_is_the_month_over_thirty_one_days(api):
    assert bing(api).daily_quota(SITE) == 22


def test_allowance_never_passes_the_daily_figure(api):
    api.quotas["https://" + SITE] = (15, 3100)
    assert bing(api).daily_quota(SITE) == 15


def test_allowance_is_asked_for_each_site(api):
    api.quotas["https://nordseite.be"] = (100, 217)
    engine = bing(api)
    assert (engine.daily_quota(SITE), engine.daily_quota("nordseite.be")) == (22, 7)


def test_unanswered_allowance_falls_to_the_floor(api):
    api.quota_down = True
    assert bing(api).daily_quota(SITE) == QUOTA_WHEN_UNASKED


def test_floor_is_said_to_be_a_floor(api):
    api.quota_down = True
    engine = bing(api)
    engine.daily_quota(SITE)
    assert not engine.quota_was_asked(SITE)


def test_dead_allowance_endpoint_is_given_up_after_three_tries(api):
    api.quota_down = True
    engine = bing(api)
    for domain in ("a.de", "b.de", "c.de", "d.de", "e.de"):
        engine.daily_quota(domain)
    assert len([request for request in api.server.requests if "Quota" in request.path]) == 3


def test_failing_site_counts_once_however_often_it_is_asked(api):
    api.quota_down = True
    engine = bing(api)
    for domain in ("a.de", "a.de", "a.de", "b.de"):
        engine.daily_quota(domain)
    assert len([request for request in api.server.requests if "Quota" in request.path]) == 2


def test_error_status_without_a_code_takes_nothing(api):
    api.submit_answer = 500, {"Message": "An error has occurred."}
    assert bing(api).submit_all(SITE, ["https://abendseite.de/"]) == {"https://abendseite.de/": False}


def test_code_written_as_text_is_still_a_refusal(api):
    api.submit_answer = 200, {"ErrorCode": "14", "Message": "ERROR!!! NotAuthorized"}
    with pytest.raises(night.Refused) as refused:
        bing(api).submit_all(SITE, ["https://abendseite.de/"])
    assert refused.value.ownership


def test_batch_goes_in_one_call(api):
    bing(api).submit_all(SITE, ["https://abendseite.de/", "https://abendseite.de/escort"])
    assert api.accepted == {"https://abendseite.de": ["https://abendseite.de/", "https://abendseite.de/escort"]}


def test_spent_day_is_green_refusal(api):
    api.error_code = 2
    with pytest.raises(night.Refused) as refused:
        bing(api).submit_all(SITE, ["https://abendseite.de/"])
    assert (refused.value.exhausted, refused.value.too_fast) == (True, False)


def test_throttle_is_a_pace_refusal(api):
    api.error_code = 5
    with pytest.raises(night.Refused) as refused:
        bing(api).submit_all(SITE, ["https://abendseite.de/"])
    assert refused.value.too_fast


def test_site_outside_the_account_is_an_ownership_refusal(api):
    api.error_code = 14
    with pytest.raises(night.Refused) as refused:
        bing(api).submit_all(SITE, ["https://abendseite.de/"])
    assert refused.value.ownership


def test_unreachable_bing_takes_nothing(api):
    engine = bing(api)
    api.close()
    assert engine.submit_all(SITE, ["https://abendseite.de/"]) == {"https://abendseite.de/": False}


def test_refusal_never_quotes_the_key(api):
    api.error_code = 3
    with pytest.raises(night.Refused) as refused:
        bing(api).submit_all(SITE, ["https://abendseite.de/"])
    assert "bing-units-key" not in str(refused.value)
