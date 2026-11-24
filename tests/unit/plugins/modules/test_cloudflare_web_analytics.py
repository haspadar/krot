from fakes.cloudflare import DEFAULT_ACCOUNT, TOKEN, FakeCloudflare

ACCOUNT = DEFAULT_ACCOUNT


def args(server, zone_id=None, **extra):
    found = dict(api_token=TOKEN, api_url=server.url, **extra)
    if zone_id:
        found["zone_id"] = zone_id
    return found


def entry_of(cloudflare, zone_id):
    return next(e for e in cloudflare.rum if e["ruleset"]["zone_tag"] == zone_id)


def test_lite_record_of_a_new_zone_is_brought_to_the_full_one(run, serve):
    cloudflare = FakeCloudflare()
    zone = cloudflare.add_zone("frischzone.de")
    run("cloudflare_web_analytics", args(serve(cloudflare), zone["id"]))
    assert entry_of(cloudflare, zone["id"]) == {
        "site_tag": entry_of(cloudflare, zone["id"])["site_tag"], "auto_install": True,
        "ruleset": {"zone_tag": zone["id"], "zone_name": "frischzone.de", "enabled": True, "lite": False}}


def test_the_change_names_what_differed(run, serve):
    cloudflare = FakeCloudflare()
    zone = cloudflare.add_zone("nurlite.de")
    assert run("cloudflare_web_analytics", args(serve(cloudflare), zone["id"]))["changed_fields"] == ["lite"]


def test_a_zone_without_a_record_gets_one_made_full(run, serve):
    cloudflare = FakeCloudflare()
    cloudflare.rum_on_new_zone = False
    zone = cloudflare.add_zone("ohnezaehler.de")
    result = run("cloudflare_web_analytics", args(serve(cloudflare), zone["id"]))
    assert (result["changed_fields"], entry_of(cloudflare, zone["id"])["ruleset"]["lite"]) == (["created", "lite"], False)


def test_a_record_made_with_automatic_installation_off_is_switched_on(run, serve):
    cloudflare = FakeCloudflare()
    cloudflare.rum_on_new_zone = False
    cloudflare.rum_creates_lite = False
    zone = cloudflare.add_zone("handarbeit.de")
    cloudflare.add_rum(zone, auto_install=False, enabled=False)
    run("cloudflare_web_analytics", args(serve(cloudflare), zone["id"]))
    held = entry_of(cloudflare, zone["id"])
    assert (held["auto_install"], held["ruleset"]["enabled"]) == (True, True)


def test_a_record_that_is_already_right_is_not_written(run, serve):
    cloudflare = FakeCloudflare()
    cloudflare.rum_creates_lite = False
    zone = cloudflare.add_zone("stimmtschon.de")
    server = serve(cloudflare)
    run("cloudflare_web_analytics", args(server, zone["id"]))
    assert server.writes() == []


def test_second_run_is_unchanged(run, serve):
    cloudflare = FakeCloudflare()
    zone = cloudflare.add_zone("zweimal.de")
    server = serve(cloudflare)
    run("cloudflare_web_analytics", args(server, zone["id"]))
    assert run("cloudflare_web_analytics", args(server, zone["id"]))["changed"] is False


def test_check_mode_writes_nothing_and_reports_the_change(run, serve):
    cloudflare = FakeCloudflare()
    zone = cloudflare.add_zone("nurlesen.de")
    server = serve(cloudflare)
    result = run("cloudflare_web_analytics", args(server, zone["id"]), check=True)
    assert (server.writes(), result["changed"]) == ([], True)


def test_check_mode_on_a_zone_without_a_record_writes_nothing(run, serve):
    cloudflare = FakeCloudflare()
    cloudflare.rum_on_new_zone = False
    zone = cloudflare.add_zone("spaeter.de")
    server = serve(cloudflare)
    result = run("cloudflare_web_analytics", args(server, zone["id"]), check=True)
    assert (server.writes(), result["changed_fields"]) == ([], ["created"])


def test_the_record_is_found_by_its_zone_not_by_its_name(run, serve):
    cloudflare = FakeCloudflare()
    cloudflare.rum_creates_lite = False
    other = cloudflare.add_zone("andere.de")
    zone = cloudflare.add_zone("meine.de")
    entry_of(cloudflare, other["id"])["ruleset"]["lite"] = True
    run("cloudflare_web_analytics", args(serve(cloudflare), zone["id"]))
    assert entry_of(cloudflare, other["id"])["ruleset"]["lite"] is True


