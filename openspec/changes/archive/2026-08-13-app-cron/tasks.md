# Tasks: application periodic jobs

## Role `cron`
- [x] `cron_jobs` — a list in the inventory; the role knows not a single job name. Empty list by
      default, applying it to a machine with no jobs is a no-op
- [x] A job expands into the pair `krot-<name>.service` + `.timer`. The unit name is derived from
      the job name, so the output is found without knowing the path to a file
- [x] Output goes to the journal by default. Verified as `km` **without sudo**:
      `journalctl -u krot-selftest` prints stdout and stderr, although `km` belongs to neither
      `adm` nor `systemd-journal` — the lines belong to the `km` process. Entries from
      `systemd[1]` itself are not visible; the exit code is given by `systemctl status`, also
      without sudo
- [x] `Environment=` for each variable. `APP_ENV=prod` is not lost: systemd has the same trait as
      cron — a unit starts with an empty environment
- [x] `RandomizedDelaySec` (15m) instead of picking a minute by hand. The minute 17 in the original
      cron entry was picked so as not to collide with the other hourly jobs — that knowledge lived
      only with the author of the line, and a second author would have had to work it out again
- [x] `Persistent=true` — a machine switched off at the moment of firing catches up on the miss
- [x] `TimeoutStartSec` (30m): otherwise a hung job blocks all subsequent starts of the unit while
      the timer keeps firing correctly — the job stops running, and the timer looks healthy
- [x] `AssertPathIsDirectory` on `working_directory`: a `current` pointing nowhere after a failed
      deploy fails the unit with a clear reason instead of running the command from `/`
- [x] File mode (`log_file`) — not the default, and the role creates the file with an owner
      **and** writes `/etc/logrotate.d/krot-cron`. Half of that pair reproduces the original
      defect

## Declaration validation
- [x] `assert` on `name`/`command`/`schedule`; the name is restricted to `[a-z0-9-]`, because it
      becomes the unit file name
- [x] `assert` on name uniqueness: two units with the same name silently overwrite each other

## Removal of retired jobs (the main risk)
- [x] A job removed from the inventory is removed from the machine: otherwise it keeps firing
      against a release that no longer expects it, and at the same time is absent from the
      inventory — that is, from the record of what the machine does
- [x] **Ownership is determined by the marker `# krot-cron-job` inside the `.service`, not by the
      file name.** `krot-cf-ranges.timer` belongs to the `firewall` role and falls under the same
      glob. Verified by a run: in the retire loop it showed up and was skipped, `is-enabled`/
      `is-active` afterwards — `enabled`/`active`
- [x] A timer without a paired `.service` is not touched: there is nothing to prove ownership with,
      and the safe error here is a leftover unit, not someone else's unit deleted

## Check on a live machine (busel, 2026-08-13)
Run with an isolated playbook and a test job; the production `colony:traffic` and its line in
`crontab` were not touched.

- [x] The first run installs the units, `systemctl list-timers 'krot-*'` shows the job
- [x] The run works, the output in the journal is readable as `km` without sudo
- [x] **The original defect was reproduced on the new mechanism and became visible.** The unit was
      given the same write to `/var/log/busel-traffic.log`, which `km` has no rights for. The
      result — three independent signals without sudo, where before there were five days of
      silence:

      ```
      systemctl --failed
      ● krot-selftest.service  loaded failed failed
      journalctl -u krot-selftest
      /bin/sh: 1: cannot create /var/log/busel-traffic.log: Permission denied
      systemctl status  →  Main PID: … (code=exited, status=2)
      ```
- [x] A repeat run — `changed=0`
- [x] Manual corruption of the unit is rolled back by a run (`changed=1`, the next one — `0`)
- [x] **The equivalent of `crontab -r`:** the units were removed by hand, the run brought the job
      back by itself (`changed=3`)
