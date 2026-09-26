from fakes.cloudflare import OTHER_TOKEN, TOKEN
from fakes.cloudflare_rulesets import FakeCloudflareRulesets

PHASE = "http_request_cache_settings"

MEDIA = dict(
    ref="krot_cache_media",
    action="set_cache_settings",
    expression='(starts_with(http.request.uri.path, "/media/")'
               ' or http.request.uri.path in {"/style.css" "/share.png" "/favicon.ico" "/apple-touch-icon.png"})',
    description="Cache immutable assets served by routes",
    action_parameters={"cache": True, "edge_ttl": {"mode": "respect_origin"}},
)

FONTS = dict(
    ref="krot_cache_fonts",
    action="set_cache_settings",
    expression='(starts_with(http.request.uri.path, "/fonts/"))',
    action_parameters={"cache": True},
)

HANDMADE = dict(
    ref="dashboard_bypass_admin",
    action="set_cache_settings",
    expression='(starts_with(http.request.uri.path, "/admin"))',
    action_parameters={"cache": False},
)


def zone(cloudflare, name):
    return cloudflare.add_zone(name)["id"]


def rules_of(cloudflare, zone_id):
    return cloudflare.rulesets[(zone_id, PHASE)]["rules"]


def args(server, zone_id, rules):
    return dict(zone_id=zone_id, rules=rules, api_token=TOKEN, api_url=server.url)


# busel's cache rule as Cloudflare holds it: made without a ref of ours, so the
# ref is one Cloudflare assigned.
BUSEL_MADE = dict(MEDIA, ref="8d2f41c07a9e4b7c")


def test_rule_another_tool_made_word_for_word_is_not_added_twice(run, serve):
    cloudflare = FakeCloudflareRulesets()
    zone_id = zone(cloudflare, "uebernommen.de")
    cloudflare.add_rules(zone_id, PHASE, [BUSEL_MADE])
    run("cloudflare_ruleset", args(serve(cloudflare), zone_id, [MEDIA]))
    assert [r["ref"] for r in rules_of(cloudflare, zone_id)] == ["8d2f41c07a9e4b7c"]


def test_rule_another_tool_made_word_for_word_reports_unchanged(run, serve):
    cloudflare = FakeCloudflareRulesets()
    zone_id = zone(cloudflare, "gleichlaut.de")
    cloudflare.add_rules(zone_id, PHASE, [BUSEL_MADE])
    assert run("cloudflare_ruleset", args(serve(cloudflare), zone_id, [MEDIA]), check=True)["changed"] is False


def test_rule_another_tool_made_differently_stays_and_ours_is_added(run, serve):
    cloudflare = FakeCloudflareRulesets()
    zone_id = zone(cloudflare, "abweichend.de")
    cloudflare.add_rules(zone_id, PHASE, [dict(BUSEL_MADE, expression='(starts_with(http.request.uri.path, "/media/"))')])
    run("cloudflare_ruleset", args(serve(cloudflare), zone_id, [MEDIA]))
    assert [r["ref"] for r in rules_of(cloudflare, zone_id)] == ["8d2f41c07a9e4b7c", "krot_cache_media"]


def test_creates_the_phase_ruleset_when_the_zone_has_none(run, serve):
    cloudflare = FakeCloudflareRulesets()
    zone_id = zone(cloudflare, "erstregel.de")
    run("cloudflare_ruleset", args(serve(cloudflare), zone_id, [MEDIA]))
    assert [r["ref"] for r in rules_of(cloudflare, zone_id)] == ["krot_cache_media"]


def test_zone_without_the_phase_gets_a_ruleset_of_its_own_rules(run, serve):
    cloudflare = FakeCloudflareRulesets()
    zone_id = zone(cloudflare, "ohnephase.de")
    run("cloudflare_ruleset", args(serve(cloudflare), zone_id, [MEDIA]))
    assert [r["ref"] for r in cloudflare.rulesets[(zone_id, PHASE)]["rules"]] == ["krot_cache_media"]

