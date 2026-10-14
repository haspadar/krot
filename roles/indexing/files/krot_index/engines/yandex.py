"""Yandex: asked to walk named pages again — 150 a day for every site.

A port of an earlier PHP implementation, with one fix. There the pause sat
between the addresses of ONE call, and it offers one address a call, so the
pause never happened; here it sits between calls.

Not the same channel as IndexNow, which also reaches Yandex: the protocol says a
page exists and answers nothing, this asks for a walk and says whether it was
taken.
"""

import datetime
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

# How far back the page counts are asked for each night. The history is a handful
# of points on the dates Yandex refreshed its results, not a point a day.
HISTORY_DAYS = 35

# Yandex has nothing to say about a site it has not walked or loaded yet: the
# ordinary state of a site opened this week, not a fault.
NO_DATA_YET = ("HOST_NOT_LOADED", "HOST_NOT_INDEXED")

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

    def _read(self, domain, host, path):
        """One reading call about a host: the answer, or NoData for a site not walked yet.

        Refused for everything a person must look at. Spends nothing of the recrawl
        allowance — these only read statistics.
        """
        try:
            status, raw = self.call("GET", "%s/user/%s/hosts/%s%s" % (self.api, self.user, host, path),
                                    headers={"Authorization": "OAuth " + self.token}, timeout=30)
        except web.Unreachable:
            raise night.Refused("Yandex could not be reached for the figures of %s" % domain)
        answer = web.decoded(raw)
        code = answer.get("error_code") if isinstance(answer, dict) and isinstance(answer.get("error_code"), str) else ""
        if status == 200 and isinstance(answer, dict):
            return answer
        if code in NO_DATA_YET:
            raise night.NoData("Yandex has no figures for %s yet (%s)" % (domain, code))
        if status == 429 or code in QUOTA:
            # Reading statistics spends no allowance, but Yandex still paces its callers; it repairs itself.
            raise night.Refused("Yandex asked for the figures of %s faster than it answers" % domain,
                                exhausted=True, too_fast=True)
        if status == 401:
            raise night.Refused("Yandex: the token was refused",
                                repair="Yandex no longer accepts KROT_INDEX_YANDEX_TOKEN — a new OAuth token")
        if code in OWNERSHIP or status in (403, 404):
            raise night.Refused("Yandex: %s answered %d %s" % (path, status, code), ownership=True,
                                repair="the site is not verified in this Yandex Webmaster account")
        raise night.Refused("Yandex answered %s with %d %s" % (path, status, code))

    def index_counts(self, domain, today):
        """What Yandex holds of the site: [(day, in_index, not_in_index)], oldest first.

        in_index: the page count of the search results, on the day each point is dated
        — Yandex's own, in its own zone. Points are the dates Yandex refreshed its
        results, so most days have none; none is invented between them, and the
        last point of a day wins.

        not_in_index: Yandex gives the excluded pages as today's number only — its
        events history is a flow (appeared, removed), not a stock — so it is stored
        on `today`, the day it was read, and no earlier day gets one. Read again
        each night, the days gather their own history from the first night on.
        """
        host = self.host(domain)
        if host is None:
            raise night.Refused("Yandex does not hold %s" % domain, ownership=True,
                                repair="the site is not in this Yandex Webmaster account — the site_search role adds it")
        since = today - datetime.timedelta(days=HISTORY_DAYS)
        # date_to a day past today: Yandex dates its points in Moscow time, ahead of a machine
        # on UTC, and a point dated tomorrow there would otherwise fall outside the window.
        until = today + datetime.timedelta(days=1)
        history = self._read(domain, host, "/search-urls/in-search/history?date_from=%s&date_to=%s"
                             % (since.isoformat(), until.isoformat()))
        points = history.get("history")
        if not isinstance(points, list):
            # ⚠️ A refusal, not "no days": an answer without its list is an API that changed or
            # an outage in a 200, and read as an empty history the unit would stay green while
            # nothing is written. A real empty history is the list `[]`.
            raise night.Refused("Yandex answered the page counts of %s without a list of points" % domain)
        found = {}
        for point in points:
            if not isinstance(point, dict):
                continue
            stamp, value = point.get("date"), point.get("value")
            day = _stamp_day(stamp)
            if day is None or isinstance(value, bool) or not isinstance(value, int) or value < 0:
                continue
            if day not in found or stamp >= found[day][0]:
                found[day] = (stamp, value)
        if points and not found:
            # Points came and none is readable: the shape moved, not a young site.
            raise night.Refused("Yandex answered the page counts of %s with points none of which can be read" % domain)
        days = {day: [value, None] for day, (_, value) in found.items()}
        try:
            excluded = self._read(domain, host, "/summary").get("excluded_pages_count")
            if isinstance(excluded, bool) or not isinstance(excluded, int) or excluded < 0:
                raise night.Refused("Yandex answered the summary of %s without a usable excluded_pages_count" % domain)
            days.setdefault(today, [None, None])[1] = excluded
        except night.NoData:
            # The history is already in hand; the summary being behind it costs only today's excluded figure.
            pass
        except night.Refused as refused:
            # ⚠️ The page counts are the series; the excluded figure is the extra. A summary that
            # fails must not take the history with it, nor go unsaid: written, and still red.
            raise night.Partial(str(refused), _rows(days), ownership=refused.ownership, exhausted=refused.exhausted,
                                too_fast=refused.too_fast, repair=refused.repair)
        return _rows(days)


def _rows(days):
    return [(day, held, left) for day, (held, left) in sorted(days.items())]


def _stamp_day(stamp):
    """The date part of `2026-09-19T10:00:11.592+03:00`, as Yandex dated it — or None."""
    if not isinstance(stamp, str):
        return None
    try:
        return datetime.date.fromisoformat(stamp[:10])
    except ValueError:
        return None
