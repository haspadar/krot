#!/usr/bin/python
# -*- coding: utf-8 -*-
# MIT License

from __future__ import absolute_import, division, print_function

__metaclass__ = type

DOCUMENTATION = r"""
---
module: dynadot_ns
short_description: Points a domain at the given nameservers at Dynadot
description:
  - Asks public DNS first. When the world already resolves through the wanted
    nameservers, the registrar is not asked at all. When public DNS cannot be
    asked, the module stops without touching the registrar — a registrar write
    made on a guess changes the live delegation of a working site.
  - A domain Dynadot does not hold (bought at another registrar, or a zone
    Dynadot does not serve) is not a failure. The module warns that the
    nameservers have to be set where the domain was bought, and reports
    C(registrar_holds=false).
  - Dynadot answers 200 with the result code in the body, so the status line
    proves nothing; after a write the nameservers are read back.
  - In check mode nothing is written.
options:
  domain:
    description: The registered domain.
    type: str
    required: true
  nameservers:
    description: The nameservers to delegate to, usually the pair Cloudflare assigned.
    type: list
    elements: str
    required: true
  api_key:
    description:
      - Dynadot API key. Dynadot issues two; only the shorter "API Production
        Key" works with this endpoint, the longer secret belongs to the signed
        API and is refused here as an invalid key.
    type: str
    required: true
  api_url:
    description: Dynadot api3.json address; changed only by tests.
    type: str
    default: https://api.dynadot.com/api3.json
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
- name: Delegate the domain to the zone's nameservers
  haspadar.krot.dynadot_ns:
    domain: example.de
    nameservers: "{{ zone.name_servers }}"
    api_key: "{{ dynadot_key }}"
  delegate_to: localhost
  register: registrar
"""

RETURN = r"""
delegated:
  description: Whether public resolvers already see the wanted nameservers.
  type: bool
  returned: always
registrar_holds:
  description: Whether Dynadot holds the domain. False means it was bought elsewhere.
  type: bool
  returned: always
answers:
  description: What each public resolver reported.
  type: dict
  returned: always
registrar_nameservers:
  description: The nameservers Dynadot holds after the run.
  type: list
  elements: str
  returned: when registrar_holds
"""

from ansible.module_utils.basic import AnsibleModule

from ansible_collections.haspadar.krot.plugins.module_utils.api import Http, Unreachable
from ansible_collections.haspadar.krot.plugins.module_utils.delegation import (
    RESOLVERS,
    answers,
    delegated,
    normalised,
)

API_URL = "https://api.dynadot.com/api3.json"

# The only two refusals that mean "not ours". Every other refusal — a rate
# limit, an outage, a malformed answer — is a fault, and reported as "bought
# elsewhere" it would send someone to delegate by hand while the real reason
# scrolled past.
NOT_HELD = ("unsupported domain type", "could not find domain")


class Refused(Exception):
    pass


class NotHeld(Exception):
    pass


class Dynadot:
    def __init__(self, key, url):
        self.http = Http(url)
        self.key = key

    def call(self, command, section, **query):
        query = dict(query, key=self.key, command=command)
        status, answer = self.http.call("GET", "", query)
        if not isinstance(answer, dict):
            raise Unreachable("Dynadot answered %s with no body (HTTP %d)" % (command, status))
        # A refused key arrives under Response rather than under the command's own section.
        refusal = (answer.get("Response") or {}).get("Error") if isinstance(answer.get("Response"), dict) else None
        if isinstance(refusal, str):
            raise Refused("Dynadot rejected the request: %s" % refusal)
        part = answer.get(section)
        if not isinstance(part, dict):
            raise Unreachable("Dynadot answered %s without %s" % (command, section))
        code = part.get("ResponseCode")
        if str(code) == "0":
            return part
        reason = part.get("Error")
        if isinstance(reason, str) and any(marker in reason for marker in NOT_HELD):
            raise NotHeld(reason)
        raise Refused("Dynadot refused %s: %s" % (command, reason if isinstance(reason, str) else "no reason given"))

    def nameservers(self, domain):
        content = self.call("get_ns", "GetNsResponse", domain=domain).get("NsContent")
        if not isinstance(content, dict):
            return []
        # Reported as Host0, Host1, ... rather than as a list.
        return sorted(set(
            normalised(value) for field, value in content.items()
            if str(field).startswith("Host") and isinstance(value, str) and value
        ))

    def point(self, domain, nameservers):
        query = dict(("ns%d" % i, host) for i, host in enumerate(nameservers))
        # set_ns is a GET, so the HTTP layer may repeat it after a lost answer.
        # That is safe: setting the same nameservers twice leaves them the same.
        self.call("set_ns", "SetNsResponse", domain=domain, **query)


def main():
    module = AnsibleModule(
        argument_spec=dict(
            domain=dict(type="str", required=True),
            nameservers=dict(type="list", elements="str", required=True),
            api_key=dict(type="str", required=True, no_log=True),
            api_url=dict(type="str", default=API_URL),
            resolvers=dict(type="list", elements="str", default=RESOLVERS),
        ),
        supports_check_mode=True,
    )
    domain = module.params["domain"]
    wanted = sorted(set(normalised(host) for host in module.params["nameservers"] if host.strip()))
    if not wanted:
        module.fail_json(msg="Refusing to point %s at no nameservers" % domain)

    try:
        found = answers(domain, module.params["resolvers"])
    except Unreachable as error:
        module.fail_json(msg="Public DNS could not be asked, so the registrar is left alone: %s" % error)
    if delegated(found, wanted):
        module.exit_json(changed=False, delegated=True, registrar_holds=True, answers=found)

    dynadot = Dynadot(module.params["api_key"], module.params["api_url"])
    result = dict(delegated=False, answers=found)
    try:
        held = dynadot.nameservers(domain)
        if held == wanted:
            # Set already; the world has not caught up yet.
            module.exit_json(changed=False, registrar_holds=True, registrar_nameservers=held, **result)
        if module.check_mode:
            module.exit_json(changed=True, registrar_holds=True, registrar_nameservers=held, **result)

        dynadot.point(domain, wanted)
        held = dynadot.nameservers(domain)
        if held != wanted:
            module.fail_json(msg="Dynadot accepted the nameservers for %s but holds %s" % (domain, ", ".join(held) or "none"),
                             changed=True, registrar_holds=True, registrar_nameservers=held, **result)
        module.exit_json(changed=True, registrar_holds=True, registrar_nameservers=held, **result)
    except NotHeld as reason:
        module.warn("Dynadot does not hold %s (%s): it was bought elsewhere; set the nameservers %s at that registrar"
                    % (domain, reason, ", ".join(wanted)))
        module.exit_json(changed=False, registrar_holds=False, **result)
    except (Unreachable, Refused) as error:
        module.fail_json(msg=str(error))


if __name__ == "__main__":
    main()
