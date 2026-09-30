"""The address ranges crawlers publish: collected nightly, asked per line.

Run BEFORE the crawl: the crawl reads what this leaves behind, and against an
empty table every family is simply unconfirmed — counted as it always was.
"""

import json
import os
import re
import urllib.request
from datetime import datetime, timezone

from krot_collect import fetched as judged
from krot_collect import prefix as prefixes

SOURCES = os.path.join(os.path.dirname(os.path.abspath(__file__)), "sources.json")

# ⚠️ Only for the one source that refuses anything else: asked plainly,
# yandex.com/ips answers a captcha page — HTTP 200, HTML, no ranges — and with a
# browser's line returns all its networks. Without it the source fails in the
# shape that reads as success, which is why an answer carrying no ranges is refused.
BROWSER = "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36"
AGENT = "krot-collect (published crawler ranges)"

# Generous — once a night, and a slow source beats an unconfirmed family; bounded —
# a source that hangs must not hold the run.
SECONDS = 30

# Anything shaped like a range, judged afterwards, rather than a pattern aimed at
# one page's layout: a page is rewritten without warning, and a reader tuned to
# its markup fails silently the day it changes.
DUG = re.compile(r"\b(?:\d{1,3}(?:\.\d{1,3}){3}|[0-9a-f]{1,4}(?::[0-9a-f]{0,4}){2,7})/\d{1,3}\b", re.IGNORECASE)

# When a source's own publication date is worth a line: a list that stops moving
# confirms fewer real arrivals every month, and each one it stops confirming is
# filed as unverified. The earlier implementation found two of seventeen sources
# unmoved for over a year, fetching cleanly.
STALE_MONTHS = 12


def load(extra=(), path=SOURCES):
    with open(path) as source:
        shared = json.load(source)["sources"]
    return shared + list(extra)


def http_get(url, browser_agent):
    """The body, following redirects — two sources answer 302 on the way to their file."""
    request = urllib.request.Request(url, headers={"User-Agent": BROWSER if browser_agent else AGENT})
    with urllib.request.urlopen(request, timeout=SECONDS) as response:
        return response.read().decode("utf-8", "replace")


def fetch(source, get=http_get):
    try:
        body = get(source["url"], source.get("browser_agent", False))
    except Exception as failure:
        return judged.refused("%s could not be read: %s" % (source["name"], failure))
    shape = source["shape"]
    if shape == "json":
        return from_json(source["name"], body)
    if shape == "markup":
        return judged.judge(source["name"], DUG.findall(body))
    return judged.judge(source["name"], body.split("\n"))


def from_json(name, body):
    try:
        document = json.loads(body)
    except ValueError as broken:
        # A source that starts serving a page where it served a document: refused,
        # not read as empty.
        return judged.refused("%s could not be read: not a JSON document: %s" % (name, broken))
    # ⚠️ Every step checked: valid JSON of an unexpected shape is what a source
    # serves the day it is redesigned, and read trustingly it would throw and cost
    # every source after it in the run.
    if not isinstance(document, dict) or not isinstance(document.get("prefixes"), list):
        return judged.refused("%s could not be read: a JSON document carrying no list of prefixes" % name)
    lines = []
    for entry in document["prefixes"]:
        text = None
        if isinstance(entry, dict):
            text = entry.get("ipv4Prefix") if entry.get("ipv4Prefix") is not None else entry.get("ipv6Prefix")
        # An entry without a range weighs against the readable share exactly as a
        # malformed line does: dropped as blank, a document whose entries moved to
        # a new key would pass as a short healthy list.
        lines.append(text if isinstance(text, str) else "unreadable entry")
    published = document.get("creationTime")
    return judged.judge(name, lines, published if isinstance(published, str) else None)


def published_at(text):
    """The source's date, or None where it gave none or one that cannot be read.

    ⚠️ An empty string is "did not say", not "said now" — a source serving
    `"creationTime": ""` would otherwise report a frozen list as published this
    minute.
    """
    if not text or not text.strip():
        return None
    try:
        at = datetime.fromisoformat(text.strip().replace("Z", "+00:00"))
    except ValueError:
        return None
    return at if at.tzinfo else at.replace(tzinfo=timezone.utc)


def months_since(text, now):
    at = published_at(text)
    if at is None:
        return None
    # A date ahead of now is zero months old, not that many in the past.
    if at > now:
        return 0
    return (now - at).days // 30


class Ranges:
    """confirms(family, address): True inside a published range, False outside all of
    the family's, None where the family has none.

    ⚠️ Three answers, and the third is the point: AhrefsBot publishes nothing and a
    source can fail for an evening. Answered False, every one of those arrivals
    would be unverified, and the count this exists to clean gets dirtier than before.
    """

    def __init__(self, by_family):
        self.by_family = by_family

    def confirms(self, family, address):
        known = self.by_family.get(family)
        if not known:
            return None
        return any(one.holds(address) for one in known)


def from_rows(rows):
    """Ranges out of stored (family, prefix) rows; a row that no longer reads is skipped."""
    by_family = {}
    for family, text in rows:
        one = prefixes.read(text)
        if one is not None:
            by_family.setdefault(family, []).append(one)
    return Ranges(by_family)


class Collection:
    def __init__(self, sources, store, out, err, get=http_get, now=None):
        self.sources = sources
        self.store = store
        self.out = out
        self.err = err
        self.get = get
        self.now = now or datetime.now(timezone.utc)

    def collect(self):
        """Fetches every source and returns how many refused."""
        refused = 0
        stale = []
        for source in self.sources:
            answer = fetch(source, self.get)
            if answer.refused:
                # ⚠️ A refused source keeps what it stored last time: yesterday's
                # ranges beat none. Cleared, one bad evening would unconfirm every
                # family it covers.
                print(answer.refusal, file=self.err)
                refused += 1
                continue
            self.store.store_ranges(source["name"], source["families"], answer.ranges,
                                    published_at(answer.published))
            months = months_since(answer.published, self.now)
            age = "" if not months else " (published %d month%s ago)" % (months, "" if months == 1 else "s")
            print("%s: %d ranges for %s%s" % (source["name"], len(answer.ranges),
                                             ", ".join(source["families"]) or "no family yet", age), file=self.out)
            if answer.unreadable:
                print("  ⚠ %d of its lines are not ranges — the family may lose real arrivals" % answer.unreadable,
                      file=self.out)
            if months is not None and months >= STALE_MONTHS:
                stale.append(source["name"])
        # After the run, so a source that refused tonight keeps yesterday's rows:
        # only what the list stopped naming goes. Rows of a renamed source would
        # otherwise confirm addresses from a list nothing updates.
        self.store.forget_sources_other_than([source["name"] for source in self.sources])
        if stale:
            print("note: %s last published over %d months ago; a list that stops moving starts calling real "
                  "crawlers unverified" % (", ".join(stale), STALE_MONTHS), file=self.out)
        return refused
