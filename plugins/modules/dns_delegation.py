#!/usr/bin/python
# -*- coding: utf-8 -*-
# MIT License

from __future__ import absolute_import, division, print_function

__metaclass__ = type

DOCUMENTATION = r"""
---
module: dns_delegation
short_description: Reports whether public resolvers see a domain delegated to the given nameservers
description:
  - Asks two independent public resolvers over DNS-over-HTTPS for the domain's
    NS records and compares each answer, as a set, with the expected
    nameservers. Only reads; safe in check mode.
  - Every resolver must answer. One that cannot (SERVFAIL, timeout, an answer
    that is not JSON) fails the module rather than counting as "not delegated"
    — a caller waiting on delegation should stop, not conclude.
  - Resolvers that disagree are an ordinary state while a delegation spreads;
    the module reports both answers and C(delegated=false).
options:
  domain:
    description: The domain whose delegation is asked about.
    type: str
    required: true
  nameservers:
    description: The nameservers the domain should be delegated to.
    type: list
    elements: str
    required: true
  resolvers:
    description: DNS-over-HTTPS JSON endpoints to ask; changed only by tests.
    type: list
    elements: str
    default:
      - https://dns.google/resolve
      - https://cloudflare-dns.com/dns-query
author:
  - haspadar
"""

EXAMPLES = r"""
- name: Ask whether the world resolves through Cloudflare yet
  haspadar.krot.dns_delegation:
    domain: example.de
    nameservers: "{{ zone.name_servers }}"
  delegate_to: localhost
  register: delegation
"""

RETURN = r"""
delegated:
  description: Whether every resolver sees exactly the expected nameservers.
  type: bool
  returned: always
answers:
  description: Resolver address to the nameservers it reported, lowercased, without the trailing dot.
  type: dict
  returned: always
"""

from ansible.module_utils.basic import AnsibleModule

from ansible_collections.haspadar.krot.plugins.module_utils.api import Unreachable
from ansible_collections.haspadar.krot.plugins.module_utils.delegation import RESOLVERS, answers, delegated


def main():
    module = AnsibleModule(
        argument_spec=dict(
            domain=dict(type="str", required=True),
            nameservers=dict(type="list", elements="str", required=True),
            resolvers=dict(type="list", elements="str", default=RESOLVERS),
        ),
        supports_check_mode=True,
    )
    try:
        found = answers(module.params["domain"], module.params["resolvers"])
    except Unreachable as error:
        module.fail_json(msg=str(error))
    module.exit_json(changed=False, answers=found, delegated=delegated(found, module.params["nameservers"]))


if __name__ == "__main__":
    main()
