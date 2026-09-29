"""One engine over every site of one project, and what the night says about each.

A port of busel's IndexCommand::walk and ::report. Every line names the engine:
with several jobs on a machine, a line without it merges two channels into one
figure, and a stopped channel then looks like a spent allowance.
"""

import sys

from krot_index import night
from krot_index.submission import Submission


class Walk:
    def __init__(self, engine, store, sitemap, out=None, err=None, sleep=None):
        self.engine = engine
        self.store = store
        self.sitemap = sitemap
        self.out = out or sys.stdout
        self.err = err or sys.stderr
        self.sleep = sleep

    def say(self, domain, text):
        print("%s %s: %s" % (self.engine.slug, domain, text), file=self.out)

    def warn(self, domain, text):
        print("%s %s: %s" % (self.engine.slug, domain, text), file=self.err)

    def over(self, sites):
        """Walks the sites in turn. Returns how many need a person — the exit code's source."""
        # ⚠️ How the allowance divides is the engine's to say: Google's 200 belong
        # to the project and are split between its sites, a per-site allowance is
        # whole at every site and splitting it would waste most of it nightly.
        sharing = 1 if self.engine.quota_is_per_site() else len(sites)
        submission = Submission(self.engine, self.store, sharing, self.sleep)
        failed = 0
        for position, site in enumerate(sites):
            domain = site["domain"]
            pages = self.sitemap.pages(site["sitemap_url"], domain, site.get("cards_path"), site.get("cards_sitemap"))
            offer = submission.of(domain, pages)
            self.report(domain, offer)
            # Before the walk can stop below: the site it stops at is the one
            # whose night needs explaining.
            self.store.record(night.Spending(domain, self.engine.slug, offer,
                                             night.share_of(self.engine.daily_quota(domain), sharing),
                                             self.engine.quota_was_asked(domain)))
            if offer.fails():
                failed += 1
            refused = offer.refused
            if refused is not None and refused.exhausted and not refused.too_fast and not self.engine.quota_is_per_site():
                # The project's day is spent for every site behind this one;
                # asking them would collect the same refusal again and again.
                left = len(sites) - position - 1
                self.warn(domain, "the day's %d submissions are gone%s — normal after a hand-run, "
                                  "the allowance returns when the engine resets it"
                          % (self.engine.daily_quota(domain),
                             " — stopping, %d sites not reached" % left if left else " on the last site"))
                break
        if sites and not self.engine.quota_was_asked(sites[-1]["domain"]):
            self.warn(sites[-1]["domain"], "could not ask what the engine accepts today — planned against a "
                                           "deliberately small number; every night means the key or the endpoint")
        return failed

    def report(self, domain, offer):
        name = self.engine.slug
        if offer.states is None:
            # Not "nothing to do": the next move is the opposite one.
            self.warn(domain, "could not read the sitemap — nothing was asked or offered")
            return
        for state, count in offer.states.items():
            self.say(domain, "%-9s %d" % (state, count))
        refused = offer.refused
        if refused is not None:
            if refused.too_fast:
                self.say(domain, "asked faster than it answers — the pace belongs to the key, the pages wait")
            elif refused.exhausted:
                self.say(domain, "allowance spent for today — the pages wait")
            elif refused.repair:
                self.warn(domain, "%s does not accept pages: %s (%s)" % (name, refused.repair, refused))
            else:
                self.warn(domain, "%s refused: %s" % (name, refused))
            return
        if offer.answered_nothing():
            self.warn(domain, "%s answered about none of these pages — asked too fast, a revoked key, "
                              "or an outage; not an empty site" % name)
            return
        if offer.accepted_nothing():
            self.warn(domain, "%s took none of the %d pages it was offered — an outage or a revoked key; "
                              "not an empty site" % (name, offer.attempted))
            return
        if offer.held:
            self.say(domain, "%-9s %d (already in %s's queue)" % ("held", offer.held, name))
        covered = offer.covered()
        self.say(domain, "%d offered, %d unknown pages left for the next run%s" % (
            len(offer.submitted), offer.left(),
            "" if covered is None else " — %d/%d %s" % (covered[0], covered[1], offer.record_is())))
