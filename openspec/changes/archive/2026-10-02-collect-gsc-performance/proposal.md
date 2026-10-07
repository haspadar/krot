# Collect finalized Search Console performance in the shared collector

## Why

Projects need the same durable daily search measurements. Keeping the mechanism in each
application duplicates API, pagination, retention and scheduling rules. The machine collects;
applications own their screens, baselines and experiments.

## What Changes

- Extend `collecting` with an explicitly selected `gsc` job, preserving existing crawl/ranges defaults
- Collect the three independent reports: query/country/device, page, page/query; explicit final data,
  daily requests in America/Los_Angeles, configurable initial backfill (at least 28 days), overlap
  and repair of missing days
- Store each site's day/report atomically with a successful marker, keep failed attempts separately,
  preserve old successful data on failure and distinguish API pagination success from Google's
  incomplete coverage
- Add durable history and read-only SQL/JSONL access, explicit additional reader roles; credentials
  remain separate private files, never part of public config or export

## Boundaries

No experiment membership, baseline decisions, application screens, provisional/hourly collection,
other search engines, production deployment or automatic consumer migration. Existing history is
imported by the consumer, preserving provenance and old completeness flags.
