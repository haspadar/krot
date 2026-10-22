#!/usr/bin/python
# -*- coding: utf-8 -*-
# MIT License

from __future__ import absolute_import, division, print_function

__metaclass__ = type

DOCUMENTATION = r"""
---
module: gsc_access
short_description: Makes the key that collects search data an owner of a Search Console domain, and proves it
description:
  - Asks Search Console, with the collecting key, what that key may do on the domain property
    (C(sites.get) on C(sc-domain:<domain>)). C(siteOwner) is the answer wanted, because the
    Indexing API takes pages only from an owner; when that is the answer, nothing is written.
  - When the collecting key is not an owner, the launching key adds it to the domain's owners
    (Site Verification C(webResource), the list M(haspadar.krot.gsc_site) shares with people), the
    collecting key adds the property to its own Search Console, and the level is read again until
    it is C(siteOwner) or the attempts run out.
  - Fails, rather than leaving a 403 for the collector's next night, when the launching key cannot
    add owners (it is not a verified owner of the domain) or the ownership does not show. The
    message names the collecting key's address and the manual step.
  - Grants only on Google's own words for a key without rights on the property. Any other refusal
    (the Search Console API switched off in the collecting key's project, a wrong address) fails
    as it is, with Google's reason, and nothing is written.
  - The owners list is written whole with the existing owners kept, because the call replaces
    the list. Nobody is ever removed.
  - A collecting key that is the launching key is never added to anything; it only adds the
    property to its own Search Console when the verification left it out.
  - Needs the Search Console and Site Verification APIs enabled for the keys' projects, and the
    cryptography library on the machine running the module.
  - In check mode nothing is written; C(owner) says whether the collecting key owns the domain now
    and C(grantable) whether the launching key could make it one.
options:
  domain:
    description: The domain, without scheme or subdomain.
    type: str
    required: true
  service_account:
    description: The launching key, as JSON text. The one that verified the domain.
    type: str
    required: true
  reader_service_account:
    description: The key that collects search data and sends pages, as JSON text. The key this module makes an owner.
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
  wait_attempts:
    description: How many times the level is read after the grant before giving up.
    type: int
    default: 8
  wait_delay:
    description: Seconds between those reads.
    type: int
    default: 4
requirements:
  - cryptography
author:
  - haspadar
"""

EXAMPLES = r"""
- name: The collecting key owns the domain it will read and send pages of
  haspadar.krot.gsc_access:
    domain: example.de
    service_account: "{{ launch_key }}"
    reader_service_account: "{{ collecting_key }}"
  delegate_to: localhost
"""

RETURN = r"""
reader:
  description: The collecting key's address.
  type: str
  returned: always
owner:
  description: Whether the collecting key owns the domain property — after the run, or now in check mode.
  type: bool
  returned: success
granted:
  description: Whether this run added the collecting key to the domain's owners.
  type: bool
  returned: always
grantable:
  description: Whether the launching key is a verified owner of the domain and so could add the collecting key.
  type: bool
  returned: in check mode, when the collecting key is not an owner
"""

import time

from ansible.module_utils.basic import AnsibleModule, missing_required_lib
from ansible.module_utils.six.moves.urllib.parse import quote

from ansible_collections.haspadar.krot.plugins.module_utils.api import Unreachable
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
OWNER = "siteOwner"


def level(console, site):
    """The key's permission level on the property, or None when Google says it has none.

    Only Google's own words count as none: 404 "is not a verified Search Console site in
    this account" and 403 "does not have sufficient permission" — both measured on
    2026-10-22 for a key without rights on a domain. A 404 from a wrong address or a 403
    from a switched-off API is not a missing right, and granting would not cure it: it
    propagates, and nothing is written.
    """
    try:
        answer = call(console, "GET", "/webmasters/v3/sites/" + quote(site, safe=""))
    except Refused as error:
        words = str(error).lower()
        if ((error.status == 404 and "not a verified search console site" in words)
                or (error.status == 403 and "sufficient permission" in words)):
            return None
        raise
    found = answer.get("permissionLevel") if isinstance(answer, dict) else None
    if not isinstance(found, str) or answer.get("siteUrl") != site:
        raise Unreachable("Search Console answered %s without its permission level" % site)
    return found