def test_rule_held_with_server_fields_is_not_rewritten(run, serve):
    cloudflare = FakeCloudflareRulesets()
    zone_id = zone(cloudflare, "stimmt.de")
    cloudflare.add_rules(zone_id, PHASE, [MEDIA])
    server = serve(cloudflare)
    run("cloudflare_ruleset", args(server, zone_id, [MEDIA]))
    assert server.writes() == []


def test_changed_expression_is_written(run, serve):
    cloudflare = FakeCloudflareRulesets()
    zone_id = zone(cloudflare, "ausdruck.de")
    cloudflare.add_rules(zone_id, PHASE, [dict(MEDIA, expression='(starts_with(http.request.uri.path, "/img/"))')])
    run("cloudflare_ruleset", args(serve(cloudflare), zone_id, [MEDIA]))
    assert rules_of(cloudflare, zone_id)[0]["expression"] == MEDIA["expression"]


def test_changed_rule_keeps_its_id(run, serve):
    cloudflare = FakeCloudflareRulesets()
    zone_id = zone(cloudflare, "gleicheid.de")
    held = cloudflare.add_rules(zone_id, PHASE, [dict(MEDIA, description="old words")])["rules"][0]["id"]
    run("cloudflare_ruleset", args(serve(cloudflare), zone_id, [MEDIA]))
    assert rules_of(cloudflare, zone_id)[0]["id"] == held


def test_foreign_rule_survives_the_write(run, serve):
    cloudflare = FakeCloudflareRulesets()
    zone_id = zone(cloudflare, "handarbeit.de")
    cloudflare.add_rules(zone_id, PHASE, [HANDMADE])
    run("cloudflare_ruleset", args(serve(cloudflare), zone_id, [MEDIA]))
    assert [r["ref"] for r in rules_of(cloudflare, zone_id)] == ["dashboard_bypass_admin", "krot_cache_media"]


def test_unchanged_own_rule_is_written_once_when_another_changes(run, serve):
    cloudflare = FakeCloudflareRulesets()
    zone_id = zone(cloudflare, "einmalig.de")
    cloudflare.add_rules(zone_id, PHASE, [MEDIA])
    run("cloudflare_ruleset", args(serve(cloudflare), zone_id, [MEDIA, FONTS]))
    assert [r["ref"] for r in rules_of(cloudflare, zone_id)] == ["krot_cache_media", "krot_cache_fonts"]


def test_second_run_is_unchanged(run, serve):
    cloudflare = FakeCloudflareRulesets()
    zone_id = zone(cloudflare, "zweiterlauf.de")
    server = serve(cloudflare)
    run("cloudflare_ruleset", args(server, zone_id, [MEDIA, FONTS]))
    assert run("cloudflare_ruleset", args(server, zone_id, [MEDIA, FONTS]))["changed"] is False


def test_check_mode_writes_nothing(run, serve):
    cloudflare = FakeCloudflareRulesets()
    zone_id = zone(cloudflare, "nurschauen.de")
    server = serve(cloudflare)
    run("cloudflare_ruleset", args(server, zone_id, [MEDIA]), check=True)
    assert server.writes() == []


def test_check_mode_names_the_rules_it_would_write(run, serve):
    cloudflare = FakeCloudflareRulesets()
    zone_id = zone(cloudflare, "vorschau.de")
    result = run("cloudflare_ruleset", args(serve(cloudflare), zone_id, [MEDIA]), check=True)
    assert result["changed_refs"] == ["krot_cache_media"]


def test_rule_without_ref_is_refused_before_any_request(run, serve):
    cloudflare = FakeCloudflareRulesets()
    server = serve(cloudflare)
    unnamed = dict((k, v) for k, v in MEDIA.items() if k != "ref")
    run("cloudflare_ruleset", args(server, zone(cloudflare, "namenlos.de"), [unnamed]))
    assert server.requests == []


def test_two_rules_with_one_ref_are_refused(run, serve):
    cloudflare = FakeCloudflareRulesets()
    result = run("cloudflare_ruleset", args(serve(cloudflare), zone(cloudflare, "doppelref.de"), [MEDIA, dict(FONTS, ref=MEDIA["ref"])]))
    assert "ref of its own" in result["msg"]


