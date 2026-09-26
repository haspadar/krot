"""Yandex Webmaster API v4 as far as yandex_site uses it.

Reproduces what makes the module wait or tolerate: the verification token is
minted a few reads after the host is added, verification sits IN_PROGRESS for
a while, a sitemap Yandex already holds is refused as SITEMAP_ALREADY_ADDED,
and a new host refuses sitemaps as HOST_NOT_LOADED.
"""

import re

# Made-up token: it exists only between a test and this fake, on 127.0.0.1.
TOKEN = "ya-oauth"  # secret-lint: allow — fake token, never leaves the test process

USER = 4711


def refused(status, code, message):
    return status, {"error_code": code, "error_message": message}


class FakeYandex:
    def __init__(self, token=TOKEN):
        self.token = token
        self.hosts = []
        self.sitemaps = {}
        self.states = {}
        # Reads of the verification before a new host's token shows up.
        self.uin_delay = 0
        # Verification reads answered IN_PROGRESS after a check is started.
        self.progress_reads = 0
        # A started check that ends VERIFICATION_FAILED instead of VERIFIED.
        self.fails_verification = False
        self.not_loaded = False
        # The user id sent as a string, as Yandex is free to.
        self.user_as_text = False
        # A sitemap that is held but, like a race with another run, not yet listed.
        self.hidden_sitemaps = []
        # The host list answered without its hosts field.
        self.host_list_broken = False
        self._pending_uin = {}

    def add_host(self, domain, verified=False, scheme="https", unicode_only=False):
        port = 443 if scheme == "https" else 80
        host = {"host_id": "%s:%s:%d" % (scheme, domain, port), "verified": verified}
        url = "%s://%s/" % (scheme, domain)
        host["unicode_host_url"] = url
        if not unicode_only:
            host["ascii_host_url"] = url
        self.hosts.append(host)
        self.states[host["host_id"]] = "VERIFIED" if verified else "NONE"
        self.sitemaps[host["host_id"]] = []
        return host

    def handle(self, request):
        if request.headers.get("Authorization") != "OAuth " + self.token:
            return refused(401, "INVALID_OAUTH_TOKEN", "Invalid oauth token")
        path, method = request.path, request.method

        if path == "/user" and method == "GET":
            return 200, {"user_id": str(USER) if self.user_as_text else USER}

        if path == "/user/%d/hosts" % USER:
            if method == "GET":
                if self.host_list_broken:
                    return 200, {"count": len(self.hosts)}
                return 200, {"hosts": self.hosts}
            url = request.body["host_url"]
            domain = url.split("://", 1)[1].rstrip("/")
            if any(h["host_id"] == "https:%s:443" % domain for h in self.hosts):
                return refused(409, "HOST_ALREADY_ADDED", "Host already added")
            host = self.add_host(domain)
            self._pending_uin[host["host_id"]] = self.uin_delay
            return 201, {"host_id": host["host_id"]}

        found = re.match(r"^/user/%d/hosts/([^/]+)(/.*)$" % USER, path)
        if not found:
            return refused(404, "RESOURCE_NOT_FOUND", "No route for %s %s" % (method, path))
        host_id, tail = found.groups()
        if host_id not in self.states:
            return refused(404, "HOST_NOT_FOUND", "Host not found")

        if tail == "/verification":
            if method == "POST":
                if request.query.get("verification_type") != "DNS":
                    return refused(400, "FIELD_VALIDATION_ERROR", "verification_type")
                self.states[host_id] = "IN_PROGRESS"
                return 200, self._verification(host_id)
            return 200, self._read_verification(host_id)

        if tail == "/user-added-sitemaps":
            if method == "GET":
                return 200, {"sitemaps": [{"sitemap_id": str(i), "sitemap_url": u}
                                          for i, u in enumerate(self.sitemaps[host_id])], "count": len(self.sitemaps[host_id])}
            if self.not_loaded:
                return refused(400, "HOST_NOT_LOADED", "Host not loaded")
            url = request.body["url"]
            if url in self.hidden_sitemaps:
                self.hidden_sitemaps.remove(url)
                self.sitemaps[host_id].append(url)
                return refused(409, "SITEMAP_ALREADY_ADDED", "Sitemap already added")
            if url in self.sitemaps[host_id]:
                return refused(409, "SITEMAP_ALREADY_ADDED", "Sitemap already added")
            self.sitemaps[host_id].append(url)
            return 201, {"sitemap_id": str(len(self.sitemaps[host_id]))}

        if tail == "/sitemaps" and method == "POST":
            # Read-only list of the maps Yandex found itself.
            return refused(404, "RESOURCE_NOT_FOUND", "Resource not found")

        return refused(404, "RESOURCE_NOT_FOUND", "No route for %s %s" % (method, path))

    def _verification(self, host_id):
        uin = "" if self._pending_uin.get(host_id) else "5e1f%d" % sum(map(ord, host_id))
        return {"verification_uin": uin, "verification_state": self.states[host_id],
                "applicable_verifiers": ["DNS", "META_TAG"]}

    def _read_verification(self, host_id):
        left = self._pending_uin.get(host_id, 0)
        if left:
            self._pending_uin[host_id] = left - 1
        if self.states[host_id] == "IN_PROGRESS":
            if self.progress_reads:
                self.progress_reads -= 1
            else:
                self.states[host_id] = "VERIFICATION_FAILED" if self.fails_verification else "VERIFIED"
        return self._verification(host_id)
