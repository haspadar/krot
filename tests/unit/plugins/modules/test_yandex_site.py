from fakes.yandex import TOKEN, FakeYandex


def args(server, domain, **extra):
    return dict(domain=domain, oauth_token=TOKEN, api_url=server.url, **extra)


def test_adds_absent_host(run, serve):
    yandex = FakeYandex()
    run("yandex_site", args(serve(yandex), "neuland.de"))
    assert [h["host_id"] for h in yandex.hosts] == ["https:neuland.de:443"]


def test_returns_the_whole_line_as_the_txt_value(run, serve):
    yandex = FakeYandex()
    host = yandex.add_host("zeile.de")
    result = run("yandex_site", args(serve(yandex), "zeile.de"))
    expected = "yandex-verification: 5e1f%d" % sum(map(ord, host["host_id"]))
    assert result["verification_record"] == dict(type="TXT", name="zeile.de", content=expected)


def test_waits_for_the_token_yandex_mints_late(run, serve):
    yandex = FakeYandex()
    yandex.uin_delay = 3
    result = run("yandex_site", args(serve(yandex), "spaetmarke.de"))
    assert result["verification_record"]["content"].startswith("yandex-verification: 5e1f")


def test_token_that_never_comes_fails_asking_for_a_rerun(run, serve):
    yandex = FakeYandex()
    yandex.uin_delay = 100
    assert "run again" in run("yandex_site", args(serve(yandex), "niemals.de", wait_attempts=2))["msg"]


def test_host_added_over_http_is_not_added_again(run, serve):
    yandex = FakeYandex()
    yandex.add_host("altbau.de", scheme="http")
    server = serve(yandex)
    run("yandex_site", args(server, "altbau.de"))
    assert server.writes() == []


def test_host_known_only_by_its_unicode_address_is_found(run, serve):
    yandex = FakeYandex()
    yandex.add_host("xn--mnchen-3ya.de", unicode_only=True)
    server = serve(yandex)
    run("yandex_site", args(server, "xn--mnchen-3ya.de"))
    assert server.writes() == []


def test_user_id_sent_as_text_is_the_same_account(run, serve):
    yandex = FakeYandex()
    yandex.user_as_text = True
    yandex.add_host("textnummer.de")
    assert run("yandex_site", args(serve(yandex), "textnummer.de"))["added"] is True


def test_unreadable_host_list_is_not_read_as_no_host(run, serve):
    server = serve(FakeYandex())
    server.outages = [None, 503, 503, 503]
    run("yandex_site", args(server, "stummliste.de"))
    assert server.writes() == []


def test_add_whose_answer_was_lost_is_not_repeated(run, serve):
    yandex = FakeYandex()
    server = serve(yandex)
    server.outages = [None, None, "lost"]
    run("yandex_site", args(server, "einmalhost.de"))
    assert len(yandex.hosts) == 1


def test_verifies_once_the_check_completes(run, serve):
    yandex = FakeYandex()
    yandex.add_host("pruefung.de")
    yandex.progress_reads = 2
    assert run("yandex_site", args(serve(yandex), "pruefung.de", verify=True))["verified"] is True


def test_starts_the_check_as_dns(run, serve):
    yandex = FakeYandex()
    yandex.add_host("dnsweg.de")
    server = serve(yandex)
    run("yandex_site", args(server, "dnsweg.de", verify=True))
    assert [r.query for r in server.writes()] == [{"verification_type": "DNS"}]


def test_check_already_running_is_not_started_again(run, serve):
    yandex = FakeYandex()
    host = yandex.add_host("laeuftschon.de")
    yandex.states[host["host_id"]] = "IN_PROGRESS"
    # Still in progress when the module first looks, so the branch is reached.
    yandex.progress_reads = 2
    server = serve(yandex)
    run("yandex_site", args(server, "laeuftschon.de", verify=True))
    assert server.writes() == []


def test_failed_verification_fails_asking_for_dns(run, serve):
    yandex = FakeYandex()
    yandex.add_host("ohnetxt.de")
    yandex.fails_verification = True
    assert "once DNS has the TXT" in run("yandex_site", args(serve(yandex), "ohnetxt.de", verify=True))["msg"]


