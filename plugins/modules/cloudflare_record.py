#!/usr/bin/python
# -*- coding: utf-8 -*-
# MIT License

from __future__ import absolute_import, division, print_function

__metaclass__ = type

DOCUMENTATION = r"""
---
module: cloudflare_record
short_description: Keeps one DNS record in a Cloudflare zone
description:
  - Two kinds of record, told apart by type, and they behave differently on
    purpose.
  - An address (A, AAAA, CNAME to a host of ours) is one per name and type. An
    existing one is updated in place; a missing one is created. Matched on type
    as well as name, since a verified apex also carries the search engines'
    TXT and CNAME under the same name, and matching by name alone would rewrite
    the wrong record.
  - A proof (TXT) sits beside others of its kind under one name — each search
    engine puts its own on the domain. One whose content is already there is
    left alone, and nothing else under the name is touched. Content compares
    without surrounding quotes, as a TXT added in the dashboard comes back
    quoted and one written through the API does not.
  - Cloudflare's own module (community.general.cloudflare_dns) is not used
    because its API address cannot be changed, which leaves the most dangerous
    step of a launch — publishing an address — outside every test.
  - In check mode nothing is written.
options:
  zone_id:
    description: The zone.
    type: str
    required: true
  type:
    description: Record type.
    type: str
    required: true
    choices: [A, AAAA, CNAME, TXT]
  name:
    description: Full record name, e.g. C(example.de) or C(www.example.de).
    type: str
    required: true
  content:
    description: The address, target or text.
    type: str
    required: true
  proxied:
    description:
      - Serve through Cloudflare. Defaults to true for addresses, and an
        unproxied address is refused unless C(allow_unproxied) is set — a
        record that publishes the origin stays in DNS history for good.
      - Ignored for TXT.
    type: bool
    default: true
  allow_unproxied:
    description: Permit an address record with C(proxied=false).
    type: bool
    default: false
  api_token:
    description: Cloudflare API token with DNS Edit.
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
- name: Point the apex at the machine, through Cloudflare
  haspadar.krot.cloudflare_record:
    zone_id: "{{ zone.zone_id }}"
    type: A
    name: example.de
    content: 203.0.113.7
    api_token: "{{ cloudflare_token }}"
  delegate_to: localhost

- name: Prove the domain to Yandex
  haspadar.krot.cloudflare_record:
    zone_id: "{{ zone.zone_id }}"
    type: TXT
    name: example.de
    content: "yandex-verification: 0123abcd"
    api_token: "{{ cloudflare_token }}"
  delegate_to: localhost
"""

RETURN = r"""
record_id:
  description: The record's id. Absent in check mode for a record not yet made.
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

ADDRESSES = ("A", "AAAA", "CNAME")


def unquoted(text):
    return (text or "").strip().strip('"')


def records(api, zone, kind, name):
    found = api.call("GET", "/zones/%s/dns_records" % zone, {"type": kind, "name": name, "per_page": 100})
    if not isinstance(found, list):
        raise Unreachable("Cloudflare answered the record lookup without a list")
    return [r for r in found if isinstance(r, dict)]


def main():
    module = AnsibleModule(
        argument_spec=dict(
            zone_id=dict(type="str", required=True),
            type=dict(type="str", required=True, choices=["A", "AAAA", "CNAME", "TXT"]),
            name=dict(type="str", required=True),
            content=dict(type="str", required=True),
            proxied=dict(type="bool", default=True),
            allow_unproxied=dict(type="bool", default=False),
            **ARGUMENTS
        ),
        supports_check_mode=True,
    )
    p = module.params
    zone, kind, name, content = p["zone_id"], p["type"], p["name"], p["content"]
    address = kind in ADDRESSES
    if address and not p["proxied"] and not p["allow_unproxied"]:
        module.fail_json(msg="an unproxied %s publishes the origin for good; set allow_unproxied to mean it" % kind)

    wanted = dict(type=kind, name=name, content=content, ttl=1)
    if address:
        wanted["proxied"] = p["proxied"]

    api = Cloudflare(p["api_token"], p["api_url"])
    try:
        held = records(api, zone, kind, name)
        if address:
            if len(held) > 1:
                module.fail_json(msg="%d %s records named %s; refusing to guess which one is the site's" % (len(held), kind, name))
            current = held[0] if held else None
            same = current is not None and current.get("content") == content and bool(current.get("proxied")) == p["proxied"]
        else:
            current = next((r for r in held if unquoted(r.get("content")) == unquoted(content)), None)
            same = current is not None
        if same:
            module.exit_json(changed=False, record_id=current.get("id"))
        if module.check_mode:
            module.exit_json(changed=True)

        if address and current is not None:
            api.call("PUT", "/zones/%s/dns_records/%s" % (zone, current["id"]), body=wanted)
        else:
            api.call("POST", "/zones/%s/dns_records" % zone, body=wanted)

        after = records(api, zone, kind, name)
        if address:
            kept = [r for r in after if r.get("content") == content and bool(r.get("proxied")) == p["proxied"]]
        else:
            kept = [r for r in after if unquoted(r.get("content")) == unquoted(content)]
        if not kept:
            module.fail_json(msg="Cloudflare accepted the %s record for %s but does not hold it" % (kind, name), changed=True)
        module.exit_json(changed=True, record_id=kept[0].get("id"))
    except (Unreachable, Refused) as error:
        module.fail_json(msg=str(error))


if __name__ == "__main__":
    main()
