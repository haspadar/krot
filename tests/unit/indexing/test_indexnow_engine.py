import pytest

from fakes.indexing import FakeIndexNowEndpoint, FakeSite, FakeStore
from krot_index import night
from krot_index.engines.indexnow import IndexNow, site_key
from krot_index.submission import Submission

SITE = "stadtdame.de"
SECRET = "network-secret"  # secret-lint: allow — a made-up value the tests share


@pytest.fixture
def endpoint():
    served = FakeIndexNowEndpoint()
    yield served
    served.close()


@pytest.fixture
def site():
    served = FakeSite()
    served.files["/" + site_key(SECRET, SITE) + ".txt"] = (200, site_key(SECRET, SITE))
    yield served
    served.close()


def indexnow(endpoint, site):
    return IndexNow(SECRET, endpoint=endpoint.endpoint, origin=lambda domain: site.url(""))


def test_key_holds_the_formula_busel_published():
    # ⚠️ A value, not a property: every other test passes under any formula.
    # Failing here means every published key file must be reissued, not that
    # this number needs updating. Checked against PHP's
    # substr(hash('sha256', 'network-secret:stadtdame.de'), 0, 32).  secret-lint: allow — the made-up value above
    assert site_key(SECRET, " Stadtdame.de ") == "007dbf4b4337deb97863e2368646c699"


def test_every_address_goes_in_one_post(endpoint, site):
    indexnow(endpoint, site).submit_all(SITE, ["https://stadtdame.de/", "https://stadtdame.de/escort"])
    assert [post["urlList"] for post in endpoint.posts] == [["https://stadtdame.de/", "https://stadtdame.de/escort"]]


def test_post_names_where_the_key_lives(endpoint, site):
    indexnow(endpoint, site).submit_all(SITE, ["https://stadtdame.de/"])
    assert endpoint.posts[0]["keyLocation"] == site.url("/007dbf4b4337deb97863e2368646c699.txt")


def test_site_not_serving_its_key_is_refused_before_posting(endpoint, site):
    site.files.clear()
    with pytest.raises(night.Refused):
        indexnow(endpoint, site).submit_all(SITE, ["https://stadtdame.de/"])
    assert endpoint.posts == []


def test_site_serving_another_key_is_an_ownership_refusal(endpoint, site):
    site.files["/" + site_key(SECRET, SITE) + ".txt"] = (200, "0" * 32)
    with pytest.raises(night.Refused) as refused:
        indexnow(endpoint, site).submit_all(SITE, ["https://stadtdame.de/"])
    assert refused.value.ownership


def test_key_file_down_takes_nothing_without_blaming_the_key(endpoint, site):
    site.files["/" + site_key(SECRET, SITE) + ".txt"] = (503, "Service Unavailable")
    assert indexnow(endpoint, site).submit_all(SITE, ["https://stadtdame.de/"]) == {"https://stadtdame.de/": False}


def test_key_file_down_posts_nothing(endpoint, site):
    site.files["/" + site_key(SECRET, SITE) + ".txt"] = (503, "Service Unavailable")
    indexnow(endpoint, site).submit_all(SITE, ["https://stadtdame.de/"])
    assert endpoint.posts == []


def test_site_unreachable_takes_nothing(endpoint, site):
    engine = indexnow(endpoint, site)
    site.close()
    assert engine.submit_all(SITE, ["https://stadtdame.de/"]) == {"https://stadtdame.de/": False}


def test_night_is_one_post_a_site(endpoint, site):
    # ⚠️ Deliberate, as in busel: the rest waits for the next night. See AT_ONCE.
    pages = {"https://stadtdame.de/%d" % number: False for number in range(10001)}
    Submission(indexnow(endpoint, site), FakeStore()).of(SITE, pages)
    assert [len(post["urlList"]) for post in endpoint.posts] == [10000]


def test_202_is_accepted(endpoint, site):
    endpoint.status = 202
    assert indexnow(endpoint, site).submit_all(SITE, ["https://stadtdame.de/"]) == {"https://stadtdame.de/": True}


def test_outage_takes_nothing_and_refuses_nothing(endpoint, site):
    endpoint.status = 503
    assert indexnow(endpoint, site).submit_all(SITE, ["https://stadtdame.de/"]) == {"https://stadtdame.de/": False}


def test_too_often_is_a_pace_refusal(endpoint, site):
    endpoint.status = 429
    with pytest.raises(night.Refused) as refused:
        indexnow(endpoint, site).submit_all(SITE, ["https://stadtdame.de/"])
    assert refused.value.too_fast


def test_key_refusal_and_address_refusal_name_different_repairs(endpoint, site):
    repairs = []
    for status in (403, 422):
        endpoint.status = status
        with pytest.raises(night.Refused) as refused:
            indexnow(endpoint, site).submit_all(SITE, ["https://stadtdame.de/"])
        repairs.append(refused.value.repair)
    assert repairs[0] != repairs[1]


def test_key_file_is_read_once_a_site(endpoint, site):
    engine = indexnow(endpoint, site)
    engine.submit_all(SITE, ["https://stadtdame.de/"])
    engine.submit_all(SITE, ["https://stadtdame.de/escort"])
    assert len([request for request in site.server.requests if request.path.endswith(".txt")]) == 1
