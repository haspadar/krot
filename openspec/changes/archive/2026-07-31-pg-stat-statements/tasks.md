# Tasks: pg_stat_statements

## Variables
- [x] `postgresql_stat_statements` (default `true`, rationale in the comment)
- [x] `postgresql_stat_statements_max` (5000), `..._track` (`top`)
- [x] `postgresql_shared_preload_libraries` — a **list**, so that a second consumer does not fight
      over the line

## Template
- [x] `shared_preload_libraries` is assembled from the list + `pg_stat_statements`, through `unique`
- [x] The line is not written when there is nothing to preload (otherwise the role would pin `''`)
- [x] `pg_stat_statements.max` / `.track` are written only when the feature is enabled
- [x] Verified by rendering: with `['auto_explain','pg_cron']` the output is
      `'auto_explain,pg_cron,pg_stat_statements'` — nothing lost and nothing duplicated
- [x] Verified by rendering: with the feature off and an empty list there are no lines at all

## Tasks
- [x] `meta: flush_handlers` before creating the extension — the library is in memory only after a
      restart
- [x] `postgresql_ext` into the `postgres` database, `check_mode: false`
- [x] `state` follows the variable (`present`/`absent`)

## Verification on a live machine
- [x] `SHOW shared_preload_libraries` → `pg_stat_statements`
- [x] `SELECT count(*) FROM pg_stat_statements` works
- [x] Repeat run — `changed=0`, not a single `RUNNING HANDLER`
- [x] A restart was required, measured: **3.7 s**
- [x] `pgbench`: 300 queries at 0.052 ms — not one of them would have reached the slow log, in
      `pg_stat_statements` they are the first row. Test tables deleted, statistics reset
- [x] `yamllint` and `ansible-lint` clean

## README
- [x] A section with ready-made SQL for the top by `total_exec_time`
- [x] `pg_stat_statements_reset()` and when it is needed

## Fixed after review
- [x] The SQL failed: `round(double precision, integer)` does not exist → `::numeric`. Found by a
      run on the server, not by proofreading
- [x] `pg_stat_statements.save` is `on` by default — the statistics **survive** a restart.
      Verified: 9 rows before, 9 after. The wording "accumulates since the restart" was wrong
- [x] The claim "it restarts only when this line changes" was narrower than the code — rewritten
- [ ] A variant of the query for PG 12 (`total_time`) — **rejected**: the role pins the version,
      such code would not have run on any supported host
