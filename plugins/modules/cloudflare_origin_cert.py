#!/usr/bin/python
# -*- coding: utf-8 -*-
# MIT License

from __future__ import absolute_import, division, print_function

__metaclass__ = type

DOCUMENTATION = r"""
---
module: cloudflare_origin_cert
short_description: Issues a Cloudflare Origin CA certificate for a signing request
description:
  - Signs the given CSR and returns the certificate. The private key is never
    seen by this module; it stays wherever the CSR was made, which should be
    the machine that will serve it.
  - Every call issues a new certificate — there is no "already issued" to find,
    because an issued certificate is useless without the key made for it. The
    caller decides whether to issue, typically by checking that the machine
    does not already hold a non-empty certificate and key.
  - In check mode nothing is issued.
options:
  csr:
    description: PEM signing request.
    type: str
    required: true
  hostnames:
    description: Names the certificate covers, usually the domain and its wildcard.
    type: list
    elements: str
    required: true
  request_type:
    description: Key type the CSR was made with.
    type: str
    choices: [origin-rsa, origin-ecc]
    default: origin-rsa
  validity_days:
    description:
      - Lifetime. Fifteen years by default, since the certificate is only ever
        presented to Cloudflare and a short life buys nothing but a renewal.
    type: int
    choices: [7, 30, 90, 365, 730, 1095, 5475]
    default: 5475
  api_token:
    description: Cloudflare API token with SSL and Certificates Edit.
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
- name: Sign the request made on the machine
  haspadar.krot.cloudflare_origin_cert:
    csr: "{{ csr.stdout }}"
    hostnames: ["{{ site_domain }}", "*.{{ site_domain }}"]
    api_token: "{{ cloudflare_token }}"
  delegate_to: localhost
  register: origin
"""

RETURN = r"""
certificate:
  description: PEM certificate. Empty in check mode.
  type: str
  returned: always
certificate_id:
  description: Cloudflare's id of the certificate.
  type: str
  returned: when issued
expires_on:
  description: Expiry as Cloudflare reports it.
  type: str
  returned: when issued
"""

from ansible.module_utils.basic import AnsibleModule

from ansible_collections.haspadar.krot.plugins.module_utils.api import Unreachable
from ansible_collections.haspadar.krot.plugins.module_utils.cloudflare import (
    ARGUMENTS,
    Cloudflare,
    Refused,
)


def main():
    module = AnsibleModule(
        argument_spec=dict(
            csr=dict(type="str", required=True),
            hostnames=dict(type="list", elements="str", required=True),
            request_type=dict(type="str", choices=["origin-rsa", "origin-ecc"], default="origin-rsa"),
            validity_days=dict(type="int", choices=[7, 30, 90, 365, 730, 1095, 5475], default=5475),
            **ARGUMENTS
        ),
        supports_check_mode=True,
    )
    if module.check_mode:
        module.exit_json(changed=True, certificate="")

    api = Cloudflare(module.params["api_token"], module.params["api_url"])
    try:
        issued = api.call("POST", "/certificates", body=dict(
            csr=module.params["csr"],
            hostnames=module.params["hostnames"],
            request_type=module.params["request_type"],
            requested_validity=module.params["validity_days"],
        ))
        if not isinstance(issued, dict) or not issued.get("id") or not issued.get("certificate"):
            module.fail_json(msg="Cloudflare answered the certificate request without an id or certificate")

        # Read back by id: the certificate that goes on the machine has to be one
        # Cloudflare holds and will accept from the origin.
        held = api.call("GET", "/certificates/%s" % issued["id"])
        if not isinstance(held, dict) or (held.get("certificate") or "").strip() != issued["certificate"].strip():
            module.fail_json(msg="Certificate %s does not read back as issued" % issued["id"])
        module.exit_json(
            changed=True,
            certificate=issued["certificate"],
            certificate_id=issued["id"],
            expires_on=issued.get("expires_on", ""),
        )
    except (Unreachable, Refused) as error:
        module.fail_json(msg=str(error))


if __name__ == "__main__":
    main()
