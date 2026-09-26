"""Cloudflare's Rulesets API on top of the zone fake.

Answers the way the live API does where it matters to cloudflare_ruleset: the
phase address answers 404 on a zone that never had a ruleset in that phase,
every stored rule carries an id, a version and a timestamp the caller never
sent, and a PUT replaces the phase's rules as a whole.
"""

import itertools
import re

from fakes.cloudflare import FakeCloudflare, ok, refused


class FakeCloudflareRulesets(FakeCloudflare):
    def __init__(self, *args, **kwargs):
        super(FakeCloudflareRulesets, self).__init__(*args, **kwargs)
        self.rulesets = {}
        self.rule_ids = itertools.count(1)
        # A PUT that is answered as taken while the ruleset stays as it was.
        self.ignores_writes = False

    def add_rules(self, zone_id, phase, rules):
        ruleset = self.rulesets.setdefault((zone_id, phase), {
            "id": "rs-%d" % next(self.rule_ids), "kind": "zone", "phase": phase,
            "name": "default", "rules": []})
        ruleset["rules"].extend(self._stored(rule) for rule in rules)
        return ruleset

    def _stored(self, rule):
        stored = dict(rule)
        stored.setdefault("id", "rule-%d" % next(self.rule_ids))
        stored.setdefault("enabled", True)
        stored["version"] = "1"
        stored["last_updated"] = "2026-09-26T10:00:00Z"
        return stored

    def handle(self, request):
        if request.headers.get("Authorization") != "Bearer " + self.token:
            return refused(403, "Authentication error", 10000)
        path, method = request.path, request.method

        listing = re.match(r"^/zones/([^/]+)/rulesets$", path)
        if listing and method == "GET":
            zone = listing.group(1)
            return ok([dict((k, v) for k, v in r.items() if k != "rules")
                       for (z, _), r in self.rulesets.items() if z == zone])

        entry = re.match(r"^/zones/([^/]+)/rulesets/phases/([^/]+)/entrypoint$", path)
        if entry:
            zone, phase = entry.groups()
            if method == "GET":
                if (zone, phase) not in self.rulesets:
                    return refused(404, "could not find entrypoint ruleset in the %s phase" % phase, 10003)
                return ok(self.rulesets[(zone, phase)])
            if method == "PUT":
                rules = request.body.get("rules") or []
                if any("version" in r or "last_updated" in r for r in rules):
                    return refused(400, "rules must not carry version or last_updated", 20021)
                if self.ignores_writes:
                    return ok(self.rulesets.get((zone, phase), {}))
                ruleset = self.rulesets.setdefault((zone, phase), {
                    "id": "rs-%d" % next(self.rule_ids), "kind": "zone", "phase": phase,
                    "name": "default", "rules": []})
                ruleset["rules"] = [self._stored(rule) for rule in rules]
                return ok(ruleset)

        one = re.match(r"^/zones/([^/]+)/rulesets/([^/]+)$", path)
        if one and method == "GET":
            zone, ruleset_id = one.groups()
            for (z, _), ruleset in self.rulesets.items():
                if z == zone and ruleset["id"] == ruleset_id:
                    return ok(ruleset)
            return refused(404, "ruleset not found", 10003)

        return super(FakeCloudflareRulesets, self).handle(request)
