import pytest

from fakes.analytics import FakeAnalytics, HUMAN, ADMIN
from fakes.google import EMAIL, FakeTokens, service_account


@pytest.fixture
def tokens():
    served = FakeTokens()
    yield served
    served.close()


def args(server, tokens, domain, **extra):
    return dict(domain=domain, account_id="301144", owner_email=HUMAN,
                service_account=service_account(tokens.uri), token_uri=tokens.uri,
                api_url=server.url, access_api_url=server.url, google_api_url=server.url, **extra)


def owned(domain):
    google = FakeAnalytics()
    google.verified(domain, owners=[EMAIL, HUMAN])
    return google


def test_creates_property_in_explicit_account_with_berlin_time(run, serve, tokens):
    google = owned("frisch.de")
    result = run("ga4_property", args(serve(google), tokens, "frisch.de"))
    assert (result.get("failed"), google.properties[0]["parent"], google.properties[0]["timeZone"],
            google.properties[0]["currencyCode"], result["measurement_id"].startswith("G-")) == (
            None, "accounts/301144", "Europe/Berlin", "EUR", True)


def test_repeat_is_quiet_and_keeps_existing_settings(run, serve, tokens):
    google = owned("bestand.de")
    pid = google.add_property("bestand.de", time_zone="Europe/Minsk", currency="USD")
    server = serve(google)
    result = run("ga4_property", args(server, tokens, "bestand.de"))
    assert (result.get("changed"), result["property_id"], result["time_zone"],
            google.properties[0]["currencyCode"], server.writes()) == (False, pid, "Europe/Minsk", "USD", [])


def test_resumes_property_without_stream(run, serve, tokens):
    google = owned("halb.de")
    pid = google.add_property("halb.de", stream=False)
    server = serve(google)
    result = run("ga4_property", args(server, tokens, "halb.de"))
    assert (result["property_id"], len(google.properties), [r.path for r in server.writes()]) == (
        pid, 1, ["/properties/%s/dataStreams" % pid])


def test_renamed_property_is_found_by_domain_stream(run, serve, tokens):
    google = owned("umbenannt.de")
    pid = google.add_property("umbenannt.de")
    google.properties[0]["displayName"] = "Old title"
    assert run("ga4_property", args(serve(google), tokens, "umbenannt.de"))["property_id"] == pid


def test_reads_all_property_and_stream_pages(run, serve, tokens):
    google = owned("spaet.de")
    google.page_size = 1
    google.add_property("andere.de")
    pid = google.add_property("spaet.de")
    google.add_app_stream(pid)
    google.account_bindings["301144"].insert(0, {"user": "guest@example.de", "roles": []})
    server = serve(google)
    result = run("ga4_property", args(server, tokens, "spaet.de"))
    assert (result["property_id"], result["changed"], server.writes()) == (pid, False, [])


def test_rejects_two_properties_before_writing(run, serve, tokens):
    google = owned("doppelt.de")
    google.add_property("doppelt.de")
    google.add_property("doppelt.de")
    server = serve(google)
    result = run("ga4_property", args(server, tokens, "doppelt.de"))
    assert ("Ambiguous GA4 properties" in result["msg"], server.writes()) == (True, [])


def test_explicit_property_resolves_ambiguity(run, serve, tokens):
    google = owned("auswahl.de")
    google.add_property("auswahl.de")
    pid = google.add_property("auswahl.de")
    assert run("ga4_property", args(serve(google), tokens, "auswahl.de", property_id=pid))["property_id"] == pid


def test_refuses_missing_explicit_property_without_replacement(run, serve, tokens):
    google = owned("fehlt.de")
    google.add_property("fehlt.de", account="402255")
    server = serve(google)
    result = run("ga4_property", args(server, tokens, "fehlt.de", property_id="550407450"))
    assert (result.get("failed"), server.writes()) == (True, [])


def test_selects_matching_domain_stream_not_first_web_stream(run, serve, tokens):
    google = owned("passend.de")
    pid = google.add_property("fremd.de")
    google._stream(pid, "passend.de")
    expected = google.streams[pid][-1]["name"].split("/")[-1]
    assert run("ga4_property", args(serve(google), tokens, "passend.de"))["stream_id"] == expected


def test_rejects_two_matching_streams(run, serve, tokens):
    google = owned("zweifach.de")
    pid = google.add_property("zweifach.de")
    google._stream(pid, "zweifach.de")
    server = serve(google)
    result = run("ga4_property", args(server, tokens, "zweifach.de"))
    assert ("Ambiguous GA4 web streams" in result["msg"], server.writes()) == (True, [])


def test_explicit_stream_must_match_domain(run, serve, tokens):
    google = owned("ziel.de")
    pid = google.add_property("falsch.de")
    sid = google.streams[pid][0]["name"].split("/")[-1]
    server = serve(google)
    result = run("ga4_property", args(server, tokens, "ziel.de", property_id=pid, stream_id=sid))
    assert (result.get("failed"), server.writes()) == (True, [])


def test_explicit_stream_resolves_duplicate_url(run, serve, tokens):
    google = owned("genau.de")
    pid = google.add_property("genau.de")
    sid = google.streams[pid][0]["name"].split("/")[-1]
    google._stream(pid, "genau.de")
    assert run("ga4_property", args(serve(google), tokens, "genau.de", property_id=pid, stream_id=sid))["stream_id"] == sid


@pytest.mark.parametrize("status", [401, 403])
def test_account_bindings_refusal_never_creates_property(run, serve, tokens, status):
    google = owned("gesperrt.de")
    google.bindings_status = status
    server = serve(google)
    result = run("ga4_property", args(server, tokens, "gesperrt.de"))
    assert (result.get("failed"), server.writes()) == (True, [])


