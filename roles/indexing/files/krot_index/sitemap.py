"""What a site serves, read the way a search engine reads it — over HTTP, unauthenticated.

busel reads its own sitemap inside its kernel, past nginx and Cloudflare. This
program cannot: it knows no project's code, only the address the project
declared. The difference shows on a closed site, which busel still read and this
reads as unreadable — which is right, since offering an engine a site that
answers 401 spends the allowance on pages nobody may open.
"""

import re
import xml.etree.ElementTree as ElementTree
from urllib.parse import urlsplit

from krot_index import web

# A sitemap index nested deeper than this is a loop or a mistake, not a site.
DEPTH = 3

# More files than this from one site is a generator gone wrong. Reading them all
# would hold the night on one site; refusing says so.
FILES = 500


class Unreadable(Exception):
    """The site's list could not be had whole — and a part of it is no list at all."""


def _tag(element):
    return element.tag.rsplit("}", 1)[-1]


def _locs(root, parent):
    found = []
    for entry in root:
        if _tag(entry) != parent:
            continue
        for field in entry:
            if _tag(field) == "loc" and field.text and field.text.strip():
                found.append(field.text.strip())
    return found


class Sitemap:
    def __init__(self, fetch=web.call):
        self.fetch = fetch

    def pages(self, url, cards_path=None, cards_sitemap=None):
        """Every page the site serves, in its own order, each marked card or not.

        Returns None where any part of the sitemap could not be read. ⚠️ Not an
        empty dict: an empty answer means the site serves nothing, and the
        caller forgets every stored row the site no longer serves — an outage
        read as "serves nothing" would empty the site's history in one night.
        """
        try:
            listed = {}
            self._walk(url, listed, 0, [0], cards_path, cards_sitemap)
            return listed
        except Unreadable:
            return None

    def _walk(self, url, listed, depth, files, cards_path, cards_sitemap):
        if depth > DEPTH:
            raise Unreadable("%s nests sitemaps deeper than %d" % (url, DEPTH))
        files[0] += 1
        if files[0] > FILES:
            raise Unreadable("more than %d sitemap files" % FILES)
        try:
            status, raw = self.fetch("GET", url)
        except web.Unreachable as failure:
            raise Unreadable(str(failure))
        if status != 200:
            raise Unreadable("%s answered %d" % (url, status))
        try:
            root = ElementTree.fromstring(raw)
        except ElementTree.ParseError:
            # A catch-all route answers 200 with the home page to any path; the
            # engines would be handed that address as if it were a sitemap.
            raise Unreadable("%s is not XML" % url)
        kind = _tag(root)
        if kind == "sitemapindex":
            for nested in _locs(root, "sitemap"):
                self._walk(nested, listed, depth + 1, files, cards_path, cards_sitemap)
            return
        if kind != "urlset":
            raise Unreadable("%s is neither <urlset> nor <sitemapindex>" % url)
        file_is_cards = bool(cards_sitemap and re.search(cards_sitemap, url))
        for page in _locs(root, "url"):
            if page in listed:
                continue
            listed[page] = file_is_cards or bool(cards_path and re.search(cards_path, urlsplit(page).path))
