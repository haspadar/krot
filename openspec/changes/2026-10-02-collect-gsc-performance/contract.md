# GSC contract v1

Proposed additive release: 7.1.0. Schema `krot_collect` version 2 (existing crawler data retained).

## Inventory

```yaml
collecting_projects:
  atlas:
    database: stats
    reader: atlas
    extra_readers: [analyst]
    jobs: [gsc]  # omitted: [ranges, crawl]; opt-in GSC
    timers: false  # initial import; true enables declared jobs
    gsc:
      service_account: "{{ google_service_account_json }}"
      backfill_days: 28
      overlap_days: 7
      retention_months: 16
      freshness_days: 5
    sites:
      - domain: example.org
        property: sc-domain:example.org  # default sc-domain:<domain>; URL-prefix also accepted
```

Missing declared credentials or reader roles fail provisioning. `jobs` can combine ranges/crawl/gsc.
Default GSC schedule 04:00 machine time, persistent with existing jitter; override `schedules.gsc`.
Secret: `/etc/krot-collect/<project>.google.json`, mode 0600, owned by krot_collect.
Public JSON contains settings and properties, never the key. CLI `gsc --from YYYY-MM-DD --to YYYY-MM-DD`
permits deeper backfill within retention; dates are GSC/PT days, not the machine's timezone.

## Independent reports and tables

All data tables have `site`, `day`, `search_type` (web), impressions, clicks, position, collected_at.
`search_query`: query, country, device (date/query/country/device).
`search_page`: url (date/page).
`search_page_query`: url, query (date/page/query).
Query reports cannot reconstruct page totals or all anonymous queries. Full strings are retained;
wide text keys use generated hashes rather than truncation.
`search_day`: site, day, search_type, dataset (query/page/page_query), property,
row_count, collected_at, pagination_complete, coverage_limited, provenance.
`search_attempt`: attempt id, site, day, search_type, dataset, property, started_at, finished_at,
status (running/success/failed/unavailable), row_count, error. No secrets in error/export.

Each report/day replaces its own data and successful marker in one transaction. Failure leaves its
previous data/marker untouched; attempts record the failure. All three reports may complete
independently; consumers must require the reports/days needed by their analysis. `pagination_complete`
means the accessible API pages were read, not full Google coverage. `coverage_limited=true` always
for API-sourced reports. Imported history uses provenance=imported and preserves measured timestamps
and known pagination flags; unknown flags must not be upgraded to success. No baseline table is
created or reset. Other engines remain in the consumer's existing storage.

## Read-only contract

Role grants CONNECT/USAGE/SELECT and default table SELECT to reader and extra_readers, never writes.
`krot-collect --config <project.json> export --from <date> --to <date>` streams JSONL records of
{contract_version: 1, dataset, row}; includes data, search_day and search_attempt for declared sites.
No HTTP/public endpoint. SQL readers may use the above tables directly. Attempt timestamps and
successful markers expose collection freshness separately from the latest day with measured rows.
Consumer history import and reader switch happen before enabling the GSC timer. The consumer owns
its original baseline and any compatibility views/adapters.