- [x] Retire: `cron_jobs: []` removed `krot-selftest` without touching `krot-cf-ranges`
- [x] File mode: `/var/log/krot/selftest.log` created as `km:adm 0640`, the directory `0750`,
      `/etc/logrotate.d/krot-cron` written, `logrotate -d` gives no errors, the unit status is
      visible even when writing to a file
- [x] Cleaned up afterwards: only `krot-cf-ranges.*` and `krot-php` were left on the machine,
      `--failed` is empty
- [x] `yamllint`, `ansible-lint` (profile production) clean

## Incidental defect: logrotate had been failing for three days
Found while checking the machine, not part of the assignment, but of the same kind — a silent
failure.

- [x] `systemctl --failed` showed `logrotate.service` in `failed` since 11 August:
      `error: nginx:1 duplicate log entry for /var/log/nginx/access.log`
- [x] Cause: the `nginx` role drops `krot-nginx` with the glob `/var/log/nginx/*.log`, and the
      package `/etc/logrotate.d/nginx` declares the same one. logrotate treats this as an error and
      **exits with code 1 without processing a single file on the machine** — including `krot-php`
      and postgresql, which have nothing to do with it
- [x] Working around it by rewriting the template is impossible: verified by experiment — the
      duplicate is caught by the **resolved path**, not by the glob text
      (`/var/log/nginx/access.log` against `/var/log/nginx/*.log` gives the same error)
- [x] The role stopped installing a second file; `nginx_log_retention_days` is applied by editing
      the `rotate` line in the package config. The regexp was checked against the live file —
      exactly one match
- [x] `create: false` — the file belongs to the package, and creating it here would return the
      role to owning a second config under a different name
- [x] **Fixed on busel under separate permission**: `krot-nginx` was removed, `logrotate.service`
      ran with `status=0/SUCCESS`, `systemctl --failed` is empty, `/var/lib/logrotate/status` again
      tracks nginx, php and postgresql

## From review

Every remark was verified by experiment rather than taken on faith: two out of fifteen were not
confirmed, one was confirmed with a different outcome than described.

- [x] **`%` in the command was expanded as a systemd specifier.** Verified: `date +%Y-%m-%d` in
      `ExecStart` printed `/etc/systemd/system-<machine-id>-/run/credentials/<unit>` and exited
      **with code 0**. That is, a role written against silent failures carried a silent failure
      inside. Now `| replace('%', '%%')`; after the fix the same job prints `2026-08-13`
- [x] **A single quote in the command tore argv apart.** `--msg='hi there'` — a quote in the
      middle of a word is literal for systemd, `-c` takes only the first word. The same mechanism
      as when arguments are glued together in `ssh`. Now the command is quoted with the `quote`
      filter; verified on the machine — `--msg=hi there` arrives as a single argument
- [x] **A quote in an `Environment=` value lost the variable entirely.** systemd wrote
      `Ignoring invalid environment assignment` and started the unit without it — exactly the way
      of losing `APP_ENV` that the role protects against. After the fix `TRICKY=say "hi" now`
      arrives in the process; verified with `env` inside the unit
- [x] **Two jobs with the same `log_file` reproduced `duplicate log entry`** — the very defect
      this same change fixes for nginx. Verified: `logrotate -d` on such a file gives `exit=1`.
      An `assert` was added; the run fails with a clear message
- [x] **Retire left the log file forever** — already without a rotation entry, that is, growing
      until the disk fills up. The path is read from the unit by the line `# krot-cron-log=`, not
      by parsing `ExecStart`: the latter is now quoted, and a regex over it would break at the very
      first change of form. Deletion is confined to `cron_log_dir` — a job pointed at
      `/var/log/syslog` by a typo will not carry it away with itself
- [x] **`lineinfile` in the `nginx` role appended `rotate` outside the block** when the anchor line
      is missing. Here the review was wrong about the consequence, and the truth turned out worse:
      logrotate does **not** fail (`exit=0`), it silently discards the directive and rotates
      **with no retention at all** — yesterday's log is deleted instead of fourteen being kept.
      Replaced with `replace` (which appends nothing) plus an `assert` that the anchor was found.
      Verified: the run fails, the file is not touched
