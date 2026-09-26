#!/usr/bin/python
# -*- coding: utf-8 -*-
# MIT License

from __future__ import absolute_import, division, print_function

__metaclass__ = type

DOCUMENTATION = r"""
---
module: bing_site
short_description: Adds a site to Bing Webmaster Tools, verifies it and submits its sitemap
description:
  - Three stages, each run only when asked for and only when not done yet.
    Between the first two the caller writes the returned CNAME into DNS,
    which is why verification is a separate switch.
  - Adding returns the ownership record. Bing mints the record's name when the
    site is added and publishes it with a delay, so the module waits for it.
    The name already contains the domain and is used as it comes.
  - Bing refuses a sitemap for a few minutes after verification
    (InvalidParameter); the module waits that out. A throttled account
    (ThrottleUser) is not waited for, it lasts hours.
  - In check mode nothing is written.
options:
  domain:
    description: The site's domain; the site is registered as C(https://<domain>/).
    type: str
    required: true
  verify:
    description: Verify ownership. The CNAME from an earlier run must already be in DNS.
    type: bool
    default: false
  sitemap_url:
    description: Sitemap to submit once the site is verified.
    type: str
  wait_attempts:
    description: How many times to ask while Bing is not ready yet.
    type: int
    default: 6
  wait_delay:
    description: Seconds between those attempts.
    type: float
    default: 20
  api_key:
    description: Bing Webmaster API key.
    type: str
    required: true
  api_url:
    description: Bing Webmaster API address; changed only by tests.
    type: str
    default: https://ssl.bing.com/webmaster/api.svc/json
author:
  - haspadar
"""

EXAMPLES = r"""
- name: Add the site and learn the ownership record
  haspadar.krot.bing_site:
    domain: example.de
    api_key: "{{ bing_key }}"
  delegate_to: localhost
  register: bing

- name: Verify and submit the sitemap once the CNAME is in DNS
  haspadar.krot.bing_site:
    domain: example.de
    verify: true
    sitemap_url: https://example.de/sitemap.xml
    api_key: "{{ bing_key }}"
  delegate_to: localhost
"""

RETURN = r"""
added:
  description: Whether the site is in the account. False only in check mode.
  type: bool
  returned: always
verified:
  description: Whether Bing holds the site as verified.
  type: bool
  returned: always
verification_record:
  description: The CNAME that proves ownership, as type, name and content.
  type: dict
  returned: when added
sitemap_submitted:
  description: Whether the sitemap is among the site's feeds.
  type: bool
  returned: when sitemap_url is given
"""

import json
import time

from ansible.module_utils.basic import AnsibleModule
from ansible.module_utils.six.moves.urllib.parse import urlparse

from ansible_collections.haspadar.krot.plugins.module_utils.api import Http, Unreachable, wait

API_URL = "https://ssl.bing.com/webmaster/api.svc/json"

# Bing's ErrorCode values that change what the module does.
THROTTLE_USER = 4
INVALID_PARAMETER = 8


class Refused(Exception):
    def __init__(self, method, answer):
        self.code = answer.get("ErrorCode") if isinstance(answer, dict) else None
        self.text = json.dumps(answer)
        super(Refused, self).__init__("Bing refused %s: %s" % (method, self.text))

    def too_early(self):
        return self.code == INVALID_PARAMETER or "InvalidParameter" in self.text


class Bing:
    def __init__(self, key, url):
        self.http = Http(url)
        self.key = key

    def call(self, method, verb="GET", query=None, body=None):
        status, answer = self.http.call(verb, "/" + method, dict(query or {}, apikey=self.key), body)
        if status >= 400:
            refusal = Refused(method, answer)
            if refusal.code == THROTTLE_USER:
                raise Unreachable("Bing throttles this account (ThrottleUser); it lasts hours, run again later")
            raise refusal
        # Success is {"d": ...}; {"d": null} is how a write reports it worked.
        if not isinstance(answer, dict) or "d" not in answer:
            raise Unreachable("Bing answered %s without its d field" % method)
        return answer["d"]

    def site(self, domain):
        sites = self.call("GetUserSites")
        # An account with no sites answers an empty list. Anything that is not
        # a list is not an answer, and reading it as "absent" would add the
        # site a second time.
        if not isinstance(sites, list):
            raise Unreachable("Bing answered GetUserSites without a list")
        for site in sites:
            if isinstance(site, dict) and urlparse(site.get("Url") or "").hostname == domain:
                return site
        return None

    def feeds(self, url):
        feeds = self.call("GetFeeds", query={"siteUrl": url})
        if feeds is None:
            return []
        if not isinstance(feeds, list):
            raise Unreachable("Bing answered GetFeeds without a list")
        return [feed.get("Url") for feed in feeds if isinstance(feed, dict)]


