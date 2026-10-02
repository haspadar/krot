import json
from contextlib import contextmanager
from datetime import date
from http.server import BaseHTTPRequestHandler, HTTPServer
from threading import Thread

import pytest

from krot_collect.gsc_api import Client, GscError, ROW_LIMIT, SCOPE, TOKEN_URI, http_call


class FakeKey:
    def __init__(self, key_json):
        self.claims = []

    def assertion(self, scope, uri, now):
        self.claims.append((scope, uri, now))
        return "private-assertion"


class FakeHttp:
    def __init__(self, answers):
        self.answers = list(answers)
        self.requests = []

    def __call__(self, method, url, headers=None, body=None, form=None):
        self.requests.append({"method": method, "url": url, "headers": headers, "body": body, "form": form})
        assert self.answers, "unexpected HTTP request"
        return self.answers.pop(0)


class Clock:
    def __init__(self):
        self.now = 1800000000
        self.delays = []

    def __call__(self):
        return self.now

    def sleep(self, seconds):
        self.delays.append(seconds)
        self.now += seconds


def ok(body):
    return 200, body, {}


def row(keys, **values):
    return {"keys": keys, "clicks": 2.0, "impressions": 17.0, "position": 4.25, **values}


def setup(*answers, **kwargs):
    http = FakeHttp([ok({"access_token": "read-token", "expires_in": 3600}), *answers])
    clock = Clock()
    return Client("{}", call=http, clock=clock, sleep=clock.sleep, key_factory=FakeKey, **kwargs), http, clock


def test_query_dimensions_become_named_metrics():
    client, _, _ = setup(ok({"rows": [row(["2026-09-08", "train tickets", "deu", "mobile"])]}))
    assert client.fetch("sc-domain:travel.example", "2026-09-08", "query") == [
        {"query": "train tickets", "country": "deu", "device": "mobile", "clicks": 2, "impressions": 17, "position": 4.25}]


def test_page_query_keeps_full_url_and_query():
    client, _, _ = setup(ok({"rows": [row(["2026-09-09", "https://museum.example/exhibitions", "modern art"])]}))
    assert client.fetch("https://museum.example/", date(2026, 9, 9), "page_query")[0]["url"] == "https://museum.example/exhibitions"


def test_request_explicitly_selects_final_web_and_exact_day():
    client, http, _ = setup(ok({}))
    client.fetch("sc-domain:books.example", "2026-09-10", "page")
    assert http.requests[1]["body"] == {"startDate": "2026-09-10", "endDate": "2026-09-10", "dimensions": ["date", "page"],
                                         "dataState": "final", "type": "web", "rowLimit": 25000, "startRow": 0}


def test_token_uses_readonly_scope():
    client, _, clock = setup(ok({}))
    client.fetch("sc-domain:gallery.example", "2026-09-11", "page")
    assert client.key.claims == [(SCOPE, TOKEN_URI, clock.now)]


def test_property_path_is_percent_encoded():
    client, http, _ = setup(ok({}))
    client.fetch("https://garden.example/plants/", "2026-09-12", "page")
    assert http.requests[1]["url"].endswith("sites/https%3A%2F%2Fgarden.example%2Fplants%2F/searchAnalytics/query")


def test_short_page_preserves_all_rows_and_stops():
    client, http, _ = setup(ok({"rows": [row(["2026-09-13", "https://school.example/courses"])]}))
    rows = client.fetch("sc-domain:school.example", "2026-09-13", "page")
    assert (len(rows), len(http.requests)) == (1, 2)


def full_page(day):
    return {"rows": [row([day, "https://catalog.example/item/%d" % index]) for index in range(ROW_LIMIT)]}


def test_full_page_continues_until_a_short_page():
    client, http, _ = setup(ok(full_page("2026-09-14")), ok({}))
    rows = client.fetch("sc-domain:catalog.example", "2026-09-14", "page")
    assert (len(rows), [request["body"]["startRow"] for request in http.requests[1:]]) == (25000, [0, 25000])