- [x] **`lineinfile` edited only the last `rotate` block.** In the Ubuntu 24.04 package file there
      is one block, but the role is general. `replace` edits all matches; the indentation is
      preserved via `\g<1>`
- [x] **Editing a `conffile` and package upgrades** — verified with `dpkg-query`: the file really
      is a conffile of `nginx-common`, dpkg in non-interactive mode keeps the local version, and
      if it does get rolled back, the next run restores it. The trade-off is written up in README
      and CHANGELOG
- [x] **`RandomizedDelaySec` is re-randomised on every firing** — an hourly job would drift
      between 45 and 75 minutes. `FixedRandomDelay=true` was added (`cron_fixed_random_delay`,
      enabled by default): the offset is constant. Verified — systemd 255 accepts it,
      `FixedRandomDelay=yes`, the next run at minute 07
- [x] **A multi-line `description` would break `Description=`** — line breaks are collapsed into a
      space
- [x] **Semver.** The `cron` role is an addition, but `nginx` changes the state of deployed
      machines. Formally it does not fall under the rule "major for renaming a variable or changing
      a default", names and meanings did not change; the version was left at 5.1.0, but the section
      in CHANGELOG was renamed to "Fixed — with a change of state on already deployed machines",
      so that the update does not read as silent
- [x] **Docs drift:** README and ARCHITECTURE listed "rotation" for the `nginx` role, although the
      role no longer owns it — replaced with "log retention"

### A regression caught by a run (not by review)

- [x] The fix for the remark about log cleanup **broke the retire of journal jobs**: they have no
      marker, `regex_search` returns `None`, and `first` failed with
      `'NoneType' object is not iterable`. The run failed on any job without `log_file`. Fixed with
      `default([], true)` before `first`; re-checked on both forms of jobs

### Not confirmed

- [ ] **`Persistent=true` supposedly runs the job immediately on first installation.** Verified on
      systemd 255: no stamp — no run, the unit waits for its schedule. In theory this is true for
      the case where a stamp exists and is stale, but it does not produce the described scenario
      (first installation)
- [ ] **The retire regexp may delete someone else's unit.** It can enter the loop, but delete —
      no: ownership is decided by the marker. Confirmed by a run, `krot-cf-ranges` is skipped at
      every step

## Decisions
- [x] **A new role, not `common`.** The jobs have their own list, their own unit templates and their
      own tag for `--tags`; in `common` (hostname, timezone, packages) they are alien. `deploy` is
      ruled out by the direct instruction of the assignment — it is a thin wrapper over Deployer
- [x] **systemd timers, not a crontab entry via an Ansible module.** The `cron` module would have
      solved "survives a machine rebuild", but not the main thing: cron only reports that it
      **started** the line, and does not know how it ended. That is exactly what produced five days
      of green runs
- [ ] **Automatic removal of the manual line from `crontab`** — rejected. The role does not tell
      apart the line it replaces from someone else's job it knows nothing about; a run that
      silently carries off someone else's cron entry is the same class of defect from the other
      side. Removal remains an explicit migration step (see below)
- [ ] **The "did not run N times in a row" notification** — proposed, not implemented. The
      mechanics are cheap (`OnFailure=` on a shared `krot-job-failed@.service` plus a marker in
      `/var/lib/krot/`), but the addressee has not been chosen, and a notification with nobody to
      read it is one more silent failure, only with a larger volume of code. `systemctl --failed`
      closes the main gap: today a failure is visible through nothing

## busel migration (not part of krot, done in busel)
- [ ] Declare `colony:traffic` in `group_vars`, add the `cron` role to `site.yml`
- [ ] Run the role, make sure `krot-traffic.timer` is in place and has run
- [ ] **Only after that** remove the manual line from `crontab -l` under `km` — replacement is
      done by a run, not by `crontab -e`
- [ ] Check that the job fails when it has not done the work: a command that returned 0 and
      uploaded nothing stays green under any transport, and that is the job's own responsibility
