# Changelog

Versions follow [semver](https://semver.org/). Breaking role changes (renaming a variable,
changing a default that affects production) bump major.

## 5.3.0

### Added

- **Role `common` caps the systemd journal** — `common_journal_max_use`, `500M` by default,
  through the drop-in `/etc/systemd/journald.conf.d/krot-journal.conf` rather than an edit to
  `journald.conf`, which the package rewrites on upgrade. Uncapped, journald takes 10% of the
  partition but no more than 4 GB — on busel's 77 GB disk it is that 4 GB ceiling that applies,
  since 10% would be 7.6 GB — and it keeps everything: the journal had grown to 1 GB, holding
  every message since the machine was installed a month and a half earlier. That was 1.1 GB of
  the 1.2 GB in all of `/var/log`, while nginx (4.8 MB) and php (2 MB) rotated as they should.

  A size cap, not a retention window: a ceiling holds the price of the journal however talkative
  the machine gets, whereas a retention window bounds age and lets a single bad day fill the
  disk. At busel's rate, 500 MB is about three weeks.

  The limit is read at start-up, so the handler restarts journald — a reload would leave the old
  ceiling in place.

  **The role shrinks future records only.** The restart applies the cap to new entries; what has
  already accumulated goes at the next rotation. To cut it immediately:
  `journalctl --rotate --vacuum-size=500M` — without `--rotate`, vacuum removes archived files
  only and leaves the one currently being written to, whatever its size. The role does not do
  this on its own: deleting history on a machine that still has room is the operator's call, not
  a side effect of a run.

## 5.2.0

### Fixed

- **Role `common`: unattended upgrades installed the whole release, not only security.** The
  drop-in claimed its origins "replace the distro list" because the file sorts after
  `50unattended-upgrades`. They did not — `Allowed-Origins` is an apt list and the block syntax
  expands to `::`, which **appends**. Measured with `apt-config dump`: eight origins in effect
  instead of three, among them `${distro_id}:${distro_codename}` — the entire release pocket.
  Confirmed at the level that decides, not only the config: `unattended-upgrade --dry-run --debug`
  reported `Allowed origins are: o=Ubuntu,a=noble, o=Ubuntu,a=noble-security, ...`.

  Fixed with `#clear Unattended-Upgrade::Allowed-Origins;` before the block, after which apt
  reports the three security origins and nothing else. Checked that the cure is not worse: with
  `50unattended-upgrades` deleted outright, the three still apply and packages still upgrade —
  the list never ends up empty. `#clear` is a real directive, not a comment; with a space
  (`# clear`) the release pocket comes straight back.

  **Already-provisioned machines take the new file on the next run** and stop installing
  non-security updates unattended. Nothing else changes.

- **Role `php`: PHP-FPM did not start at all when the pool was renamed.** The package ships
  `pool.d/www.conf` on `/run/php/php<ver>-fpm.sock` and the role writes its own pool on the same
  socket. FPM does not choose between them — it rejects the whole configuration with `unable to
  set listen address as it's already used in another pool`, exits `78/CONFIG`, and systemd gives
  up after five restarts.

  Invisible at the default `php_fpm_pool: www`, where the role overwrites that same file. It
  appeared the moment a project named its pool anything else — which is the only reason the
  variable exists, so the broken case was the configured one.

  The role now moves the packaged pool aside — to `www.conf.disabled`, since FPM includes
  `pool.d/*.conf` — but **only when that file actually listens on the socket the role's own pool
  claims**. Both conditions are needed, and the second was learned the hard way: the first version
  keyed on the pool's name alone, and review measured that a hand-written `www.conf` on a
  *different* socket coexists perfectly (`--test` passes, both sockets are served) while that
  condition deleted it anyway, taking the site behind it to 502.

  So on an already-provisioned machine: a `www.conf` that conflicts is renamed, one that does not
  is left alone, and nothing is deleted outright.

### Added

- **Molecule scenarios for 7 of the 11 roles** (`cron`, `firewall` ×2, `nginx` ×2, `postgresql`,
  `common`, `fail2ban`, `php`) — 94 of 118 tasks. Each brings up a systemd container, runs the
  role, runs it again for idempotence, then reads the machine back.

  Every scenario was checked by deliberately breaking the role it covers: a correct one keeps
  `converge` and `idempotence` green while `verify` goes red. Both defects above were found this
  way, as were several checks of ours that passed against a machine the role had never touched.

  The remaining four roles are recorded with the reason they have none rather than left unnamed —
  `scripts/coverage.py` fails if a role appears in no list, and holds the floor already reached.

