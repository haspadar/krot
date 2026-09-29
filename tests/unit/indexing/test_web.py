import pytest

from fakes.indexing import FakeSite
from krot_index import web


@pytest.fixture
def site():
    served = FakeSite({"/": "home"})
    yield served
    served.close()


def test_refusal_whose_body_stalls_is_unreachable(site):
    site.server.outages.append("stall")
    with pytest.raises(web.Unreachable):
        web.call("GET", site.url("/"), timeout=0.3)


def test_failure_text_leaves_the_query_out(site):
    address = site.url("/json/SubmitUrlBatch?apikey=bing-units-key")
    site.close()
    with pytest.raises(web.Unreachable) as failure:
        web.call("POST", address, body={}, timeout=5)
    assert "bing-units-key" not in str(failure.value)


def test_failure_still_names_where_it_went(site):
    address = site.url("/json/SubmitUrlBatch?apikey=bing-units-key")
    site.close()
    with pytest.raises(web.Unreachable) as failure:
        web.call("POST", address, body={}, timeout=5)
    assert "/json/SubmitUrlBatch" in str(failure.value)
