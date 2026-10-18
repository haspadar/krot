import pytest

from fakes.google import ADMIN, EMAIL, FakeGoogle, FakeTokens, service_account

COLLECTOR = "collector@krot-units.iam.gserviceaccount.com"
VIEWER = "predefinedRoles/viewer"


@pytest.fixture
def tokens():
    served = FakeTokens()
    yield served
    served.close()


def args(server, tokens, number, **extra):
    base = dict(property_id=number, service_account=service_account(tokens.uri),
                reader_service_account=service_account(tokens.uri, COLLECTOR), token_uri=tokens.uri,
                api_url=server.url, data_api_url=server.url + "/data")
    base.update(extra)
    return base


def seeded(domain="zugang.de"):
    google = FakeGoogle()
    return google, google.add_property(domain)


def test_collector_without_access_gets_viewer_on_the_property(run, serve, tokens):
    google, number = seeded()
    run("ga4_access", args(serve(google), tokens, number))
    assert google.bindings == [(number, COLLECTOR, [VIEWER])]


def test_grant_leaves_the_launching_key_an_administrator(run, serve, tokens):
    google, number = seeded()
    run("ga4_access", args(serve(google), tokens, number))
    assert google.access[number] == {EMAIL: ADMIN, COLLECTOR: VIEWER}


def test_grant_is_reported_with_the_collectors_address(run, serve, tokens):
    google, number = seeded()
    result = run("ga4_access", args(serve(google), tokens, number))
    assert (result["changed"], result["granted"], result["reader"]) == (True, True, COLLECTOR)


def test_second_run_writes_nothing(run, serve, tokens):
    google, number = seeded()
    run("ga4_access", args(serve(google), tokens, number))
    server = serve(google)
    result = run("ga4_access", args(server, tokens, number))
    assert (server.writes(), result["changed"]) == ([], False)


def test_collector_that_already_reads_is_left_alone(run, serve, tokens):
    google, number = seeded()
    google.access[number][COLLECTOR] = "predefinedRoles/editor"
    server = serve(google)
    run("ga4_access", args(server, tokens, number))
    assert (server.writes(), google.access[number][COLLECTOR]) == ([], "predefinedRoles/editor")


def test_launching_key_that_is_the_collecting_key_needs_no_grant(run, serve, tokens):
    google, number = seeded()
    server = serve(google)
    result = run("ga4_access", args(server, tokens, number, reader_service_account=service_account(tokens.uri)))
    assert (server.writes(), result["changed"]) == ([], False)


def test_check_mode_says_a_grant_is_due_and_grants_nothing(run, serve, tokens):
    google, number = seeded()
    server = serve(google)
    result = run("ga4_access", args(server, tokens, number), check=True)
    assert (server.writes(), result["changed"]) == ([], True)


def test_check_mode_is_quiet_when_the_collector_reads(run, serve, tokens):
    google, number = seeded()
    google.access[number][COLLECTOR] = VIEWER
    assert run("ga4_access", args(serve(google), tokens, number), check=True)["changed"] is False


def test_grant_that_reaches_the_data_api_late_is_waited_for(run, serve, tokens, pauses):
    google, number = seeded()
    google.grant_lag = 2
    result = run("ga4_access", args(serve(google), tokens, number, wait_delay=7))
    assert (result.get("failed", False), pauses) == (False, [7, 7])


def test_grant_whose_accepted_report_is_incomplete_is_waited_for(run, serve, tokens, pauses):
    google, number = seeded()
    google.report_lag = 2
    result = run("ga4_access", args(serve(google), tokens, number, wait_delay=7))
    assert (result.get("failed", False), result["granted"], pauses) == (False, True, [7, 7])


def test_grant_that_never_reaches_the_data_api_fails_naming_the_key(run, serve, tokens):
    google, number = seeded()
    google.grant_lag = 99
    result = run("ga4_access", args(serve(google), tokens, number, wait_attempts=3))
    assert COLLECTOR in result["msg"] and number in result["msg"]


