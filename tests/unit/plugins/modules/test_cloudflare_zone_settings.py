from fakes.cloudflare import FakeCloudflare


def zone(cloudflare, name, **settings):
    found = cloudflare.add_zone(name)
    cloudflare.settings[found["id"]].update(settings)
    return found["id"]


def args(server, zone_id, **extra):
    return dict(zone_id=zone_id, api_token="cf-token", api_url=server.url, **extra)


def test_defaults_reach_the_zone(run, serve):
    cloudflare = FakeCloudflare()
    zone_id = zone(cloudflare, "frischezone.de")
    run("cloudflare_zone_settings", args(serve(cloudflare), zone_id))
    kept = cloudflare.settings[zone_id]
    assert (kept["ssl"], kept["always_use_https"], kept["browser_cache_ttl"]) == ("strict", "on", 0)


def test_cache_ttl_is_sent_as_a_number(run, serve):
    cloudflare = FakeCloudflare()
    zone_id = zone(cloudflare, "cachezahl.de")
    server = serve(cloudflare)
    run("cloudflare_zone_settings", args(server, zone_id))
    sent = [r.body["value"] for r in server.writes() if r.path.endswith("/browser_cache_ttl")]
    assert sent == [0]


def test_numeric_setting_already_right_is_not_rewritten(run, serve):
    cloudflare = FakeCloudflare()
    zone_id = zone(cloudflare, "stimmtschon.de", ssl="strict", always_use_https="on", browser_cache_ttl=0)
    server = serve(cloudflare)
    run("cloudflare_zone_settings", args(server, zone_id))
    assert server.writes() == []


def test_only_differing_settings_are_written(run, serve):
    cloudflare = FakeCloudflare()
    zone_id = zone(cloudflare, "halbfertig.de", ssl="strict", browser_cache_ttl=0)
    assert run("cloudflare_zone_settings", args(serve(cloudflare), zone_id))["changed_settings"] == ["always_use_https"]


def test_second_run_is_unchanged(run, serve):
    cloudflare = FakeCloudflare()
    zone_id = zone(cloudflare, "zweimal.de")
    server = serve(cloudflare)
    run("cloudflare_zone_settings", args(server, zone_id))
    assert run("cloudflare_zone_settings", args(server, zone_id))["changed"] is False


def test_check_mode_writes_nothing(run, serve):
    cloudflare = FakeCloudflare()
    zone_id = zone(cloudflare, "nurlesen.de")
    server = serve(cloudflare)
    run("cloudflare_zone_settings", args(server, zone_id), check=True)
    assert server.writes() == []


def test_setting_accepted_but_not_kept_fails(run, serve):
    cloudflare = FakeCloudflare()
    cloudflare.forgets_settings = True
    zone_id = zone(cloudflare, "vergesslich.de")
    assert "did not keep" in run("cloudflare_zone_settings", args(serve(cloudflare), zone_id))["msg"]


def test_origin_pulls_refused_before_the_certificate(run, serve):
    cloudflare = FakeCloudflare()
    zone_id = zone(cloudflare, "ohnezert.de")
    server = serve(cloudflare)
    run("cloudflare_zone_settings", args(server, zone_id, settings={"tls_client_auth": "on"}))
    assert server.requests == []


def test_origin_pulls_allowed_once_the_certificate_is_in(run, serve):
    cloudflare = FakeCloudflare()
    zone_id = zone(cloudflare, "mitzert.de")
    run("cloudflare_zone_settings", args(serve(cloudflare), zone_id, settings={"tls_client_auth": "on"},
                                         origin_certificate_installed=True))
    assert cloudflare.settings[zone_id]["tls_client_auth"] == "on"


def test_unknown_zone_fails_with_cloudflares_reason(run, serve):
    result = run("cloudflare_zone_settings", args(serve(FakeCloudflare()), "zone-missing"))
    assert "Invalid zone identifier" in result["msg"]
