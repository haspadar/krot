#!/usr/bin/python
# -*- coding: utf-8 -*-
# MIT License

from __future__ import absolute_import, division, print_function

__metaclass__ = type

DOCUMENTATION = r"""
---
module: yandex_site
short_description: Adds a site to Yandex Webmaster, verifies it and submits its sitemap
description:
  - Three stages, each run only when asked for and only when not done yet.
    Between the first two the caller writes the returned TXT record into DNS,
    which is why verification is a separate switch.
  - Yandex holds a site not under its domain but under an address it spells
    itself (C(https:example.de:443)), so the host is always looked up, never
    built. It is matched on the host part of the address, so a site added over
    plain http earlier is found rather than added a second time.
  - The verification token is minted a while after the host is added; the
    module waits for it. The TXT value is the whole line, the
    C(yandex-verification) prefix with the token after it; a bare token does
    not match.
  - Sitemaps go to C(user-added-sitemaps). The neighbouring C(sitemaps) is
    read-only and answers a write with RESOURCE_NOT_FOUND.
  - HOST_NOT_LOADED — Yandex has not crawled the site yet — lasts weeks on a
    new site and is not a failure; the module warns and reports the sitemap
    as not submitted.
  - In check mode nothing is written.
options:
  domain:
    description: The site's domain; the host is added as C(https://<domain>).
    type: str
    required: true
  verify:
    description: Verify ownership. The TXT record from an earlier run must already be in DNS.
    type: bool
    default: false
  sitemap_url:
    description: Sitemap to submit once the site is verified.
    type: str
  wait_attempts:
    description: How many times to ask while Yandex is not ready yet.
    type: int
    default: 6
  wait_delay:
    description: Seconds between those attempts.
    type: float
    default: 20
  oauth_token:
    description: OAuth token of the Yandex account that holds the sites.
    type: str
    required: true
  api_url:
    description: Yandex Webmaster API address; changed only by tests.
    type: str
    default: https://api.webmaster.yandex.net/v4
author:
  - haspadar
"""

EXAMPLES = r"""
- name: Add the site and learn the ownership record
  haspadar.krot.yandex_site:
    domain: example.de
    oauth_token: "{{ yandex_token }}"
  delegate_to: localhost
  register: yandex

- name: Verify and submit the sitemap once the TXT is in DNS
  haspadar.krot.yandex_site:
    domain: example.de
    verify: true
    sitemap_url: https://example.de/sitemap.xml
    oauth_token: "{{ yandex_token }}"
  delegate_to: localhost
"""

RETURN = r"""
added:
  description: Whether the host is in the account. False only in check mode.
  type: bool
  returned: always
host_id:
  description: The address Yandex holds the site under.
  type: str
  returned: when added
verified:
  description: Whether Yandex holds the site as verified.
  type: bool
  returned: always
verification_record:
  description: The TXT record that proves ownership, as type, name and content.
  type: dict
  returned: when added
sitemap_submitted:
  description: Whether the sitemap is among the user-added sitemaps.
  type: bool
  returned: when sitemap_url is given
"""

from ansible.module_utils.basic import AnsibleModule
from ansible.module_utils.six.moves.urllib.parse import urlparse

from ansible_collections.haspadar.krot.plugins.module_utils.api import Http, Unreachable, wait

API_URL = "https://api.webmaster.yandex.net/v4"

ALREADY_ADDED = "SITEMAP_ALREADY_ADDED"
NOT_LOADED = "HOST_NOT_LOADED"


class Refused(Exception):
    def __init__(self, what, status, answer):
        self.code = answer.get("error_code") if isinstance(answer, dict) else None
        message = answer.get("error_message") if isinstance(answer, dict) else None
        super(Refused, self).__init__("Yandex refused %s (HTTP %d): %s %s" % (
            what, status, self.code or "", message or "no reason given"))


class Yandex:
    def __init__(self, token, url):
        self.http = Http(url, headers={"Authorization": "OAuth " + token})
        self._user = None

    def call(self, method, path, query=None, body=None):
        status, answer = self.http.call(method, path, query, body)
        if status >= 400:
            raise Refused("%s %s" % (method, path), status, answer)
        if not isinstance(answer, dict):
            raise Unreachable("Yandex answered %s %s without a body" % (method, path))
        return answer

    def user(self):
        if self._user is None:
            user = self.call("GET", "/user").get("user_id")
            # A number in the answer and a path segment here; either spelling is the
            # same account. Anything else is not an answer.
            if isinstance(user, bool) or not isinstance(user, (int, str)) or str(user) == "":
                raise Unreachable("Yandex answered /user without a user_id")
            self._user = str(user)
        return self._user

    def host(self, domain):
        hosts = self.call("GET", "/user/%s/hosts" % self.user()).get("hosts")
        if not isinstance(hosts, list):
            raise Unreachable("Yandex answered the host list without a list")
        for host in hosts:
            if not isinstance(host, dict):
                continue
            # Both spellings: a site named in Cyrillic carries only the unicode one.
            url = host.get("ascii_host_url") or host.get("unicode_host_url") or ""
            if urlparse(url).hostname == domain and host.get("host_id"):
                return host["host_id"]
        return None

    def path(self, host, tail):
        return "/user/%s/hosts/%s%s" % (self.user(), host, tail)

    def verification(self, host):
        return self.call("GET", self.path(host, "/verification"))

    def sitemaps(self, host):
        sitemaps = self.call("GET", self.path(host, "/user-added-sitemaps")).get("sitemaps")
        if sitemaps is None:
            return []
        if not isinstance(sitemaps, list):
            raise Unreachable("Yandex answered user-added-sitemaps without a list")
        return [s.get("sitemap_url") for s in sitemaps if isinstance(s, dict)]


