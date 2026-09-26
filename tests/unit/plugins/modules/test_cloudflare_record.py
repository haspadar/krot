from fakes.cloudflare import TOKEN, FakeCloudflare

ORIGIN = "203.0.113.7"


def zone(cloudflare, name):
    return cloudflare.add_zone(name)["id"]


def args(server, zone_id, kind, name, content, **extra):
    return dict(zone_id=zone_id, type=kind, name=name, content=content, api_token=TOKEN, api_url=server.url, **extra)


def test_creates_a_proxied_address(run, serve):
    cloudflare = FakeCloudflare()
    zone_id = zone(cloudflare, "adresse.de")
    run("cloudflare_record", args(serve(cloudflare), zone_id, "A", "adresse.de", ORIGIN))
    assert [(r["content"], r["proxied"]) for r in cloudflare.zone_records(zone_id)] == [(ORIGIN, True)]


def test_address_already_right_is_left_alone(run, serve):
    cloudflare = FakeCloudflare()
    zone_id = zone(cloudflare, "stimmt.de")
    cloudflare.add_record(zone_id, "A", "stimmt.de", ORIGIN, proxied=True)
    server = serve(cloudflare)
    run("cloudflare_record", args(server, zone_id, "A", "stimmt.de", ORIGIN))
    assert server.writes() == []


def test_address_pointing_elsewhere_is_updated_in_place(run, serve):
    cloudflare = FakeCloudflare()
    zone_id = zone(cloudflare, "umzug.de")
    held = cloudflare.add_record(zone_id, "A", "umzug.de", "198.51.100.4", proxied=True)
    run("cloudflare_record", args(serve(cloudflare), zone_id, "A", "umzug.de", ORIGIN))
    assert (len(cloudflare.zone_records(zone_id)), held["content"]) == (1, ORIGIN)


def test_unproxied_address_is_turned_proxied(run, serve):
    cloudflare = FakeCloudflare()
    zone_id = zone(cloudflare, "offen.de")
    held = cloudflare.add_record(zone_id, "A", "offen.de", ORIGIN, proxied=False)
    run("cloudflare_record", args(serve(cloudflare), zone_id, "A", "offen.de", ORIGIN))
    assert held["proxied"] is True


def test_unproxied_address_is_refused_before_any_request(run, serve):
    server = serve(FakeCloudflare())
    run("cloudflare_record", args(server, "zone-x", "A", "nackt.de", ORIGIN, proxied=False))
    assert server.requests == []


def test_address_is_matched_by_type_not_name_alone(run, serve):
    cloudflare = FakeCloudflare()
    zone_id = zone(cloudflare, "gemischt.de")
    proof = cloudflare.add_record(zone_id, "TXT", "gemischt.de", "google-site-verification=abc")
    run("cloudflare_record", args(serve(cloudflare), zone_id, "A", "gemischt.de", ORIGIN))
    assert proof["content"] == "google-site-verification=abc"


def test_two_addresses_under_one_name_are_not_guessed_between(run, serve):
    cloudflare = FakeCloudflare()
    zone_id = zone(cloudflare, "doppelt.de")
    cloudflare.add_record(zone_id, "A", "doppelt.de", ORIGIN, proxied=True)
    cloudflare.add_record(zone_id, "A", "doppelt.de", "198.51.100.4", proxied=True)
    assert "refusing to guess" in run("cloudflare_record", args(serve(cloudflare), zone_id, "A", "doppelt.de", ORIGIN))["msg"]


def test_proof_is_added_beside_another_engines(run, serve):
    cloudflare = FakeCloudflare()
    zone_id = zone(cloudflare, "beweis.de")
    cloudflare.add_record(zone_id, "TXT", "beweis.de", "google-site-verification=abc")
    run("cloudflare_record", args(serve(cloudflare), zone_id, "TXT", "beweis.de", "yandex-verification: 0f1e"))
    assert len(cloudflare.zone_records(zone_id)) == 2


def test_quoted_proof_from_the_dashboard_counts_as_present(run, serve):
    cloudflare = FakeCloudflare()
    zone_id = zone(cloudflare, "zitat.de")
    cloudflare.add_record(zone_id, "TXT", "zitat.de", '"yandex-verification: 0f1e"')
    server = serve(cloudflare)
    run("cloudflare_record", args(server, zone_id, "TXT", "zitat.de", "yandex-verification: 0f1e"))
    assert server.writes() == []


def test_second_run_is_unchanged(run, serve):
    cloudflare = FakeCloudflare()
    zone_id = zone(cloudflare, "zweimal.de")
    server = serve(cloudflare)
    run("cloudflare_record", args(server, zone_id, "CNAME", "a1b2.zweimal.de", "verify.bing.com"))
    assert run("cloudflare_record", args(server, zone_id, "CNAME", "a1b2.zweimal.de", "verify.bing.com"))["changed"] is False


def test_check_mode_writes_nothing(run, serve):
    cloudflare = FakeCloudflare()
    zone_id = zone(cloudflare, "probe.de")
    server = serve(cloudflare)
    run("cloudflare_record", args(server, zone_id, "A", "probe.de", ORIGIN), check=True)
    assert server.writes() == []


def test_record_accepted_but_not_held_fails(run, serve):
    cloudflare = FakeCloudflare()
    cloudflare.forgets_records = True
    zone_id = zone(cloudflare, "vergessen.de")
    assert "does not hold" in run("cloudflare_record", args(serve(cloudflare), zone_id, "A", "vergessen.de", ORIGIN))["msg"]


def test_unreadable_record_list_writes_nothing(run, serve):
    cloudflare = FakeCloudflare()
    zone_id = zone(cloudflare, "stoerung.de")
    server = serve(cloudflare)
    server.outages = ["html", "html", "html"]
    run("cloudflare_record", args(server, zone_id, "A", "stoerung.de", ORIGIN))
    assert server.writes() == []