def test_verified_host_is_not_verified_again(run, serve):
    yandex = FakeYandex()
    yandex.add_host("bestaetigt.ru", verified=True)
    server = serve(yandex)
    run("yandex_site", args(server, "bestaetigt.ru", verify=True))
    assert server.writes() == []


def test_sitemap_goes_to_user_added_sitemaps(run, serve):
    yandex = FakeYandex()
    host = yandex.add_host("kartenweg.de", verified=True)
    run("yandex_site", args(serve(yandex), "kartenweg.de", sitemap_url="https://kartenweg.de/sitemap-q4.xml"))
    assert yandex.sitemaps[host["host_id"]] == ["https://kartenweg.de/sitemap-q4.xml"]


def test_listed_sitemap_is_not_submitted_again(run, serve):
    yandex = FakeYandex()
    host = yandex.add_host("gelistet.de", verified=True)
    yandex.sitemaps[host["host_id"]] = ["https://gelistet.de/sitemap.xml"]
    server = serve(yandex)
    result = run("yandex_site", args(server, "gelistet.de", sitemap_url="https://gelistet.de/sitemap.xml"))
    assert (result["changed"], server.writes()) == (False, [])


def test_sitemap_already_added_counts_as_success(run, serve):
    yandex = FakeYandex()
    yandex.add_host("schonkarte.de", verified=True)
    yandex.hidden_sitemaps = ["https://schonkarte.de/sitemap.xml"]
    result = run("yandex_site", args(serve(yandex), "schonkarte.de", sitemap_url="https://schonkarte.de/sitemap.xml"))
    assert result["sitemap_submitted"] is True


def test_host_not_loaded_is_not_a_failure(run, serve):
    yandex = FakeYandex()
    yandex.add_host("ungeladen.de", verified=True)
    yandex.not_loaded = True
    result = run("yandex_site", args(serve(yandex), "ungeladen.de", sitemap_url="https://ungeladen.de/sitemap.xml"))
    assert (result.get("failed", False), result["sitemap_submitted"]) == (False, False)


def test_host_not_loaded_warns(run, serve):
    yandex = FakeYandex()
    yandex.add_host("ungeladen.de", verified=True)
    yandex.not_loaded = True
    result = run("yandex_site", args(serve(yandex), "ungeladen.de", sitemap_url="https://ungeladen.de/sitemap.xml"))
    # A string in older ansible-core, a dict with the message inside in newer.
    assert "HOST_NOT_LOADED" in str(result["warnings"])


def test_sitemap_on_an_unverified_host_is_refused_before_submitting(run, serve):
    yandex = FakeYandex()
    yandex.add_host("unbestaetigt.de")
    server = serve(yandex)
    run("yandex_site", args(server, "unbestaetigt.de", sitemap_url="https://unbestaetigt.de/sitemap.xml"))
    assert server.writes() == []


def test_wrong_token_is_not_retried(run, serve):
    server = serve(FakeYandex("another-account"))
    run("yandex_site", args(server, "fremdkonto.de"))
    assert len(server.requests) == 1


def test_check_mode_writes_nothing(run, serve):
    server = serve(FakeYandex())
    run("yandex_site", args(server, "trocken.de", verify=True, sitemap_url="https://trocken.de/s.xml"), check=True)
    assert server.writes() == []


def test_full_run_twice_is_unchanged_the_second_time(run, serve):
    yandex = FakeYandex()
    yandex.add_host("vollstaendig.de")
    server = serve(yandex)
    full = args(server, "vollstaendig.de", verify=True, sitemap_url="https://vollstaendig.de/sitemap.xml")
    run("yandex_site", full)
    assert run("yandex_site", full)["changed"] is False


def test_token_does_not_leak_into_the_failure_message(run, serve):
    server = serve(FakeYandex())
    server.outages = ["drop", "drop", "drop"]
    assert TOKEN not in run("yandex_site", args(server, "geheimnis.de"))["msg"]


def test_host_list_without_hosts_is_not_read_as_no_host(run, serve):
    yandex = FakeYandex()
    yandex.host_list_broken = True
    server = serve(yandex)
    run("yandex_site", args(server, "leerfeld.de"))
    assert server.writes() == []