def test_launching_key_that_cannot_grant_fails_with_the_manual_step(run, serve, tokens):
    google = FakeGoogle()
    number = google.add_property("fremd.de", owner="someone-else@x.iam.gserviceaccount.com")
    result = run("ga4_access", args(serve(google), tokens, number))
    assert "Give %s the Viewer role on property %s" % (COLLECTOR, number) in result["msg"]


def test_launching_key_that_cannot_grant_writes_no_binding(run, serve, tokens):
    google = FakeGoogle()
    number = google.add_property("fremd.de", owner="someone-else@x.iam.gserviceaccount.com")
    run("ga4_access", args(serve(google), tokens, number))
    assert google.bindings == []


def test_switched_off_data_api_fails_without_granting(run, serve, tokens):
    google, number = seeded()
    google.data_disabled = True
    server = serve(google)
    result = run("ga4_access", args(server, tokens, number))
    assert (server.writes(), "has not been used" in result["msg"]) == ([], True)


def test_property_that_is_not_there_fails_without_granting(run, serve, tokens):
    google, _ = seeded()
    server = serve(google)
    result = run("ga4_access", args(server, tokens, "1"))
    assert (server.writes(), "HTTP 404" in result["msg"]) == ([], True)


def test_binding_already_there_but_not_in_force_is_waited_for(run, serve, tokens):
    google, number = seeded()
    google.access[number][COLLECTOR] = VIEWER
    google.pending[(number, COLLECTOR)] = 1
    result = run("ga4_access", args(serve(google), tokens, number))
    assert (result.get("failed", False), result["granted"]) == (False, False)


def test_key_that_is_not_a_service_account_fails(run, serve, tokens):
    google, number = seeded()
    result = run("ga4_access", args(serve(google), tokens, number, reader_service_account="{}"))
    assert result["failed"] is True


@pytest.mark.parametrize("answer", [{}, {"error": {"code": 403}}, {"rows": []}, {"metricHeaders": []},
                                    {"metricHeaders": [{"name": "users"}]}, []])
def test_ok_without_a_report_is_not_access(run, serve, tokens, answer):
    google, number = seeded()
    google.access[number][COLLECTOR] = VIEWER
    google.report_replaced_by = answer
    server = serve(google)
    result = run("ga4_access", args(server, tokens, number))
    assert (server.writes(), result["failed"]) == ([], True)


def test_property_without_data_still_counts_as_read(run, serve, tokens):
    google, number = seeded()
    google.access[number][COLLECTOR] = VIEWER
    result = run("ga4_access", args(serve(google), tokens, number))
    assert result.get("failed", False) is False


def test_refusal_that_is_not_about_rights_grants_nothing(run, serve, tokens):
    google, number = seeded()
    google.refusal = "The caller's key is restricted to other APIs."
    server = serve(google)
    result = run("ga4_access", args(server, tokens, number))
    assert (server.writes(), result["failed"], "restricted" in result["msg"]) == ([], True, True)


def test_launching_key_refused_on_its_own_property_is_waited_for_not_granted(run, serve, tokens, pauses):
    google, number = seeded()
    google.pending[(number, EMAIL)] = 2
    server = serve(google)
    result = run("ga4_access", dict(args(server, tokens, number), reader_service_account=service_account(tokens.uri)))
    assert (server.writes(), result.get("failed", False), len(pauses)) == ([], False, 1)


def test_launching_key_that_never_reads_its_own_property_fails_without_granting(run, serve, tokens):
    google, number = seeded()
    google.pending[(number, EMAIL)] = 99
    server = serve(google)
    result = run("ga4_access", dict(args(server, tokens, number), reader_service_account=service_account(tokens.uri),
                                    wait_attempts=2))
    assert (server.writes(), result["failed"]) == ([], True)