def test_unterminated_pagination_fails_instead_of_claiming_success():
    client, _, _ = setup(ok(full_page("2026-09-15")), max_pages=1)
    with pytest.raises(GscError, match="pagination_limit"):
        client.fetch("sc-domain:catalog.example", "2026-09-15", "page")


def test_duplicate_page_keys_fail():
    client, _, _ = setup(ok(full_page("2026-09-16")), ok({"rows": [row(["2026-09-16", "https://catalog.example/item/7"])]}))
    with pytest.raises(GscError, match="duplicate_row"):
        client.fetch("sc-domain:catalog.example", "2026-09-16", "page")


@pytest.mark.parametrize("response", [None, [], "secret-response", {"rows": None}, {"rows": {}},
                                     {"rows": [None]}, {"rows": [{"keys": ["2026-09-17"]}]},
                                     {"error": {"message": "private-assertion"}}])
def test_malformed_response_never_becomes_empty_success(response):
    client, _, _ = setup(ok(response))
    with pytest.raises(GscError):
        client.fetch("sc-domain:archive.example", "2026-09-17", "page")


@pytest.mark.parametrize("keys", [["2026-09-18", "https://news.example/story"], ["2026-09-19", 13],
                                  ["2026-09-19", ""], ["2026-09-19", "bad\x00key"],
                                  ["20260919", "https://news.example/story"]])
def test_bad_keys_or_wrong_date_fail(keys):
    client, _, _ = setup(ok({"rows": [row(keys)]}))
    with pytest.raises(GscError):
        client.fetch("sc-domain:news.example", "2026-09-19", "page")


@pytest.mark.parametrize("metric,value", [("clicks", -1), ("clicks", 2.5), ("clicks", True), ("impressions", "17"),
                                         ("position", float("nan")), ("position", float("inf")), ("position", -2),
                                         ("impressions", None)])
def test_bad_metrics_fail(metric, value):
    client, _, _ = setup(ok({"rows": [row(["2026-09-20", "https://weather.example/today"], **{metric: value})]}))
    with pytest.raises(GscError, match="invalid_metrics"):
        client.fetch("sc-domain:weather.example", "2026-09-20", "page")


@pytest.mark.parametrize("country,device", [("DE", "mobile"), ("deu", "watch"), ("123", "tablet")])
def test_invalid_country_or_device_fails(country, device):
    client, _, _ = setup(ok({"rows": [row(["2026-09-21", "coffee", country, device])]}))
    with pytest.raises(GscError):
        client.fetch("sc-domain:cafe.example", "2026-09-21", "query")


def test_finalized_days_only_contains_dates_google_returned():
    client, _, _ = setup(ok({"rows": [row(["2026-09-22"]), row(["2026-09-24"])]}))
    assert client.finalized_days("sc-domain:maps.example", "2026-09-22", "2026-09-24") == {"2026-09-22", "2026-09-24"}


def test_absent_finalized_day_is_not_claimed_available():
    client, _, _ = setup(ok({}))
    assert client.finalized_days("sc-domain:notes.example", "2026-09-25", "2026-09-25") == set()


def test_final_probe_requests_date_dimension():
    client, http, _ = setup(ok({}))
    client.finalized_days("sc-domain:notes.example", "2026-09-25", "2026-09-26")
    assert http.requests[1]["body"]["dimensions"] == ["date"]


def test_outside_probe_range_fails():
    client, _, _ = setup(ok({"rows": [row(["2026-09-27"])]}))
    with pytest.raises(GscError, match="unexpected_date"):
        client.finalized_days("sc-domain:events.example", "2026-09-25", "2026-09-26")


def test_quota_retry_honors_capped_retry_after():
    client, http, clock = setup((429, {"error": {"status": "RESOURCE_EXHAUSTED"}}, {"Retry-After": "120"}), ok({}))
    client.fetch("sc-domain:recipes.example", "2026-09-27", "page")
    assert clock.delays == [60]


