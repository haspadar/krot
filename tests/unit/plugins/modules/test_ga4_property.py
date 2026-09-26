import pytest

from fakes.google import ANALYTICS_SCOPE, FakeGoogle, FakeTokens, service_account


@pytest.fixture
def tokens():
    served = FakeTokens()
    yield served
    served.close()


def args(server, tokens, domain, **extra):
    base = dict(domain=domain, account_id="301144", time_zone="Europe/Berlin", currency_code="EUR",
                service_account=service_account(tokens.uri), token_uri=tokens.uri, api_url=server.url)
    base.update(extra)
    return base


def test_creates_absent_property_named_after_the_domain(run, serve, tokens):
    google = FakeGoogle()
    run("ga4_property", args(serve(google), tokens, "neuzaehler.de"))
    assert [p["displayName"] for p in google.properties] == ["neuzaehler.de"]


def test_new_property_counts_days_in_the_given_zone(run, serve, tokens):
    google = FakeGoogle()
    run("ga4_property", args(serve(google), tokens, "wien-nacht.at", time_zone="Europe/Vienna"))
    assert google.properties[0]["timeZone"] == "Europe/Vienna"


def test_new_property_reports_in_the_given_currency(run, serve, tokens):
    google = FakeGoogle()
    run("ga4_property", args(serve(google), tokens, "zloty.pl", currency_code="PLN"))
    assert google.properties[0]["currencyCode"] == "PLN"


def test_new_property_returns_its_measurement_id(run, serve, tokens):
    google = FakeGoogle()
    result = run("ga4_property", args(serve(google), tokens, "messung.de"))
    assert result["measurement_id"] == google.streams[result["property_id"]][0]["webStreamData"]["measurementId"]


def test_existing_property_is_not_created_again(run, serve, tokens):
    google = FakeGoogle()
    google.add_property("vorhanden.de")
    server = serve(google)
    run("ga4_property", args(server, tokens, "vorhanden.de"))
    assert server.writes() == []


def test_property_past_the_first_page_is_found(run, serve, tokens):
    google = FakeGoogle()
    google.page_size = 2
    for name in ("eins.de", "zwei.de", "drei.de"):
        google.add_property(name)
    server = serve(google)
    run("ga4_property", args(server, tokens, "drei.de"))
    assert server.writes() == []


def test_half_created_property_gets_its_stream(run, serve, tokens):
    google = FakeGoogle()
    number = google.add_property("abgebrochen.de", stream=False)
    run("ga4_property", args(serve(google), tokens, "abgebrochen.de"))
    assert len(google.streams[number]) == 1


def test_half_created_property_is_not_created_twice(run, serve, tokens):
    google = FakeGoogle()
    google.add_property("abgebrochen.de", stream=False)
    run("ga4_property", args(serve(google), tokens, "abgebrochen.de"))
    assert len(google.properties) == 1


def test_wrong_time_zone_is_corrected(run, serve, tokens):
    google = FakeGoogle()
    google.add_property("stadtnacht.de", time_zone="Europe/Minsk")
    run("ga4_property", args(serve(google), tokens, "stadtnacht.de"))
    assert google.properties[0]["timeZone"] == "Europe/Berlin"


def test_correction_touches_only_the_drifted_field(run, serve, tokens):
    google = FakeGoogle()
    google.add_property("nurzone.de", time_zone="Europe/Minsk")
    server = serve(google)
    run("ga4_property", args(server, tokens, "nurzone.de"))
    assert server.writes()[0].query["updateMask"] == "timeZone"


def test_correction_accepted_but_not_kept_fails(run, serve, tokens):
    google = FakeGoogle()
    google.forgets_patches = True
    google.add_property("stur.de", currency="USD")
    assert "did not keep" in run("ga4_property", args(serve(google), tokens, "stur.de"))["msg"]


def test_second_run_is_unchanged(run, serve, tokens):
    server = serve(FakeGoogle())
    run("ga4_property", args(server, tokens, "zweiterlauf.de"))
    assert run("ga4_property", args(server, tokens, "zweiterlauf.de"))["changed"] is False


def test_check_mode_creates_nothing(run, serve, tokens):
    server = serve(FakeGoogle())
    run("ga4_property", args(server, tokens, "trocken.de"), check=True)
    assert server.writes() == []


def test_check_mode_corrects_nothing(run, serve, tokens):
    google = FakeGoogle()
    google.add_property("nurschauen.de", time_zone="Europe/Minsk")
    server = serve(google)
    run("ga4_property", args(server, tokens, "nurschauen.de"), check=True)
    assert server.writes() == []


def test_property_creation_whose_answer_was_lost_is_not_repeated(run, serve, tokens):
    google = FakeGoogle()
    server = serve(google)
    server.outages = [None, "lost"]
    run("ga4_property", args(server, tokens, "antwortweg.de"))
    assert len(google.properties) == 1


def test_rerun_after_a_lost_answer_finishes_the_property(run, serve, tokens):
    google = FakeGoogle()
    server = serve(google)
    server.outages = [None, "lost"]
    run("ga4_property", args(server, tokens, "antwortweg.de"))
    assert run("ga4_property", args(server, tokens, "antwortweg.de"))["measurement_id"].startswith("G-")


def test_property_accepted_but_not_listed_fails(run, serve, tokens):
    google = FakeGoogle()
    google.hides_new_properties = True
    assert "does not list it" in run("ga4_property", args(serve(google), tokens, "verschollen.de"))["msg"]


def test_account_without_the_role_fails_with_googles_reason(run, serve, tokens):
    result = run("ga4_property", args(serve(FakeGoogle()), tokens, "ohnerolle.de", account_id="999"))
    assert "does not have permission" in result["msg"]


def test_asks_with_the_analytics_scope(run, serve, tokens):
    run("ga4_property", args(serve(FakeGoogle()), tokens, "bereich.de"))
    assert tokens.issued == [ANALYTICS_SCOPE]


def test_unreadable_property_list_is_not_read_as_no_property(run, serve, tokens):
    server = serve(FakeGoogle())
    server.outages = ["html", "html", "html"]
    run("ga4_property", args(server, tokens, "portal.de"))
    assert server.writes() == []
