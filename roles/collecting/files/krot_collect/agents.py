"""Which crawler a User-Agent line belongs to, and what the collection may believe about it.

A family rather than the line: one bot writes several. Measured by the earlier
implementation, Googlebot arrived as three distinct strings in one day — counting
strings would show three crawlers where there is one, and a drop in any of them
would hide inside the other two.

⚠️ The mark sits INSIDE the line, not at its front: the busiest Googlebot string
begins `Mozilla/5.0 (Linux; Android 6.0.1; Nexus 5X …`. A prefix would miss most of
every crawler here.
"""

import json
import os

DICTIONARY = os.path.join(os.path.dirname(os.path.abspath(__file__)), "agents.json")

# Anything a robot the dictionary does not name. Kept, not dropped: the dictionary
# ages, an AI crawler appears without warning, and a growing `other` is the signal
# to extend it. A person is not `other` — see family().
OTHER = "other"

# A claimed AI crawler whose request gives it away as a scan (see Prowling). Its
# own family rather than `other`: "a robot we have not named" and "somebody is
# scanning the network" are different kinds of work.
IMPOSTOR = "impostor"

# ⚠️ Appended, and deliberately NOT `impostor`. This says only that an address is
# not on a published list, and a list goes out of date on its own: an operator adds
# a point of presence, an aggregator lags a week. Merged with `impostor`, a lagging
# source prints an attack — the loudest case being a project's own uptime monitor,
# most of a quiet site's requests, judged against somebody else's copy of a list.
UNVERIFIED = "-unverified"

# A family fetching photographs rather than reading pages. Measured by the earlier
# implementation over a fortnight: media was 86% of what AhrefsBot took and 77% of
# GPTBot, against 24% for Googlebot — summed, the number says "crawled heavily";
# split, it says who downloads the photographs.
MEDIA = "-media"


class Agents:
    def __init__(self, extra=(), dictionary=DICTIONARY):
        with open(dictionary) as source:
            data = json.load(source)
        # The project's marks go FIRST: its monitor is the single largest line of
        # a quiet site, and read after the shared words it would fall into `other`
        # by the `bot` in its name.
        self.marks = [(one["mark"].lower(), one["family"]) for one in extra] + [tuple(pair) for pair in data["marks"]]
        readers = list(data["ai_readers"]) + [one["family"] for one in extra if one.get("ai") == "read"]
        trainers = list(data["ai_trainers"]) + [one["family"] for one in extra if one.get("ai") == "train"]
        # The pages these read were put in front of a person; the only families
        # whose paths are kept. Trainers read for a corpus: counted, never kept —
        # measured, they were 99% of every AI request and of the rows a path table
        # had grown.
        self.readers = frozenset(readers)
        # A name is worth faking whether or not its paths are kept, so both lists
        # are open to the scan check — the first live run found one scan wearing
        # five of these names in turn.
        self.impersonated = frozenset(readers + trainers)
        self.robotic = tuple(data["robotic"])

    def family(self, agent):
        """The family, or None for a person.

        None rather than `other` for a browser: a visitor belongs to the counter,
        and filing an audience under the bucket meant for unrecognised robots would
        hide the one thing that bucket is watched for.
        """
        lowered = agent.lower()
        for mark, family in self.marks:
            if mark in lowered:
                return family
        # Crude by nature: a crawler wanting to look human can. That is the safe
        # direction — a missed robot understates crawling, a browser taken for one
        # would put a real audience in `other`.
        return OTHER if any(sign in lowered for sign in self.robotic) else None

    def is_impersonated(self, family):
        return family in self.impersonated

    def reads_for_ai(self, family):
        """Whether this family's paths are kept: an AI reader, bare name only.

        ⚠️ Neither suffix counts. `-unverified` arrived from an address the operator
        does not publish, so it is exactly not evidence of what an AI showed anybody;
        `-media` is a photograph, and the question is which pages were read.
        """
        return family in self.readers