def test_server_retry_uses_bounded_backoff():
    client, _, clock = setup((503, None, {}), (502, None, {}), ok({}))
    client.fetch("sc-domain:flights.example", "2026-09-28", "page")
    assert clock.delays == [1, 2]


def test_http_date_retry_after_is_honored():
    client, _, clock = setup((429, None, {"retry-after": "Fri, 15 Jan 2027 08:00:09 GMT"}), ok({}))
    # Clock epoch is Fri, 15 Jan 2027 08:00:00 GMT.
    client.fetch("sc-domain:calendar.example", "2026-09-29", "page")
    assert clock.delays == [9]


def test_retry_exhaustion_fails():
    client, _, clock = setup((500, None, {}), (500, None, {}), retries=1)
    with pytest.raises(GscError, match="HTTP 500"):
        client.fetch("sc-domain:store.example", "2026-09-30", "page")
    assert clock.delays == [1]


def test_permission_failure_is_not_retried_and_retains_reason():
    client, http, _ = setup((403, {"error": {"errors": [{"reason": "insufficientPermissions"}]}}, {}))
    with pytest.raises(GscError) as failure:
        client.fetch("sc-domain:portal.example", "2026-09-30", "page")
    assert (failure.value.status, failure.value.reason, len(http.requests)) == (403, "insufficientPermissions", 2)


def test_error_messages_do_not_echo_credentials():
    client, _, _ = setup((403, {"error": {"message": "private-assertion read-token private-key", "status": "private-key"}}, {}))
    with pytest.raises(GscError) as failure:
        client.fetch("sc-domain:private.example", "2026-09-30", "page")
    assert str(failure.value) == "GSC HTTP 403: request_failed"


def test_token_reused_before_fifty_minutes():
    client, http, clock = setup(ok({}), ok({}))
    client.fetch("sc-domain:lab.example", "2026-09-29", "page")
    clock.now += 2999
    client.fetch("sc-domain:lab.example", "2026-09-30", "page")
    assert len([request for request in http.requests if request["url"] == TOKEN_URI]) == 1


def test_token_refreshed_at_fifty_minutes():
    client, http, clock = setup(ok({}), ok({"access_token": "fresh-token", "expires_in": 3600}), ok({}))
    client.fetch("sc-domain:lab.example", "2026-09-29", "page")
    clock.now += 3000
    client.fetch("sc-domain:lab.example", "2026-09-30", "page")
    assert http.requests[-1]["headers"] == {"Authorization": "Bearer fresh-token"}


def test_shorter_token_expiry_is_respected():
    http = FakeHttp([ok({"access_token": "brief-token", "expires_in": 30}), ok({}),
                     ok({"access_token": "renewed-token", "expires_in": 3600}), ok({})])
    clock = Clock()
    client = Client("{}", call=http, key_factory=FakeKey, clock=clock)
    client.fetch("sc-domain:minute.example", "2026-09-29", "page")
    clock.now += 30
    client.fetch("sc-domain:minute.example", "2026-09-30", "page")
    assert http.requests[-1]["headers"]["Authorization"] == "Bearer renewed-token"


@pytest.mark.parametrize("answer", [{}, {"access_token": "with space"}, {"access_token": "token", "expires_in": -1}])
def test_bad_token_response_fails(answer):
    http = FakeHttp([ok(answer)])
    client = Client("{}", call=http, key_factory=FakeKey)
    with pytest.raises(GscError, match="invalid_token_response"):
        client.fetch("sc-domain:account.example", "2026-09-30", "page")


def test_invalid_service_key_error_is_safe():
    with pytest.raises(GscError, match="invalid_service_account"):
        Client(json.dumps({"private_key": "private-key"}))


@pytest.mark.parametrize("day", ["2026-02-30", "20260930", "2026-9-30", None])
def test_bad_requested_day_fails_before_http(day):
    client, http, _ = setup()
    with pytest.raises(GscError, match="invalid_date"):
        client.fetch("sc-domain:date.example", day, "page")
    assert http.requests == []


