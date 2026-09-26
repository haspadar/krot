#!/usr/bin/python
# -*- coding: utf-8 -*-
# MIT License

from __future__ import absolute_import, division, print_function

__metaclass__ = type

DOCUMENTATION = r"""
---
module: umami_website
short_description: Finds or creates a website in a self-hosted Umami and returns its id
description:
  - Meant to run on the machine that hosts Umami, against its API on the
    loopback address, so no tunnel is needed and nothing but Umami writes to
    its database.
  - Looks the website up by domain first and creates it only when the lookup
    answered with nothing. A lookup that failed stops the module instead.
  - In check mode nothing is created.
options:
  domain:
    description: The site's domain, as Umami stores it.
    type: str
    required: true
  api_url:
    description:
      - Umami's address including its base path, for example
        C(http://127.0.0.1:3000/counter) where Umami is served under /counter.
      - A missing base path answers 404 on login, which the module reports as
        a wrong address rather than a refused login.
    type: str
    required: true
  username:
    description: Umami login.
    type: str
    required: true
  password:
    description: Umami password.
    type: str
    required: true
author:
  - haspadar
"""

EXAMPLES = r"""
- name: Find or create the site's counter
  haspadar.krot.umami_website:
    domain: example.de
    api_url: "http://127.0.0.1:{{ umami_port }}{{ umami_base_path }}"
    username: "{{ umami_login }}"
    password: "{{ umami_password }}"
  register: umami
"""

RETURN = r"""
exists:
  description: Whether the website exists after the run. False only in check mode.
  type: bool
  returned: always
website_id:
  description: Umami's id of the website.
  type: str
  returned: when exists
"""

from ansible.module_utils.basic import AnsibleModule

from ansible_collections.haspadar.krot.plugins.module_utils.api import Http, Unreachable


class Refused(Exception):
    """Umami answered and said no."""


class Umami:
    def __init__(self, url):
        self.url = url
        self.http = Http(url)

    def login(self, username, password):
        try:
            status, answer = self.http.call("POST", "/api/auth/login", body={"username": username, "password": password})
        except Unreachable as error:
            # Served under a base path (busel's /counter), Umami answers the
            # path without it with the web app's own 404 page — not JSON, and
            # easy to mistake for Umami being down.
            raise Unreachable("%s; check that %s includes Umami's base path" % (error, self.url))
        if status == 404:
            raise Refused("%s has no Umami login; check that it includes Umami's base path" % self.url)
        if status >= 400:
            raise Refused("Umami refused the login (HTTP %d)" % status)
        session = answer.get("token") if isinstance(answer, dict) else None
        if not session:
            raise Unreachable("Umami answered the login without a token")
        self.http.headers["Authorization"] = "Bearer " + session

    def website(self, domain):
        status, answer = self.http.call("GET", "/api/websites", {"search": domain, "pageSize": 100})
        if status >= 400:
            raise Refused("Umami refused the website lookup (HTTP %d)" % status)
        # Umami 2 wraps the list in `data`, Umami 1 answers the bare list.
        # Anything else is not an answer, and reading it as "no website" would
        # create a second one.
        websites = answer.get("data") if isinstance(answer, dict) else answer
        if not isinstance(websites, list):
            raise Unreachable("Umami answered the website lookup without a list")
        # `search` matches substrings, so shop.de would also find myshop.de.
        found = [site for site in websites if isinstance(site, dict) and site.get("domain") == domain]
        return found[0] if found else None


def main():
    module = AnsibleModule(
        argument_spec=dict(
            domain=dict(type="str", required=True),
            api_url=dict(type="str", required=True),
            username=dict(type="str", required=True),
            password=dict(type="str", required=True, no_log=True),
        ),
        supports_check_mode=True,
    )
    domain = module.params["domain"]
    umami = Umami(module.params["api_url"])
    changed = False

    try:
        umami.login(module.params["username"], module.params["password"])
        site = umami.website(domain)
        if site is None:
            if module.check_mode:
                module.exit_json(changed=True, exists=False)
            status, _ = umami.http.call("POST", "/api/websites", body={"name": domain, "domain": domain})
            if status >= 400:
                raise Refused("Umami refused to create %s (HTTP %d)" % (domain, status))
            changed = True
            # The creation's answer is not the proof; the website being findable is.
            site = umami.website(domain)
            if site is None:
                module.fail_json(msg="Umami accepted %s but does not list it" % domain, changed=True)
        if not site.get("id"):
            module.fail_json(msg="Umami lists %s without an id" % domain, changed=changed)
        module.exit_json(changed=changed, exists=True, website_id=str(site["id"]))
    except (Unreachable, Refused) as error:
        module.fail_json(msg=str(error), changed=changed)


if __name__ == "__main__":
    main()