def test_human_gsc_owner_must_already_administer_account(run, serve, tokens):
    google = owned("mensch.de")
    google.account_bindings["301144"] = [{"user": HUMAN, "roles": ["predefinedRoles/editor"]}]
    server = serve(google)
    result = run("ga4_property", args(server, tokens, "mensch.de"))
    assert ("not an administrator" in result["msg"], server.writes()) == (True, [])


def test_account_admin_must_own_this_domain(run, serve, tokens):
    google = owned("besitzer.de")
    google.resources["dns://besitzer.de"] = [EMAIL, "other@example.de"]
    server = serve(google)
    result = run("ga4_property", args(server, tokens, "besitzer.de"))
    assert ("not a GSC owner" in result["msg"], server.writes()) == (True, [])


def test_no_global_owner_fallback(run, serve, tokens):
    google = owned("leer.de")
    parameters = args(serve(google), tokens, "leer.de")
    parameters["owner_email"] = ""
    assert run("ga4_property", parameters).get("failed") is True


def test_service_account_cannot_be_human_owner(run, serve, tokens):
    google = owned("technisch.de")
    parameters = args(serve(google), tokens, "technisch.de")
    parameters["owner_email"] = EMAIL
    assert "human Google account" in run("ga4_property", parameters)["msg"]


def test_check_new_domain_is_pending_without_writes(run, serve, tokens):
    google = FakeAnalytics()
    server = serve(google)
    result = run("ga4_property", args(server, tokens, "neu.de"), check=True)
    assert (result["changed"], result["owner_verified"], result["property_id"], server.writes()) == (True, False, "", [])


def test_apply_unverified_domain_fails_without_writes(run, serve, tokens):
    server = serve(FakeAnalytics())
    result = run("ga4_property", args(server, tokens, "unbewiesen.de"))
    assert (result.get("failed"), server.writes()) == (True, [])


def test_check_existing_property_missing_stream_writes_nothing(run, serve, tokens):
    google = owned("planung.de")
    pid = google.add_property("planung.de", stream=False)
    server = serve(google)
    result = run("ga4_property", args(server, tokens, "planung.de"), check=True)
    assert (result["changed"], result["property_id"], result["stream_id"], server.writes()) == (True, pid, "", [])


def test_missing_measurement_id_is_failure_not_another_stream(run, serve, tokens):
    google = owned("messung.de")
    pid = google.add_property("messung.de")
    google.streams[pid][0]["webStreamData"].pop("measurementId")
    server = serve(google)
    result = run("ga4_property", args(server, tokens, "messung.de"))
    assert (result.get("failed"), server.writes()) == (True, [])


def test_property_creation_ack_without_readback_fails(run, serve, tokens):
    google = owned("unsichtbar.de")
    google.hides_new_properties = True
    result = run("ga4_property", args(serve(google), tokens, "unsichtbar.de"))
    assert (result.get("failed"), result["changed"]) == (True, True)


@pytest.mark.parametrize("key,value", [("properties", None), ("properties", [None]),
                                        ("properties", [{"displayName": "defekt.de"}])])
def test_malformed_property_listing_never_creates(run, serve, tokens, key, value):
    google = owned("defekt.de")
    original = google.analytics

    def broken(request, path, email):
        return (200, {key: value}) if path == "/properties" else original(request, path, email)

    google.analytics = broken
    server = serve(google)
    result = run("ga4_property", args(server, tokens, "defekt.de"))
    assert (result.get("failed"), server.writes()) == (True, [])


def test_repeated_pagination_token_is_failure(run, serve, tokens):
    google = owned("schleife.de")
    original = google.analytics

    def looping(request, path, email):
        return (200, {"properties": [], "nextPageToken": "again"}) if path == "/properties" else original(request, path, email)

    google.analytics = looping
    server = serve(google)
    result = run("ga4_property", args(server, tokens, "schleife.de"))
    assert (result.get("failed"), server.writes()) == (True, [])


def test_lost_property_response_is_recovered_without_duplicate(run, serve, tokens):
    google = owned("abbruch.de")
    server = serve(google)
    server.outages = [None, None, None, "lost"]
    first = run("ga4_property", args(server, tokens, "abbruch.de"))
    second = run("ga4_property", args(server, tokens, "abbruch.de"))
    assert (first.get("failed"), second.get("failed"), len(google.properties),
            len(google.streams[second["property_id"]])) == (True, None, 1, 1)


def test_lost_stream_response_is_recovered_without_duplicate(run, serve, tokens):
    google = owned("unterbrochen.de")
    pid = google.add_property("unterbrochen.de", stream=False)
    server = serve(google)
    server.outages = [None, None, None, None, "lost"]
    first = run("ga4_property", args(server, tokens, "unterbrochen.de"))
    second = run("ga4_property", args(server, tokens, "unterbrochen.de"))
    assert (first.get("failed"), second.get("failed"), second["changed"], len(google.streams[pid])) == (True, None, False, 1)


@pytest.mark.parametrize("domain", ["foo..bar.de", "foo.-bar.de", "foo.bar-.de", "a" * 64 + ".de",
                                    "https://seite.de", "www.seite.de", "SEITE.de"])
def test_invalid_domain_fails_before_api_calls(run, serve, tokens, domain):
    server = serve(FakeAnalytics())
    result = run("ga4_property", args(server, tokens, domain))
    assert (result.get("failed"), server.requests) == (True, [])