@contextmanager
def fake_server(status, raw, response_headers=None):
    requests = []

    class Handler(BaseHTTPRequestHandler):
        def do_POST(self):
            length = int(self.headers.get("Content-Length", "0"))
            requests.append((self.path, dict(self.headers), self.rfile.read(length)))
            self.send_response(status)
            for name, value in (response_headers or {}).items():
                self.send_header(name, value)
            self.end_headers()
            self.wfile.write(raw)

        def log_message(self, *args):
            pass

    server = HTTPServer(("127.0.0.1", 0), Handler)
    worker = Thread(target=server.serve_forever, daemon=True)
    worker.start()
    try:
        yield "http://127.0.0.1:%d/source" % server.server_port, requests
    finally:
        server.shutdown()
        worker.join()
        server.server_close()


def test_default_transport_encodes_json_and_decodes_response():
    with fake_server(200, b'{"rows": []}') as (url, requests):
        status, answer, _ = http_call("POST", url, body={"dataState": "final"})
    assert (status, answer, json.loads(requests[0][2])) == (200, {"rows": []}, {"dataState": "final"})


def test_default_transport_encodes_token_form():
    with fake_server(200, b'{"access_token": "issued"}') as (url, requests):
        http_call("POST", url, form={"assertion": "claim+signed", "grant_type": "jwt"})
    assert requests[0][2] == b"assertion=claim%2Bsigned&grant_type=jwt"


def test_default_transport_refuses_successful_non_json_body():
    with fake_server(200, b"private-key echo") as (url, _):
        with pytest.raises(GscError, match="invalid_json"):
            http_call("POST", url)


def test_non_json_proxy_failure_preserves_retryable_status():
    with fake_server(503, b"<html>proxy unavailable</html>") as (url, _):
        status, answer, _ = http_call("POST", url)
    assert (status, answer) == (503, None)


def test_default_transport_does_not_forward_bearer_to_redirect():
    with fake_server(302, b"", {"Location": "/destination"}) as (url, requests):
        status, _, _ = http_call("POST", url, headers={"Authorization": "Bearer private-token"})
    assert (status, [request[0] for request in requests]) == (302, ["/source"])


def test_huge_integer_in_metrics_is_a_controlled_failure():
    client, _, _ = setup(ok({"rows": [row(["2026-09-30", "https://math.example/numbers"], clicks=10 ** 1000)]}))
    with pytest.raises(GscError, match="invalid_metrics"):
        client.fetch("sc-domain:math.example", "2026-09-30", "page")


@pytest.mark.parametrize("property", ["", "sc-domain:", "sc-domain:bad domain", "sc-domain:bad/path",
                                      "https://user:password@portal.example/", "https://[broken/", "ftp://archive.example/"])
def test_invalid_property_fails_before_http(property):
    client, http, _ = setup()
    with pytest.raises(GscError, match="invalid_property"):
        client.fetch(property, "2026-09-30", "page")
    assert http.requests == []


@pytest.mark.parametrize("page", [
    "not a URL",
    "ftp://files.example/document",
    "https://secret:password@portal.example/",  # secret-lint: allow — fabricated URL rejected by the test
    "https://[broken/",
])
def test_invalid_page_key_fails(page):
    client, _, _ = setup(ok({"rows": [row(["2026-09-30", page])]}))
    with pytest.raises(GscError, match="invalid_page"):
        client.fetch("sc-domain:pages.example", "2026-09-30", "page")


def test_unknown_dataset_fails_before_http():
    client, http, _ = setup()
    with pytest.raises(GscError, match="invalid_dataset"):
        client.fetch("sc-domain:reports.example", "2026-09-30", "hour")
    assert http.requests == []


def test_reversed_final_range_fails_before_http():
    client, http, _ = setup()
    with pytest.raises(GscError, match="invalid_date_range"):
        client.finalized_days("sc-domain:reports.example", "2026-09-30", "2026-09-29")
    assert http.requests == []
