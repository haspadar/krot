"""Folds log lines into what the store keeps: per family, per section, per day.

Plain arithmetic over lines somebody else read, so it is tested without a file, a
database or a server. What it must get right is small and easy to get wrong:
which lines are people, which crawler a line claims to be, whether the claim
holds, and which day a line belongs to.
"""

from krot_collect import agents as names
from krot_collect import logline
from krot_collect.prowling import is_prowling
from krot_collect.sections import without_query

# Above which a response is slow: Google's crawl-budget documentation names a
# second as where fetch time starts limiting how much of a site is crawled.
SLOW_SECONDS = 1.0

# How much of a path is kept. No page of the earlier network reached 65
# characters; past 255 it is a traversal or a tracking tail — still worth a row,
# since "an AI crawler asks for nonsense" is a fact, not noise.
PATH_BYTES = 255

# The three addresses where a 5xx stops the crawl rather than one page: an
# unreachable robots.txt reads to Google as "do not crawl this site", the maps are
# the list of what exists, the home page is where everybody starts.
ROBOTS, SITEMAP, HOME = "robots", "sitemap", "home"


def essential(path):
    clean = without_query(path)
    if clean in ("", "/"):
        return HOME
    if clean == "/robots.txt":
        return ROBOTS
    return SITEMAP if clean.startswith("/sitemap") else None


class Reading:
    """One pass: what was counted, and which days were covered.

    The two travel together: figures without days cannot tell an absent crawler
    from an unread one, and days without figures would mark a day collected and
    lose what it held.
    """

    def __init__(self, crawlers, days, sections, requests, paths):
        # {(day, family): [requests, bytes, errors]}
        self.crawlers = crawlers
        # {day}: every day the lines spoke for, days of people alone included
        self.days = days
        # {(day, family, section, status_class): requests}
        self.sections = sections
        # {day: {requests, human, errors_5xx, rt_sum, rt_count, slow, robots_5xx, sitemap_5xx, home_5xx}}
        self.requests = requests
        # {(day, family, path): requests}
        self.paths = paths

    def without(self, spoiled):
        """This reading minus the days a broken file spoke for — each dropped whole.

        ⚠️ Both the figures and the mark, never one without the other: the figures
        alone store an undercount as fact, the mark alone records "nobody came"
        for a day nobody finished reading.
        """
        if not spoiled:
            return self
        return Reading(
            {key: value for key, value in self.crawlers.items() if key[0] not in spoiled},
            {day for day in self.days if day not in spoiled},
            {key: value for key, value in self.sections.items() if key[0] not in spoiled},
            {day: value for day, value in self.requests.items() if day not in spoiled},
            {key: value for key, value in self.paths.items() if key[0] not in spoiled},
        )


def new_day():
    return {"requests": 0, "human": 0, "errors_5xx": 0, "rt_sum": 0.0, "rt_count": 0, "slow": 0,
            "robots_5xx": 0, "sitemap_5xx": 0, "home_5xx": 0}


class Tally:
    def __init__(self, agents, ranges, sections, pattern, ai_paths=False, pairs=None):
        self.agents = agents
        # confirms(family, address) -> True / False / None
        self.ranges = ranges
        self.sections = sections
        self.pattern = pattern
        self.ai_paths = ai_paths
        # domain -> Pair, for the sites that declared one
        self.pairs = pairs or {}
        self.media_prefix = sections.media_prefix

    def of(self, lines, domain=None):
        pair = self.pairs.get(domain)
        crawlers, sections, requests, paths = {}, {}, {}, {}
        days = set()
        for text in lines:
            one = logline.read(text, self.pattern)
            if one is None:
                continue
            day = one.day
            # Before deciding whether the line interests us: a day where every
            # request came from people is still a day that was read, and a day the
            # store is not told about is asked for again forever.
            days.add(day)

            # Counted before any decision, and the placement is the guarantee: the
            # sum check — families plus `human` equal this — proves nothing was
            # dropped only while this is taken before anything can be.
            served = requests.setdefault(day, new_day())
            served["requests"] += 1
            if one.status >= 500:
                served["errors_5xx"] += 1
                # Only 5xx: a 404 on robots.txt is a site saying "crawl
                # everything", not an outage.
                which = essential(one.path)
                if which is not None:
                    served[which + "_5xx"] += 1
            if one.response_time is not None:
                served["rt_sum"] += one.response_time
                served["rt_count"] += 1
                if one.response_time > SLOW_SECONDS:
                    served["slow"] += 1

            family = self.agents.family(one.agent)
            if family is None:
                served["human"] += 1
                continue

            # A name anybody can type, on a request no crawler makes: filed as what
            # it is. Counted as an arrival, a scan argues for work on a channel it
            # says nothing about — the wrong conclusion the first live run drew.
            if self.agents.is_impersonated(family) and is_prowling(one.path):
                family = names.IMPOSTOR

            # ⚠️ Only a "no" marks it. None means the family publishes nothing or
            # its source failed tonight, and read as a denial it would move
            # thousands of honest requests a fortnight into the suspect bucket.
            if self.ranges.confirms(family, one.address) is False:
                family += names.UNVERIFIED

            # Not for an impostor: `/media/../.env` would split one scan across two
            # families and halve whichever a screen reads.
            if (self.media_prefix and family != names.IMPOSTOR and not family.endswith(names.UNVERIFIED)
                    and one.path.startswith(self.media_prefix)):
                family += names.MEDIA

            figures = crawlers.setdefault((day, family), [0, 0, 0])
            figures[0] += 1
            figures[1] += one.bytes
            if one.status >= 400:
                figures[2] += 1

            # Under the SAME family name, suffixes and all: that is what lets the
            # sections be summed against the requests.
            part = (day, family, self.sections.of(one.path, pair), one.status // 100)
            sections[part] = sections.get(part, 0) + 1

            # Asked after every suffix, so `-media` and `-unverified` fall out here.
            if self.ai_paths and self.agents.reads_for_ai(family):
                key = (day, family, stored_path(one.path))
                paths[key] = paths.get(key, 0) + 1

        return Reading(crawlers, days, sections, requests, paths)


def stored_path(path):
    """Without its query, cut to 255 bytes — within the column's 255 characters however they encode.

    The query is dropped for the reason sections drop it: `/berlin?page=2` kept
    whole would file one page under as many rows as it has parameters.
    """
    clean = without_query(path).encode("utf-8", "surrogateescape")[:PATH_BYTES]
    # Invalid bytes cannot reach a varchar at all; a cut through a character or a
    # stray byte in a scanner's path is dropped rather than refused by the column.
    return clean.decode("utf-8", "ignore")