def record(site):
    return dict(type="CNAME", name=site["DnsVerificationCode"], content="verify.bing.com")


def main():
    module = AnsibleModule(
        argument_spec=dict(
            domain=dict(type="str", required=True),
            verify=dict(type="bool", default=False),
            sitemap_url=dict(type="str"),
            wait_attempts=dict(type="int", default=6),
            wait_delay=dict(type="float", default=20),
            api_key=dict(type="str", required=True, no_log=True),
            api_url=dict(type="str", default=API_URL),
        ),
        supports_check_mode=True,
    )
    p = module.params
    domain, sitemap = p["domain"], p["sitemap_url"]
    url = "https://%s/" % domain
    bing = Bing(p["api_key"], p["api_url"])
    attempts, delay = p["wait_attempts"], p["wait_delay"]
    changed = False

    def published(site):
        return site is not None and bool(site.get("DnsVerificationCode"))

    try:
        site = bing.site(domain)
        if site is None:
            if module.check_mode:
                module.exit_json(changed=True, added=False, verified=False)
            bing.call("AddSite", "POST", body={"siteUrl": url})
            changed = True
            site = wait(lambda: bing.site(domain), published, attempts, delay)
            if site is None:
                module.fail_json(msg="Bing accepted %s but does not list it" % domain, changed=True)

        if not published(site):
            # Usually a delay rather than a refusal: the next run finds it.
            module.fail_json(msg="Bing has not published the verification name for %s yet; run again in a minute" % domain,
                             changed=changed)

        result = dict(added=True, verification_record=record(site), verified=site.get("IsVerified") is True)

        if p["verify"] and not result["verified"]:
            if module.check_mode:
                module.exit_json(changed=True, **result)
            # VerifySite answers false until Bing's resolver sees the CNAME.
            wait(lambda: bing.call("VerifySite", "POST", body={"siteUrl": url}), lambda d: d is True, attempts, delay)
            changed = True
            again = bing.site(domain)
            result["verified"] = again is not None and again.get("IsVerified") is True
            if not result["verified"]:
                module.fail_json(msg="Bing does not see the CNAME for %s yet; run again once DNS has it" % domain,
                                 changed=changed, **result)

        if sitemap:
            submitted = sitemap in bing.feeds(url) if result["verified"] else False
            if not submitted:
                if module.check_mode:
                    module.exit_json(changed=True, sitemap_submitted=False, **result)
                if not result["verified"]:
                    module.fail_json(msg="Bing takes a sitemap only from a verified site; verify %s first" % domain,
                                     changed=changed, sitemap_submitted=False, **result)
                submit(bing, url, sitemap, attempts, delay)
                changed = True
                submitted = sitemap in bing.feeds(url)
                if not submitted:
                    module.fail_json(msg="Bing accepted the sitemap but does not list it", changed=changed,
                                     sitemap_submitted=False, **result)
            result["sitemap_submitted"] = submitted

        module.exit_json(changed=changed, **result)
    except (Unreachable, Refused) as error:
        module.fail_json(msg=str(error), changed=changed)


def submit(bing, url, sitemap, attempts, delay):
    for attempt in range(attempts):
        if attempt:
            time.sleep(delay)
        try:
            bing.call("SubmitFeed", "POST", body={"siteUrl": url, "feedUrl": sitemap})
            return
        except Refused as refusal:
            # Right after verification Bing refuses the feed for a few minutes.
            if not refusal.too_early() or attempt == attempts - 1:
                raise


if __name__ == "__main__":
    main()
