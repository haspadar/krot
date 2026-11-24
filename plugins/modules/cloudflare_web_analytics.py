#!/usr/bin/python
# -*- coding: utf-8 -*-
# MIT License

from __future__ import absolute_import, division, print_function

__metaclass__ = type

DOCUMENTATION = r"""
---
module: cloudflare_web_analytics
short_description: Turns on Cloudflare Web Analytics for a zone, for every visitor
description:
  - Cloudflare creates a Web Analytics record when a zone is added, but a new
    zone gets it in the lite form, and the script is then not put into pages
    served to visitors from the EU. This module brings the zone's record to
    automatic installation, enabled, not lite, creating the record when the
    zone has none, and reads it back.
  - The script itself is not part of any site's templates; Cloudflare inserts
    it into the HTML of a proxied zone.
  - A write that Cloudflare accepted but did not keep fails the module.
  - Without C(zone_id) nothing is looked up by zone and nothing is written; the
    module only lists the account's records, which proves the token may read
    Web Analytics before a zone exists.
  - The token needs Account Settings Read to read and Account Settings Write to
    change. A token that may read but not write is found only by the write.
options:
  zone_id:
    description: The zone to bring to the wanted state.
    type: str
  account_id:
    description:
      - The account holding the zone. When empty, it is read from the zone.
      - Required when C(zone_id) is not given.
    type: str
  api_token:
    description: Cloudflare API token with Account Settings Write.
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
- name: Web Analytics on for everyone, the EU included
  haspadar.krot.cloudflare_web_analytics:
    zone_id: "{{ zone.zone_id }}"
    api_token: "{{ cloudflare_token }}"
  delegate_to: localhost
"""

RETURN = r"""
changed_fields:
  description:
    - What was (or in check mode would be) written. C(created) when the zone had no
      record, then any of C(auto_install), C(enabled), C(lite) that differed.
  type: list
  elements: str
  returned: always
site_tag:
  description: The record's tag. Absent when the zone has no record yet, and when no zone was given.
  type: str
  returned: when the record exists
"""

from ansible.module_utils.basic import AnsibleModule

from ansible_collections.haspadar.krot.plugins.module_utils.api import Unreachable
from ansible_collections.haspadar.krot.plugins.module_utils.cloudflare import (
    ARGUMENTS,
    Cloudflare,
    Refused,
)

WANTED = (("auto_install", True), ("enabled", True), ("lite", False))


def differing(entry):
    ruleset = entry.get("ruleset") or {}
    held = dict(auto_install=entry.get("auto_install"), enabled=ruleset.get("enabled"), lite=ruleset.get("lite"))
    # `is not`: a missing or null field is not the wanted value, and 0/1 are not booleans here.
    return [name for name, value in WANTED if held[name] is not value]


def listing(account):
    return "/accounts/%s/rum/site_info/list" % account


def record_of(api, account, zone):
    found = [e for e in api.pages(listing(account))
             if isinstance(e, dict) and isinstance(e.get("ruleset"), dict) and e["ruleset"].get("zone_tag") == zone]
    if len(found) > 1:
        raise Refused("%d Web Analytics records name zone %s; remove the extra ones by hand" % (len(found), zone))
    if found and not found[0].get("site_tag"):
        raise Refused("Cloudflare lists the Web Analytics record of zone %s without a site_tag" % zone)
    return found[0] if found else None


def account_of(api, zone):
    account = ((api.call("GET", "/zones/%s" % zone) or {}).get("account") or {}).get("id")
    if not account:
        raise Refused("Cloudflare does not say which account zone %s is in; set account_id" % zone)
    return account


def bring(module, api, account, zone):
    record = record_of(api, account, zone)
    fields = ["created"] if record is None else differing(record)
    if module.check_mode or not fields:
        module.exit_json(changed=bool(fields), changed_fields=fields,
                         **({"site_tag": record["site_tag"]} if record else {}))

    if record is None:
        api.call("POST", "/accounts/%s/rum/site_info" % account, body={"zone_tag": zone, "auto_install": True})
        # The answer to a creation is not the proof; finding the record is. And a
        # new record may come in lite whatever was asked, so it is brought as well.
        record = record_of(api, account, zone)
        if record is None:
            module.fail_json(msg="Cloudflare accepted Web Analytics for zone %s but does not list it" % zone)
    needed = differing(record)
    if needed:
        api.call("PUT", "/accounts/%s/rum/site_info/%s" % (account, record["site_tag"]),
                 body={"zone_tag": zone, "auto_install": True, "enabled": True, "lite": False})
        fields = fields + [name for name in needed if name not in fields]
        record = record_of(api, account, zone)
        kept = differing(record) if record else [name for name, _ in WANTED]
        if kept:
            module.fail_json(msg="Cloudflare accepted but did not keep: %s" % ", ".join(kept), changed_fields=fields)
    module.exit_json(changed=True, changed_fields=fields, site_tag=record["site_tag"])


def main():
    module = AnsibleModule(
        argument_spec=dict(
            zone_id=dict(type="str"),
            account_id=dict(type="str"),
            **ARGUMENTS
        ),
        required_one_of=[["zone_id", "account_id"]],
        supports_check_mode=True,
    )
    zone = module.params["zone_id"] or None
    given = module.params["account_id"] or None
    if not zone and not given:
        module.fail_json(msg="one of zone_id or account_id must not be empty")
    api = Cloudflare(module.params["api_token"], module.params["api_url"])

    try:
        # Outside the hint below: a refusal to read the zone says nothing about Web Analytics.
        account = given or account_of(api, zone)
        try:
            if not zone:
                api.call("GET", listing(account), {"per_page": 1, "page": 1})
                module.exit_json(changed=False, changed_fields=[])
            bring(module, api, account, zone)
        except Refused as error:
            if error.status in (401, 403):
                raise Refused("%s; the token needs Account Settings Read and Write for Web Analytics" % error,
                              error.status)
            raise
    except (Unreachable, Refused) as error:
        module.fail_json(msg=str(error))


if __name__ == "__main__":
    main()
