# Tasks: goaccess role

## Role
- [x] Package `goaccess` from the Ubuntu repository (1.8.1)
- [x] System user `goaccess` in the `adm` group, `nologin`, no home directory
- [x] Parser config: `log-format`/`date-format`/`time-format` for the `recipient` format
- [x] Site list in a separate file — the parser config knows not a single domain
- [x] Site discovery via `sites-enabled`, not via a glob over the logs
- [x] Build script in `files/`, not inline shell
- [x] systemd timer (hourly) + oneshot service with `ProtectSystem=strict`
- [x] vhost on `127.0.0.1:8443`, `autoindex off`, `X-Robots-Tag noindex`
- [x] basic auth — the snippet from the `nginx` role, not a second mechanism
- [x] `assert` that the snippet exists before referencing it: an `include` of a missing file is
      `emerg`, that is, ALL sites on the machine go down
- [x] The handler checks `nginx -t` before reload — in the same order as in the `nginx` role

## Verification on a live machine
- [x] `goaccess --version` → 1.8.1
- [x] Four reports built, no orphans from test vhosts among them
- [x] The data is real: 99 requests, 59 valid, 10 unique, 4 referrers — 59 matches the number of
      new-format lines in the log
- [x] `http://127.0.0.1:8443/berlindame.de.html` → 401 without a password, 200 with it (602 KB)
- [x] `ss -tlnp` → listens on `127.0.0.1` only, unreachable from outside
- [x] Timer registered, next run visible in `systemctl list-timers`
- [x] Repeat run — `changed=0`
- [x] Full busel playbook — `ok=84 changed=0 failed=0`
- [x] `nginx -t` passes, three sites return 200
- [x] `yamllint` and `ansible-lint` (profile production) clean

## Defects found by running it, not by reading it
- [x] **An empty log brought down the whole build.** GoAccess does not create the file when there
      is nothing to parse, and `mv` failed, taking every other site's reports with it. A check
      for the file's existence
- [x] **`.html.tmp` was silently not written.** GoAccess picks the output format by extension and
      for an unrecognised one writes nothing — successfully, without a word. The temporary name
      now ends in `.html` too
- [x] **Old lines buried the report.** Not "skipped as invalid" but the whole file dropped: 119
      old lines against 3 new ones produced `Format Errors` and zero reports. A `grep '^\['`
      filter at the input
- [x] **`grep` on an empty log tripped pipefail** — `|| true`, otherwise a site with no traffic
      read as a broken report
- [x] **The role was not idempotent**: the build with `changed_when: true` reported `changed` on
      every run. Now it builds only when there are no reports yet — the timer updates them

## From review (codex)
- [x] **Reports of removed sites stayed reachable.** The vhost was taken away — the report kept
      being served, naming the domain and its traffic to anyone who remembered the URL. The script
      deletes reports for domains absent from the list. Verified: a planted
      `retired.example.html` was removed, the four real ones untouched
- [x] **`--persist` recounted the live log on every run.** The reviewer was right; I first
      wrongly considered the point refuted: my initial test fed the file via stdin, where
      `log_path` = `STDIN`, and the figure did not grow. Running the real script showed
      3 → 5 → 7 → 9 across four builds. GoAccess has no line deduplication at all, only
      `--keep-last` by days. Persist removed, the report is built from scratch from all logs on
      disk — after the fix 3, 3, 3, 3
- [x] **An hour of traffic was lost each day.** Rotation is daily, the build is hourly: requests
      between the last build and the rotation remained only in `.1`. Rebuilding from all logs,
      including the `.gz` ones, closes this as well. Verified: a request present only in the
      rotated file made it into the report
- [x] **An unfinished report sat in the served directory** at a predictable path, and `try_files`
      did not refuse a dotfile. The build was moved into `.build/` inside the same directory —
      inside, because `mv` is atomic only within one filesystem, and the role cannot rely on
      `/var/www` and `/var/lib` being on the same one. The directory is blocked in the vhost.
      Verified: `/.build/…` → 403

- [x] **A report outlived its logs.** Since the figures now reflect only what is on disk, the
      report of a site whose records had rotated away would show traffic that is no longer in any
      log. It is deleted. A subtlety found by running it: when reading from stdin GoAccess
      **always** writes a report — on empty input it produces a page of zeros rather than no file,
      so what must be checked is the number of parsed lines, not the presence of a result

- [x] **A removed site stayed reachable until the timer.** A role run rewrote the list but skipped
      the build if any report already existed — the removed domain was still readable for up to an
      hour. Now a change to the list triggers the build within the same run. Verified: a planted
      `ghost.example.html` vanished immediately, and `changed=0` with no changes was preserved
