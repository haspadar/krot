#!/usr/bin/python
# -*- coding: utf-8 -*-
# MIT License

from __future__ import absolute_import, division, print_function

__metaclass__ = type

DOCUMENTATION = r"""
---
module: cloudflare_ruleset
short_description: Keeps given rules in a Cloudflare zone's phase ruleset
description:
  - Cloudflare holds a zone's rules of one phase as one ruleset and replaces it
    as a whole; there is no "add one rule" call. The module therefore reads the
    ruleset, puts its own rules into it and writes the whole list back.
  - Its own rules are recognised by C(ref). Rules with any other ref — added in
    the dashboard, or by another tool — are written back untouched, so the
    module never takes away what it did not put there.
  - A rule compares by the fields given only. Cloudflare adds an id, a version
    and a timestamp to every rule; requiring those to match would rewrite a
    correct rule on every run.
  - The phase ruleset is looked up in the zone's list rather than fetched by
    phase. The phase address answers 404 on a zone that never had one, and
    that 404 means "none yet" rather than a failure.
  - In check mode nothing is written.
options:
  zone_id:
    description: The zone.
    type: str
    required: true
  phase:
    description: The ruleset phase.
    type: str
    default: http_request_cache_settings
  rules:
    description:
      - Rules as the Rulesets API takes them. Each needs a unique C(ref), an
        C(action) and an C(expression); the expression is compared character
        for character, so write it the way Cloudflare stores it.
    type: list
    elements: dict
    required: true
  api_token:
    description: Cloudflare API token with Zone Rulesets Edit (Cache Rules Edit for the cache phase).
    type: str
    required: true
  api_url:
    description: Cloudflare API address; changed only by tests.
    type: str
    default: https://api.cloudflare.com/client/v4
author:
  - haspadar
"""

EXAMPLES = r"""
- name: Cache the photos served by routes
  haspadar.krot.cloudflare_ruleset:
    zone_id: "{{ zone.zone_id }}"
    rules:
      - ref: krot_cache_media
        action: set_cache_settings
        expression: '(starts_with(http.request.uri.path, "/media/"))'
        description: Cache immutable assets served by routes
        action_parameters:
          cache: true
          edge_ttl: {mode: respect_origin}
    api_token: "{{ cloudflare_token }}"
  delegate_to: localhost
"""

RETURN = r"""
changed_refs:
  description: Refs of the rules that were (or in check mode would be) written.
  type: list
  elements: str
  returned: always
"""

from ansible.module_utils.basic import AnsibleModule

from ansible_collections.haspadar.krot.plugins.module_utils.api import Unreachable
from ansible_collections.haspadar.krot.plugins.module_utils.cloudflare import (
    ARGUMENTS,
    Cloudflare,
    Refused,
)

# Fields Cloudflare keeps for itself and does not take back on a write.
SERVER_FIELDS = ("version", "last_updated")


def holds(existing, wanted):
    """Whether what Cloudflare holds carries every field that was asked for."""
    if isinstance(wanted, dict):
        return isinstance(existing, dict) and all(k in existing and holds(existing[k], v) for k, v in wanted.items())
    return existing == wanted


def current_rules(api, zone, phase):
    rulesets = api.call("GET", "/zones/%s/rulesets" % zone)
    if not isinstance(rulesets, list):
        raise Unreachable("Cloudflare answered the zone's rulesets without a list")
    entry = [r for r in rulesets if isinstance(r, dict) and r.get("phase") == phase and r.get("kind") == "zone"]
    if not entry:
        return []
    ruleset = api.call("GET", "/zones/%s/rulesets/%s" % (zone, entry[0]["id"]))
    if not isinstance(ruleset, dict):
        raise Unreachable("Cloudflare answered ruleset %s without a body" % entry[0]["id"])
    rules = ruleset.get("rules") or []
    if not isinstance(rules, list):
        raise Unreachable("Cloudflare answered ruleset %s without a rule list" % entry[0]["id"])
    return rules


def sendable(rule):
    return dict((k, v) for k, v in rule.items() if k not in SERVER_FIELDS)


def main():
    module = AnsibleModule(
        argument_spec=dict(
            zone_id=dict(type="str", required=True),
            phase=dict(type="str", default="http_request_cache_settings"),
            rules=dict(type="list", elements="dict", required=True),
            **ARGUMENTS
        ),
        supports_check_mode=True,
    )
    zone, phase, wanted = module.params["zone_id"], module.params["phase"], module.params["rules"]

    refs = [rule.get("ref") for rule in wanted]
    if not all(refs) or len(set(refs)) != len(refs):
        module.fail_json(msg="every rule needs a ref of its own; the ref is how the module tells its rules from others")
    for rule in wanted:
        if not rule.get("action") or not rule.get("expression"):
            module.fail_json(msg="rule %s needs an action and an expression" % rule["ref"])

    api = Cloudflare(module.params["api_token"], module.params["api_url"])
    try:
        held = current_rules(api, zone, phase)
        by_ref = dict((r.get("ref"), r) for r in held if isinstance(r, dict) and r.get("ref"))
        differing = [rule["ref"] for rule in wanted if not holds(by_ref.get(rule["ref"]), rule)]
        if module.check_mode or not differing:
            module.exit_json(changed=bool(differing), changed_refs=differing)

        mine = dict((rule["ref"], rule) for rule in wanted)
        written = []
        for rule in held:
            ref = rule.get("ref") if isinstance(rule, dict) else None
            if ref in mine:
                # Updated in place, keeping its id, so the rule keeps its position
                # and history rather than being deleted and made again.
                ours = mine.pop(ref)
                written.append(dict(ours, id=rule["id"]) if ref in differing else sendable(rule))
            else:
                written.append(sendable(rule))
        written.extend(rule for rule in wanted if rule["ref"] in mine)

        api.call("PUT", "/zones/%s/rulesets/phases/%s/entrypoint" % (zone, phase), body={"rules": written})

        after = current_rules(api, zone, phase)
        after_refs = dict((r.get("ref"), r) for r in after if isinstance(r, dict) and r.get("ref"))
        kept = [rule["ref"] for rule in wanted if not holds(after_refs.get(rule["ref"]), rule)]
        lost = [r["id"] for r in held if isinstance(r, dict) and r.get("id") not in set(a.get("id") for a in after)]
        if kept or lost:
            module.fail_json(msg="Cloudflare took the ruleset but did not keep rules %s and lost rules %s"
                             % (", ".join(kept) or "none", ", ".join(lost) or "none"), changed=True, changed_refs=differing)
        module.exit_json(changed=True, changed_refs=differing)
    except (Unreachable, Refused) as error:
        module.fail_json(msg=str(error))


if __name__ == "__main__":
    main()