def owners(verification, resource, domain):
    """The domain's owners as the launching key sees them, or None when it is not one of them."""
    try:
        answer = call(verification, "GET", resource)
    except Refused as error:
        # A domain this key has not verified answers 404, or 403 as Google often does.
        if error.status in (403, 404):
            return None
        raise
    found = answer.get("owners") if isinstance(answer, dict) else None
    # Google always names at least the verifying account. An empty or unreadable list is a
    # broken answer, and written back with one more name it would drop every other owner.
    if not isinstance(found, list) or not found:
        raise Unreachable("Google answered the owners of %s without a list of them" % domain)
    return found


def main():
    module = AnsibleModule(
        argument_spec=dict(
            domain=dict(type="str", required=True),
            reader_service_account=dict(type="str", required=True, no_log=True),
            api_url=dict(type="str", default=API_URL),
            wait_attempts=dict(type="int", default=8),
            wait_delay=dict(type="int", default=4),
            **ARGUMENTS
        ),
        supports_check_mode=True,
    )
    if not HAS_CRYPTOGRAPHY:
        module.fail_json(msg=missing_required_lib("cryptography"), exception=CRYPTOGRAPHY_ERROR)
    p = module.params
    domain = p["domain"]
    site = "sc-domain:" + domain
    resource = "/siteVerification/v1/webResource/" + quote("dns://" + domain, safe="")
    prop = "/webmasters/v3/sites/" + quote(site, safe="")

    try:
        launcher = ServiceAccount(p["service_account"], p["token_uri"])
        reader = ServiceAccount(p["reader_service_account"], p["token_uri"])
    except ValueError as error:
        module.fail_json(msg=str(error))

    manual = ("Make %s an owner of %s: Search Console > Settings > Users and permissions > Add user, "
              "permission Owner, signed in as a verified owner of the domain; then run again."
              % (reader.email, site))
    granted = False

    try:
        console = reader.http(p["api_url"], CONSOLE_SCOPE)
        first = level(console, site)
        if first == OWNER:
            module.exit_json(changed=False, owner=True, granted=False, reader=reader.email)

        verification = launcher.http(p["api_url"], VERIFY_SCOPE)
        listed = owners(verification, resource, domain)

        if module.check_mode:
            module.exit_json(changed=True, owner=False, granted=False, grantable=listed is not None,
                             reader=reader.email)

        if listed is None:
            module.fail_json(msg="%s cannot make %s an owner of %s: it is not a verified owner of the domain. %s"
                                 % (launcher.email, reader.email, site, manual), granted=False, reader=reader.email)

        if reader.email not in listed:
            call(verification, "PUT", resource,
                 body=dict(id="dns://" + domain, site=dict(type="INET_DOMAIN", identifier=domain),
                           owners=listed + [reader.email]))
            granted = True
            after = owners(verification, resource, domain)
            if after is None or reader.email not in after:
                module.fail_json(msg="Google accepted %s as an owner of %s but does not list it. %s"
                                     % (reader.email, domain, manual), changed=True, granted=True,
                                 reader=reader.email)

        attempts = max(p["wait_attempts"], 1)
        now = first
        added = False
        for attempt in range(attempts):
            if attempt:
                time.sleep(p["wait_delay"])
            # An owner by Site Verification still has to add the property to its own Search
            # Console before sites.get answers for it; adding is idempotent. Refused with 403
            # while the ownership has not reached Search Console: the next read waits for it.
            try:
                call(console, "PUT", prop)
                added = True
            except Refused as error:
                if error.status != 403:
                    raise
            now = level(console, site)
            if now == OWNER:
                module.exit_json(changed=granted or added, owner=True, granted=granted, reader=reader.email)
        module.fail_json(
            msg="%s is still not an owner of %s after %d reads, %ds apart (level: %s). %s"
                % (reader.email, site, attempts, p["wait_delay"], now or "none", manual),
            changed=granted or added, granted=granted, reader=reader.email)
    except (Unreachable, Refused) as error:
        module.fail_json(msg=str(error), changed=granted, granted=granted, reader=reader.email)


if __name__ == "__main__":
    main()
