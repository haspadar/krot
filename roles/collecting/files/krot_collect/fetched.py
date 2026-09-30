"""What a source returned, judged: accepted with its ranges, or refused with a reason."""

from krot_collect import prefix as prefixes

# The share of range-shaped lines below which the whole answer is refused. Not
# zero — sources carry the odd comment and heading — and not one; far above any
# healthy source and far below the mask-stripped file, where nothing has a mask.
READABLE = 0.8


class Fetched:
    def __init__(self, ranges, refusal, unreadable=0, published=None):
        self.ranges = ranges
        self.refusal = refusal
        # Offered lines that did not become a range, on an accepted answer. ⚠️
        # Reported: a source that half-breaks stays under the threshold, loses up
        # to a fifth of a family's ranges and otherwise looks healthy.
        self.unreadable = unreadable
        # The source's own creationTime, when it publishes one.
        self.published = published

    @property
    def refused(self):
        return self.refusal is not None


def refused(why):
    return Fetched([], why)


def judge(source, lines, published=None):
    offered = [line.strip() for line in lines]
    offered = [line for line in offered if line and not line.startswith("#")]
    if not offered:
        # An empty answer and a broken one cost the same: stored, either would
        # unconfirm every family of the source in one run.
        return refused("%s returned no ranges at all" % source)

    seen = set()
    ranges = []
    repeats = 0
    for line in offered:
        one = prefixes.read(line)
        if one is None:
            continue
        # Deduplicated by the text the source wrote: one source prints each range
        # three times in its page, another's file repeats itself.
        if one.text in seen:
            repeats += 1
            continue
        seen.add(one.text)
        ranges.append(one)

    # Against what was OFFERED, repeats included: a source repeating itself is odd,
    # not broken. Shape is counted, not acceptance — a too-wide network is dropped
    # but is not evidence the source broke.
    shaped = sum(1 for line in offered if prefixes.shaped_like_a_range(line))
    if shaped < len(offered) * READABLE:
        return refused("%s returned %d ranges out of %d lines — too few to be a list of networks; a source "
                       "serving addresses without their network mask reads as this" % (source, shaped, len(offered)))
    # Repeats are NOT unreadable: counting a source's thrice-printed page as broken
    # every night would teach the eye to skip the warning that matters.
    return Fetched(ranges, None, len(offered) - len(seen) - repeats, published)
