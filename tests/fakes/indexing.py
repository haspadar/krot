"""What krot-index talks to, faked: its store, an engine, Google's two APIs, a site.

The store and the engine are working implementations in memory rather than
stubs, so a test states a situation — "Google knows two of these five" — and the
program finds its own way through it. Google and the site are real HTTP servers
(fakes.server), so the program goes through its own urllib path.
"""

import datetime

from fakes.server import FakeServer

HOLD = datetime.timedelta(days=14)


class FakeStore:
    """krot.page_index and krot.index_run, in memory, with a clock the test moves."""

    def __init__(self):
        self.now = datetime.datetime(2026, 9, 29, 12, 0)
        # (site, engine, url) -> {"state", "asked_at", "submitted_at"}
        self.pages = {}
        self.runs = []
        self.offer_fails = False
        self.record_fails = False

    def tick(self, **delta):
        self.now += datetime.timedelta(**delta)

    def remember(self, site, engine, url, state):
        row = self.pages.setdefault((site, engine, url), {"submitted_at": None})
        row.update(state=state, asked_at=self.now)

    def offered(self, site, engine, url):
        if self.offer_fails:
            raise RuntimeError("permission denied for table page_index")
        row = self.pages.setdefault((site, engine, url), {"state": "unknown", "asked_at": self.now})
        row["submitted_at"] = self.now

    def offered_recently(self, site, engine):
        return [url for (s, e, url), row in self.pages.items()
                if s == site and e == engine and row["submitted_at"] and row["submitted_at"] > self.now - HOLD]

    def asked(self, site, engine):
        rows = [(row["asked_at"], url) for (s, e, url), row in self.pages.items() if s == site and e == engine]
        return [url for _, url in sorted(rows)]

    def ever_offered(self, site, engine):
        return sum(1 for (s, e, _), row in self.pages.items() if s == site and e == engine and row["submitted_at"])

    def forget_gone(self, site, serving):
        if not serving:
            return 0
        gone = [key for key in self.pages if key[0] == site and key[2] not in set(serving)]
        for key in gone:
            del self.pages[key]
        return len(gone)

    def record(self, spending):
        if not self.record_fails:
            self.runs.append(spending)

    def state(self, site, engine, url):
        return self.pages.get((site, engine, url), {}).get("state")


class FakeEngine:
    """An engine in memory: knows what it knows, takes what it is given, counts its day."""

    def __init__(self, slug="google", quota=200, per_site=False, asking=True, at_once=50):
        self.slug = slug
        self.quota = quota
        self.per_site = per_site
        self.asking = asking
        self.at_once = at_once
        # url -> state the engine answers
        self.knows = {}
        self.inspected = []
        self.submitted = []
        self.refuse_with = None
        self.quota_named = True
        self.silent = False

    def daily_quota(self, domain=""):
        return self.quota

    def quota_was_asked(self, domain=""):
        return self.quota_named

    def quota_is_per_site(self):
        return self.per_site

    def worth_asking(self):
        return self.asking

    def pause_between_batches(self):
        return 0

    def offer_at_once(self):
        return self.at_once

    def states(self, domain, urls):
        self.inspected.extend(urls)
        if self.silent:
            return {url: "unasked" for url in urls}
        return {url: self.knows.get(url, "unknown") for url in urls}

    def submit_all(self, domain, urls):
        if self.refuse_with is not None:
            raise self.refuse_with
        self.submitted.extend(urls)
        return {url: True for url in urls}


class FakeIndexing:
    """URL Inspection and the Indexing API behind one address, as Google answers them."""

    def __init__(self):
        # url -> coverageState Google words it with
        self.coverage = {}
        self.published = []
        self.publish_answer = None
        self.inspect_status = 200
        self.server = FakeServer(self)

    @property
    def inspect_url(self):
        return self.server.url + "/v1/urlInspection/index:inspect"

    @property
    def submit_url(self):
        return self.server.url + "/v3/urlNotifications:publish"

    def handle(self, request):
        bearer = request.headers.get("Authorization", "")
        if request.path.endswith("index:inspect"):
            if "webmasters" not in bearer:
                return 403, {"error": {"code": 403, "message": "wrong scope", "status": "PERMISSION_DENIED"}}
            if self.inspect_status != 200:
                return self.inspect_status, {"error": {"code": self.inspect_status, "message": "down"}}
            url = request.body["inspectionUrl"]
            words = self.coverage.get(url, "URL is unknown to Google")
            return 200, {"inspectionResult": {"indexStatusResult": {"coverageState": words}}}
        if request.path.endswith("urlNotifications:publish"):
            if "indexing" not in bearer:
                return 403, {"error": {"code": 403, "message": "wrong scope", "status": "PERMISSION_DENIED"}}
            if self.publish_answer is not None:
                return self.publish_answer
            self.published.append(request.body["url"])
            return 200, {"urlNotificationMetadata": {"url": request.body["url"]}}
        return 404, None

    def close(self):
        self.server.close()


