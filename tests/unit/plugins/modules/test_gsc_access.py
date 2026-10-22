import pytest

from fakes.google import CONSOLE_SCOPE, EMAIL, VERIFY_SCOPE, FakeGoogle, FakeTokens, refused, service_account

COLLECTOR = "sammler@krot-units.iam.gserviceaccount.com"
OPERATOR = "betreiber@example.de"
PROPERTY = "/webmasters/v3/sites/sc-domain%3Abesitz.de"


@pytest.fixture
def tokens():
    served = FakeTokens()
    yield served
    served.close()


def args(server, tokens, domain, **extra):
    base = dict(domain=domain, service_account=service_account(tokens.uri),
                reader_service_account=service_account(tokens.uri, COLLECTOR), token_uri=tokens.uri,
                api_url=server.url)
    base.update(extra)
    return base


def seeded(domain="besitz.de", owners=None):
    google = FakeGoogle()
    google.verified(domain, owners)
    return google


def test_collector_without_access_becomes_an_owner_of_the_domain(run, serve, tokens):
    google = seeded()
    run("gsc_access", args(serve(google), tokens, "besitz.de"))
    assert google.resources["dns://besitz.de"] == [EMAIL, COLLECTOR]


def test_collector_ends_up_owning_the_property_in_its_own_console(run, serve, tokens):
    google = seeded()
    run("gsc_access", args(serve(google), tokens, "besitz.de"))
    assert google.others[COLLECTOR] == {"sc-domain:besitz.de": "siteOwner"}


def test_grant_keeps_every_owner_already_there(run, serve, tokens):
    google = seeded(owners=[EMAIL, OPERATOR])
    run("gsc_access", args(serve(google), tokens, "besitz.de"))
    assert google.resources["dns://besitz.de"] == [EMAIL, OPERATOR, COLLECTOR]


def test_grant_is_reported_with_the_collectors_address(run, serve, tokens):
    google = seeded()
    result = run("gsc_access", args(serve(google), tokens, "besitz.de"))
    assert (result["changed"], result["granted"], result["owner"], result["reader"]) == (True, True, True, COLLECTOR)


def test_second_run_writes_nothing(run, serve, tokens):
    google = seeded()
    run("gsc_access", args(serve(google), tokens, "besitz.de"))
    server = serve(google)
    result = run("gsc_access", args(server, tokens, "besitz.de"))
    assert (server.writes(), result["changed"]) == ([], False)


def test_collector_that_already_owns_is_left_alone(run, serve, tokens):
    google = seeded(owners=[EMAIL, COLLECTOR])
    google.others[COLLECTOR] = {"sc-domain:besitz.de": "siteOwner"}
    server = serve(google)
    result = run("gsc_access", args(server, tokens, "besitz.de"))
    assert (server.writes(), result["owner"]) == ([], True)


def test_collector_with_less_than_ownership_is_made_an_owner(run, serve, tokens):
    google = seeded()
    google.others[COLLECTOR] = {"sc-domain:besitz.de": "siteFullUser"}
    result = run("gsc_access", args(serve(google), tokens, "besitz.de"))
    assert (result["granted"], google.others[COLLECTOR]["sc-domain:besitz.de"]) == (True, "siteOwner")


def test_owner_by_verification_only_adds_the_property_to_its_console(run, serve, tokens):
    google = seeded(owners=[EMAIL, COLLECTOR])
    server = serve(google)
    result = run("gsc_access", args(server, tokens, "besitz.de"))
    assert ([r.path for r in server.writes()], result["granted"]) == ([PROPERTY], False)


def test_launching_key_that_is_the_collecting_key_is_never_added_as_owner(run, serve, tokens):
    google = FakeGoogle()
    google.verified("besitz.de", owned=False)
    server = serve(google)
    run("gsc_access", args(server, tokens, "besitz.de", reader_service_account=service_account(tokens.uri)))
    assert [r.path for r in server.writes()] == [PROPERTY]


def test_check_mode_says_access_is_due_and_writes_nothing(run, serve, tokens):
    google = seeded()
    server = serve(google)
    result = run("gsc_access", args(server, tokens, "besitz.de"), check=True)
    assert (server.writes(), result["changed"], result["owner"]) == ([], True, False)


def test_check_mode_says_the_launching_key_can_grant(run, serve, tokens):
    google = seeded()
    assert run("gsc_access", args(serve(google), tokens, "besitz.de"), check=True)["grantable"] is True


def test_check_mode_says_a_launching_key_that_owns_nothing_cannot_grant(run, serve, tokens):
    google = FakeGoogle()
    assert run("gsc_access", args(serve(google), tokens, "neu.de"), check=True)["grantable"] is False


def test_check_mode_is_quiet_when_the_collector_owns(run, serve, tokens):
    google = seeded(owners=[EMAIL, COLLECTOR])
    google.others[COLLECTOR] = {"sc-domain:besitz.de": "siteOwner"}
    result = run("gsc_access", args(serve(google), tokens, "besitz.de"), check=True)
    assert (result["changed"], result["owner"]) == (False, True)


def test_launching_key_that_does_not_own_the_domain_fails_with_the_manual_step(run, serve, tokens):
    google = seeded(owners=["fremd@x.iam.gserviceaccount.com"])
    result = run("gsc_access", args(serve(google), tokens, "besitz.de"))
    assert "Make %s an owner of sc-domain:besitz.de" % COLLECTOR in result["msg"]


