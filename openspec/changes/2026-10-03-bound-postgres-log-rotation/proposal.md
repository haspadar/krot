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
- Applying the config compares each of the role's settings as the files give it
  (`postgres -C`) with the running value: a differing postmaster-level setting restarts, any
  other difference reloads, an invalid value fails the run before the server is touched. Until
  now every change restarted, so rolling out this very log setting would have dropped every
  connection of a machine serving its sites live. `pg_file_settings` errors cannot decide it:
  PostgreSQL 18 reports an invalid value and a restart-only change with the same message
- Version 8.0.0: the log file names change and a variable is removed

## Boundaries

Files already written under the dated names are left alone: the new names never overwrite them,
and deleting history is the operator's decision, not a side effect of a run.
