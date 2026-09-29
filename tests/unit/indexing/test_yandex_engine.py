import pytest

from fakes.indexing import FakeYandexRecrawl
from krot_index import night
from krot_index.engines.yandex import Yandex

SITE = "sezimder.kz"


@pytest.fixture
def api():
    served = FakeYandexRecrawl()
    served.held(SITE)
    yield served
    served.close()


def yandex(api, pauses=None):
    return Yandex("yandex-units-token", api=api.api, sleep=(pauses if pauses is not None else []).append)


def test_page_is_queued_for_a_walk(api):
    yandex(api).submit_all(SITE, ["https://sezimder.kz/"])
    assert api.queued == ["https://sezimder.kz/"]


def test_requests_are_a_second_apart_across_calls(api):
    pauses = []
    engine = yandex(api, pauses)
    engine.submit_all(SITE, ["https://sezimder.kz/"])
    engine.submit_all(SITE, ["https://sezimder.kz/almaty"])
    assert pauses == [1]


def test_site_the_account_does_not_hold_is_an_ownership_refusal(api):
    with pytest.raises(night.Refused) as refused:
        yandex(api).submit_all("sezimder.uz", ["https://sezimder.uz/"])
    assert refused.value.ownership


def test_spent_day_is_green_refusal(api):
    api.error = 429, {"error_code": "QUOTA_EXCEEDED", "error_message": "Quota exceeded"}
    with pytest.raises(night.Refused) as refused:
        yandex(api).submit_all(SITE, ["https://sezimder.kz/"])
    assert refused.value.exhausted


def test_unverified_host_is_an_ownership_refusal(api):
    api.error = 403, {"error_code": "HOST_NOT_VERIFIED", "error_message": "Host not verified"}
    with pytest.raises(night.Refused) as refused:
        yandex(api).submit_all(SITE, ["https://sezimder.kz/"])
    assert refused.value.ownership


def test_page_yandex_will_not_walk_is_only_that_page(api):
    api.error = 400, {"error_code": "URL_NOT_ALLOWED", "error_message": "Url does not belong to host"}
    assert yandex(api).submit_all(SITE, ["https://sezimder.kz/x"]) == {"https://sezimder.kz/x": False}


def test_pages_taken_before_a_refusal_travel_with_it(api):
    engine = yandex(api)
    engine.submit_all(SITE, ["https://sezimder.kz/"])
    api.error = 429, {"error_code": "QUOTA_EXCEEDED", "error_message": "Quota exceeded"}
    queued = []

    original = engine.offer

    def take_first_then_run_out(host, url, domain):
        if not queued:
            queued.append(url)
            return True
        return original(host, url, domain)

    engine.offer = take_first_then_run_out
    with pytest.raises(night.Refused) as refused:
        engine.submit_all(SITE, ["https://sezimder.kz/a", "https://sezimder.kz/b"])
    assert refused.value.accepted == ["https://sezimder.kz/a"]
