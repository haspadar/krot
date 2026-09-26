from fakes.bing import FakeBing


def args(server, domain, **extra):
    return dict(domain=domain, api_key="bing-key", api_url=server.url, **extra)


def test_adds_absent_site(run, serve):
    bing = FakeBing()
    run("bing_site", args(serve(bing), "neuanmeldung.de"))
    assert [s["Url"] for s in bing.sites] == ["https://neuanmeldung.de/"]


def test_returns_the_code_as_the_cname_name_without_appending_the_domain(run, serve):
    result = run("bing_site", args(serve(FakeBing()), "cname.de"))
    assert result["verification_record"] == dict(type="CNAME", name="a1b2c3.cname.de", content="verify.bing.com")


def test_waits_for_the_code_bing_publishes_late(run, serve):
    bing = FakeBing()
    bing.code_delay = 3
    result = run("bing_site", args(serve(bing), "spaetcode.de"))
    assert result["verification_record"]["name"] == "a1b2c3.spaetcode.de"


def test_code_that_never_comes_fails_asking_for_a_rerun(run, serve):
    bing = FakeBing()
    bing.code_delay = 100
    assert "run again" in run("bing_site", args(serve(bing), "nie.de", wait_attempts=2))["msg"]


def test_existing_site_is_not_added_again(run, serve):
    bing = FakeBing()
    bing.add_site("schonda.de")
    server = serve(bing)
    run("bing_site", args(server, "schonda.de"))
    assert server.writes() == []


def test_unreadable_site_list_is_not_read_as_no_site(run, serve):
    server = serve(FakeBing())
    server.outages = [500, 500, 500]
    run("bing_site", args(server, "keineantwort.de"))
    assert server.writes() == []


def test_verifies_once_the_cname_is_visible(run, serve):
    bing = FakeBing()
    bing.add_site("pruefen.de")
    bing.verify_after = 2
    assert run("bing_site", args(serve(bing), "pruefen.de", verify=True))["verified"] is True


def test_verification_that_never_comes_fails(run, serve):
    bing = FakeBing()
    bing.add_site("ohnecname.de")
    bing.verify_after = 100
    assert "does not see the CNAME" in run("bing_site", args(serve(bing), "ohnecname.de", verify=True, wait_attempts=3))["msg"]


def test_verified_site_is_not_verified_again(run, serve):
    bing = FakeBing()
    bing.add_site("bestaetigt.de", verified=True)
    server = serve(bing)
    run("bing_site", args(server, "bestaetigt.de", verify=True))
    assert server.writes() == []


def test_sitemap_refused_right_after_verification_is_retried(run, serve):
    bing = FakeBing()
    bing.add_site("karte.de", verified=True)
    bing.feed_refusals = 2
    run("bing_site", args(serve(bing), "karte.de", sitemap_url="https://karte.de/sitemap-x7.xml"))
    assert bing.feeds["https://karte.de/"] == ["https://karte.de/sitemap-x7.xml"]


def test_submitted_sitemap_is_not_submitted_again(run, serve):
    bing = FakeBing()
    bing.add_site("eingereicht.de", verified=True)
    bing.feeds["https://eingereicht.de/"] = ["https://eingereicht.de/sitemap.xml"]
    server = serve(bing)
    result = run("bing_site", args(server, "eingereicht.de", sitemap_url="https://eingereicht.de/sitemap.xml"))
    assert (result["changed"], server.writes()) == (False, [])


def test_sitemap_on_an_unverified_site_is_refused_before_submitting(run, serve):
    bing = FakeBing()
    bing.add_site("unbestaetigt.de")
    server = serve(bing)
    run("bing_site", args(server, "unbestaetigt.de", sitemap_url="https://unbestaetigt.de/sitemap.xml"))
    assert server.writes() == []


def test_throttled_account_is_not_waited_for(run, serve):
    bing = FakeBing()
    bing.throttled = True
    server = serve(bing)
    run("bing_site", args(server, "gedrosselt.de"))
    assert len(server.requests) == 1


def test_throttled_account_says_it_lasts_hours(run, serve):
    bing = FakeBing()
    bing.throttled = True
    assert "hours" in run("bing_site", args(serve(bing), "gedrosselt.de"))["msg"]


def test_check_mode_adds_nothing(run, serve):
    server = serve(FakeBing())
    run("bing_site", args(server, "nurschauen.de", verify=True, sitemap_url="https://nurschauen.de/s.xml"), check=True)
    assert server.writes() == []


def test_full_run_twice_is_unchanged_the_second_time(run, serve):
    bing = FakeBing()
    bing.add_site("komplett.de")
    server = serve(bing)
    full = args(server, "komplett.de", verify=True, sitemap_url="https://komplett.de/sitemap.xml")
    run("bing_site", full)
    assert run("bing_site", full)["changed"] is False


def test_key_does_not_leak_into_the_failure_message(run, serve):
    server = serve(FakeBing())
    server.outages = ["drop", "drop", "drop"]
    assert "bing-key" not in run("bing_site", args(server, "geheim.de"))["msg"]


def test_site_list_that_is_not_a_list_is_not_read_as_no_site(run, serve):
    bing = FakeBing()
    bing.site_list_broken = True
    server = serve(bing)
    run("bing_site", args(server, "leereliste.de"))
    assert server.writes() == []