def main():
    module = AnsibleModule(
        argument_spec=dict(
            domain=dict(type="str", required=True),
            verify=dict(type="bool", default=False),
            sitemap_url=dict(type="str"),
            wait_attempts=dict(type="int", default=6),
            wait_delay=dict(type="float", default=20),
            oauth_token=dict(type="str", required=True, no_log=True),
            api_url=dict(type="str", default=API_URL),
        ),
        supports_check_mode=True,
    )
    p = module.params
    domain, sitemap = p["domain"], p["sitemap_url"]
    attempts, delay = p["wait_attempts"], p["wait_delay"]
    yandex = Yandex(p["oauth_token"], p["api_url"])
    changed = False

    try:
        host = yandex.host(domain)
        if host is None:
            if module.check_mode:
                module.exit_json(changed=True, added=False, verified=False)
            yandex.call("POST", "/user/%s/hosts" % yandex.user(), body={"host_url": "https://%s" % domain})
            changed = True
            host = yandex.host(domain)
            if host is None:
                module.fail_json(msg="Yandex accepted %s but does not list it" % domain, changed=True)

        state = wait(lambda: yandex.verification(host), lambda s: bool(s.get("verification_uin")), attempts, delay)
        uin = state.get("verification_uin")
        if not uin:
            # Usually a delay rather than a refusal: the next run finds it.
            module.fail_json(msg="Yandex has not minted a verification token for %s yet; run again in a minute" % domain,
                             changed=changed, host_id=host)

        result = dict(added=True, host_id=host, verified=state.get("verification_state") == "VERIFIED",
                      verification_record=dict(type="TXT", name=domain, content="yandex-verification: %s" % uin))

        if p["verify"] and not result["verified"]:
            if module.check_mode:
                module.exit_json(changed=True, **result)
            # IN_PROGRESS means a check Yandex already runs; starting another only
            # restarts it.
            if state.get("verification_state") != "IN_PROGRESS":
                yandex.call("POST", yandex.path(host, "/verification"), query={"verification_type": "DNS"})
                changed = True
            state = wait(lambda: yandex.verification(host), lambda s: s.get("verification_state") == "VERIFIED",
                         attempts, delay)
            result["verified"] = state.get("verification_state") == "VERIFIED"
            if not result["verified"]:
                module.fail_json(msg="Yandex has not verified %s yet (%s); run again once DNS has the TXT record"
                                 % (domain, state.get("verification_state") or "no state"), changed=changed, **result)

        if sitemap:
            submitted = result["verified"] and sitemap in yandex.sitemaps(host)
            if not submitted:
                if module.check_mode:
                    module.exit_json(changed=True, sitemap_submitted=False, **result)
                if not result["verified"]:
                    module.fail_json(msg="Yandex takes a sitemap only from a verified site; verify %s first" % domain,
                                     changed=changed, sitemap_submitted=False, **result)
                try:
                    yandex.call("POST", yandex.path(host, "/user-added-sitemaps"), body={"url": sitemap})
                    changed = True
                except Refused as refusal:
                    if refusal.code == NOT_LOADED:
                        module.warn("Yandex has not loaded %s yet (HOST_NOT_LOADED); new sites stay so for weeks, "
                                    "the sitemap goes in on a later run" % domain)
                        module.exit_json(changed=changed, sitemap_submitted=False, **result)
                    # Handing over a map Yandex already holds is an error to it, and
                    # the ordinary answer on every run after the first.
                    if refusal.code != ALREADY_ADDED:
                        raise
                submitted = sitemap in yandex.sitemaps(host)
                if not submitted:
                    module.fail_json(msg="Yandex accepted the sitemap but does not list it", changed=changed,
                                     sitemap_submitted=False, **result)
            result["sitemap_submitted"] = submitted

        module.exit_json(changed=changed, **result)
    except (Unreachable, Refused) as error:
        module.fail_json(msg=str(error), changed=changed)


if __name__ == "__main__":
    main()
