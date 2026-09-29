"""Google: asked through URL Inspection, offered through the Indexing API.

A port of an earlier PHP implementation.

⚠️ The Indexing API is documented for job postings and livestreams. The
earlier implementation submitted ordinary catalogue pages and Google answers 200 (tested 2026-08-22);
what it does refuse is a domain the account does not own. That is Google's
promise to keep, not ours — if it starts refusing ordinary pages, look here
first.
"""

import time
from concurrent.futures import ThreadPoolExecutor

from krot_index import night, web
from krot_index.google_jwt import TOKEN_URI, ServiceAccountKey, reason

INSPECT_SCOPE = "https://www.googleapis.com/auth/webmasters"
SUBMIT_SCOPE = "https://www.googleapis.com/auth/indexing"
INSPECT_URL = "https://searchconsole.googleapis.com/v1/urlInspection/index:inspect"
SUBMIT_URL = "https://indexing.googleapis.com/v3/urlNotifications:publish"

# Per Cloud PROJECT, not per property: DefaultPublishRequestsPerDayPerProject.
# With a day's 200 spent on one site, a page of another is refused at once
# (measured 2026-08-22). The caller divides it between the project's sites.
DAILY_QUOTA = 200

# A token lives an hour. Minted again before that, so a walk over a large
# project that outlives the hour does not meet 401 on every later page — read
# as an outage on inspection and as a red refusal on submission.
TOKEN_LIFE = 50 * 60


def coverage_state(coverage):
    """Google's console wording read as a state — by substring, since Google rewords it.

    Anything unrecognised is UNASKED rather than a guess: guessing unknown
    submits a page that may be indexed, guessing indexed hides one that is not.
    """
    said = (coverage or "").lower()
    # Before "indexed": "currently not indexed" contains the word.
    if "not indexed" in said:
        return night.KNOWN
    if "indexed" in said:
        return night.INDEXED
    if "unknown" in said:
        return night.UNKNOWN
    return night.UNASKED


def _coverage_of(answer):
    if not isinstance(answer, dict):
        return ""
    result = answer.get("inspectionResult")
    status = result.get("indexStatusResult") if isinstance(result, dict) else None
    coverage = status.get("coverageState") if isinstance(status, dict) else None
    return coverage if isinstance(coverage, str) else ""


class Google:
    slug = "google"

    def __init__(self, key_json, call=web.call, token_uri=TOKEN_URI, inspect_url=INSPECT_URL, submit_url=SUBMIT_URL,
                 clock=time.monotonic):
        self.key = ServiceAccountKey(key_json)
        self.call = call
        self.token_uri = token_uri
        self.inspect_url = inspect_url
        self.submit_url = submit_url
        self.clock = clock
        # scope -> (token, when it was minted)
        self.tokens = {}

    def daily_quota(self, domain=""):
        return DAILY_QUOTA

    def quota_was_asked(self, domain=""):
        # Published and fixed: nothing to ask, so no doubt to report.
        return True

    def quota_is_per_site(self):
        return False

    def worth_asking(self):
        # The day's 200 belong to the project; one spent on an indexed page is one
        # the others do not get. 2000 inspections a day make the question cheap.
        return True

    def pause_between_batches(self):
        return 0

    def offer_at_once(self):
        # No batch form: submit_all sends one by one. The figure only sets how
        # often the caller comes back.
        return 50

    def token(self, scope):
        held = self.tokens.get(scope)
        if held is None or self.clock() - held[1] > TOKEN_LIFE:
            status, raw = self.call("POST", self.token_uri, form=self.key.grant(scope, self.token_uri))
            answer = web.decoded(raw)
            access = answer.get("access_token") if isinstance(answer, dict) else None
            if status >= 400 or not access:
                raise night.Refused("Google gave no token for %s (HTTP %d): %s" % (scope, status, reason(answer)))
            self.tokens[scope] = held = (access, self.clock())
        return held[0]

    def _inspect(self, token, domain, url):
        # Anything at all, not only the network: one page failing in a way
        # nobody foresaw must not end the walk over every site — it is that
        # page's answer, and UNASKED spends no allowance.
        try:
            status, raw = self.call("POST", self.inspect_url, headers={"Authorization": "Bearer " + token},
                                    body={"inspectionUrl": url, "siteUrl": "sc-domain:" + domain})
            if status == 429:
                # Inspection has its own limits (2000 a day per property, and a
                # pace). A refusal of pace repairs itself and must not paint the
                # unit red the way silence from a dead key does.
                return night.THROTTLED
            if status != 200:
                return night.UNASKED
            return coverage_state(_coverage_of(web.decoded(raw)))
        except Exception:
            return night.UNASKED

    def states(self, domain, urls):
        """Asks about several pages at once, keyed by URL.

        Together rather than in turn: one inspection takes about 6.8 seconds and
        twenty together 8.1 (measured 2026-08-22). Every failure is UNASKED for that
        page alone — the one answer that spends no allowance.
        """
        try:
            token = self.token(INSPECT_SCOPE)
        except (night.Refused, web.Unreachable):
            return {url: night.UNASKED for url in urls}
        with ThreadPoolExecutor(max_workers=max(1, len(urls))) as pool:
            answers = pool.map(lambda url: self._inspect(token, domain, url), urls)
            return dict(zip(urls, answers))

    def submit_all(self, domain, urls):
        """One request a page; a refusal about the site stops the rest by raising.

        The refusal carries what was taken before it — see Refused.accepted.
        """
        accepted = {}
        for url in urls:
            try:
                accepted[url] = self.submit(url)
            except night.Refused as refusal:
                refusal.accepted = [taken for taken, ok in accepted.items() if ok]
                raise
        return accepted

    def submit(self, url):
        try:
            token = self.token(SUBMIT_SCOPE)
            status, raw = self.call("POST", self.submit_url, headers={"Authorization": "Bearer " + token},
                                    body={"url": url, "type": "URL_UPDATED"})
        except web.Unreachable as failure:
            # Stop offering this site rather than end the walk: the next site may
            # well be reachable, and the pages wait.
            raise night.Refused(str(failure))
        if status < 300:
            return True
        raise self.refusal(status, web.decoded(raw))

    @staticmethod
    def refusal(status, answer):
        error = answer.get("error") if isinstance(answer, dict) else None
        error = error if isinstance(error, dict) else {}
        message = error.get("message") if isinstance(error.get("message"), str) else ""
        state = error.get("status") if isinstance(error.get("status"), str) else ""
        message = message or "HTTP %d" % status
        # Google's own status field first; the English beside it is reworded at will.
        ownership = status == 403 and (state == "PERMISSION_DENIED" or "ownership" in message.lower())
        # A spent day says RESOURCE_EXHAUSTED; a pace limit says "too many requests"
        # and must not end the walk as a spent day would.
        exhausted = state == "RESOURCE_EXHAUSTED" or (status == 429 and "quota exceeded" in message.lower())
        repair = ""
        if ownership:
            repair = "the service account is not an owner of this domain's property in Search Console"
        return night.Refused(message, ownership=ownership, exhausted=exhausted, repair=repair)
