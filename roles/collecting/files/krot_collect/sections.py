"""Which part of a site a path belongs to, by a project's own rules.

The count of a crawler's visits answers the wrong question. Measured by the
earlier implementation, the share of cards in Googlebot's crawl was 28–38% on
healthy sites and 10% on one that had just lost its pages, while request counts
were indistinguishable: volume said nothing, composition said everything.

⚠️ Folded from the PATH ALONE. Asking the site's router would cost a boot per site
over a fortnight of archives, and would answer about today's routes for a line
written two weeks ago.

The rules are the project's (one set per project, from the inventory); the order
they are applied in is this module's, and it repeats the earlier implementation
exactly — the golden test compares the two.
"""

import re

HOME = "home"
ROBOTS = "robots"
SITEMAP = "sitemap"
MEDIA = "media"
# The last resort, and it carries weight: nothing may be filed under no section,
# because the sections of a family and day summed against its requests are the
# only check that the folding dropped no line.
OTHER = "other"

BUILT_IN = (HOME, ROBOTS, SITEMAP, MEDIA, OTHER)

# Files a site serves from its public directory. `other` explicitly, so a request
# for `favicon.ico` is never read as a place called "favicon.ico". Compared WITH
# case, as the earlier implementation did: `/FAVICON.ICO` falls through.
FILE_SUFFIXES = (".css", ".js", ".png", ".ico", ".txt", ".json", ".webmanifest")


def without_query(path):
    """The path without query or fragment: `/berlin?page=2` is the page `/berlin`."""
    cut = len(path)
    for mark in "?#":
        at = path.find(mark)
        if at != -1:
            cut = min(cut, at)
    return path[:cut]


class Pair:
    """A site's rule that a path of exactly two segments is a place: `/france/paris`.

    For a site whose places are named by data (a country, then a city), so no prefix
    can list them. It is the SITE's, not the project's: the other sites of a project
    keep their two-segment doors (`/go/<id>`) in `other`, and a rule shared by the
    project would move their rows without a word.

    section:      where such a path is filed
    except_first: first segments that are not places (`onward`, `exit`), lower case
    """

    def __init__(self, section, except_first=()):
        self.section = section
        self.except_first = frozenset(word.lower() for word in except_first)


class Sections:
    """One project's rule set.

    rules:        [{section, prefixes, bare: self|other}] in declaration order
    bare_segment: the section of a lone unknown segment at the root, or None
    service_words: lone segments that are not places, compared in lower case
    slice:        {segments, last, section} or None — `/uralsk/parni/25-30`
    media_prefix: where the project serves its photographs, or None
    """

    def __init__(self, rules=(), bare_segment=None, service_words=(), slice=None, media_prefix=None):
        self.rules = [(one["section"], tuple(one["prefixes"]), one.get("bare", "other") == "self") for one in rules]
        self.bare_segment = bare_segment
        self.service_words = frozenset(word.lower() for word in service_words)
        self.slice = None
        if slice:
            self.slice = (int(slice["segments"]), re.compile(slice["last"], re.ASCII), slice["section"])
        self.media_prefix = media_prefix

    def of(self, path, pair=None):
        clean = without_query(path)
        if clean in ("", "/"):
            return HOME
        if clean == "/robots.txt":
            return ROBOTS
        # Before the file suffixes, which would claim every `.xml` map — and a
        # tokenised `/sitemap-<hex>.xml` included.
        if clean.startswith("/sitemap"):
            return SITEMAP
        if self.media_prefix and clean.startswith(self.media_prefix):
            return MEDIA

        # Every rule's prefixes WITH a tail first, and only then the bare ones.
        # Rule by rule instead, a bare prefix of the first rule would be judged
        # before a tailed prefix of the second.
        for section, prefixes, _ in self.rules:
            for prefix in prefixes:
                if clean.startswith(prefix) and len(clean) > len(prefix):
                    return section
        for section, prefixes, bare_is_section in self.rules:
            for prefix in prefixes:
                if clean == prefix or clean == prefix.rstrip("/"):
                    # A card prefix with no name is nothing served; an index of
                    # places under its bare prefix is a page. The rule says which.
                    return section if bare_is_section else OTHER

        segments = [one for one in clean.split("/") if one != ""]

        if self.slice and len(segments) == self.slice[0] and self.slice[1].fullmatch(segments[-1]):
            return self.slice[2]

        # After every rule and the slice: a path they claim never gets here. Not a
        # file, as a lone segment is not.
        if (pair and len(segments) == 2 and segments[0].lower() not in pair.except_first
                and not segments[1].endswith(FILE_SUFFIXES)):
            return pair.section

        # Deeper than one segment and nothing above: an outbound door, a beacon, a
        # scanner's traversal. None of them a page the audit counts.
        if len(segments) != 1:
            return OTHER

        only = segments[0]
        if only.endswith(FILE_SUFFIXES):
            return OTHER
        if only.lower() in self.service_words:
            return OTHER
        # Unconditional where the project names one: on a site whose places sit at
        # the root, a lone unknown segment is a place, and a place counted as a
        # service page leaves the share the audit reads. Diluting is the cheaper
        # mistake.
        return self.bare_segment or OTHER