## 5.1.1

### Fixed

- **Role `cron`: a job with a broken `working_directory` was skipped silently.** The `.service`
  carried `AssertPathIsDirectory=`, and the comment beside it promised a loud failure. `Assert*=`
  does not deliver one: a failed assert **does not fail the unit** — the run is skipped, the state
  stays successful, `systemctl --failed` is empty. Measured on busel (systemd 255), including a
  timer-driven run:

  | | with `AssertPathIsDirectory` | `WorkingDirectory` only |
  |---|---|---|
  | `Result` | **success** | `exit-code` |
  | `ExecMainStatus` | **0** | 200 (CHDIR) |
  | lines in `systemctl --failed` | **0** | **1** |

  It fires exactly where it was promised to: `working_directory` is the `current` release symlink,
  and after a botched deploy it points nowhere. The job stopped running while the machine reported
  health — the very class of failure the role was written for.

  The second half, found during review and measured there too: **the assert checked the path as
  root** (PID 1 evaluates it), while the work in that directory is done by `User=`. On a directory
  root can enter but `km` cannot, the assert passed and the command **ran from someone else's
  directory**, having silently lost the one assigned to it. `WorkingDirectory=` catches this case:
  systemd performs `chdir` after switching users.

  The assert is gone; `WorkingDirectory=` fails the unit. **Units on already-provisioned machines
  are rewritten** (a line leaves the `.service`) — the run will report `changed`, and no job
  restart is required.

## 5.1.0

### Added

