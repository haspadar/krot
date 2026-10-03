# Tasks

- [x] Name the log by day of month and drive connection logging by a setting
- [x] Remove the unused retention setting
- [x] Restart only for settings the server reports as needing it, reload otherwise
- [x] Check the running server's settings in the molecule scenario
- [x] Update the logging wiki page, changelog and collection version
- [x] Two independent reviews before push

## Verification

- Molecule postgresql locally (OrbStack): converge restart, idempotence `changed=0`, reload
  without moving the postmaster start time, `work_mem: 0` refused with the previous file back
  and the server untouched, `pg_stat_statements.max: 0` refused up front, a missing preload
  library rolled back with the server started on the previous file, preload removal restarted
- Four review rounds, each Codex adversarial plus Claude correctness. The apply mechanism was
  redesigned twice: reading `pg_file_settings` messages (an invalid value reads like a
  restart-only change), then comparing `postgres -C` with `pg_settings` (one value prints two
  ways), before settling on check-first, reload by load time, restart by `pending_restart`
- Declined: deleting the old dated log files (the operator's decision), the same-day append
  after a restart (PostgreSQL behaviour, documented), check mode of the extension task
  (unchanged by this change)
