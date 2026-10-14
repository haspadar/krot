"""python3 -m krot_index.counts --config <project.json>

Once a day, what each engine holds of each of the project's sites, written to
krot_index.index_count. Only Bing and Yandex: Google's figures come from its own
export. Reads statistics and nothing else, so it spends none of the allowance the
nights offer pages against — which is why it is a unit of its own: a failed count
must not colour a night of offering, nor the other way round.

Exit code: 0 where nothing needs a person — a site the engine has not walked yet
included; 1 where something does (a key, an account that does not hold the site,
an engine that could not be read, a row that could not be written).
"""

import argparse
import json
import os
import sys

from krot_index import night, store as stores
from krot_index.cli import FAILED, KEYS, OK, build

# The engines that publish a figure for a site, in the order they are read.
COUNTED = ("bing", "yandex")


def over(engine, name, sites, store, today, out, err):
    """One engine over every site. Returns how many sites need a person."""
    failed = 0
    for site in sites:
        domain = site["domain"]
        try:
            days = engine.index_counts(domain, today)
        except night.NoData as nothing:
            print("%s %s: %s — nothing to write yet" % (name, domain, stores.first_line(nothing)), file=out)
            continue
        except night.Refused as refused:
            failed += 1
            print("%s %s: %s%s" % (name, domain, stores.first_line(refused),
                                   " (%s)" % refused.repair if refused.repair else ""), file=err)
            continue
        if not days:
            print("%s %s: the engine named no days yet — nothing to write" % (name, domain), file=out)
            continue
        try:
            for day, in_index, not_in_index in days:
                store.count(domain, name, day, in_index, not_in_index)
        except Exception as failure:
            # Not stopping: a refused write costs this site's figures, and the other sites' are still readable.
            failed += 1
            print("%s %s: the figures were not recorded: %s" % (name, domain, stores.first_line(failure)), file=err)
            continue
        print("%s %s: %d days, %s to %s, latest in_index %s" % (
            name, domain, len(days), days[0][0], days[-1][0],
            next((held for _, held, _ in reversed(days) if held is not None), "unknown")), file=out)
    return failed


def main(argv=None, connect=None, engines=None, out=None, err=None, store=None):
    parser = argparse.ArgumentParser(prog="krot-index-counts")
    parser.add_argument("--config", required=True)
    args = parser.parse_args(argv)
    out, err = out or sys.stdout, err or sys.stderr

    with open(args.config) as source:
        config = json.load(source)
    names = [name for name in COUNTED if name in config.get("engines", [])]
    if not names:
        print("krot-index-counts: %s declares neither of %s — the role should not have installed this unit"
              % (config.get("project"), " and ".join(COUNTED)), file=err)
        return FAILED
    sites = config.get("sites", [])
    if not sites:
        print("krot-index-counts: %s declares no sites" % config.get("project"), file=err)
        return FAILED

    try:
        store = store or stores.PostgresStore(config["database"], connect)
        store.check(oldest=stores.SCHEMA_VERSION)
        today = store.today()
    except stores.Missing as missing:
        print("krot-index-counts: %s" % missing, file=err)
        return FAILED
    except Exception as failure:
        print("krot-index-counts: database %s cannot be reached: %s" % (config["database"], failure), file=err)
        return FAILED

    failed = 0
    for name in names:
        key = os.environ.get(KEYS[name], "")
        if not key:
            print("krot-index-counts: %s is empty — the unit's env file has no key for %s" % (KEYS[name], name),
                  file=err)
            failed += 1
            continue
        try:
            engine = (engines or build)(name, key)
        except (OSError, ValueError) as failure:
            print("krot-index-counts: the %s key could not be used: %s" % (name, failure), file=err)
            failed += 1
            continue
        failed += over(engine, name, sites, store, today, out, err)
    return OK if failed == 0 else FAILED


if __name__ == "__main__":
    sys.exit(main())
