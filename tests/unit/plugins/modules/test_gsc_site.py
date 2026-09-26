import pytest

from fakes.google import CONSOLE_SCOPE, EMAIL, VERIFY_SCOPE, FakeGoogle, FakeTokens, service_account

OPERATOR = "betreiber@example.de"


@pytest.fixture
def tokens():
    served = FakeTokens()
    yield served
    served.close()


def args(server, tokens, domain, **extra):
    return dict(domain=domain, service_account=service_account(tokens.uri), token_uri=tokens.uri,
                api_url=server.url, **extra)


def test_returns_the_txt_record_on_the_domain_itself(run, serve, tokens):
    result = run("gsc_site", args(serve(FakeGoogle()), tokens, "texteintrag.de"))
    assert result["verification_record"] == dict(type="TXT", name="texteintrag.de",
                                                 content="google-site-verification=v-texteintrag")


def test_learning_the_record_writes_nothing(run, serve, tokens):
    server = serve(FakeGoogle())
    run("gsc_site", args(server, tokens, "nurlernen.de"))
    assert [r.path for r in server.writes()] == ["/siteVerification/v1/token"]


def test_verifies_once_google_sees_the_record(run, serve, tokens):
    google = FakeGoogle()
    google.dns_visible_after = 2
    run("gsc_site", args(serve(google), tokens, "sichtbar.de", verify=True))
    assert google.resources["dns://sichtbar.de"] == [EMAIL]


def test_waits_between_attempts_while_google_answers_400(run, serve, tokens, pauses):
    google = FakeGoogle()
    google.dns_visible_after = 2
    run("gsc_site", args(serve(google), tokens, "geduld.de", verify=True, wait_delay=20))
    assert pauses == [20, 20]


def test_record_never_seen_fails_asking_for_a_rerun(run, serve, tokens):
    google = FakeGoogle()
    google.dns_visible_after = 100
    result = run("gsc_site", args(serve(google), tokens, "unsichtbar.de", verify=True, wait_attempts=3))
    assert "run again" in result["msg"]


def test_disabled_api_is_not_waited_for(run, serve, tokens):
    google = FakeGoogle()
    google.disabled_scopes = {VERIFY_SCOPE}
    server = serve(google)
    run("gsc_site", args(server, tokens, "abgeschaltet.de", verify=True))
    assert len(server.requests) == 1


def test_disabled_api_fails_with_googles_reason(run, serve, tokens):
    google = FakeGoogle()
    google.disabled_scopes = {VERIFY_SCOPE}
    result = run("gsc_site", args(serve(google), tokens, "abgeschaltet.de", verify=True))
    assert "not been used in project" in result["msg"]


def test_verification_adds_the_domain_property(run, serve, tokens):
    google = FakeGoogle()
    run("gsc_site", args(serve(google), tokens, "eigentum.de", verify=True))
    assert google.sites["sc-domain:eigentum.de"] == "siteOwner"


def test_waits_for_ownership_to_show(run, serve, tokens):
    google = FakeGoogle()
    google.verified("verzoegert.de", owned=False)
    google.permission_lag = 2
    assert run("gsc_site", args(serve(google), tokens, "verzoegert.de", verify=True))["verified"] is True


def test_ownership_that_never_shows_fails(run, serve, tokens):
    google = FakeGoogle()
    google.verified("nurgast.de", owned=False)
    google.permission_lag = 100
    result = run("gsc_site", args(serve(google), tokens, "nurgast.de", verify=True, owner_attempts=2))
    assert "not as owned" in result["msg"]


def test_property_verified_by_someone_else_is_verified_by_this_account(run, serve, tokens):
    google = FakeGoogle()
    google.sites["sc-domain:fremdbestaetigt.de"] = "siteFullUser"
    run("gsc_site", args(serve(google), tokens, "fremdbestaetigt.de", verify=True))
    assert google.sites["sc-domain:fremdbestaetigt.de"] == "siteOwner"


def test_verified_domain_is_not_verified_again(run, serve, tokens):
    google = FakeGoogle()
    google.verified("bestaetigt.de")
    server = serve(google)
    run("gsc_site", args(server, tokens, "bestaetigt.de", verify=True))
    assert [r.path for r in server.writes()] == ["/siteVerification/v1/token"]


def test_operator_is_added_beside_the_service_account(run, serve, tokens):
    google = FakeGoogle()
    google.verified("geteilt.de")
    run("gsc_site", args(serve(google), tokens, "geteilt.de", owners=[OPERATOR]))
    assert google.resources["dns://geteilt.de"] == [EMAIL, OPERATOR]


def test_owners_already_there_are_not_written(run, serve, tokens):
    google = FakeGoogle()
    google.verified("schongeteilt.de", owners=[EMAIL, OPERATOR])
    server = serve(google)
    run("gsc_site", args(server, tokens, "schongeteilt.de", owners=[OPERATOR]))
    assert [r.method for r in server.writes()] == ["POST"]


def test_empty_owner_list_is_not_written_back(run, serve, tokens):
    google = FakeGoogle()
    google.verified("leereliste.de")
    google.owners_broken = True
    server = serve(google)
    run("gsc_site", args(server, tokens, "leereliste.de", owners=[OPERATOR]))
    assert [r.method for r in server.writes()] == ["POST"]


