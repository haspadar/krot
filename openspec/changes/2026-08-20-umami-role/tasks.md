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
