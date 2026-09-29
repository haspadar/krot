import pytest

from fakes.google import FakeTokens, service_account
from fakes.indexing import FakeIndexing
from krot_index import night, web
from krot_index.engines.google import Google, coverage_state

SITE = "rufnummer.de"


@pytest.fixture
def tokens():
    served = FakeTokens()
    yield served
    served.close()


@pytest.fixture
def api():
    served = FakeIndexing()
    yield served
    served.close()


def google(tokens, api):
    return Google(service_account(tokens.uri), token_uri=tokens.uri, inspect_url=api.inspect_url,
                  submit_url=api.submit_url)


def test_submitted_and_indexed_reads_as_indexed():
    assert coverage_state("Submitted and indexed") == night.INDEXED


def test_discovered_not_indexed_reads_as_known():
    assert coverage_state("Discovered - currently not indexed") == night.KNOWN


def test_unknown_to_google_reads_as_unknown():
    assert coverage_state("URL is unknown to Google") == night.UNKNOWN


def test_wording_nobody_has_seen_is_not_a_guess():
    assert coverage_state("Seite wird geprüft") == night.UNASKED


def test_pages_are_answered_by_url(tokens, api):
    api.coverage["https://rufnummer.de/"] = "Submitted and indexed"
    answers = google(tokens, api).states(SITE, ["https://rufnummer.de/", "https://rufnummer.de/vorwahl"])
    assert answers == {"https://rufnummer.de/": "indexed", "https://rufnummer.de/vorwahl": "unknown"}


def test_no_token_leaves_every_page_unasked(tokens, api):
    tokens.refuses = True
    assert set(google(tokens, api).states(SITE, ["https://rufnummer.de/"]).values()) == {night.UNASKED}


def test_inspection_outage_leaves_the_page_unasked(tokens, api):
    api.inspect_status = 503
    assert google(tokens, api).states(SITE, ["https://rufnummer.de/"]) == {"https://rufnummer.de/": night.UNASKED}


def test_accepted_page_is_published(tokens, api):
    google(tokens, api).submit_all(SITE, ["https://rufnummer.de/"])
    assert api.published == ["https://rufnummer.de/"]


def test_spent_day_is_an_exhausted_refusal(tokens, api):
    api.publish_answer = 429, {"error": {"code": 429, "status": "RESOURCE_EXHAUSTED",
                                         "message": "Quota exceeded for quota metric 'Publish requests'"}}
    with pytest.raises(night.Refused) as refused:
        google(tokens, api).submit_all(SITE, ["https://rufnummer.de/"])
    assert refused.value.exhausted


def test_unowned_domain_is_an_ownership_refusal(tokens, api):
    api.publish_answer = 403, {"error": {"code": 403, "status": "PERMISSION_DENIED",
                                         "message": "Permission denied. Failed to verify the URL ownership."}}
    with pytest.raises(night.Refused) as refused:
        google(tokens, api).submit_all(SITE, ["https://rufnummer.de/"])
    assert refused.value.ownership


def test_pace_limit_is_not_a_spent_day(tokens, api):
    api.publish_answer = 429, {"error": {"code": 429, "message": "Too many requests"}}
    with pytest.raises(night.Refused) as refused:
        google(tokens, api).submit_all(SITE, ["https://rufnummer.de/"])
    assert not refused.value.exhausted


def test_token_is_asked_for_once_per_scope(tokens, api):
    engine = google(tokens, api)
    engine.submit_all(SITE, ["https://rufnummer.de/", "https://rufnummer.de/vorwahl"])
    assert tokens.issued == ["https://www.googleapis.com/auth/indexing"]


def test_pages_taken_before_a_refusal_travel_with_it(tokens, api):
    engine = google(tokens, api)
    sent = []

    def publish_one_then_run_out(method, url, **kwargs):
        if url == api.submit_url:
            sent.append(url)
            if len(sent) > 1:
                return 429, b'{"error": {"code": 429, "status": "RESOURCE_EXHAUSTED", "message": "Quota exceeded"}}'
        return web.call(method, url, **kwargs)

    engine.call = publish_one_then_run_out
    with pytest.raises(night.Refused) as refused:
        engine.submit_all(SITE, ["https://rufnummer.de/a", "https://rufnummer.de/b"])
    assert refused.value.accepted == ["https://rufnummer.de/a"]


def test_inspection_pace_limit_reads_as_throttled(tokens, api):
    api.inspect_status = 429
    assert google(tokens, api).states(SITE, ["https://rufnummer.de/"]) == {"https://rufnummer.de/": night.THROTTLED}


def test_token_older_than_fifty_minutes_is_minted_again(tokens, api):
    now = [0.0]
    engine = Google(service_account(tokens.uri), token_uri=tokens.uri, inspect_url=api.inspect_url,
                    submit_url=api.submit_url, clock=lambda: now[0])
    engine.submit_all(SITE, ["https://rufnummer.de/"])
    now[0] += 51 * 60
    engine.submit_all(SITE, ["https://rufnummer.de/vorwahl"])
    assert len(tokens.issued) == 2
