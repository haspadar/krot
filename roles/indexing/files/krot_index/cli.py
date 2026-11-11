"""krot-index --config <project.json> --engine <name>

The config is written by the indexing role: which database, which engines, which
sites. Keys come from the environment the unit loads from the project's env
file, never from the config, so the config can be read by anyone on the machine
and the keys by nobody but this program.

Exit code: 0 where nothing needs a person — a spent allowance, a throttle, a site
with nothing due included; 1 where something does. A red that arrives nightly
over a condition that repairs itself stops being read before a revoked key
produces one.
"""

import argparse
import json
import os
import re
import sys
import time

from krot_index import store as stores
from krot_index.sitemap import Sitemap
from krot_index.walk import Walk

OK = 0
FAILED = 1

# Which environment variable holds each engine's key. Google's is a path: the
# service account is multi-line JSON, and systemd's EnvironmentFile= parses
# quotes and backslashes its own way — the key would arrive mangled.
KEYS = {
    "google": "KROT_INDEX_GOOGLE_KEY_FILE",
    "bing": "KROT_INDEX_BING_KEY",
    "yandex": "KROT_INDEX_YANDEX_TOKEN",
    "indexnow": "KROT_INDEX_INDEXNOW_SECRET",
}


def build(name, key):
    if name == "google":
        from krot_index.engines.google import Google

        with open(key) as source:
            return Google(source.read())
    if name == "bing":
        from krot_index.engines.bing import Bing

        return Bing(key)
    if name == "yandex":
        from krot_index.engines.yandex import Yandex

        return Yandex(key)
    if name == "indexnow":
        from krot_index.engines.indexnow import IndexNow

        return IndexNow(key)
    raise ValueError(name)


def offered(config, name, out):
    """The project's sites that are offered to this engine, the others named as skipped.

    A site lists its own `engines` where its account at an engine is not the project's key's: walking it
    would be refused every night, and a red that repeats over a decision already taken stops being read
    before a revoked key produces one. Absent, a site is offered to every engine of the project.
    One line per skipped site, so a site left out is as audible as one walked.
    """
    chosen = []
    for site in config.get("sites", []):
        if name in site.get("engines", config.get("engines", [])):
            chosen.append(site)
        else:
            print("%s %s: skipped — the inventory does not offer this site to %s" % (name, site.get("domain"), name),
                  file=out)
    return chosen


def key_variable(name, account=None):
    """The environment variable holding an engine's key, for a named account the account's own.

    Bing and Yandex sites in another Webmaster account use that account's key.
    """
    if account and name in ("bing", "yandex"):
        return "%s_%s" % (KEYS[name], account.upper())
    return KEYS[name]


def accounts(name, sites):
    """[(account, sites)] in the order the accounts first appear; account is None for the project's own key.

    One group is one key and, for Bing, one engine: its allowance question, the cut-off after three
    sites it cannot answer, and the throttle are the account's, so a site in another account must
    not spend the first one's tries.
    """
    groups = {}
    for site in sites:
        account = (site.get(name + "_account") or None) if name in ("bing", "yandex") else None
        groups.setdefault(account, []).append(site)
    return list(groups.items())


def main(argv=None, connect=None, engines=None, out=None, err=None):
    parser = argparse.ArgumentParser(prog="krot-index")
    parser.add_argument("--config", required=True)
    parser.add_argument("--engine", required=True)
    args = parser.parse_args(argv)
    err = err or sys.stderr

    with open(args.config) as source:
        config = json.load(source)
    name = args.engine.lower()

    # ⚠️ Checked before the key, and in this order: a misspelt engine in a timer
    # answered with a sentence about keys sends the reader to the one thing that
    # is fine.
    if name not in KEYS:
        print("krot-index: no engine named %r — this program knows: %s" % (args.engine, ", ".join(sorted(KEYS))),
              file=err)
        return FAILED
    if name not in config.get("engines", []):
        print("krot-index: %s is not among %s's engines — the role should not have installed this unit"
              % (name, config.get("project")), file=err)
        return FAILED
    out = out or sys.stdout
    sites = offered(config, name, out)
    if not sites:
        print("krot-index: %s declares no site for %s" % (config.get("project"), name), file=err)
        return FAILED

    # A group whose key is missing or unusable is red but does not stop the others: one account's
    # revoked key must not keep another account's pages from going out.
    failed = 0
    runnable = []
    for account, group in accounts(name, sites):
        variable = key_variable(name, account)
        key = os.environ.get(variable, "")
        if not key:
            print("krot-index: %s is empty — the unit's env file has no key for %s%s"
                  % (variable, name, " account %s" % account if account else ""), file=err)
            failed += 1
            continue
        try:
            runnable.append((account, group, (engines or build)(name, key)))
        except (OSError, ValueError) as failure:
            # Never quoting the key: a malformed one is still mostly a key.
            print("krot-index: the %s key%s could not be used: %s"
                  % (name, " of account %s" % account if account else "", failure), file=err)
            failed += 1
    if not runnable:
        return FAILED

    try:
        store = stores.PostgresStore(config["database"], connect)
        store.check()
    except stores.Missing as missing:
        print("krot-index: %s" % missing, file=err)
        return FAILED
    except Exception as failure:
        print("krot-index: database %s cannot be reached: %s" % (config["database"], failure), file=err)
        return FAILED

    # Before any site is walked: a typo found on the third site would leave the
    # first two offered and the rest not, and the night half-done.
    for _, group, _ in runnable:
        for site in group:
            for field in ("cards_path", "cards_sitemap"):
                try:
                    re.compile(site.get(field) or "")
                except re.error as failure:
                    print("krot-index: %s of %s is not a pattern: %s" % (field, site.get("domain"), failure),
                          file=err)
                    return FAILED

    for _, group, engine in runnable:
        try:
            failed += Walk(engine, store, Sitemap(), out=out, err=err, sleep=time.sleep).over(group)
        except Exception as failure:
            # A page row that could not be written: stopping is the point. That row
            # is what keeps the page out of tomorrow's offer, and carrying on would
            # spend the allowance on repeats every night after.
            print("krot-index: %s stopped: %s" % (name, failure), file=err)
            return FAILED
    return OK if failed == 0 else FAILED


if __name__ == "__main__":
    sys.exit(main())
