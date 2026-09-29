"""Yandex: asked to walk named pages again — 150 a day for every site.

A port of busel's YandexIndex (src/Colony/Index/YandexIndex.php), with one fix.
busel's pause sits between the addresses of ONE call, and it offers one address
a call, so the pause never happens; here it sits between calls.

Not the same channel as IndexNow, which also reaches Yandex: the protocol says a
page exists and answers nothing, this asks for a walk and says whether it was
taken.
"""

import time

from krot_index import night, web

API = "https://api.webmaster.yandex.net/v4"

# Read from the live API 2026-09-09 on a fresh host: daily_quota 150,
# quota_remainder 150, 149 after one page. Per site.
DAILY_QUOTA = 150

# Seconds between one request and the next. Yandex names no rate; 150 requests
# a night is not a pace worth defending, and a second keeps a site under three
# minutes.
PACE = 1

QUOTA = ("QUOTA_EXCEEDED", "TOO_MANY_REQUESTS_ERROR")
OWNERSHIP = ("HOST_NOT_VERIFIED", "HOST_NOT_INDEXED", "FORBIDDEN")


class Yandex:
    slug = "yandex"

    def __init__(self, token, call=web.call, api=API, sleep=time.sleep):
        self.token = token
        self.call = call
        self.api = api
        self.sleep = sleep
        self.user = None
        self.hosts = {}
        self.host_list = None
        self.posted = False

    def daily_quota(self, domain=""):
        return DAILY_QUOTA

    def quota_was_asked(self, domain=""):
        # A figure Yandex states, not one guessed; a doubt about it would warn nightly.
        return True

    def quota_is_per_site(self):
        return True

    def worth_asking(self):
        # Nothing Yandex answers about a page costs less than the walk it would save.
        return False

    def pause_between_batches(self):
        # The caller pauses only around asking, and this engine is never asked.
        return 0

    def offer_at_once(self):
        # No batch form: one address a request.
        return 1

    def states(self, domain, urls):
        return {url: night.UNASKED for url in urls}

    def _get(self, path):
        status, raw = self.call("GET", self.api + path, headers={"Authorization": "OAuth " + self.token}, timeout=30)
        answer = web.decoded(raw)
        if status != 200 or not isinstance(answer, dict):
            raise night.Refused("Yandex answered %s with %d" % (path, status))
        return answer

    def host(self, domain):
        """Yandex's id for the site — `https:rufnummer.de:443` — looked up, never built."""
        if domain in self.hosts:
            return self.hosts[domain]
        found = {}
        for host in self.listed():
            if not isinstance(host, dict) or not host.get("host_id"):
                continue
            # Both spellings: a site named in Cyrillic carries only the unicode one.
            url = host.get("ascii_host_url") or host.get("unicode_host_url") or ""
            if web.host_of(url) == domain.lower():
                found.setdefault(url.split(":", 1)[0].lower(), host["host_id"])
        # ⚠️ https first: an account often keeps a site's old http host beside
        # the https one, and the pages queued against it are "outside the host"
        # — refused one by one, as if each page were at fault.
        self.hosts[domain] = found.get("https") or found.get("http")
        return self.hosts[domain]

    def listed(self):
        """Every host of the account — asked once a run, not once a site."""
        if self.host_list is not None:
            return self.host_list
        try:
            if self.user is None:
                user = self._get("/user").get("user_id")
                if isinstance(user, bool) or not isinstance(user, (int, str)) or str(user) == "":
                    raise night.Refused("Yandex answered /user without a user_id")
                self.user = str(user)
            hosts = self._get("/user/%s/hosts" % self.user).get("hosts")
        except web.Unreachable:
            raise night.Refused("Yandex could not be reached for the host list")
        self.host_list = hosts if isinstance(hosts, list) else []
        return self.host_list

    def submit_all(self, domain, urls):
        host = self.host(domain)
        if host is None:
            raise night.Refused("Yandex does not hold %s" % domain, ownership=True,
                                repair="the site is not in this Yandex Webmaster account — the site_search role adds it")
        taken = {}
        for url in urls:
            try:
                taken[url] = self.offer(host, url, domain)
            except night.Refused as refusal:
                refusal.accepted = [page for page, ok in taken.items() if ok]
                raise
        return taken

    def offer(self, host, url, domain):
        if self.posted:
            self.sleep(PACE)
        self.posted = True
        try:
            status, raw = self.call("POST", "%s/user/%s/hosts/%s/recrawl/queue" % (self.api, self.user, host),
                                    headers={"Authorization": "OAuth " + self.token}, body={"url": url}, timeout=30)
        except web.Unreachable:
            # The night's fault, not the site's: this page is not taken, the next may be.
            return False
        answer = web.decoded(raw)
        answer = answer if isinstance(answer, dict) else {}
        if status < 300:
            return isinstance(answer.get("task_id"), str)
        code = answer.get("error_code") if isinstance(answer.get("error_code"), str) else ""
        message = answer.get("error_message") if isinstance(answer.get("error_message"), str) else "HTTP %d" % status
        if code in QUOTA or (not code and status == 429):
            raise night.Refused("Yandex: " + message, exhausted=True, too_fast=not code)
        if code in OWNERSHIP or (not code and status == 403):
            raise night.Refused("Yandex: " + message, ownership=True,
                                repair="the site is not verified in this Yandex Webmaster account")
        if status == 401:
            # The token, not the site: 149 more tries would each get the same.
            raise night.Refused("Yandex: " + message,
                                repair="Yandex no longer accepts KROT_INDEX_YANDEX_TOKEN — a new OAuth token")
        # About this page — outside the host, an address Yandex will not walk —
        # or a 5xx about this one request. One bad address must not end a night
        # that has 149 more.
        return False
