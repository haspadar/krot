"""Bing Webmaster Tools JSON API as far as bing_site uses it.

Reproduces the delays that make the module wait: the verification code is
published a few reads after AddSite, VerifySite says false until "DNS" has the
record, and SubmitFeed is refused with InvalidParameter for a while after
verification.
"""

THROTTLE_USER = 4
INVALID_PARAMETER = 8


def refused(code, message):
    return 400, {"ErrorCode": code, "Message": "ERROR!!! " + message}


class FakeBing:
    def __init__(self, key="bing-key"):
        self.key = key
        self.sites = []
        self.feeds = {}
        # Reads of GetUserSites before a new site's code shows up.
        self.code_delay = 0
        # VerifySite calls answered false before true.
        self.verify_after = 0
        # SubmitFeed calls refused as InvalidParameter before one is taken.
        self.feed_refusals = 0
        self.throttled = False
        # GetUserSites answering {"d": null}, which is not a list of sites.
        self.site_list_broken = False
        self._pending_code = {}

    def add_site(self, domain, verified=False):
        site = {"Url": "https://%s/" % domain, "IsVerified": verified,
                "DnsVerificationCode": "a1b2c3.%s" % domain}
        self.sites.append(site)
        self.feeds.setdefault(site["Url"], [])
        return site

    def handle(self, request):
        if request.query.get("apikey") != self.key:
            return 401, {"ErrorCode": 3, "Message": "ERROR!!! InvalidApiKey"}
        if self.throttled:
            return refused(THROTTLE_USER, "ThrottleUser")
        method = request.path.rsplit("/", 1)[-1]

        if method == "GetUserSites":
            if self.site_list_broken:
                return 200, {"d": None}
            for site in self.sites:
                left = self._pending_code.get(site["Url"], 0)
                if left:
                    self._pending_code[site["Url"]] = left - 1
            return 200, {"d": [dict(s, DnsVerificationCode="" if self._pending_code.get(s["Url"]) else s["DnsVerificationCode"])
                               for s in self.sites]}
        if method == "AddSite":
            url = request.body["siteUrl"]
            if any(s["Url"] == url for s in self.sites):
                return refused(9, "AlreadyExists")
            self.add_site(url.split("/")[2])
            self._pending_code[url] = self.code_delay
            return 200, {"d": None}
        if method == "VerifySite":
            site = self._site(request.body["siteUrl"])
            if site is None:
                return refused(INVALID_PARAMETER, "InvalidParameter")
            if self.verify_after:
                self.verify_after -= 1
                return 200, {"d": False}
            site["IsVerified"] = True
            return 200, {"d": True}
        if method == "GetFeeds":
            return 200, {"d": [{"Url": u, "Status": "Pending"} for u in self.feeds.get(request.query["siteUrl"], [])]}
        if method == "SubmitFeed":
            site = self._site(request.body["siteUrl"])
            if site is None or not site["IsVerified"]:
                return refused(INVALID_PARAMETER, "InvalidParameter")
            if self.feed_refusals:
                self.feed_refusals -= 1
                return refused(INVALID_PARAMETER, "InvalidParameter")
            self.feeds[site["Url"]].append(request.body["feedUrl"])
            return 200, {"d": None}
        return 404, {"Message": "No such method %s" % method}

    def _site(self, url):
        return next((s for s in self.sites if s["Url"] == url), None)
