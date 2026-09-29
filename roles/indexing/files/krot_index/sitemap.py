"""What a site serves, read the way a search engine reads it — over HTTP, unauthenticated.

busel reads its own sitemap inside its kernel, past nginx and Cloudflare. This
program cannot: it knows no project's code, only the address the project
declared. The difference shows on a closed site, which busel still read and this
reads as unreadable — which is right, since offering an engine a site that
answers 401 spends the allowance on pages nobody may open.
"""

import gzip
import io
import re
import xml.etree.ElementTree as ElementTree
import zlib
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


def _gunzip(raw):
    unpacked = gzip.GzipFile(fileobj=io.BytesIO(raw)).read(web.MAX_BYTES + 1)
    if len(unpacked) > web.MAX_BYTES:
        raise OSError("unpacks to more than %d bytes" % web.MAX_BYTES)
    return unpacked


_host = web.host_of


class Sitemap:
    def __init__(self, fetch=web.call):
        self.fetch = fetch

    def pages(self, url, domain=None, cards_path=None, cards_sitemap=None):
        """Every page the site serves, in its own order, each marked card or not.

        Returns None where any part of the sitemap could not be read. ⚠️ Not an
        empty dict: an empty answer means the site serves nothing, and the
        caller forgets every stored row the site no longer serves — an outage
        read as "serves nothing" would empty the site's history in one night.

        ⚠️ The sitemap is the site's word, not the project's, and is trusted
        only as far as the project's own declaration reaches: nested files from
        the host of the declared address, pages from `domain`. busel never had
        this question — it builds its URLs from its own paths. Here a sitemap
        listing another host would send this program to fetch it, hand its pages
        to the engine under this site's property, and forget every real page of
        the site because none of them were listed. Anything outside is unreadable.
        """
        try:
            listed = {}
            self._walk(url, listed, 0, [0], _host(url), domain, cards_path, cards_sitemap)
            return listed
        except Unreadable:
            return None

    def _walk(self, url, listed, depth, files, home, domain, cards_path, cards_sitemap):
        if _host(url) != home:
            raise Unreadable("%s is not on %s, where the sitemap was declared" % (url, home))
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
        if raw[:2] == b"\x1f\x8b":
            # sitemap-1.xml.gz is an ordinary nested file; urllib does not
            # unpack it, and read as XML it would turn a healthy site red.
            try:
                raw = _gunzip(raw)
            except (OSError, EOFError, zlib.error) as failure:
                raise Unreadable("%s: %s" % (url, failure))
        try:
            root = ElementTree.fromstring(raw)
        except ElementTree.ParseError:
            # A catch-all route answers 200 with the home page to any path; the
            # engines would be handed that address as if it were a sitemap.
            raise Unreadable("%s is not XML" % url)
        kind = _tag(root)
        if kind == "sitemapindex":
            for nested in _locs(root, "sitemap"):
                self._walk(nested, listed, depth + 1, files, home, domain, cards_path, cards_sitemap)
            return
        if kind != "urlset":
            raise Unreadable("%s is neither <urlset> nor <sitemapindex>" % url)
        file_is_cards = bool(cards_sitemap and re.search(cards_sitemap, url))
        for page in _locs(root, "url"):
            if page in listed:
                continue
            if domain is not None and (urlsplit(page).scheme not in ("http", "https") or _host(page) != domain.lower()):
                raise Unreadable("%s lists %s, which is not on %s" % (url, page, domain))
            listed[page] = file_is_cards or bool(cards_path and re.search(cards_path, urlsplit(page).path))