def test_launching_key_that_does_not_own_the_domain_writes_nothing(run, serve, tokens):
    google = seeded(owners=["fremd@x.iam.gserviceaccount.com"])
    server = serve(google)
    run("gsc_access", args(server, tokens, "besitz.de"))
    assert server.writes() == []


def test_ownership_that_reaches_search_console_late_is_waited_for(run, serve, tokens, pauses):
    google = seeded()
    google.owner_lag = 2
    result = run("gsc_access", args(serve(google), tokens, "besitz.de", wait_delay=7))
    assert (result.get("failed", False), pauses) == (False, [7, 7])


def test_adding_the_property_refused_while_ownership_propagates_is_retried(run, serve, tokens, pauses):
    google = seeded()
    google.add_refusals = 1
    result = run("gsc_access", args(serve(google), tokens, "besitz.de", wait_delay=5))
    assert (result.get("failed", False), pauses) == (False, [5])


def test_ownership_that_never_shows_fails_naming_the_key(run, serve, tokens):
    google = seeded()
    google.owner_lag = 99
    result = run("gsc_access", args(serve(google), tokens, "besitz.de", wait_attempts=3))
    assert (result["failed"], COLLECTOR in result["msg"]) == (True, True)


def test_owners_google_accepts_but_does_not_list_fail_the_run(run, serve, tokens):
    google = seeded()
    google.forgets_owners = True
    result = run("gsc_access", args(serve(google), tokens, "besitz.de"))
    assert (result["failed"], "does not list" in result["msg"]) == (True, True)


def test_empty_owner_list_is_never_written_back(run, serve, tokens):
    google = seeded()
    google.owners_broken = True
    server = serve(google)
    result = run("gsc_access", args(server, tokens, "besitz.de"))
    assert (server.writes(), result["failed"]) == ([], True)


def test_switched_off_search_console_fails_without_granting(run, serve, tokens):
    google = seeded()
    google.disabled_scopes = {CONSOLE_SCOPE}
    server = serve(google)
    result = run("gsc_access", args(server, tokens, "besitz.de"))
    assert (server.writes(), "has not been used" in result["msg"]) == ([], True)


def test_switched_off_site_verification_fails_without_granting(run, serve, tokens):
    google = seeded()
    google.disabled_scopes = {VERIFY_SCOPE}
    server = serve(google)
    result = run("gsc_access", args(server, tokens, "besitz.de"))
    assert (server.writes(), "has not been used" in result["msg"]) == ([], True)


def test_collector_refused_in_searchanalytics_words_is_granted(run, serve, tokens):
    google = seeded()
    google.unknown_site_status = 403
    result = run("gsc_access", args(serve(google), tokens, "besitz.de"))
    assert (result.get("failed", False), result["granted"]) == (False, True)


def test_owners_read_refused_in_other_words_writes_nothing(run, serve, tokens):
    google = seeded()

    def replaced(request, path, email):
        return refused(403, "The caller does not have permission", "PERMISSION_DENIED")

    google.verification = replaced
    server = serve(google)
    result = run("gsc_access", args(server, tokens, "besitz.de"))
    assert (server.writes(), "not a verified owner" in result["msg"]) == ([], False)


def test_owner_google_drops_on_the_write_fails_the_run(run, serve, tokens):
    google = seeded(owners=[EMAIL, OPERATOR])
    original = google.verification

    def replaced(request, path, email):
        answer = original(request, path, email)
        if request.method == "PUT":
            google.resources["dns://besitz.de"].remove(OPERATOR)
        return answer

    google.verification = replaced
    result = run("gsc_access", args(serve(google), tokens, "besitz.de"))
    assert (result["failed"], "every owner it had" in result["msg"]) == (True, True)


@pytest.mark.parametrize("answer", [None, {}, {"siteUrl": "sc-domain:anders.de", "permissionLevel": "siteOwner"},
                                    {"siteUrl": "sc-domain:besitz.de"}, []])
def test_ok_without_a_level_for_the_site_is_not_access(run, serve, tokens, answer):
    google = seeded(owners=[EMAIL, COLLECTOR])

    def replaced(request, path, email):
        if request.method == "GET" and path == "/webmasters/v3/sites/sc-domain:besitz.de":
            return 200, answer
        return FakeGoogle.console(google, request, path, email)

    google.console = replaced
    server = serve(google)
    result = run("gsc_access", args(server, tokens, "besitz.de"))
    assert (server.writes(), result["failed"]) == ([], True)


@pytest.mark.parametrize("status,message", [(404, "Requested entity was not found."),
                                            (403, "The caller's key is restricted to other APIs.")])
def test_refusal_in_other_words_grants_nothing(run, serve, tokens, status, message):
    google = seeded()

    def replaced(request, path, email):
        return refused(status, message)

    google.console = replaced
    server = serve(google)
    result = run("gsc_access", args(server, tokens, "besitz.de"))
    assert (server.writes(), result["failed"]) == ([], True)


def test_key_that_is_not_a_service_account_fails(run, serve, tokens):
    google = seeded()
    result = run("gsc_access", args(serve(google), tokens, "besitz.de", reader_service_account="{}"))
    assert result["failed"] is True
