# Tasks

## 1. The role

- [x] 1.1 `defaults` — version, paths, account, bind address, port, build and migrate switches
- [x] 1.2 `vars` — derived paths and the Node floor, kept out of defaults so an inventory
      cannot desynchronise them from `umami_root`
- [x] 1.3 Asserts before anything is installed: database URL, secret length, loopback, port
- [x] 1.4 System account with no login shell, owning the tree it runs from
- [x] 1.5 `node.yml` — NodeSource with suite `nodistro`, vendored key, pnpm via corepack
- [x] 1.6 `build.yml` — source tarball, heap ceiling, nice, stamp written only on success
- [x] 1.7 `migrate.yml` — `prisma migrate deploy`, from the play rather than from ExecStartPre
- [x] 1.8 Environment file 0640, separate from the unit so `systemctl cat` prints no password
- [x] 1.9 Unit with HOSTNAME and PORT named explicitly, plus systemd hardening
- [x] 1.10 `meta` and handlers

## 2. The scenario

- [x] 2.1 `molecule.yml` — every value different from the role's defaults, so a setting read
      back proves the role carried it rather than matching a default by accident
- [x] 2.2 `prepare.yml` — plants a real server at the release path, so the address and port
      are checked against a process
- [x] 2.3 `verify.yml` — port, bind address, secrets, file mode and owner, no login shell,
      unit active and enabled
- [x] 2.4 Scenario runs green: 7/7, idempotence `changed=0`

## 3. Checks

- [x] 3.1 `yamllint` clean
- [x] 3.2 `ansible-lint` profile `production`, 0 failures
- [x] 3.3 `coverage.py` counts the role and passes
- [x] 3.4 Raise `MIN_COVERED_ROLES` / `MIN_COVERED_TASKS` to the new floor
- [x] 3.5 `wiki-lint` and `wiki-index`

## 4. Documentation

- [x] 4.1 `wiki/operations/analytics-counter.md`, linked from the README; the role table in
      `collection-layout.md` names it among busel's roles

## 5. Fixed in review

Two independent reviews, different angles. Both found real defects; these are the ones that
were fixed rather than argued with.

- [x] 5.1 **`async:` wrote the password to disk.** An async task records its result — resolved
      environment included — in `~/.ansible_async/<jobid>` under the connection user, mode
      0644, and nothing removes it. `no_log` filters the console, not that file. Measured
      2026-08-20: files five days old were still there at 0644. Replaced with `timeout:`;
      `poll: 15` blocked the play anyway, so the asynchrony bought nothing but the leak.
- [x] 5.2 **`become` to an unprivileged user published the payload.** Without `acl`, Ansible
      falls back to `chmod a+r` on `/tmp/ansible-tmp-*`, putting the connection string in a
      world-readable file for the length of the task — on a machine where `www-data` serves
      nine sites. The role installs `acl`.
- [x] 5.3 **The build no longer sees the real password at all.** `prisma generate` needs the
      variable to EXIST, not to work, so it gets a placeholder. That removed the reason for
      `no_log` on the build — which had been censoring the build's own failure, defeating the
      heap ceiling's whole purpose of making the build fail as the build.
- [x] 5.4 **`umami_environment` could override the loopback.** systemd applies
      `EnvironmentFile` after `Environment=`, so an inventory could pass every assert and
      still publish the service on all interfaces. Reserved keys and newlines now refused.
- [x] 5.5 **The unit was installed after the migration.** On a version bump that left a window
      where the schema was new and the running process was the old build — and `state: started`
      cannot close it, because an active service is already started. Unit first, restart
      inline rather than through a handler at the end of the play.
- [x] 5.6 **Migration with no prisma named a path, not a cause.** A ready-built standalone tree
      has no `node_modules`, and `umami_migrate` defaults to true. Refused out loud, and the
      refusal itself is exercised by the scenario.
- [x] 5.7 **Old release trees accumulated forever.** Each is a checkout plus node_modules plus
      .next plus a pnpm store; the first symptom is a full disk, which on this machine hits
      PostgreSQL. Two kept, older removed — after the new one is running, never before.
- [x] 5.8 **Unit hardening completed.** `ProtectProc=invisible` (without it `/proc/<pid>/environ`
      hands the password to anything that can read it, ending the 0640 split the moment the
      process starts), `MemoryMax`, `StartLimitIntervalSec` — the last because systemd's
      default bounds a service that dies instantly and not one that dies half a minute in,
      which loops forever.
- [ ] 5.9 **Tag pinning is a KNOWN GAP, not a fixed defect.** A tag can be moved, and the role
      does not verify which commit it got. Two approaches were tried and rejected on
      measurement: GitHub's tarball carries no commit metadata (verified 2026-08-20 by
      unpacking v3.3.0), and a tarball checksum is not stable because those archives are
      generated on demand. The real fix is fetching by SHA instead of by tag; left for the
      next version bump, because it changes the URL shape. What limits the damage meanwhile:
      `--frozen-lockfile` pins every dependency by integrity hash, and the build runs
      unprivileged.

Scenario after all of it: 7/7, idempotence `changed=0`.
