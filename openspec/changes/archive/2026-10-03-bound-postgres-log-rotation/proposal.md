# The PostgreSQL log recycles within a month, and connection logging is a setting

## Why

The template promises that a dated filename plus `log_truncate_on_rotation` recycles the log
set after a year. It cannot: `postgresql-%Y-%m-%d` contains the year, the name never repeats,
and truncation never happens — the set grows forever. `postgresql_log_retention_days: 14` in
the defaults is read by nothing.

Measured 2026-10-03 on a production machine whose application opens a connection per request:
229 868 "connection authenticated" lines in one day, the log grew from 19 MB a day in August to
330 MB a day in October, 7.0 GB in 128 files on a 77 GB disk. Connection lines are almost the
whole volume; the useful part — slow queries, checkpoints, lock waits — is small. A checkpoint
record is what located that machine's disk stalls.

## What Changes

- The log file is named by day of month, so truncate-on-rotation recycles it within a month
- `postgresql_log_connections` (default `true`, as before) drives both connection and
  disconnection logging; a machine without a connection pool turns it off in its inventory
- The unused `postgresql_log_retention_days` is removed
- Slow queries, checkpoints, lock waits, temp files and autovacuum stay logged
- Applying the config asks the server: `postgres -C` checks the files first (a refused value
  fails the run, the previous file goes back, the server untouched), reload when the file is
  newer than its last config load, then restart only for settings it reports
  `pending_restart`; a restart that fails puts the previous file back and starts the server. Until now every change restarted, so rolling out this very
  log setting would have dropped every connection of a machine serving its sites live. Neither
  `pg_file_settings` messages (an invalid value and a restart-only change read alike) nor
  comparing `postgres -C` with `pg_settings` (one value printed two ways) can decide it
- Version 8.0.0: the log file names change and a variable is removed

## Boundaries

Files already written under the dated names are left alone: the new names never overwrite them,
and deleting history is the operator's decision, not a side effect of a run.
