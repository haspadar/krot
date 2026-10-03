# Tasks

- [x] Report the role's settings a later source overrides (an `overridden:` line, found by seqno)
- [x] Fail the run last in the role, after any restart, without rolling the file back
- [x] Reload on any source change and on a running value taken from elsewhere
- [x] Put the previous file back on any failure before the server took the new one
- [x] Molecule: ALTER SYSTEM on work_mem and on max_connections, RESET without a reload, a
      deleted conf.d override, no copies of the previous file left
- [x] Wiki, changelog, version 9.0.0
- [x] Two independent reviews before push

## Verification

- Molecule postgresql locally (OrbStack): every earlier path plus both overrides failing the
  run with the winning file named, recovery after RESET and after deleting the override file,
  each without a manual reload, and no `99-krot.conf.*` copies left in conf.d
- Two review rounds, Codex adversarial plus Claude correctness: an `applied`-based join missed a
  winner pending a restart; refusing before the restart skipped its rollback; RESET and a
  deleted override were never reloaded; a non-refusal failure dropped the only copy of the
  previous file. All closed and covered above
- Declined: treating an override with the same value as no override (one rule — what the role
  wrote is in effect — is simpler and honest about the source)
