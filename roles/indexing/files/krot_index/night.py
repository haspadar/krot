"""What one night over one site found and did, and what it is allowed.

A port of busel's Offer, Share, Spending and Refusal (src/Colony/Index/). The
reasons behind each rule are written there and in design.md of the change; the
comments here keep only what a reader of this file needs to not undo them.
"""

INDEXED = "indexed"
KNOWN = "known"
UNKNOWN = "unknown"
# The engine said nothing about the page — unreachable, refused, a key gone.
UNASKED = "unasked"
# The engine refused to answer at this pace.
THROTTLED = "throttled"
# Not an answer at all: the page was past the night's bound on asking.
NOT_ASKED = "not asked"

# ⚠️ Neither is written to the store. Both are about the night, not the page,
# and written they overwrite yesterday's real answer with today's blip.
SILENT = (UNASKED, THROTTLED)


class Refused(Exception):
    """The engine refused for a reason about the SITE, not one page.

    `exhausted` is a spent day and `too_fast` a pace refusal: both repair
    themselves and do not colour the unit. Anything else is for a person, and
    `repair` names what to do where the engine's own words do not.
    """

    def __init__(self, message, ownership=False, exhausted=False, too_fast=False, repair=""):
        super().__init__(message)
        self.ownership = ownership
        self.exhausted = exhausted
        self.too_fast = too_fast
        self.repair = repair


def share_of(allowance, between):
    """This site's part of an allowance shared by `between` sites.

    ⚠️ Floor, not round: three sites rounding up would send 67 each, 201 against
    Google's 200 for the project, and the last one would meet the refusal.
    """
    return max(1, allowance // max(1, between))


class Offer:
    def __init__(self, states, submitted=None, unknown=0, refused=None, held=0,
                 attempted=0, answered=0, serving=0, asked=False):
        # None where the site could not be read; {} where it serves nothing.
        self.states = states
        self.submitted = list(submitted or [])
        self.unknown = unknown
        self.refused = refused
        # Unknown to the engine, but offered recently enough to be in its queue.
        self.held = held
        self.attempted = attempted
        self.answered = answered
        self.serving = serving
        self.asked = asked

    @classmethod
    def unreadable(cls):
        return cls(None)

    def covered(self):
        """(pages the store has a record of, pages served) — counts, never a percentage.

        A percentage of 35 500 pages gains 0.06 a night and prints 0% for nine
        nights; a count moves every night, and a count that stands still is
        exactly the stall this line exists to show.
        """
        if self.serving <= 0:
            return None
        return self.answered, self.serving

    def record_is(self):
        # An asked engine's record is its ANSWER; an unasked one's is what we SENT.
        return "answered" if self.asked else "sent"

    def accepted_nothing(self):
        """Pages were handed over, none taken, and the engine said no reason.

        The only way a dead endpoint shows on an engine nobody asks. A spent day
        or a throttle also take nothing, but they carry a refusal and repair
        themselves; nothing attempted is a site with nothing due.
        """
        return self.refused is None and self.attempted > 0 and not self.submitted

    def unasked(self):
        states = self.states or {}
        return states.get(UNASKED, 0) + states.get(NOT_ASKED, 0)

    def answered_nothing(self):
        """The engine was asked and answered about none of the pages."""
        if not self.states:
            return False
        answered = sum(count for state, count in self.states.items() if state not in (UNASKED, NOT_ASKED, THROTTLED))
        return answered == 0

    def was_throttled(self):
        return (self.states or {}).get(THROTTLED, 0) > 0

    def left(self):
        """Unknown pages that did not fit today, plus the ones never reached."""
        return max(0, self.unknown - len(self.submitted)) + self.unasked()

    def fails(self):
        """Whether this site should turn the unit red: something a person must repair."""
        if self.states is None:
            # ⚠️ Red here, where busel stays green. busel walks only sites it has
            # opened and reads them in-process; here the project DECLARED the site,
            # so a sitemap that answers 401, 404 or a Cloudflare challenge is a
            # site the engines cannot be told about until somebody looks.
            return True
        if self.answered_nothing() and not self.was_throttled():
            return True
        if self.accepted_nothing():
            return True
        return self.refused is not None and not self.refused.exhausted and not self.refused.too_fast


def refusal_of(offer):
    """The word stored for why a night ended short, or None where it did not."""
    if offer.states is None:
        return "unreadable"
    refused = offer.refused
    if refused is None:
        return None
    if refused.too_fast:
        return "throttle"
    if refused.ownership:
        return "ownership"
    if refused.exhausted:
        return "quota"
    # Unrecognised words: filed with what a person must look at, not with the
    # harmless two — guessing harmless would hide the case the column is for.
    return "ownership"


class Spending:
    """One row of krot.index_run: what the night was allowed and what it did."""

    def __init__(self, site, engine, offer, share, asked):
        unreadable = offer.states is None
        self.site = site
        self.engine = engine
        # The site's share, never the engine's raw figure. Named by the engine,
        # it is the allowance; planned against a guess, it is the floor.
        self.allowance = share if asked and not unreadable else None
        self.floor = None if asked or unreadable else share
        self.attempted = offer.attempted
        self.accepted = len(offer.submitted)
        # ⚠️ Null, not zero, for a site that could not be read: zero would
        # overwrite yesterday's queue with "nothing to wait for" on exactly the
        # site somebody has to look at.
        self.held = None if unreadable else offer.held
        self.waiting = None if unreadable else offer.left()
        self.refusal = refusal_of(offer)
