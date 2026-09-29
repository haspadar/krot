"""IndexNow: one post, several engines — Yandex, Seznam, Naver, Yep, and Bing again.

A port of busel's IndexNowIndex (src/Colony/Index/IndexNowIndex.php) and
SiteKey. The protocol answers nothing about a page, keeps no account and names
no daily allowance — only a ceiling of 10 000 addresses a post.

The site proves itself by serving its key at /{key}.txt, and that file belongs to
the site's code, not to krot: the vhost is the project's. What krot owns is the
formula, and the program checks the file itself before posting, so a site that
does not serve it is named as such rather than as a night of 403s.
"""

import hashlib

from krot_index import night, web

ENDPOINT = "https://api.indexnow.org/indexnow"

# The protocol's own ceiling for one post, and the only limit it names.
#
# ⚠️ Also the night's limit for a site, deliberately: one post a site a night, as
# in busel. A queue larger than this drains over the following nights, and with
# offered pages held 14 days a site of up to 140 000 pages is still offered
# whole every fortnight. What must not happen is a SMALL nightly figure — fifty
# a night would strand a large site's queue for years while every night reported
# success.
AT_ONCE = 10000

KEY_LENGTH = 32


def site_key(secret, domain):
    """The site's key: half of sha256 over the project's secret and the domain.

    ⚠️ A contract with files already published. busel's sites serve keys made by
    this formula (Colony\\Index\\IndexNow\\SiteKey); changed, the network would
    post today's key while its sites serve yesterday's. Pinned by a test with a
    value.
    """
    return hashlib.sha256((secret + ":" + domain.strip().lower()).encode()).hexdigest()[:KEY_LENGTH]


class IndexNow:
    slug = "indexnow"

    def __init__(self, secret, call=web.call, endpoint=ENDPOINT, origin=None):
        self.secret = secret  # secret-lint: allow — a parameter passed on, not a value
        self.call = call
        self.endpoint = endpoint
        # Where the site answers; a parameter only so a test can put the site on a
        # local port.
        self.origin = origin or (lambda domain: "https://" + domain)
        self.proven = set()

    def daily_quota(self, domain=""):
        # One post's worth — see AT_ONCE for why a night is one post.
        return AT_ONCE

    def quota_was_asked(self, domain=""):
        # True: the ceiling is published and certain, not a fallback. busel's
        # wiki says false; its code says true, and the code is right — false
        # printed "could not ask" every night about an endpoint never asked.
        return True

    def quota_is_per_site(self):
        # No running total per submitter: dividing a limit that does not exist
        # would cut every site to a fraction of a ceiling nobody enforces.
        return True

    def worth_asking(self):
        # Nothing to ask: the protocol has no question.
        return False

    def pause_between_batches(self):
        return 0

    def offer_at_once(self):
        # One post does the work; fifty a post made 700 unpaced posts of a large site.
        return AT_ONCE

    def states(self, domain, urls):
        return {url: night.UNASKED for url in urls}

    def key_location(self, domain):
        return "%s/%s.txt" % (self.origin(domain), site_key(self.secret, domain))

    def prove(self, domain):
        """Reads the key file as the protocol's engines will, before posting anything.

        True where the site serves its key; False where the site did not answer
        usefully at all — a timeout, a 5xx — which says nothing about the key and
        must not send anybody to its route.
        """
        if domain in self.proven:
            return True
        location = self.key_location(domain)
        try:
            status, raw = self.call("GET", location, timeout=30)
        except web.Unreachable:
            return False
        if status >= 500:
            return False
        if status != 200 or raw.decode(errors="replace").strip() != site_key(self.secret, domain):
            raise night.Refused(
                "IndexNow: %s answered %d%s" % (location, status, "" if status != 200 else " with another key"),
                ownership=True,
                repair="the site does not serve its key at %s — the route belongs to the site's code, by krot's "
                       "formula; a site not open yet answers 401 to everything" % location)
        self.proven.add(domain)
        return True

    def submit_all(self, domain, urls):
        """Every address in one post; accepted as a batch, since the endpoint names none.

        Every failure to be heard — the site down while its key is read, the
        endpoint down or answering 5xx — is "not accepted" rather than a refusal:
        the night goes red through "attempted and nothing taken", with no repair
        named, since none is owed to a key file or a route that are fine.
        """
        if not urls:
            return {}
        if not self.prove(domain):
            return {url: False for url in urls}
        key = site_key(self.secret, domain)
        try:
            status, _ = self.call("POST", self.endpoint, timeout=30, body={
                "host": domain, "key": key, "keyLocation": self.key_location(domain), "urlList": list(urls)})
        except web.Unreachable:
            return {url: False for url in urls}
        if status >= 500:
            # The service, not the protocol. Still red, but not as a refusal: a
            # refusal would send somebody to a key file that is fine.
            return {url: False for url in urls}
        if status in (200, 202):
            # 202: taken, the key not yet fetched. Accepted all the same — and
            # accepted is not indexed; the protocol says 200 means "received".
            return {url: True for url in urls}
        raise self.refusal(status, domain)

    def refusal(self, status, domain):
        if status == 403:
            return night.Refused("IndexNow could not verify the key of %s" % domain, ownership=True,
                                 repair="the key at %s is not the one posted" % self.key_location(domain))
        if status == 422:
            # Unlike 403 the file is fine here — prove() read it a moment ago.
            return night.Refused("IndexNow refused the addresses of %s" % domain, ownership=True,
                                 repair="the addresses are not on %s, or the key is not of the protocol's form"
                                        % domain)
        if status == 429:
            return night.Refused("IndexNow was posted to about %s too often" % domain, exhausted=True, too_fast=True)
        return night.Refused("IndexNow refused the submission for %s with status %d" % (domain, status))