def test_owners_accepted_but_not_kept_fail(run, serve, tokens):
    google = FakeGoogle()
    google.verified("vergessen.de")
    google.forgets_owners = True
    result = run("gsc_site", args(serve(google), tokens, "vergessen.de", owners=[OPERATOR]))
    assert "does not list them" in result["msg"]


def test_sharing_an_unverified_domain_is_refused(run, serve, tokens):
    result = run("gsc_site", args(serve(FakeGoogle()), tokens, "unbewiesen.de", owners=[OPERATOR]))
    assert "verify unbewiesen.de first" in result["msg"]


def test_new_sitemap_is_submitted(run, serve, tokens):
    google = FakeGoogle()
    google.verified("karte.de")
    run("gsc_site", args(serve(google), tokens, "karte.de", sitemap_url="https://karte.de/sitemap-x7.xml"))
    assert google.sitemaps["sc-domain:karte.de"] == ["https://karte.de/sitemap-x7.xml"]


def test_new_sitemap_is_a_change(run, serve, tokens):
    google = FakeGoogle()
    google.verified("neukarte.de")
    result = run("gsc_site", args(serve(google), tokens, "neukarte.de", sitemap_url="https://neukarte.de/s.xml"))
    assert result["changed"] is True


def test_listed_sitemap_is_submitted_again(run, serve, tokens):
    google = FakeGoogle()
    google.verified("nochmal.de")
    google.sitemaps["sc-domain:nochmal.de"] = ["https://nochmal.de/s.xml"]
    run("gsc_site", args(serve(google), tokens, "nochmal.de", sitemap_url="https://nochmal.de/s.xml"))
    assert google.submissions == ["https://nochmal.de/s.xml"]


def test_listed_sitemap_submitted_again_is_not_a_change(run, serve, tokens):
    google = FakeGoogle()
    google.verified("unveraendert.de")
    google.sitemaps["sc-domain:unveraendert.de"] = ["https://unveraendert.de/s.xml"]
    result = run("gsc_site", args(serve(google), tokens, "unveraendert.de", sitemap_url="https://unveraendert.de/s.xml"))
    assert result["changed"] is False


def test_sitemap_of_an_unverified_domain_is_refused_before_submitting(run, serve, tokens):
    google = FakeGoogle()
    server = serve(google)
    run("gsc_site", args(server, tokens, "ohnebeweis.de", sitemap_url="https://ohnebeweis.de/s.xml"))
    assert google.submissions == []


def test_check_mode_writes_nothing(run, serve, tokens):
    server = serve(FakeGoogle())
    run("gsc_site", args(server, tokens, "probelauf.de", verify=True, owners=[OPERATOR],
                         sitemap_url="https://probelauf.de/s.xml"), check=True)
    assert [r.path for r in server.writes()] == ["/siteVerification/v1/token"]


def test_full_run_twice_is_unchanged_the_second_time(run, serve, tokens):
    server = serve(FakeGoogle())
    full = args(server, tokens, "komplett.de", verify=True, owners=[OPERATOR], sitemap_url="https://komplett.de/s.xml")
    run("gsc_site", full)
    assert run("gsc_site", full)["changed"] is False


def test_each_api_is_asked_with_its_own_scope(run, serve, tokens):
    google = FakeGoogle()
    google.verified("zweischluessel.de")
    run("gsc_site", args(serve(google), tokens, "zweischluessel.de", sitemap_url="https://zweischluessel.de/s.xml"))
    assert sorted(tokens.issued) == sorted([VERIFY_SCOPE, CONSOLE_SCOPE])


def test_refused_key_fails_with_googles_reason(run, serve, tokens):
    tokens.refuses = True
    assert "invalid_grant" in run("gsc_site", args(serve(FakeGoogle()), tokens, "widerrufen.de"))["msg"]


def test_malformed_key_fails_without_quoting_it(run, serve, tokens):
    result = run("gsc_site", dict(args(serve(FakeGoogle()), tokens, "kaputt.de"), service_account='{"geheim-9"'))
    assert "geheim-9" not in result["msg"]


def test_unreachable_google_fails(run, serve, tokens):
    server = serve(FakeGoogle())
    server.outages = ["drop"]
    assert run("gsc_site", args(server, tokens, "funkstille.de"))["failed"] is True


def test_refused_verification_is_not_retried(run, serve, tokens):
    google = FakeGoogle()
    google.verification_refused_with = 403
    server = serve(google)
    run("gsc_site", args(server, tokens, "verweigert.de", verify=True))
    assert [r.path for r in server.writes()] == ["/siteVerification/v1/token", "/siteVerification/v1/webResource"]


def test_refused_verification_fails_with_googles_reason(run, serve, tokens):
    google = FakeGoogle()
    google.verification_refused_with = 401
    result = run("gsc_site", args(serve(google), tokens, "verweigert.de", verify=True))
    assert "does not have permission" in result["msg"]


def test_owner_list_that_comes_back_empty_is_not_written_back(run, serve, tokens):
    google = FakeGoogle()
    google.verified("verschwunden.de")
    google.owners_vanish_after = 1
    server = serve(google)
    run("gsc_site", args(server, tokens, "verschwunden.de", owners=[OPERATOR]))
    assert [r.method for r in server.writes()] == ["POST"]


def test_resource_answering_403_reads_as_not_yet_verified(run, serve, tokens):
    google = FakeGoogle()
    google.unowned_status = 403
    assert run("gsc_site", args(serve(google), tokens, "dreinull.de", verify=True))["verified"] is True