- [x] **SC2045 from qlty**: iterating over `ls` output breaks on names with spaces. Replaced with
      a glob and `sort -rV`; an unmatched glob returns the pattern itself, so each candidate is
      checked for readability

## From review (CodeRabbit)
- [x] **Report deletion looked only at the live log.** If it was temporarily unreadable while the
      rotated ones were in place, the report was destroyed while the data was still live. The
      whole set of sources is checked
- [x] **`--check` wrote real reports.** `check_mode: false` on the build made it run in dry-run
      too. Added `not ansible_check_mode`; verified — `changed=0`
- [x] **The binding could be moved off loopback without a password.** `goaccess_listen_address:
      0.0.0.0` plus auth switched off would have exposed the domain list to the outside. An
      `assert` stops the run before anything is installed. The variable is kept: on another
      network a different address may be needed, but leaving loopback is now a deliberate act
- [x] **Only the existence of the auth snippet was checked.** An empty or edited file passed that
      check and left the reports open. Now the presence of `auth_basic`, `auth_basic_user_file`
      and of the password file the snippet names is checked
- [x] **A failed build left the old report in place.** `grep '^\['` proves only a bracket at the
      start of a line, not fitness for GoAccess, so a format change could leave behind a page that
      nothing will ever update again — worse than a missing one, because it looks fresh. Verified:
      on an unusable log the report is deleted, on a normal one it is restored
- [x] A comment promised HTTPS although inside the tunnel it is plain HTTP — fixed
- [x] MD040: the block with the GoAccess error had no language

## Serving moved to busel (2026-08-02, after the first delivery)

Everything above marked as vhost, basic auth and tunnel was **done and then removed**. The reason
is not technical: through an SSH tunnel the report cannot be opened from a phone, and that is the
principal scenario. In busel the decision had been made earlier and written into its `CLAUDE.md`
— the report opens at the route `/traffic` inside the `busel.click` admin panel under its login,
without a second password and without a subdomain in public DNS. That decision was never carried
over into krot, so the role did not know it.

- [x] Removed the vhost, the loopback guard, both auth checks, the reload handler and the
      variables `goaccess_listen_address` / `goaccess_listen_port` / `goaccess_auth_enabled`
- [x] The role **removes** `/etc/nginx/conf.d/krot-goaccess.conf` rather than merely ceasing to
      install it: on deployed machines nginx would otherwise keep serving 8443 after the update
- [x] Report permissions `0644` → `0640` plus `chgrp` into the directory's group. The directory
      was already closed with `0750`, but the protection rested on one line of defence instead of
      two, and the files will now also be read by PHP-FPM
- [x] The reader group was factored out into `goaccess_reader_group` (default `www-data`)
- [x] **`chgrp` from the script failed: `Operation not permitted`.** The builder runs as
      `goaccess`, which is deliberately not a member of `www-data`, and only root may change a
      file's group to one it is not a member of — the build failed entirely on the first report,
      not just the permissions. Solved with a setgid bit on the directory: the kernel assigns the
      group. Found by running it
- [x] **Setgid on the reports directory did not help.** The file is built in `.build/` and
      inherits *its* group, and `mv` does not change the group. The build directory is recreated
      on every run so that it inherits the bit and the group from the parent. Verified:
      `www-data` reads, `nobody` is refused
- [x] **Recreating `.build` opened a race.** The timer and a role run can coincide (all the more
      easily because `Persistent=true` catches up on missed runs), and the second builder would
      have removed the directory out from under the first. `flock --nonblock` on the reports
      directory; `--conflict-exit-code 0`, otherwise systemd would have recorded a busy lock as a
      unit failure. Verified: two simultaneous runs — both 0, reports intact
- [ ] The `/traffic` route — **on the busel side**, not part of this task
- [ ] **The role is not wired into busel's `site.yml`** — it is on the machine from a manual run,
      but the playbook does not know it: on a new machine it will be absent. The line goes into
      busel

## Rejected
- [ ] A `stats.*` subdomain — needs a CF zone, DNS and an origin certificate, and the domains are
      not bought yet; and it would expose the domain list to the internet behind one password
- [ ] A `/krot-stats/` location on each site — would require editing the vhost template in busel
      and would add surface on a public domain
- [ ] `--persist/--restore` — accumulates without deduplication, see the review section
- [ ] Keeping the vhost behind a disabled flag as a fallback path — dead code that nobody enables
      rots unnoticed; it can always be brought back from git history
