#!/usr/bin/python
# -*- coding: utf-8 -*-
# MIT License

from __future__ import absolute_import, division, print_function

__metaclass__ = type

DOCUMENTATION = r"""
---
module: cloudflare_zone
short_description: Finds or creates a Cloudflare zone and reports its nameservers
description:
  - Looks the zone up by name first and creates it only when the lookup
    answered with nothing. A lookup that failed stops the module instead.
  - Returns the nameserver pair Cloudflare assigned. The pair is assigned per
    account and is not known in advance, which is why the zone is created
    before the registrar is touched.
  - In check mode nothing is created.
options:
  domain:
    description: The zone name, the registered domain without a subdomain.
    type: str
    required: true
  account_id:
    description:
      - The account the zone belongs to. Narrows the lookup to it and is sent
        on creation.
      - A token that sees several accounts could otherwise find a same-named
        zone in another one, with a different nameserver pair.
    type: str
  api_token:
    description: Cloudflare API token with Zone Read and Zone Edit.
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
- name: Find or create the zone
  haspadar.krot.cloudflare_zone:
    domain: example.de
    account_id: "{{ site_cloudflare_account_id }}"
    api_token: "{{ cloudflare_token }}"
  delegate_to: localhost
  register: zone
"""

RETURN = r"""
exists:
  description: Whether the zone exists after the run. False only in check mode.
  type: bool
  returned: always
zone_id:
  description: The zone id.
  type: str
  returned: when exists
status:
  description: C(pending) until Cloudflare has seen the delegation, then C(active).
  type: str
  returned: when exists
name_servers:
  description: The nameserver pair to set at the registrar.
  type: list
  elements: str
  returned: when exists
"""

from ansible.module_utils.basic import AnsibleModule

from ansible_collections.haspadar.krot.plugins.module_utils.api import Unreachable
from ansible_collections.haspadar.krot.plugins.module_utils.cloudflare import (
    ARGUMENTS,
    Cloudflare,
    Refused,
)


def shaped(zone):
    return dict(
        exists=True,
        zone_id=zone.get("id"),
        status=zone.get("status"),
        name_servers=list(zone.get("name_servers") or []),
    )


def only(zones, domain):
    # The name filter is exact, so two answers mean the token sees the same
    # zone name in two accounts. Picking one would hand the registrar a pair
    # that may belong to the wrong account.
    if len(zones) > 1:
        raise Refused("%d zones named %s are visible to this token; set account_id" % (len(zones), domain))
    return zones[0] if zones else None


def main():
    module = AnsibleModule(
        argument_spec=dict(
            domain=dict(type="str", required=True),
            account_id=dict(type="str"),
            **ARGUMENTS
        ),
        supports_check_mode=True,
    )
    domain = module.params["domain"]
    account = module.params["account_id"]
    api = Cloudflare(module.params["api_token"], module.params["api_url"])

    try:
        zone = only(api.zones(domain, account), domain)
        if zone is not None:
            module.exit_json(changed=False, **shaped(zone))
        if module.check_mode:
            module.exit_json(changed=True, exists=False)

        body = {"name": domain, "type": "full"}
        if account:
            body["account"] = {"id": account}
        api.call("POST", "/zones", body=body)

        # The creation's answer is not the proof; the zone being findable is.
        zone = only(api.zones(domain, account), domain)
        if zone is None:
            module.fail_json(msg="Cloudflare accepted zone %s but does not list it" % domain)
        module.exit_json(changed=True, **shaped(zone))
    except (Unreachable, Refused) as error:
        module.fail_json(msg=str(error))


if __name__ == "__main__":
    main()
