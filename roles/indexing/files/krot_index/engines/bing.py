"""Bing: never asked, offered through SubmitUrlBatch.

A port of busel's BingIndex (src/Colony/Index/BingIndex.php). Asking costs Bing
more than it saves: GetUrlInfo has no batch form and is throttled within four
sites (ThrottleHost on the 11th request, ThrottleUser after a hundred), while
SubmitUrlBatch took 62 addresses in one call in the same minute (busel,
2026-09-02). So pages are chosen from what was sent, and Bing is only offered.

⚠️ The key travels in the query string — the API wants it there. No message
this module writes includes a URL, and a network failure is reported by kind,
never by its text: urllib's text names the address, key and all, and it would
land in the journal.
"""

from krot_index import night, web

ENDPOINT = "https://ssl.bing.com/webmaster/api.svc/json"

# What a site may be sent when Bing could not be asked: the smallest useful
# figure, not a guess at the real one — the refusal that would reveal an
# overspend is exactly what is not arriving. 310 a month against one site sits
# well inside the smallest monthly figure Bing has named.
QUOTA_WHEN_UNASKED = 10

# The monthly figure is divided, not the daily one: Bing names 100 a day and 700
# a month, and a run believing the first spends the month in a week. 31, since a
# month that has 31 days overspends on the last one at 30.
DAYS_IN_MONTH = 31

# Asking the allowance fails for this many sites, and the walk stops asking: the
# failure describes the endpoint, and a dead one would otherwise be given three
# tries on every site. Counted by site, not by call — the walk asks each site's
# figure several times, and counted by call two sites would use up all three.
ATTEMPTS = 3

# Bing's own codes; the English beside them is rewritten between versions.
QUOTA_SPENT = 2
THROTTLED_USER = 4
THROTTLED = 5
NOT_AUTHORIZED = 14


def _number(value):
    """A positive whole number out of whatever shape Bing used, or None.

    Lenient about the shape (700, 700.0, "700"), strict about the value: zero
    divided floors to one page a night per site, which reads as a working run.
    """
    try:
        number = int(float(value))
    except (TypeError, ValueError):
        return None
    return number if number > 0 else None


def _code(value):
    """Bing's ErrorCode as a number: 14 and "14" are the same refusal; absent is 0."""
    if value is None:
        return 0
    try:
        return int(float(value))
    except (TypeError, ValueError):
        # A code that is not a number is still not the absence of one.
        return -1


class Bing:
    slug = "bing"

    def __init__(self, key, call=web.call, endpoint=ENDPOINT):
        self.key = key
        self.call = call
        self.endpoint = endpoint
        # ⚠️ By domain: the allowance belongs to the site, and one answer kept for
        # all would print nine plausible identical numbers (busel measured 91 / 7 /
        # 300 come back as 91 three times).
        self.answered = {}
        self.unanswered = set()

    def site_url(self, domain):
        # As the property was verified; a mismatch answers NotAuthorized, which
        # reads exactly like a missing key.
        return "https://" + domain

    def _post(self, method, body):
        try:
            status, raw = self.call("POST", "%s/%s?apikey=%s" % (self.endpoint, method, web.quoted(self.key)), body=body,
                                    timeout=30)
        except web.Unreachable:
            return None, None
        return status, web.decoded(raw)

    def _get(self, method, domain):
        try:
            status, raw = self.call("GET", "%s/%s?siteUrl=%s&apikey=%s" % (
                self.endpoint, method, web.quoted(self.site_url(domain)), web.quoted(self.key)), timeout=30)
        except web.Unreachable:
            return None
        answer = web.decoded(raw)
        if status != 200 or not isinstance(answer, dict) or answer.get("ErrorCode", 0) != 0:
            return None
        payload = answer.get("d")
        return payload if isinstance(payload, dict) else None

    def daily_quota(self, domain=""):
        """What Bing says it takes from this site today — asked every run, never written down.

        It named 800 a month on 2026-08-24 and 700 the next day, for every domain
        at once: a limit, not a remainder, and one that moves.
        """
        if domain in self.answered:
            return self.answered[domain]
        if not domain or domain in self.unanswered or len(self.unanswered) >= ATTEMPTS:
            return QUOTA_WHEN_UNASKED
        answer = self._get("GetUrlSubmissionQuota", domain)
        monthly = _number((answer or {}).get("MonthlyQuota"))
        if monthly is None:
            self.unanswered.add(domain)
            return QUOTA_WHEN_UNASKED
        daily = monthly // DAYS_IN_MONTH
        # Held under the daily figure too: while the month stays where it has been
        # this never binds, but a larger month would plan past a limit Bing keeps.
        today = _number((answer or {}).get("DailyQuota"))
        self.answered[domain] = max(1, daily if today is None else min(daily, today))
        return self.answered[domain]

    def quota_was_asked(self, domain=""):
        return domain in self.answered

    def quota_is_per_site(self):
        return True

    def worth_asking(self):
        return False

    def pause_between_batches(self):
        # The pace limit was GetUrlInfo's, and Bing is no longer asked.
        return 0

    def offer_at_once(self):
        # Under the 62 that worked once; not a published ceiling.
        return 50

    def states(self, domain, urls):
        return {url: night.UNASKED for url in urls}

    def submit_all(self, domain, urls):
        """Every page in one call; accepted as a batch, since Bing names no address in its answer.

        ⚠️ The caller must not send more than the site has left: Bing takes an
        oversized batch, spends the rest and refuses the NEXT call.
        """
        if not urls:
            return {}
        status, answer = self._post("SubmitUrlBatch", {"siteUrl": self.site_url(domain), "urlList": list(urls)})
        code = _code(answer.get("ErrorCode")) if isinstance(answer, dict) else 0
        if code != 0:
            raise self.refusal(code, domain)
        if status != 200 or not isinstance(answer, dict):
            # The network, an HTML error page, or a 5xx in JSON without a code:
            # not accepted, and the walk goes on. A dead endpoint still turns the
            # night red, through "attempted and nothing taken".
            return {url: False for url in urls}
        # Success is {"d": null} with 200: no field to check, the absence of an
        # error is it — which is why the status is read first.
        return {url: True for url in urls}

    @staticmethod
    def refusal(code, domain):
        if code == NOT_AUTHORIZED:
            return night.Refused("Bing does not list %s under this key's account" % domain, ownership=True,
                                 repair="the site is not in this Bing Webmaster account — the site_search role adds it")
        if code in (THROTTLED, THROTTLED_USER):
            return night.Refused("Bing was offered %s's pages faster than it takes them" % domain, exhausted=True,
                                 too_fast=True)
        if code == QUOTA_SPENT:
            return night.Refused("Bing has taken all it will take from %s today" % domain, exhausted=True)
        return night.Refused("Bing refused the submission for %s with code %s" % (domain, code))
