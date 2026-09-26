"""Umami's API as far as umami_website uses it, served under a base path.

The base path is the point: busel serves Umami under /counter, and a request
that leaves it out gets a 404 rather than a login.
"""

import itertools

# Made-up account: it exists only between a test and this fake, on 127.0.0.1.
USERNAME = "admin"
PASSWORD = "umami-pass"  # secret-lint: allow — fake password, never leaves the test process


class FakeUmami:
    def __init__(self, base="/counter"):
        self.base = base
        self.websites = []
        self.ids = itertools.count(1)
        self.session = "session-7"
        # Knobs for the failures worth testing.
        self.bare_list = False
        self.broken_listing = False
        self.hides_new = False

    def add_website(self, domain):
        site = {"id": "site-%d" % next(self.ids), "name": domain, "domain": domain}
        self.websites.append(site)
        return site

    def handle(self, request):
        if not request.path.startswith(self.base + "/"):
            return 404, None
        path = request.path[len(self.base):]

        if path == "/api/auth/login" and request.method == "POST":
            if (request.body or {}).get("username") != USERNAME or request.body.get("password") != PASSWORD:
                return 401, {"error": "Incorrect username and/or password."}
            return 200, {"token": self.session, "user": {"username": USERNAME}}

        if request.headers.get("Authorization") != "Bearer " + self.session:
            return 401, {"error": "Unauthorized"}

        if path == "/api/websites" and request.method == "GET":
            if self.broken_listing:
                return 200, {"rows": []}
            term = request.query.get("search", "")
            found = [site for site in self.websites if term in site["domain"]]
            return 200, (found if self.bare_list else {"data": found, "count": len(found)})

        if path == "/api/websites" and request.method == "POST":
            site = self.add_website(request.body["domain"])
            if self.hides_new:
                self.websites.remove(site)
            return 200, site

        return 404, None
