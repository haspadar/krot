import io
import json
from datetime import datetime, timezone

from krot_collect import prefix
from krot_collect.fetched import judge
from krot_collect.ranges import Collection, fetch, from_rows, months_since

NOW = datetime(2026, 9, 30, tzinfo=timezone.utc)


def test_an_address_inside_a_range_is_held():
    assert prefix.read("66.249.64.0/19").holds("66.249.66.1")


def test_an_address_of_the_other_family_is_not_held():
    assert not prefix.read("66.249.64.0/19").holds("2001:db8::1")


def test_a_bare_address_is_not_a_range():
    assert prefix.read("34.22.85.0") is None


def test_a_range_wider_than_a_slash_8_is_not_kept():
    assert prefix.read("0.0.0.0/0") is None


def test_a_range_is_kept_as_its_source_wrote_it():
    assert prefix.read("34.22.85.7/24").text == "34.22.85.7/24"


def test_confirms_is_unknown_for_a_family_without_ranges():
    assert from_rows([("googlebot", "66.249.64.0/19")]).confirms("ahrefsbot", "1.2.3.4") is None


def test_confirms_is_no_for_an_address_outside_the_familys_ranges():
    assert from_rows([("googlebot", "66.249.64.0/19")]).confirms("googlebot", "1.2.3.4") is False


def test_a_list_of_bare_addresses_is_refused():
    assert judge("s", ["34.22.85.0"] * 10).refused


def test_an_empty_answer_is_refused():
    assert judge("s", ["", "# comment"]).refused


def test_a_few_odd_lines_do_not_refuse_a_list():
    answer = judge("s", ["10.0.%d.0/24" % n for n in range(9)] + ["garbage"])
    assert (answer.refused, len(answer.ranges), answer.unreadable) == (False, 9, 1)


def test_repeats_are_neither_kept_twice_nor_called_unreadable():
    answer = judge("s", ["10.0.0.0/24"] * 3)
    assert (len(answer.ranges), answer.unreadable) == (1, 0)


def test_a_too_wide_network_is_dropped_without_refusing_the_list():
    answer = judge("s", ["10.0.%d.0/24" % n for n in range(4)] + ["0.0.0.0/0"])
    assert (answer.refused, len(answer.ranges), answer.unreadable) == (False, 4, 1)


def source(shape="json", **extra):
    return dict({"name": "s", "url": "https://s.example/list", "shape": shape, "families": ["googlebot"]}, **extra)


def test_json_prefixes_are_read_with_their_date():
    body = json.dumps({"creationTime": "2026-09-01T00:00:00.000000", "prefixes": [{"ipv4Prefix": "66.249.64.0/19"},
                                                                                     {"ipv6Prefix": "2001:db8::/32"}]})
    answer = fetch(source(), get=lambda url, browser: body)
    assert ([one.text for one in answer.ranges], answer.published) == (
        ["66.249.64.0/19", "2001:db8::/32"], "2026-09-01T00:00:00.000000")


def test_a_page_where_a_document_was_is_refused():
    assert fetch(source(), get=lambda url, browser: "<html>moved</html>").refused


def test_a_document_without_prefixes_is_refused():
    assert fetch(source(), get=lambda url, browser: json.dumps({"ranges": []})).refused


def test_entries_moved_to_a_new_key_count_against_the_list():
    body = json.dumps({"prefixes": [{"cidr": "10.0.%d.0/24" % n} for n in range(5)] + [{"ipv4Prefix": "10.1.0.0/24"}]})
    assert fetch(source(), get=lambda url, browser: body).refused


def test_ranges_are_dug_out_of_a_page():
    page = "<td>5.45.192.0/18</td><td>5.45.192.0/18</td><p>2a02:6b8::/29</p>"
    assert [one.text for one in fetch(source("markup"), get=lambda url, browser: page).ranges] == [
        "5.45.192.0/18", "2a02:6b8::/29"]


def test_the_browser_line_is_sent_only_where_the_source_needs_it():
    asked = []
    fetch(source("lines", browser_agent=True), get=lambda url, browser: asked.append(browser) or "10.0.0.0/24")
    assert asked == [True]


def test_an_unreachable_source_is_refused():
    def fail(url, browser):
        raise OSError("timed out")

    assert "timed out" in fetch(source(), get=fail).refusal


def test_a_date_ahead_of_now_is_zero_months_old():
    assert months_since("2027-01-01T00:00:00Z", NOW) == 0


def test_an_empty_date_is_not_now():
    assert months_since("", NOW) is None


class FakeRangeStore:
    def __init__(self):
        self.stored = {}
        self.kept = None

    def store_ranges(self, name, families, ranges, published):
        self.stored[name] = [one.text for one in ranges]

    def forget_sources_other_than(self, names):
        self.kept = list(names)


def run(sources, answers):
    store = FakeRangeStore()
    out, err = io.StringIO(), io.StringIO()
    refused = Collection(sources, store, out, err, get=lambda url, browser: answers[url], now=NOW).collect()
    return refused, store, out.getvalue(), err.getvalue()


def test_a_refused_source_keeps_what_it_stored_before():
    refused, store, _, _ = run([source()], {"https://s.example/list": "not json"})
    assert (refused, store.stored) == (1, {})


def test_only_sources_no_longer_listed_are_forgotten():
    _, store, _, _ = run([source()], {"https://s.example/list": "not json"})
    assert store.kept == ["s"]


def test_a_list_unmoved_for_a_year_is_named():
    body = json.dumps({"creationTime": "2025-01-10T00:00:00Z", "prefixes": [{"ipv4Prefix": "66.249.64.0/19"}]})
    _, _, out, _ = run([source()], {"https://s.example/list": body})
    assert "last published over 12 months ago" in out