def test_every_page_of_the_list_is_read(run, serve):
    cloudflare = FakeCloudflare()
    for number in range(7):
        cloudflare.add_zone("zone%d.de" % number)
    target = cloudflare.add_zone("hintenstehend.de")
    cloudflare.rum_page_cap = 3
    run("cloudflare_web_analytics", args(serve(cloudflare), target["id"]))
    assert entry_of(cloudflare, target["id"])["ruleset"]["lite"] is False


def test_pages_are_walked_to_the_empty_one_when_cloudflare_does_not_count_them(run, serve):
    cloudflare = FakeCloudflare()
    for number in range(7):
        cloudflare.add_zone("zone%d.de" % number)
    target = cloudflare.add_zone("ohnezahl.de")
    cloudflare.rum_page_cap = 3
    cloudflare.rum_counts_pages = False
    run("cloudflare_web_analytics", args(serve(cloudflare), target["id"]))
    assert entry_of(cloudflare, target["id"])["ruleset"]["lite"] is False


def test_account_comes_from_the_zone_when_it_is_not_given(run, serve):
    cloudflare = FakeCloudflare()
    zone = cloudflare.add_zone("kontoaus.de")
    server = serve(cloudflare)
    run("cloudflare_web_analytics", args(server, zone["id"]))
    assert "/accounts/%s/rum/site_info/list" % ACCOUNT in [r.path for r in server.requests]


def test_account_given_is_used_without_asking_the_zone(run, serve):
    cloudflare = FakeCloudflare()
    zone = cloudflare.add_zone("kontoda.de")
    server = serve(cloudflare)
    run("cloudflare_web_analytics", args(server, zone["id"], account_id="acc-given"))
    assert "/zones/%s" % zone["id"] not in [r.path for r in server.requests]


def test_record_accepted_but_not_kept_fails(run, serve):
    cloudflare = FakeCloudflare()
    cloudflare.forgets_rum = True
    zone = cloudflare.add_zone("vergesslich.de")
    assert "did not keep: lite" in run("cloudflare_web_analytics", args(serve(cloudflare), zone["id"]))["msg"]


def test_creation_accepted_but_not_listed_fails(run, serve):
    cloudflare = FakeCloudflare()
    cloudflare.rum_on_new_zone = False
    cloudflare.forgets_rum = True
    zone = cloudflare.add_zone("verschwunden.de")
    assert "does not list it" in run("cloudflare_web_analytics", args(serve(cloudflare), zone["id"]))["msg"]


def test_two_records_for_one_zone_are_not_guessed_between(run, serve):
    cloudflare = FakeCloudflare()
    zone = cloudflare.add_zone("doppelt.de")
    cloudflare.add_rum(zone)
    server = serve(cloudflare)
    result = run("cloudflare_web_analytics", args(server, zone["id"]))
    assert ("2 Web Analytics records" in result["msg"], server.writes()) == (True, [])


def test_a_token_without_the_right_is_told_what_it_lacks(run, serve):
    cloudflare = FakeCloudflare()
    cloudflare.rum_forbidden = True
    zone = cloudflare.add_zone("verboten.de")
    assert "Account Settings Read and Write" in run("cloudflare_web_analytics", args(serve(cloudflare), zone["id"]))["msg"]


def test_a_wrong_token_is_refused_and_nothing_is_written(run, serve):
    cloudflare = FakeCloudflare()
    zone = cloudflare.add_zone("falschertoken.de")
    server = serve(cloudflare)
    run("cloudflare_web_analytics", dict(args(server, zone["id"]), api_token="other"))
    assert server.writes() == []


def test_without_a_zone_the_account_is_only_read(run, serve):
    cloudflare = FakeCloudflare()
    server = serve(cloudflare)
    result = run("cloudflare_web_analytics", args(server, account_id=ACCOUNT))
    assert (result["changed"], server.writes()) == (False, [])


def test_without_a_zone_a_token_that_may_not_read_is_found_out(run, serve):
    cloudflare = FakeCloudflare()
    cloudflare.rum_forbidden = True
    assert "Account Settings Read" in run("cloudflare_web_analytics", args(serve(cloudflare), account_id=ACCOUNT))["msg"]


def test_neither_zone_nor_account_is_refused_before_any_request(run, serve):
    server = serve(FakeCloudflare())
    run("cloudflare_web_analytics", args(server))
    assert server.requests == []


def test_unknown_zone_fails_with_cloudflares_reason(run, serve):
    result = run("cloudflare_web_analytics", args(serve(FakeCloudflare()), "zone-missing"))
    assert "Invalid zone identifier" in result["msg"]