- **Role `cron` — periodic application jobs as systemd timers.** A job is declared in the inventory
  (`cron_jobs`) and expanded into a `krot-<name>.service` + `.timer` pair. Krot knows no job name at
  all: the list belongs to the project.

  ```yaml
  cron_jobs:
    - name: traffic
      command: bin/console colony:traffic
      schedule: hourly
      working_directory: /var/www/busel/current
      environment:
        APP_ENV: prod
  ```

  Why it appeared: on busel an hourly job **did not run once in five days**, and there was nowhere
  to learn this from. Its output was redirected into `/var/log/`, where `km` has no write
  permission — that failed before PHP started, so the error had nowhere to land either. Meanwhile
  `journalctl -u cron` dutifully printed `(km) CMD (...)`: cron reports that a line was started and
  does not know how it ended.

  What a timer gives: output in the journal under the unit's name (no file permissions needed), the
  exit code in `systemctl status`, failure in `systemctl --failed`. All of it readable by the
  operator **without sudo** — verified on busel, even though `km` belongs to neither `adm` nor
  `systemd-journal`.

  No need to pick a minute; `RandomizedDelaySec` spreads jobs apart — plus `FixedRandomDelay`
  (`cron_fixed_random_delay`, on by default) to keep the offset constant: without it an hourly job
  drifts between 45 and 75 minutes from the previous run. `APP_ENV` and other variables are declared
  explicitly: a unit, like cron, starts with an empty environment.

  The role escapes the command itself. Both cases fail silently: a `%` in a unit file is a specifier
  (`date +%Y-%m-%d` printed the path to the unit's directory and exited with code 0), and a single
  quote tears argv apart the same way string joining does in `ssh` — half the work done, exit code
  zero.

  Two jobs sharing one `log_file` are rejected during the run: that is the same `duplicate log
  entry` described below, and it stops rotation of every log on the machine.

  A job removed from `cron_jobs` is retired from the machine. Ownership is determined by a marker
  inside the `.service` rather than by file name — `krot-cf-ranges.timer` from the `firewall` role
  matches the same glob and is left alone.

### Fixed — changes state on already-provisioned machines

Variable names and their meanings did not change, hence not a major version. But during a run the
role **deletes a file and edits a foreign config**, so upgrading from 5.0.0 is not silent — read
this before running.

- **Role `nginx` no longer installs `/etc/logrotate.d/krot-nginx`.** Its glob collided with the
  packaged `/etc/logrotate.d/nginx`, and logrotate picks no winner on a duplicate: it prints
  `duplicate log entry`, exits with code 1 and **rotates nothing on the machine** — php and
  postgresql included. On busel this lasted three days.

  `nginx_log_retention_days` is now applied by editing the `rotate` line in the packaged config —
  it is a `conffile`, dpkg does not silently discard a local edit on package upgrade, and if the
  edit is reverted anyway, the next run restores it.

  **The run fails if the packaged file has no `rotate` line**, instead of appending one. A directive
  past the closing brace causes no error — logrotate discards it and rotates **with no retention at
  all**, deleting yesterday's log instead of keeping fourteen.

  **Cleanup on an already-provisioned machine happens by running the role**, which removes its own
  file. To verify rotation is back:

  ```bash
  systemctl --failed              # logrotate.service must not be listed
  sudo systemctl start logrotate.service
  ```

## 5.0.0

### Breaking

- **The operator shell is `/bin/bash` instead of fish** (`bootstrap_user_shell`). The role no longer
  installs the `fish` package; on an already-provisioned machine the next `bootstrap` run switches
  the existing `km` to bash. An active SSH session finishes in the old shell, every subsequent one
  gets bash.

  These machines are almost always driven by agents and rarely by hand. Every place where fish
  diverges from POSIX costs an agent a separate debugging session: the command arrives parsed
  differently, the error looks like a problem with the command, and the command is correct. That is
  expensive for the convenience of one person logging in occasionally; bash is always on the machine
  and asks for nothing.

  **The role does not remove the `fish` package.** If it is not needed, remove it manually — but
  **only after the role has run** and `getent passwd km` shows `/bin/bash`. Purging the package
  earlier means leaving a path to a non-existent shell in `/etc/passwd` and losing `km` login:

  ```bash
  getent passwd km   # make sure this says /bin/bash
  sudo apt-get purge fish
  ```

  For anyone who wants fish, the shell comes back through the variable, but the package is then
  yours to install: `bootstrap_user_shell: /usr/bin/fish`.

## 4.0.0

### Breaking

- **Roles `goaccess` and `geoip` removed.** The reports went unused while costing plenty to keep: a
  private apt repository, a signing key, a build timer, a MaxMind key in the inventory and a 64 MB
  database downloaded twice a week for a dashboard nobody looked at.

  A playbook listing these roles now fails on an unknown role — remove them from `site.yml` and drop
  the `goaccess_*` and `geoip_*` variables from `group_vars`.

  **Cleanup on an already-provisioned machine is manual**; the roles remove nothing after themselves
  because they no longer exist and there is nobody left to delete what they left. What to look at (on
  busel only the last item turned out to be present — the roles never ran to completion there):

  ```bash
  sudo systemctl disable --now krot-goaccess.timer krot-geoipupdate.timer
  sudo rm -f /etc/systemd/system/krot-goaccess.{timer,service} \
             /etc/systemd/system/krot-geoipupdate.{timer,service}
  sudo systemctl daemon-reload
  sudo apt-get purge goaccess geoipupdate
  sudo rm -rf /var/www/goaccess /etc/goaccess /var/lib/GeoIP /etc/GeoIP.conf
  sudo rm -f /etc/apt/sources.list.d/goaccess.sources /etc/apt/keyrings/goaccess.asc
  ```

  The GoAccess repository is worth removing even where the package was never installed: otherwise
  every `apt update` keeps fetching an index for a package nobody asks for any more.

  The `nginx` role is unaffected: it never wrote `log_format` anyway — the project's vhost generator
  owns it.

## 3.0.0

### Breaking

- **The human report is off by default** (`goaccess_humans_report: false`). On an already-provisioned
  machine the role **deletes** the `humans/` directory and `/etc/goaccess/krot-crawlers.list`; to
  keep things as they were, set `goaccess_humans_report: true` explicitly. The full report is
  untouched.

  The reason is not a breakage but that the number could not be trusted. Three passes over
  berlindame.de: `--ignore-crawlers` gave 41 "visitors", a list of names gave 36, an added behavioural
  check gave 6 addresses out of 103. Of those six, three fetched `/media/` with referers like a real
  browser and are indistinguishable from humans in the log at all; the honest answer is two. A number
  that walks from 41 down to 6 under filters each of which looks reasonable is not a measurement, yet
  it reads like one. A missing number is more honest than an invented one.

  Telling humans from machines by request pattern is possible up to a limit, and that limit has been
  reached: beyond it you need a marker the browser executes, and the log does not provide one. The
  filter code and the `goaccess_extra_crawlers` list, tuned against live traffic, stay in the role —
  the variable brings the report back, and it is rebuilt in the same run.

## 2.5.0

- **GoAccess 1.11** from the project's official repository instead of 1.8.1 from Ubuntu
  (`goaccess_upstream_repository`, on by default). The signing key is baked into the role
  (`C03B48887D5E56B046715D3297BD1A0133449C3D`, the GoAccess author) rather than fetched at runtime.
  Done for cities in geolocation; the claimed 35% parsing speed-up was not verified — no comparable
  figures were kept.
- While the repository is enabled, the package is installed with `state: latest`. With `present`, a
  machine already carrying 1.8.1 would have kept it, and the role would have reported success
  without doing anything.
- **Disabling the repository does not downgrade** — apt does not downgrade on its own, and the role
  deliberately does not either. To downgrade by hand: `apt install goaccess=<version>`.
- `geoip` downloads `GeoLite2-City` instead of `GeoLite2-Country`: the edition carries both levels,
  and 1.11 shows cities. 64 MB against 8.4.
- `geoip` **deletes databases absent from `geoip_editions`**: a copy of a file someone looks at that
  has stopped updating answers wrongly and does not say how stale it is.

## 2.4.0

- **Role `geoip`**: MaxMind GeoLite2 databases and a systemd timer keeping them fresh. A separate
  role rather than part of `goaccess`: the database is needed by more than the reports, and a machine
  may want one without the other. The config with the licence key is `0600 root`. The package's own
  timer is disabled: two schedules over the same files is one more reason to wonder why a database is
  stale.
- **A geolocation panel in `goaccess` reports** — `goaccess_geoip_database`. Empty by default:
  without a database there is simply no panel. The role **refuses** to configure a database that is
  not on disk — GoAccess would not start at all in that case, every report would stop at once, and
  the already-built ones would sit there looking fresh.
- The country comes from the database by address rather than from the `CF-IPCountry` header: GoAccess
  has no field to accept a ready-made country code. This is only correct because the project
  configures real-IP — otherwise the panel would show Cloudflare data centres.

## 2.3.0

- **The human `goaccess` report filters scanners that do not call themselves bots.**
  `--ignore-crawlers` only catches those with `bot`, `crawler` or `spider` in the User-Agent;
  `GoogleOther`, `Dataprovider`, `InternetMeasurement`, `UptimeRobot`, `HeadlessChrome` and HTTP
  libraries passed as visitors. The list is in `goaccess_extra_crawlers`, attached with the `-b` flag
  to the human report only — the full one still counts everyone. Measured: berlindame.de 41 → 36,
  stadtdame.de 26 → 20.
- The type in the file is written `Crawlers` (capitalised, plural). Spelled otherwise, GoAccess
  creates a new browser category and the visitor counter **grows** instead of falling — measured, 41
  turned into 78.

## 2.2.0

- `common` installs `btop`, `ncdu`, `ripgrep`, `jq` and `fd-find`. All of them are needed exactly
  when the machine behaves strangely — that is, when you least want to fetch them first. `btop` shows
  CPU, memory, disks and network on one screen; `ncdu` answers where the space went, which `htop`
  cannot; `ripgrep` searches a gigabyte access log in the time `grep -r` spends warming up; `jq`
  parses the JSON services return. All from the stock Ubuntu 24.04 repository, no third-party PPAs.
- **`fd-find` installs the binary as `fdfind`**, not `fd` — the name is taken by another Debian
  package. The role adds no alias: what a login shell offers is the operator's business, not the
  machine's.

## 2.1.0

- **A second `goaccess` report per site — `humans/<domain>.html`, without crawlers.** Both reports
  are needed: on berlindame.de there were 94 unique visitors in the full report against 37 in the
  human one, 57 of them bots. The full one does not say how many people came; the bot-free one does
  not show whether Googlebot visits, which matters more on a young site. Turned off with
  `goaccess_humans_report`, and the role then deletes the directory so frozen pages are not left
  being served.
- A subdirectory rather than a `-humans` suffix in the name: anything enumerating reports with a
  `*.html` glob still sees exactly one file per domain. Deleting reports for retired sites now walks
  both directories — otherwise the second page would lie there forever, naming a retired domain.

## 2.0.0

### Breaking

- **`goaccess` no longer serves reports itself.** `goaccess_listen_address`, `goaccess_listen_port`
  and `goaccess_auth_enabled` are gone along with the vhost on `127.0.0.1:8443` and basic auth; the
  role **deletes** `/etc/nginx/conf.d/krot-goaccess.conf`, otherwise nginx would keep serving it on
  already-provisioned machines. The reason is not technical: a report cannot be opened from a phone
  through an SSH tunnel, and that is the main scenario. The project serves them — busel on a
  `/traffic` route behind its own admin login, with no second password and no subdomain in public
  DNS. The same split as with `postgresql`: the role installs the server, the project does the
  per-site things.

### New

- Reports are written `0640` (was `0644`) with the `goaccess_reader_group` group (`www-data` by
  default), the directory `2750`. The group is assigned by the setgid bit: the writing account is
  deliberately not a member of the reader's group, and `chgrp` into a foreign group is forbidden to
  everyone but root. The role brings existing reports to the new mode immediately, without waiting
  for a timed rebuild.

## 1.1.0

- Role `goaccess`: traffic reports from nginx logs, one per site. Not a line of JS on the sites — a
  third-party counter across a network of domains would be evidence of the link between them. There
  is deliberately no combined report: a single page listing every domain is exactly the list the
  network is hidden for.
- The role requires a `log_format` starting with `[$time_local]`: without the time GoAccess does not
  start at all. The format belongs to the project; the role only reads it.
- The report is rebuilt from the logs on disk rather than accumulated in a GoAccess database:
  `--persist` does not remember the lines it has already read and counts an unrotated log again on
  every run.

## 1.0.0

The first version verified end to end on a live machine. Two breaking edits — hence major.

### Breaking

- **`nginx` no longer writes `log_format` and `set_real_ip_from`** and deletes what it used to write
  (`krot-real-ip.conf`, `*-log-format.conf`). The owner is the project's vhost generator: it knows
  the format name its configs refer to, and refreshes the CF ranges on every generation rather than
  once per Ansible run. Two writers on one setting drift apart, and a stale `set_real_ip_from`
  silently logs the CDN's address instead of the visitor's. The project needs to define the format
  itself.
- **`postgresql_version` defaults to `18`** (was `16`). This is not an upgrade: PostgreSQL does not
  read the data directory of a previous major version, so the role **refuses** to run alongside a
  cluster of a different version. The transition goes through `pg_upgrade`/dump-restore, then a
  one-off `postgresql_remove_other_versions=true`, which **destroys** the old databases.

### New

- Roles `deploy` and `deploy_keys`. The first runs the project's Deployer from the control machine
  without reinventing releases and rollback. The second hands out an SSH key per private repo plus
  host aliases: one deploy key cannot be used in two GitHub repositories, and without an alias ssh
  presents the first key that fits.
- `nginx` can do basic auth for unpublished sites: a password file from the secret store at runtime
  and the `krot-auth.conf` snippet. Which sites are locked is decided by the project's vhost
  generator, so they open one at a time.
- `postgresql` collects `pg_stat_statements`. The slow log catches a query that is slow once; a 20 ms
  query called 100,000 times a day never crosses the threshold, though it may be the top one by total
  time. `shared_preload_libraries` is written as a whole list: PostgreSQL takes the last assignment
  literally, and a second consumer added through a separate config would have evicted the first.

### Existing, clarified

- `firewall` can do the Cloudflare lock: 80/443 from CF ranges only, refreshed by a weekly systemd
  timer. Only firewall reads the list — `nginx` no longer touches it.
- `bootstrap` does not disable password login until it has confirmed a valid SSH key is in place, and
  removes the cloud-init drop-in that would otherwise turn it back on.
- php-fpm, nginx and PostgreSQL logs are configured for collection by an external agent.

Verified by a run against live Ubuntu 24.04: every role applies, and a repeat run yields `changed=0`.
