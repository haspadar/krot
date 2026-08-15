# Tasks: PostgreSQL 18

## Variables
- [x] `postgresql_version` 16 → 18
- [x] `postgresql_remove_other_versions` (default `false`) with an explanation of why not `true`

## Guard
- [x] `pg_lsclusters --no-header` → `vars/main.yml` computes `postgresql_other_versions`
- [x] `check_mode: false` on the detection task — otherwise `--check` skips it, the list is empty,
      and the dry-run reports a clean upgrade on top of a cluster it never saw
- [x] `assert` with a message naming the version found and the ways forward
- [x] Order: `postgresql-common` (carries `pg_lsclusters`, but not the server) → check → removal
      of the old one → `postgresql-<version>`. Otherwise the versioned package's postinst managed
      to create a cluster, and the role refused to do what it had already done
- [x] Removal of the old version — server **and** client, `purge`
- [x] Removal of `/etc/postgresql/<old>` — the role's own drop-in, purge does not touch it
- [x] `pg_createcluster ... --start` with `creates:` as a fallback path: on a clean machine the
      package manages to create the cluster, and the task is skipped

## Verification on a live machine
- [x] A run **without** the flag refused: `PostgreSQL 16 already has a cluster on this host...`
- [x] A run with the flag: PG 16 removed, cluster 18 created on 5432
- [x] `PostgreSQL 18.4 (Ubuntu 18.4-1.pgdg24.04+1)`, `shared_preload_libraries` in place
- [x] 9 Doctrine migrations applied without errors, 7 tables in place
- [x] Three sites serve 200 over HTTPS
- [x] Repeat run — `changed=0`, `skipped=2` (the guard does not get in the way of normal work)
- [x] After cleanup: zero PG 16 packages, only `/etc/postgresql/18`, one cluster
- [x] `yamllint` and `ansible-lint` clean

## Data
- [x] Dump taken and verified: all tables empty except the Doctrine migration log
- [x] Removal confirmed by the owner
- [x] The `busel` role and database recreated, password from Bitwarden (`busel-postgres-app`)
- [x] Dump deleted from the machine after verification

## Noted separately
- [x] `-e postgresql_remove_other_versions=true` passes **a string**, Ansible rejects it as
      non-boolean. JSON is required: `-e '{"postgresql_remove_other_versions": true}'`
- [x] The flag is not in the busel inventory — it was passed one time, no standing permission to
      delete databases was left on the machine

## Fixed after review
- [x] **The guard did not work in `--check`.** A bare `command` without `creates`/`removes` is
      skipped in check mode, the cluster list stayed empty. Verified: requesting PG 16 on a
      machine with 18 gave `changed=5` and stayed silent, now it refuses
- [x] **The package was installed before the check.** postinst creates a cluster when the port is
      free — on such a machine the role refused to do what it had already done. The server is now
      installed after the check
- [ ] "A taken port prevents creating a cluster rather than shifting it" — **rejected**, verified
      by experiment: next to a cluster on 5432 a new one was created and got 5433. `man` says
      "the first port not used by **an existing cluster**", that is, by the registry, not by TCP.
      The wording in the code was refined to this
