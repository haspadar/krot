# A finalized day without impressions is a measured zero

## Why

The `gsc` job decides that a day is final by asking Google's final data for that date. Google
omits dates without impressions, so a day nobody searched for is indistinguishable from a day
not yet finalized: it gets `unavailable` attempts and never a successful marker. On a young or
quiet site this means:

- consumers requiring every day of a window (a week-over-week comparison) never get one;
- the repair loop re-asks every such day each night until retention drops it — the first
  scheduled night after the cutover recorded 1029 `unavailable` attempts reaching back to the
  oldest imported day;
- five quiet days in a row turn the job red as "stale", naming the wrong cause.

A query with `dataState: all` grouped by date returns `metadata.firstIncompleteDate`; every
earlier day is final. Measured 2026-10-03 on two properties: both answered `2026-09-30` while
their last final date was `2026-09-29`. A range without any rows returns no metadata at all.

## What Changes

- Before collecting, the job asks each site's first incomplete date over the last 30 days
- A day before it is final: the three reports are read, and an empty one is stored as a
  successful zero (`row_count = 0`); a day on or after it is `unavailable` without a request
- A site whose answer names no date (no rows at all) uses the earliest date named by the
  other sites of the run; when no site names one, or the request fails, the previous
  per-day final-date probe decides as before
- Contract v1 wording changes: the availability rule, not the tables or the export

## Boundaries

No schema change, no new setting, no change to Bing/Yandex (they stay in the consumer). A
borrowed boundary later than the site's own true one could turn its last unfinished days into
zeros; those days lie inside `overlap_days`, which is re-read every night. A boundary outside
the asked range is refused as `invalid_metadata`, and a refused boundary is logged.
