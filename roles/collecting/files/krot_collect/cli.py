"""krot-collect --config <project.json> <ranges|crawl>

The config is written by the collecting role: the database, the sites, where
their logs are and in which format, the project's section rules and its own
crawler marks. It holds no key and is readable by anyone on the machine.

Exit code: 0 when every site and source was read; 1 when any was not — the timer's
exit code is the only thing `systemctl --failed` reads, and a collector returning
success while blind to one site is reported as working. That is how the earlier
implementation's traffic collector went five days without running while cron
logged a successful start every hour.
"""

import argparse
import json
import sys

from krot_collect import logline, ranges
from krot_collect import store as stores
from krot_collect.agents import Agents
from krot_collect.crawl import Collection
from krot_collect.logfiles import LogFiles
from krot_collect.sections import Sections
from krot_collect.tally import Tally

OK = 0
FAILED = 1
JOBS = ("ranges", "crawl")


def open_store(config, connect, err):
    try:
        store = stores.PostgresStore(config["database"], connect)
        store.check()
        return store
    except stores.Missing as missing:
        print("krot-collect: %s" % missing, file=err)
    except Exception as failure:
        print("krot-collect: database %s cannot be reached: %s" % (config["database"], stores.first_line(failure)),
              file=err)
    return None


def run_ranges(config, store, out, err, get):
    sources = ranges.load(config.get("extra_range_sources", []))
    refused = ranges.Collection(sources, store, out, err, get=get).collect()
    if refused:
        # ⚠️ Does not stop the crawl: the families of a refused source keep
        # yesterday's ranges, or stay unconfirmed — counted as they always were.
        print("krot-collect: %d of %d sources refused" % (refused, len(sources)), file=err)
        return FAILED
    print("Collected %d sources." % len(sources), file=out)
    return OK


def run_crawl(config, store, out, err):
    logs = config.get("logs", {})
    pattern = logline.FORMATS.get(logs.get("format", "time_first"))
    if pattern is None:
        print("krot-collect: no log format named %r — this program knows: %s"
              % (logs.get("format"), ", ".join(sorted(logline.FORMATS))), file=err)
        return FAILED
    crawl = config.get("crawl", {})
    rules = crawl.get("sections", {})
    sections = Sections(rules.get("rules", []), rules.get("bare_segment"), rules.get("service_words", []),
                        rules.get("slice"), crawl.get("media_prefix"))
    tally = Tally(Agents(crawl.get("extra_agents", [])), ranges.from_rows(store.range_rows()), sections, pattern,
                  ai_paths=crawl.get("ai_paths", False))
    files = LogFiles(logs.get("directory", "/var/log/nginx"), logs.get("pattern", "{domain}-access.log*"))
    domains = [site["domain"] for site in config["sites"]]
    failed = Collection(files, tally, store, pattern, out, err).collect(domains)
    gone = store.forget_older_than()
    if gone:
        print("Forgot %d rows past the retention window." % gone, file=out)
    if failed:
        print("krot-collect: %d of %d sites could not be read" % (failed, len(domains)), file=err)
        return FAILED
    print("Collected %d sites." % len(domains), file=out)
    return OK


def main(argv=None, connect=None, out=None, err=None, get=ranges.http_get):
    parser = argparse.ArgumentParser(prog="krot-collect")
    parser.add_argument("--config", required=True)
    parser.add_argument("job", choices=JOBS)
    args = parser.parse_args(argv)
    out = out or sys.stdout
    err = err or sys.stderr

    with open(args.config) as source:
        config = json.load(source)
    if not config.get("sites"):
        print("krot-collect: %s declares no sites" % config.get("project"), file=err)
        return FAILED

    store = open_store(config, connect, err)
    if store is None:
        return FAILED
    if args.job == "ranges":
        return run_ranges(config, store, out, err, get)
    return run_crawl(config, store, out, err)


if __name__ == "__main__":
    sys.exit(main())
