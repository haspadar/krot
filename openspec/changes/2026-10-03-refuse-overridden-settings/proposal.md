# A role setting overridden by a later config source fails the run

## Why

PostgreSQL reads `postgresql.auto.conf` (written by `ALTER SYSTEM`) after `conf.d`, so a value
set there wins over the role's file. 2026-10-03, the first 8.0.0 run on a production machine:
`changed=3`, no restart, `log_filename` applied — and `log_connections` /
`log_disconnections` still on, because a manual `ALTER SYSTEM` from a month earlier sat in
`postgresql.auto.conf`. The role reported success for settings that were not in effect.
`pg_file_settings` said so plainly: the role's lines with `applied = false` and no error.

## What Changes

- After the reload, a line of the role's own file with `applied = false` and no error (not a
  refused value, not one pending a restart) fails the run, naming the file and line that win
- The role's file is not rolled back: it is right, the override is what needs removing
- Lines of other files overridden by the role's (the packaged `postgresql.conf`) stay normal