class FakeSite:
    """A site serving sitemap files by path: {"/sitemap.xml": "<urlset>…"} and any status."""

    def __init__(self, files=None):
        self.files = dict(files or {})
        self.server = FakeServer(self)

    def url(self, path):
        return self.server.url + path

    def handle(self, request):
        served = self.files.get(request.path)
        if served is None:
            return 404, "not here", {"Content-Type": "text/html"}
        if isinstance(served, tuple):
            return served[0], served[1], {"Content-Type": "text/html"}
        return 200, served, {"Content-Type": "application/xml"}

    def close(self):
        self.server.close()


class FakeBingSubmission:
    """Bing's Webmaster JSON API as far as submission goes: the allowance and SubmitUrlBatch.

    Keeps each site's day and refuses the way Bing does — HTTP 200 with an
    ErrorCode in the body.
    """

    def __init__(self, key="bing-units-key"):
        self.key = key
        # site url -> (daily, monthly) Bing names
        self.quotas = {}
        # site url -> what it accepted
        self.accepted = {}
        self.error_code = None
        self.quota_down = False
        self.server = FakeServer(self)

    @property
    def endpoint(self):
        return self.server.url + "/webmaster/api.svc/json"

    def handle(self, request):
        if request.query.get("apikey") != self.key:
            return 200, {"ErrorCode": 3, "Message": "ERROR!!! InvalidApiKey"}
        if request.path.endswith("/GetUrlSubmissionQuota"):
            if self.quota_down:
                return 503, "<html>Service Unavailable</html>", {"Content-Type": "text/html"}
            daily, monthly = self.quotas.get(request.query.get("siteUrl"), (100, 700))
            return 200, {"d": {"__type": "UrlSubmissionQuota:#Microsoft.Bing.Webmaster.Api",
                               "DailyQuota": daily, "MonthlyQuota": monthly}}
        if request.path.endswith("/SubmitUrlBatch"):
            if self.error_code is not None:
                return 200, {"ErrorCode": self.error_code, "Message": "ERROR!!!"}
            self.accepted.setdefault(request.body["siteUrl"], []).extend(request.body["urlList"])
            return 200, {"d": None}
        return 404, None

    def close(self):
        self.server.close()


class FakeYandexRecrawl:
    """Yandex Webmaster v4: the user, the hosts, and the recrawl queue."""

    def __init__(self, accepts="yandex-units-token"):
        self.accepts = accepts
        self.user = 1130000061208761
        # domain -> host_id, for sites the account holds
        self.hosts = {}
        self.queued = []
        self.error = None
        self.server = FakeServer(self)

    @property
    def api(self):
        return self.server.url + "/v4"

    def held(self, domain):
        self.hosts[domain] = "https:%s:443" % domain

    def handle(self, request):
        if request.headers.get("Authorization") != "OAuth " + self.accepts:
            return 401, {"error_code": "INVALID_OAUTH_TOKEN", "error_message": "Invalid oauth token"}
        if request.path == "/v4/user":
            return 200, {"user_id": self.user}
        if request.path == "/v4/user/%d/hosts" % self.user:
            return 200, {"hosts": [{"host_id": host, "ascii_host_url": "https://%s/" % domain,
                                    "unicode_host_url": "https://%s/" % domain, "verified": True}
                                   for domain, host in self.hosts.items()]}
        if request.path.endswith("/recrawl/queue"):
            if self.error is not None:
                return self.error
            self.queued.append(request.body["url"])
            return 202, {"task_id": "ff7f4c3c-%04d" % len(self.queued), "quota_remainder": 150 - len(self.queued)}
        return 404, None

    def close(self):
        self.server.close()


class FakeIndexNowEndpoint:
    """api.indexnow.org: takes a list and answers a status, nothing more."""

    def __init__(self):
        self.posts = []
        self.status = 200
        self.server = FakeServer(self)

    @property
    def endpoint(self):
        return self.server.url + "/indexnow"

    def handle(self, request):
        self.posts.append(request.body)
        return self.status, None

    def close(self):
        self.server.close()


def urlset(*locs):
    entries = "".join("<url><loc>%s</loc></url>" % loc for loc in locs)
    return '<?xml version="1.0"?><urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">%s</urlset>' % entries


def sitemapindex(*locs):
    entries = "".join("<sitemap><loc>%s</loc></sitemap>" % loc for loc in locs)
    return '<?xml version="1.0"?><sitemapindex xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">%s</sitemapindex>' \
        % entries
