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
  - Keeps the given rules in a zone's phase ruleset, recognising its own by
    C(ref). Rules with any other ref — added in the dashboard, or by another
    tool — are never sent back. Once the ruleset exists, the module adds and
    updates its rules one at a time, so a rule someone else adds between this
    module's read and its write survives. Writing the phase as a whole list
    would roll such a rule back.
  - The ruleset is read at its phase address. Cloudflare answers 404 there for
    a zone that never had one, and only then does the module create it — with
    its own rules, in one write.
  - A rule compares by the fields given only. Cloudflare adds an id, a version
    and a timestamp to every rule; requiring those to match would rewrite a
    correct rule on every run.
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

def holds(existing, wanted):
    """Whether what Cloudflare holds carries every field that was asked for."""
    if isinstance(wanted, dict):
        return isinstance(existing, dict) and all(k in existing and holds(existing[k], v) for k, v in wanted.items())
    return existing == wanted


def entrypoint(api, zone, phase):
    """The phase ruleset, or None where the zone has never had one."""
    try:
        ruleset = api.call("GET", "/zones/%s/rulesets/phases/%s/entrypoint" % (zone, phase))
    except Refused as refusal:
        # 404 at this address is Cloudflare's documented "no ruleset in this
        # phase yet". It still arrived in Cloudflare's own envelope — a page
        # from anything in between is Unreachable before it gets here.
        if refusal.status == 404:
            return None
        raise
    if not isinstance(ruleset, dict) or not ruleset.get("id") or not isinstance(ruleset.get("rules", []), list):
        raise Unreachable("Cloudflare answered the %s ruleset without an id or a rule list" % phase)
    return ruleset


def by_ref(ruleset):
    rules = (ruleset or {}).get("rules") or []
    return dict((r.get("ref"), r) for r in rules if isinstance(r, dict) and r.get("ref"))


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
        ruleset = entrypoint(api, zone, phase)
        held = by_ref(ruleset)
        differing = [rule["ref"] for rule in wanted if not holds(held.get(rule["ref"]), rule)]
        if module.check_mode or not differing:
            module.exit_json(changed=bool(differing), changed_refs=differing)

        # Rules that are not ours, to check afterwards that none went missing.
        mine = set(rule["ref"] for rule in wanted)
        others = set(r.get("id") for r in (ruleset or {}).get("rules") or [] if r.get("ref") not in mine)
        if ruleset is None:
            api.call("PUT", "/zones/%s/rulesets/phases/%s/entrypoint" % (zone, phase), body={"rules": wanted})
        else:
            base = "/zones/%s/rulesets/%s/rules" % (zone, ruleset["id"])
            for rule in wanted:
                if rule["ref"] not in differing:
                    continue
                if rule["ref"] in held:
                    # In place, keeping its id and position.
                    api.call("PATCH", "%s/%s" % (base, held[rule["ref"]]["id"]), body=rule)
                else:
                    api.call("POST", base, body=rule)

        after = entrypoint(api, zone, phase)
        kept = [rule["ref"] for rule in wanted if not holds(by_ref(after).get(rule["ref"]), rule)]
        remaining = set(r.get("id") for r in (after or {}).get("rules") or [])
        lost = sorted(i for i in others if i not in remaining)
        if kept or lost:
            module.fail_json(msg="Cloudflare took the rules but does not hold %s and lost rules %s"
                             % (", ".join(kept) or "none", ", ".join(lost) or "none"), changed=True, changed_refs=differing)
        module.exit_json(changed=True, changed_refs=differing)
    except (Unreachable, Refused) as error:
        module.fail_json(msg=str(error))


if __name__ == "__main__":
    main()
