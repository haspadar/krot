#!/usr/bin/python
# -*- coding: utf-8 -*-
# MIT License

from __future__ import absolute_import, division, print_function

__metaclass__ = type

DOCUMENTATION = r"""
---
module: cloudflare_zone_settings
short_description: Brings a Cloudflare zone's settings to the given values
description:
  - Reads every named setting, writes only the ones that differ, and reads them
    back. A write that Cloudflare accepted but did not keep fails the module.
  - The defaults are what a site behind an origin certificate needs. The
    browser cache TTL is 0 ("respect existing headers") on purpose, since
    Cloudflare's default of four hours replaces the origin's Cache-Control
    rather than falling back to it.
options:
  zone_id:
    description: The zone to configure.
    type: str
    required: true
  settings:
    description:
      - Setting name to value. Values compare as text, booleans as on/off, so
        C(0) and C("0") are the same value.
    type: dict
    default:
      ssl: strict
      always_use_https: "on"
      browser_cache_ttl: 0
  origin_certificate_installed:
    description:
      - Must be true for C(tls_client_auth) (authenticated origin pulls) to be
        turned on. Turned on before the origin holds its certificate, it breaks
        every request to the site.
    type: bool
    default: false
  api_token:
    description: Cloudflare API token with Zone Settings Edit.
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
- name: Strict TLS, HTTPS only, the origin's cache headers respected
  haspadar.krot.cloudflare_zone_settings:
    zone_id: "{{ zone.zone_id }}"
    api_token: "{{ cloudflare_token }}"
  delegate_to: localhost
"""

RETURN = r"""
changed_settings:
  description: Names of the settings that were (or in check mode would be) written.
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
    comparable,
    sendable,
)

DEFAULTS = dict(ssl="strict", always_use_https="on", browser_cache_ttl=0)


def main():
    module = AnsibleModule(
        argument_spec=dict(
            zone_id=dict(type="str", required=True),
            settings=dict(type="dict", default=DEFAULTS),
            origin_certificate_installed=dict(type="bool", default=False),
            **ARGUMENTS
        ),
        supports_check_mode=True,
    )
    zone = module.params["zone_id"]
    wanted = module.params["settings"]

    if comparable(wanted.get("tls_client_auth", "off")) == "on" and not module.params["origin_certificate_installed"]:
        module.fail_json(msg="tls_client_auth before the origin certificate is installed would cut the site off")

    api = Cloudflare(module.params["api_token"], module.params["api_url"])
    try:
        differing = sorted(
            name for name, value in wanted.items()
            if comparable(api.setting(zone, name)) != comparable(value)
        )
        if module.check_mode or not differing:
            module.exit_json(changed=bool(differing), changed_settings=differing)

        for name in differing:
            api.call("PATCH", "/zones/%s/settings/%s" % (zone, name), body={"value": sendable(wanted[name])})

        kept = [name for name in differing if comparable(api.setting(zone, name)) != comparable(wanted[name])]
        if kept:
            module.fail_json(msg="Cloudflare accepted but did not keep: %s" % ", ".join(kept), changed_settings=differing)
        module.exit_json(changed=True, changed_settings=differing)
    except (Unreachable, Refused) as error:
        module.fail_json(msg=str(error))


if __name__ == "__main__":
    main()
