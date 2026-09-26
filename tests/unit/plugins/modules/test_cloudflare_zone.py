from fakes.cloudflare import PAIRS, FakeCloudflare


def args(server, domain, **extra):
    return dict(domain=domain, api_token="cf-token", api_url=server.url, **extra)


def test_finds_existing_zone_without_writing(run, serve):
    cloudflare = FakeCloudflare()
    cloudflare.add_zone("kiezfunk.de")
    server = serve(cloudflare)
    run("cloudflare_zone", args(server, "kiezfunk.de"))
    assert server.writes() == []


def test_existing_zone_reports_unchanged(run, serve):
    cloudflare = FakeCloudflare()
    cloudflare.add_zone("kiezfunk.de")
    assert run("cloudflare_zone", args(serve(cloudflare), "kiezfunk.de"))["changed"] is False


def test_creates_absent_zone(run, serve):
    cloudflare = FakeCloudflare()
    run("cloudflare_zone", args(serve(cloudflare), "neubau-radio.de"))
    assert [z["name"] for z in cloudflare.zones] == ["neubau-radio.de"]


def test_new_zone_returns_the_accounts_nameserver_pair(run, serve):
    result = run("cloudflare_zone", args(serve(FakeCloudflare()), "neubau-radio.de", account_id="acc-gudok"))
    assert result["name_servers"] == PAIRS["acc-gudok"]


def test_new_zone_is_created_in_the_given_account(run, serve):
    cloudflare = FakeCloudflare()
    run("cloudflare_zone", args(serve(cloudflare), "neubau-radio.de", account_id="acc-gudok"))
    assert cloudflare.zones[0]["account"]["id"] == "acc-gudok"


def test_second_run_after_creation_is_unchanged(run, serve):
    server = serve(FakeCloudflare())
    run("cloudflare_zone", args(server, "zweitlauf.de"))
    assert run("cloudflare_zone", args(server, "zweitlauf.de"))["changed"] is False


def test_check_mode_creates_nothing(run, serve):
    server = serve(FakeCloudflare())
    run("cloudflare_zone", args(server, "trockenlauf.de"), check=True)
    assert server.writes() == []


def test_check_mode_reports_the_zone_would_be_created(run, serve):
    result = run("cloudflare_zone", args(serve(FakeCloudflare()), "trockenlauf.de"), check=True)
    assert (result["changed"], result["exists"]) == (True, False)


def test_failed_lookup_stops_before_creating(run, serve):
    server = serve(FakeCloudflare())
    server.outages = [503, 503, 503]
    run("cloudflare_zone", args(server, "stoerung.de"))
    assert server.writes() == []


def test_failed_lookup_fails_the_module(run, serve):
    server = serve(FakeCloudflare())
    server.outages = ["drop", "drop", "drop"]
    assert run("cloudflare_zone", args(server, "stoerung.de"))["failed"] is True


def test_portal_page_instead_of_json_is_not_an_answer(run, serve):
    server = serve(FakeCloudflare())
    server.outages = ["html", "html", "html"]
    run("cloudflare_zone", args(server, "hotspot.de"))
    assert server.writes() == []


def test_one_outage_is_retried(run, serve):
    cloudflare = FakeCloudflare()
    server = serve(cloudflare)
    server.outages = [502]
    run("cloudflare_zone", args(server, "wackel.de"))
    assert [z["name"] for z in cloudflare.zones] == ["wackel.de"]


def test_wrong_token_is_not_retried(run, serve):
    server = serve(FakeCloudflare(token="real-token"))
    run("cloudflare_zone", args(server, "fremd.de"))
    assert len(server.requests) == 1


def test_wrong_token_fails_with_cloudflares_reason(run, serve):
    result = run("cloudflare_zone", args(serve(FakeCloudflare(token="real-token")), "fremd.de"))
    assert "Authentication error" in result["msg"]


def test_same_name_in_two_accounts_refuses_to_pick(run, serve):
    cloudflare = FakeCloudflare()
    cloudflare.add_zone("doppelt.de", account="acc-busel")
    cloudflare.add_zone("doppelt.de", account="acc-gudok")
    assert "set account_id" in run("cloudflare_zone", args(serve(cloudflare), "doppelt.de"))["msg"]


def test_account_narrows_the_lookup(run, serve):
    cloudflare = FakeCloudflare()
    cloudflare.add_zone("doppelt.de", account="acc-busel")
    gudok = cloudflare.add_zone("doppelt.de", account="acc-gudok")
    result = run("cloudflare_zone", args(serve(cloudflare), "doppelt.de", account_id="acc-gudok"))
    assert result["zone_id"] == gudok["id"]


def test_zone_accepted_but_not_listed_fails(run, serve):
    cloudflare = FakeCloudflare()
    cloudflare.hides_new_zones = True
    assert run("cloudflare_zone", args(serve(cloudflare), "verschwunden.de"))["failed"] is True