def test_write_that_did_not_take_fails(run, serve):
    cloudflare = FakeCloudflareRulesets()
    cloudflare.ignores_writes = True
    zone_id = zone(cloudflare, "taub.de")
    cloudflare.add_rules(zone_id, PHASE, [HANDMADE])
    assert "does not hold" in run("cloudflare_ruleset", args(serve(cloudflare), zone_id, [MEDIA]))["msg"]


def test_write_that_took_reports_changed_without_failing(run, serve):
    cloudflare = FakeCloudflareRulesets()
    zone_id = zone(cloudflare, "geklappt.de")
    result = run("cloudflare_ruleset", args(serve(cloudflare), zone_id, [MEDIA]))
    assert (result["changed"], result.get("failed", False)) == (True, False)


def test_unreadable_ruleset_list_stops_before_writing(run, serve):
    cloudflare = FakeCloudflareRulesets()
    zone_id = zone(cloudflare, "funkstille.de")
    server = serve(cloudflare)
    server.outages = [503, 503, 503]
    run("cloudflare_ruleset", args(server, zone_id, [MEDIA]))
    assert server.writes() == []


def test_ruleset_of_another_phase_is_not_taken_for_this_one(run, serve):
    cloudflare = FakeCloudflareRulesets()
    zone_id = zone(cloudflare, "andrephase.de")
    cloudflare.add_rules(zone_id, "http_request_firewall_custom", [MEDIA])
    run("cloudflare_ruleset", args(serve(cloudflare), zone_id, [MEDIA]))
    assert [r["ref"] for r in rules_of(cloudflare, zone_id)] == ["krot_cache_media"]


def test_rule_added_elsewhere_during_the_run_survives(run, serve):
    cloudflare = FakeCloudflareRulesets()
    zone_id = zone(cloudflare, "gleichzeitig.de")
    cloudflare.add_rules(zone_id, PHASE, [HANDMADE])
    cloudflare.added_after_read = dict(HANDMADE, ref="dashboard_late_rule", expression='(http.host eq "spaet.de")')
    run("cloudflare_ruleset", args(serve(cloudflare), zone_id, [MEDIA]))
    refs = [r["ref"] for r in cloudflare.rulesets[(zone_id, PHASE)]["rules"]]
    assert "dashboard_late_rule" in refs


def test_existing_ruleset_is_never_replaced_whole(run, serve):
    cloudflare = FakeCloudflareRulesets()
    zone_id = zone(cloudflare, "stueckweise.de")
    cloudflare.add_rules(zone_id, PHASE, [HANDMADE])
    server = serve(cloudflare)
    run("cloudflare_ruleset", args(server, zone_id, [MEDIA]))
    assert [r.method for r in server.writes()] == ["POST"]


def test_changed_own_rule_is_updated_in_place(run, serve):
    cloudflare = FakeCloudflareRulesets()
    zone_id = zone(cloudflare, "ersetzen.de")
    held = cloudflare.add_rules(zone_id, PHASE, [dict(MEDIA, description="old words")])["rules"][0]
    server = serve(cloudflare)
    run("cloudflare_ruleset", args(server, zone_id, [MEDIA]))
    assert [(r.method, r.path.rsplit("/", 1)[-1]) for r in server.writes()] == [("PATCH", held["id"])]


def test_refusal_other_than_404_at_the_phase_writes_nothing(run, serve):
    server = serve(FakeCloudflareRulesets(OTHER_TOKEN))
    run("cloudflare_ruleset", args(server, "zone-verboten", [MEDIA]))
    assert server.writes() == []


def test_write_that_loses_another_rule_fails(run, serve):
    cloudflare = FakeCloudflareRulesets()
    cloudflare.drops_others = True
    zone_id = zone(cloudflare, "verlust.de")
    cloudflare.add_rules(zone_id, PHASE, [HANDMADE])
    assert "lost rules rule-" in run("cloudflare_ruleset", args(serve(cloudflare), zone_id, [MEDIA]))["msg"]
