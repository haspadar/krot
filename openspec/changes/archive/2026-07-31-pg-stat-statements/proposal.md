# Proposal: PostgreSQL query statistics

## Why

The role already has `log_min_duration_statement = 500`, `log_lock_waits`, `log_temp_files`,
`log_checkpoints` and csvlog. That is enough to catch a **single** slow query.

What is missing: a query that takes 20 ms but is called 100,000 times a day. It will never reach
the slow log (the threshold is 500 ms), yet by total time it may be first in the database — and it
is exactly the one asking for an index. Load like that can only be seen by aggregating over the
normalized query text.

## What Changes

### Enabled by default

`pg_stat_statements` is on by default: the overhead is a fixed chunk of shared memory (a few MB at
`max = 5000`) and a hash lookup per query. A server role is better off measuring than guessing. The
library ships in the main `postgresql-<version>` package, `postgresql-contrib` is not needed.

### `shared_preload_libraries` is written as a list, not as a single name

PostgreSQL takes **the last assignment whole** and cannot append. So a future `auto_explain` or
`pg_cron`, added by a second config, would silently displace `pg_stat_statements`. The role writes
the whole list at once from `postgresql_shared_preload_libraries`; `pg_stat_statements` is appended
by the template when it is enabled.

If there is nothing to preload, **the line is not written at all** — the parameter stays `default`
rather than being pinned to `''`, which would overwrite someone else's value.

### The extension is created in the `postgres` database

`CREATE EXTENSION` runs in a specific database, and by its own principle the role knows nothing
about site databases. The `pg_stat_statements` view shows statistics for **the whole cluster**
regardless of which database you look from, so the service database resolves the conflict: the
principle of the role is not broken, and all the data is visible.

### Handlers are flushed before the extension is created

The library appears in memory only after a restart, so `CREATE EXTENSION` fails before it.
`meta: flush_handlers` keeps both steps in one run instead of a second run "to catch up".

## Impact

- **A PostgreSQL restart is required** — `shared_preload_libraries` is postmaster-level, `reload`
  accepts it silently without applying it. On a machine with sites that is downtime; measured:
  3.7 s.
- The restart happens on any change to `99-krot.conf`, not only to this line: the handler is bound
  to the template as a whole. The role does not try to split reload and restart by parameter
  type — the cost of an error is that a setting looks applied while it is not.
- A run with no config changes does not touch the database.
