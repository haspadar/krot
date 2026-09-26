import pytest

from ansible_collections.haspadar.krot.plugins.module_utils.api import Unreachable
from ansible_collections.haspadar.krot.plugins.module_utils.delegation import answers, delegated
from fakes.doh import SERVFAIL, FakeDoh

PAIR = ["ada.ns.cloudflare.com", "bob.ns.cloudflare.com"]


def test_reports_nameservers_without_the_trailing_dot(serve):
    resolver = serve(FakeDoh({"punkt.de": PAIR}))
    assert answers("punkt.de", [resolver.url])[resolver.url] == PAIR


def test_reports_nameservers_in_lower_case(serve):
    resolver = serve(FakeDoh({"gross.de": ["ADA.NS.Cloudflare.com", "BOB.ns.cloudflare.COM"]}))
    assert answers("gross.de", [resolver.url])[resolver.url] == PAIR


def test_nxdomain_is_an_empty_answer(serve):
    resolver = serve(FakeDoh())
    assert answers("unbekannt.de", [resolver.url])[resolver.url] == []


def test_servfail_is_not_an_answer(serve):
    doh = FakeDoh({"kaputtdns.de": PAIR})
    doh.status = SERVFAIL
    resolver = serve(doh)
    with pytest.raises(Unreachable):
        answers("kaputtdns.de", [resolver.url])


def test_second_resolver_failing_fails_the_whole_question(serve):
    first = serve(FakeDoh({"zweiter.de": PAIR}))
    second = serve(FakeDoh({"zweiter.de": PAIR}))
    second.outages = ["drop", "drop", "drop"]
    with pytest.raises(Unreachable):
        answers("zweiter.de", [first.url, second.url])


def test_page_that_is_not_json_is_not_an_answer(serve):
    resolver = serve(FakeDoh({"portal.de": PAIR}))
    resolver.outages = ["html", "html", "html"]
    with pytest.raises(Unreachable):
        answers("portal.de", [resolver.url])


def test_asks_for_the_json_form(serve):
    resolver = serve(FakeDoh({"format.de": PAIR}))
    answers("format.de", [resolver.url])
    assert resolver.requests[0].headers.get("Accept") == "application/dns-json"


def test_delegated_when_every_resolver_sees_the_pair():
    assert delegated({"a": PAIR, "b": list(reversed(PAIR))}, PAIR) is True


def test_not_delegated_while_one_resolver_still_sees_the_old_pair():
    assert delegated({"a": PAIR, "b": ["ns1.dynadot.com", "ns2.dynadot.com"]}, PAIR) is False


def test_not_delegated_when_one_extra_nameserver_is_listed():
    assert delegated({"a": PAIR + ["ns3.fremd.net"]}, PAIR) is False


def test_expected_names_are_compared_without_dot_and_case():
    assert delegated({"a": PAIR}, ["ADA.ns.cloudflare.com.", "bob.ns.cloudflare.com."]) is True


def test_no_resolvers_is_not_delegated():
    assert delegated({}, PAIR) is False
