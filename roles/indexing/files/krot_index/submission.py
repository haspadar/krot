"""Which of a site's pages to ask about and to offer tonight, and the offering itself.

A port of busel's Submission (src/Colony/Index/Submission.php). The order is the
design: an engine whose allowance belongs to the project is asked first, so the
scarce submissions go to pages it does not know.
"""

from krot_index import night

# The window of asking, as a multiple of what can be offered. A bound on TIME:
# an inspection costs seconds, and learning about more pages than the night can
# act on buys nothing.
ASK_NUMERATOR = 3
ASK_DENOMINATOR = 2

# How many questions go out together. Google limits the day, not the pace.
AT_ONCE = 10

# ⚠️ A reservation for cards, not a priority. Listings come first, but every
# site of busel serves more listings than a window holds, so without a fixed
# share no card of any site would ever be asked about.
CARD_SHARE = 4


def _chunks(items, size):
    size = max(1, size)
    for start in range(0, len(items), size):
        yield items[start:start + size]


def _by_age(pages, rank):
    """Never asked first, then longest ago asked first."""
    never = [url for url in pages if url not in rank]
    answered = sorted((url for url in pages if url in rank), key=rank.get)
    return never + answered


def what_to_ask_about(listings, cards, asked, ceiling):
    """The listings due longest, then the cards due longest, each cut to its share.

    ⚠️ Cut BEFORE they are joined: joined first, the listings alone fill every
    window. Where one group has less than its share, the other takes the rest.
    """
    rank = {url: place for place, url in enumerate(asked)}
    due_listings = _by_age(listings, rank)
    due_cards = _by_age(cards, rank)
    for_cards = min(len(due_cards), ceiling // CARD_SHARE)
    for_listings = min(len(due_listings), ceiling - for_cards)
    return due_listings[:for_listings] + due_cards[:ceiling - for_listings]


class Submission:
    def __init__(self, engine, store, sharing=1, sleep=None):
        self.engine = engine
        self.store = store
        self.sharing = sharing
        self.sleep = sleep or (lambda seconds: None)

    def share(self, domain):
        return night.share_of(self.engine.daily_quota(domain), self.sharing)

    def of(self, domain, pages):
        """`pages` is the sitemap's answer: {url: is_card}, or None where it could not be read."""
        if pages is None:
            return night.Offer.unreadable()

        # Before asking: the list is complete right here, and a night that stops
        # halfway would otherwise leave the dropping to a pass that may not come.
        self.store.forget_gone(domain, list(pages))

        listings = [url for url, card in pages.items() if not card]
        cards = [url for url, card in pages.items() if card]
        wanted = listings + cards

        if not self.engine.worth_asking():
            return self._offer_without_asking(domain, wanted)

        slug = self.engine.slug
        ceiling = self.share(domain) * ASK_NUMERATOR // ASK_DENOMINATOR
        asking = what_to_ask_about(listings, cards, self.store.asked(domain, slug), ceiling)
        states = {}
        unknown = []
        pause = self.engine.pause_between_batches()
        for batch in _chunks(asking, AT_ONCE):
            # Before every batch, not between a site's own: a pace limit counts
            # against the key, so the last batch of one site touches the next.
            self.sleep(pause)
            for url, state in self.engine.states(domain, batch).items():
                states[state] = states.get(state, 0) + 1
                if state not in night.SILENT:
                    self.store.remember(domain, slug, url, state)
                if state == night.UNKNOWN:
                    unknown.append(url)

        if len(wanted) > len(asking):
            # Named, so a survey of the first three hundred of three thousand
            # does not read as the whole site.
            states[night.NOT_ASKED] = len(wanted) - len(asking)

        # Counted after the asking: this night's answers belong in the count.
        answered = len(self.store.asked(domain, slug))
        return self._offer(domain, unknown, states, answered, len(wanted), asked=True)

    def _offer_without_asking(self, domain, wanted):
        # ⚠️ No states at all for a site serving nothing, rather than {unknown: 0}:
        # a zero count reads as an engine that answered nothing, and an empty site
        # would turn the unit red every night over nothing broken.
        states = {night.UNKNOWN: len(wanted)} if wanted else {}
        sent = self.store.ever_offered(domain, self.engine.slug)
        return self._offer(domain, wanted, states, sent, len(wanted))

    def _offer(self, domain, unknown, states, answered, serving, asked=False):
        quota = self.share(domain)
        held = set(self.store.offered_recently(domain, self.engine.slug))
        fresh = [url for url in unknown if url not in held]
        # ⚠️ Cut to the allowance BEFORE sending: an engine handed more than is
        # left takes it, spends the rest and refuses the NEXT call, and a night
        # that recorded all it sent would drift from the engine without a word.
        today = fresh[:quota]
        submitted = []
        refused = None
        for batch in _chunks(today, self.engine.offer_at_once()):
            try:
                accepted = [url for url, taken in self.engine.submit_all(domain, batch).items() if taken]
            except night.Refused as refusal:
                refused = refusal
                accepted = list(refusal.accepted)
            for url in accepted:
                # ⚠️ Not caught here. This row is what holds the page out of
                # tomorrow's offer; a write lost quietly spends the allowance on
                # repeats every night after, green.
                self.store.offered(domain, self.engine.slug, url)
                submitted.append(url)
            if refused is not None:
                break
        return night.Offer(states, submitted, len(unknown), refused, len(unknown) - len(fresh),
                           len(today), answered, serving, asked)
