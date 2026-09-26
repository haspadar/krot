import pytest

from ansible_collections.haspadar.krot.plugins.module_utils.api import Http, Unreachable, wait


class Echo:
    def handle(self, request):
        return 200, {"path": request.path, "query": request.query}


class Refusing:
    def handle(self, request):
        return 403, {"error": "forbidden"}


def test_dropped_connections_are_unreachable(serve):
    server = serve(Echo())
    server.outages = ["drop", "drop", "drop"]
    with pytest.raises(Unreachable):
        Http(server.url).call("GET", "/zones")


def test_page_that_is_not_json_is_unreachable(serve):
    server = serve(Echo())
    server.outages = ["html", "html", "html"]
    with pytest.raises(Unreachable):
        Http(server.url).call("GET", "/zones")


def test_gives_up_after_the_given_attempts(serve):
    server = serve(Echo())
    server.outages = [503, 503, 503, 503]
    with pytest.raises(Unreachable):
        Http(server.url, attempts=2).call("GET", "/zones")
    assert len(server.requests) == 2


def test_recovers_within_the_attempts(serve):
    server = serve(Echo())
    server.outages = [429, 500]
    assert Http(server.url).call("GET", "/zones")[0] == 200


def test_pauses_between_attempts(serve, pauses):
    server = serve(Echo())
    server.outages = [503]
    Http(server.url, pause=7).call("GET", "/zones")
    assert pauses == [7]


def test_refusal_is_returned_not_retried(serve):
    server = serve(Refusing())
    Http(server.url).call("GET", "/zones")
    assert len(server.requests) == 1


def test_refusal_keeps_its_status(serve):
    assert Http(serve(Refusing()).url).call("GET", "/zones")[0] == 403


def test_failure_message_leaves_the_query_out(serve):
    server = serve(Echo())
    server.outages = [503, 503, 503]
    with pytest.raises(Unreachable) as failure:
        Http(server.url).call("GET", "/GetUserSites", {"apikey": "k-secret-9"})
    assert "k-secret-9" not in str(failure.value)


def test_wait_stops_at_the_first_ready_answer():
    answers = iter(["", "", "code-7", "code-8"])
    assert wait(lambda: next(answers), bool, 5, 0) == "code-7"


def test_wait_returns_the_last_answer_when_never_ready():
    answers = iter(["", "", ""])
    assert wait(lambda: next(answers), bool, 3, 0) == ""
