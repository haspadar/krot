#!/usr/bin/python
# -*- coding: utf-8 -*-
# MIT License

from __future__ import absolute_import, division, print_function

__metaclass__ = type

DOCUMENTATION = r"""
---
module: gsc_site
short_description: Proves a domain to Google, adds it to Search Console, shares it and submits its sitemap
description:
  - Works on the domain property (C(sc-domain:<domain>)), which covers every
    scheme and subdomain at once. A URL-prefix property would split one site
    into four fractions.
  - Always returns the TXT record that proves ownership. Between that and
    verification the caller writes the record into DNS, which is why
    verification is a separate switch.
  - Verification is retried while Google answers 400, which means the record is
    not visible yet. 401 and 403 are not retried — the key is revoked or an API
    is off for the project, and no amount of waiting fixes either.
  - Success is ownership (C(siteOwner)), not presence, since a property someone
    else verified is listed too.
  - Owners are written as the whole list, the service account included, because
    the call replaces the list, and leaving the account out would have it resign
    from the domain it has just proved.
  - The sitemap is submitted on every run; the run counts as a change only when
    Google did not list it before.
  - Needs the Search Console and Site Verification APIs enabled for the key's
    project, and the cryptography library on the machine running the module.
  - In check mode nothing is written.
options:
  domain:
    description: The domain, without scheme or subdomain.
    type: str
    required: true
  owners:
    description:
      - People to own the domain beside the service account, by Google account
        email. Without them only a service account nobody logs into owns it,
        and the operator's console shows nothing.
    type: list
    elements: str
    default: []
  verify:
    description: Verify ownership and add the property. The TXT record must already be in DNS.
    type: bool
    default: false
  sitemap_url:
    description: Sitemap to submit once the domain is owned.
    type: str
  wait_attempts:
    description: How many times to ask Google to verify while it cannot see the record yet.
    type: int
    default: 6
  wait_delay:
    description: Seconds between verification attempts.
    type: float
    default: 20
  owner_attempts:
    description: How many times to read the property back until it shows as owned.
    type: int
    default: 4
  owner_delay:
    description: Seconds between those reads.
    type: float
    default: 3
  service_account:
    description: The service account's key file, as JSON text.
    type: str
    required: true
  token_uri:
    description: Google's token address; changed only by tests.
    type: str
    default: https://oauth2.googleapis.com/token
  api_url:
    description: Address of the Site Verification and Search Console APIs; changed only by tests.
    type: str
    default: https://www.googleapis.com
requirements:
  - cryptography
author:
  - haspadar
"""

EXAMPLES = r"""
- name: Learn the TXT record that proves the domain
  haspadar.krot.gsc_site:
    domain: example.de
    service_account: "{{ google_key }}"
  delegate_to: localhost
  register: google

- name: Verify, share with the operator and submit the sitemap once the TXT is in DNS
  haspadar.krot.gsc_site:
    domain: example.de
    verify: true
    owners: ["{{ search_console_owner }}"]
    sitemap_url: https://example.de/sitemap.xml
    service_account: "{{ google_key }}"
  delegate_to: localhost
"""

RETURN = r"""
verification_record:
  description: The TXT record that proves ownership, as type, name and content.
  type: dict
  returned: always
verified:
  description: Whether the service account owns the domain in Search Console.
  type: bool
  returned: always
owners:
  description: The domain's owners after the run.
  type: list
  elements: str
  returned: when owners are given and the domain is verified
sitemap_submitted:
  description: Whether Google lists the sitemap.
  type: bool
  returned: when sitemap_url is given
"""

import time

from ansible.module_utils.basic import AnsibleModule, missing_required_lib
from ansible.module_utils.six.moves.urllib.parse import quote

from ansible_collections.haspadar.krot.plugins.module_utils.api import Unreachable, wait
from ansible_collections.haspadar.krot.plugins.module_utils.google import (
    ARGUMENTS,
    CRYPTOGRAPHY_ERROR,
    HAS_CRYPTOGRAPHY,
    Refused,
    ServiceAccount,
    call,
)

API_URL = "https://www.googleapis.com"
VERIFY_SCOPE = "https://www.googleapis.com/auth/siteverification"
CONSOLE_SCOPE = "https://www.googleapis.com/auth/webmasters"


