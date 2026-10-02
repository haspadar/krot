"""Final GSC days: overlap, missing-day repair and visible failed attempts."""

from datetime import date, datetime, timedelta
from zoneinfo import ZoneInfo

from krot_collect.gsc_store import DATASETS
from krot_collect.store import months_before


def planned_days(markers, today, settings, start=None, end=None):
    cutoff = months_before(today, settings.get("retention_months", 16))
    if (start is None) != (end is None):
        raise ValueError("GSC backfill needs both --from and --to")
    if start is not None:
        if start > end or start < cutoff or end >= today:
            raise ValueError("GSC dates must be ordered, within retention, and before today in PT")
        return [(day, list(DATASETS)) for day in days(start, end)]
    eligible = {day for day, _ in markers if cutoff <= day < today}
    first = min(eligible) if eligible else today - timedelta(days=settings.get("backfill_days", 28))
    first = max(cutoff, min(first, today - timedelta(days=settings.get("backfill_days", 28))))
    overlap = today - timedelta(days=settings.get("overlap_days", 7))
    return [(day, [dataset for dataset in DATASETS if day >= overlap or (day, dataset) not in markers])
            for day in days(first, today - timedelta(days=1))
            if day >= overlap or any((day, dataset) not in markers for dataset in DATASETS)]


def days(start, end):
    while start <= end:
        yield start
        start += timedelta(days=1)


def error_label(error):
    # Arbitrary exception strings may contain transport headers or credential material.
    status = getattr(error, "status", None)
    reason = getattr(error, "reason", "")
    if reason not in ("forbidden", "rateLimitExceeded", "dailyLimitExceeded", "accessNotConfigured",
                      "invalidCredentials", "quotaExceeded", "backendError", "invalid_grant",
                      "transport_failure", "invalid_json", "invalid_response", "invalid_rows",
                      "invalid_row", "invalid_keys", "unexpected_date", "duplicate_row", "invalid_metrics",
                      "invalid_country", "invalid_device", "pagination_limit", "invalid_service_account",
                      "invalid_token_response", "invalid_property", "invalid_date", "request_failed") :
        reason = ""
    return "%s%s%s" % (type(error).__name__, " HTTP %s" % status if status else "", " " + reason if reason else "")


class Collection:
    def __init__(self, client, store, out, err, today=None):
        self.client, self.store, self.out, self.err = client, store, out, err
        self.today = today or datetime.now(ZoneInfo("America/Los_Angeles")).date()

    def collect(self, config, start=None, end=None):
        failed = 0
        settings = config.get("gsc", {})
        with self.store.exclusive():
            for site in config["sites"]:
                domain = site["domain"]
                property = site.get("property", "sc-domain:" + domain)
                plan = planned_days(self.store.markers(domain, property), self.today, settings, start, end)
                for day, datasets in plan:
                    # Probe each day: a day omitted from final data is unavailable, not a zero.
                    attempts = {dataset: self.store.start(domain, property, day, dataset) for dataset in datasets}
                    try:
                        available = self.client.finalized_days(property, day, day)
                    except Exception as error:
                        for attempt in attempts.values():
                            self.store.finish(attempt, "failed", error_label(error))
                        print("%s %s availability: %s" % (domain, day, error_label(error)), file=self.err)
                        failed += 1
                        # A permanent property refusal should not be repeated across its whole history.
                        if getattr(error, "status", None) in (401, 403):
                            break
                        continue
                    if day.isoformat() not in available:
                        for attempt in attempts.values():
                            self.store.finish(attempt, "unavailable", "no finalized date returned by Google")
                        continue
                    for dataset, attempt in attempts.items():
                        try:
                            figures = self.client.fetch(property, day, dataset)
                            self.store.replace(domain, property, day, dataset, figures, attempt)
                            print("%s %s %s: %d rows" % (domain, day, dataset, len(figures)), file=self.out)
                        except Exception as error:
                            self.store.finish(attempt, "failed", error_label(error))
                            print("%s %s %s: %s" % (domain, day, dataset, error_label(error)), file=self.err)
                            failed += 1
                # Explicit old-date backfills need not certify current freshness.
                if start is None:
                    for dataset in DATASETS:
                        latest = self.store.latest(domain, property, dataset)
                        if latest is None or (self.today - latest).days > settings.get("freshness_days", 5):
                            print("%s %s: finalized data stale (latest %s)" % (domain, dataset, latest), file=self.err)
                            failed += 1
            self.store.forget([site["domain"] for site in config["sites"]],
                              months_before(self.today, settings.get("retention_months", 16)))
        return 1 if failed else 0