class Google:
    def __init__(self, account, url, domain):
        self.account = account
        self.verification = account.http(url, VERIFY_SCOPE)
        self.console = account.http(url, CONSOLE_SCOPE)
        self.domain = domain
        self.site = dict(type="INET_DOMAIN", identifier=domain)
        self.resource = "/siteVerification/v1/webResource/" + quote("dns://" + domain, safe="")
        self.property = "/webmasters/v3/sites/" + quote("sc-domain:" + domain, safe="")

    def token(self):
        answer = call(self.verification, "POST", "/siteVerification/v1/token",
                      body=dict(site=self.site, verificationMethod="DNS_TXT"))
        proof = answer.get("token") if isinstance(answer, dict) else None
        if not proof:
            raise Unreachable("Google answered the verification token request without a token")
        return proof

    def owners(self):
        """The domain's owners, or None when the account has not verified it."""
        try:
            answer = call(self.verification, "GET", self.resource)
        except Refused as refusal:
            # Not verified by this account answers 404 or 403. The token
            # request before this proves the key and the API work, so neither
            # here is a broken key.
            if refusal.status in (403, 404):
                return None
            raise
        owners = answer.get("owners") if isinstance(answer, dict) else None
        # Google always names at least the verifying account, so an empty or
        # unreadable list is a broken answer, not a state — and sent back as the
        # complete list it would remove the service account from its own domain.
        if not isinstance(owners, list) or not owners:
            raise Unreachable("Google answered the owners of %s without a list of them" % self.domain)
        return owners

    def verified(self):
        return self.owners() is not None

    def verify(self, attempts, delay):
        for attempt in range(attempts):
            if attempt:
                time.sleep(delay)
            try:
                call(self.verification, "POST", "/siteVerification/v1/webResource",
                     query=dict(verificationMethod="DNS_TXT"), body=dict(site=self.site))
                return True
            except Refused as refusal:
                # 400 is "the record is not visible yet". Anything else — 401,
                # 403 — is a key or a project that waiting will not repair.
                if refusal.status != 400:
                    raise
        return False

    def permission(self):
        answer = call(self.console, "GET", "/webmasters/v3/sites")
        if not isinstance(answer, dict):
            raise Unreachable("Search Console answered the site list without a body")
        entries = answer.get("siteEntry", [])
        if not isinstance(entries, list):
            raise Unreachable("Search Console answered the site list without a list")
        for entry in entries:
            if isinstance(entry, dict) and entry.get("siteUrl") == "sc-domain:" + self.domain:
                return entry.get("permissionLevel")
        return None

    def sitemap_listed(self, url):
        try:
            call(self.console, "GET", self.property + "/sitemaps/" + quote(url, safe=""))
            return True
        except Refused as refusal:
            if refusal.status == 404:
                return False
            raise


def main():
    module = AnsibleModule(
        argument_spec=dict(
            domain=dict(type="str", required=True),
            owners=dict(type="list", elements="str", default=[]),
            verify=dict(type="bool", default=False),
            sitemap_url=dict(type="str"),
            wait_attempts=dict(type="int", default=6),
            wait_delay=dict(type="float", default=20),
            owner_attempts=dict(type="int", default=4),
            owner_delay=dict(type="float", default=3),
            api_url=dict(type="str", default=API_URL),
            **ARGUMENTS
        ),
        supports_check_mode=True,
    )
    if not HAS_CRYPTOGRAPHY:
        module.fail_json(msg=missing_required_lib("cryptography"), exception=CRYPTOGRAPHY_ERROR)
    p = module.params
    domain, sitemap, wanted = p["domain"], p["sitemap_url"], p["owners"]
    changed = False

    try:
        account = ServiceAccount(p["service_account"], p["token_uri"])
    except ValueError as error:
        module.fail_json(msg=str(error))

    try:
        google = Google(account, p["api_url"], domain)
        # Asking for the token writes nothing, so check mode asks too: the
        # record is what the caller needs to plan the DNS step.
        result = dict(verification_record=dict(type="TXT", name=domain, content=google.token()),
                      verified=google.verified())

        if p["verify"]:
            if not result["verified"]:
                if module.check_mode:
                    module.exit_json(changed=True, **result)
                if not google.verify(p["wait_attempts"], p["wait_delay"]):
                    module.fail_json(msg="Google does not see the TXT record for %s yet; run again once DNS has it" % domain,
                                     changed=changed, **result)
                changed = True
                result["verified"] = True
            if google.permission() != "siteOwner":
                if module.check_mode:
                    module.exit_json(changed=True, **result)
                call(google.console, "PUT", google.property)
                changed = True
                owned = wait(google.permission, lambda level: level == "siteOwner", p["owner_attempts"], p["owner_delay"])
                if owned != "siteOwner":
                    module.fail_json(msg="Search Console lists %s but not as owned by this account" % domain,
                                     changed=changed, **result)

        if wanted:
            if not result["verified"]:
                module.fail_json(msg="Only a verified domain can be shared; verify %s first" % domain, changed=changed, **result)
            owners = google.owners() or []
            missing = [owner for owner in wanted if owner not in owners]
            if missing:
                if module.check_mode:
                    module.exit_json(changed=True, owners=owners, **result)
                call(google.verification, "PUT", google.resource,
                     body=dict(id="dns://" + domain, site=google.site, owners=owners + missing))
                changed = True
                owners = google.owners() or []
                if any(owner not in owners for owner in wanted):
                    module.fail_json(msg="Google accepted the owners of %s but does not list them" % domain,
                                     changed=changed, owners=owners, **result)
            result["owners"] = owners

        if sitemap:
            if not result["verified"]:
                module.fail_json(msg="Search Console takes a sitemap only from an owned domain; verify %s first" % domain,
                                 changed=changed, sitemap_submitted=False, **result)
            listed = google.sitemap_listed(sitemap)
            if module.check_mode:
                module.exit_json(changed=changed or not listed, sitemap_submitted=listed, **result)
            # Every run, not only the first: a fresh submission asks Google to
            # read the map again. Only a sitemap Google did not list is a change.
            call(google.console, "PUT", google.property + "/sitemaps/" + quote(sitemap, safe=""))
            changed = changed or not listed
            result["sitemap_submitted"] = google.sitemap_listed(sitemap)
            if not result["sitemap_submitted"]:
                module.fail_json(msg="Search Console accepted the sitemap but does not list it", changed=changed, **result)

        module.exit_json(changed=changed, **result)
    except (Unreachable, Refused) as error:
        module.fail_json(msg=str(error), changed=changed)


if __name__ == "__main__":
    main()
