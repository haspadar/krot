# Krot

The `haspadar.krot` Ansible collection — portable roles for provisioning Ubuntu machines.
A mole (*krot*) digs under the services and fixes the plumbing unseen; hence the name.

Roles know about the **host**, not about the applications on it: project specifics live in its
`inventory`/`group_vars`, not inside a role.

## Installation

```yaml
# requirements.yml in the project
collections:
  - name: git+https://github.com/haspadar/krot.git
    type: git
    version: main   # or a tag, to freeze the infrastructure
```

```bash
ansible-galaxy collection install -r requirements.yml
```

Dependencies (`ansible.posix`, `community.general`, `community.postgresql`) come along on their own.

## Usage

```yaml
- name: Provision the machine
  hosts: web
  roles:
    - role: haspadar.krot.common
    - role: haspadar.krot.php
    - role: haspadar.krot.nginx
    - role: haspadar.krot.firewall
    - role: haspadar.krot.fail2ban
```

A bare machine — first once as root:

```yaml
- name: Bootstrap SSH access
  hosts: new
  roles:
    - role: haspadar.krot.bootstrap
      vars:
        bootstrap_authorized_keys: ["ssh-ed25519 AAAA..."]
```

```bash
ansible-playbook bootstrap.yml -u root -k
```

## Roles

| Role | What it does |
|------|-----------|
| `bootstrap` | Operator user + sudo, `authorized_keys`, `PermitRootLogin no`, `PasswordAuthentication no` |
| `common` | hostname, timezone, base packages (including `btop`, `ncdu`, `ripgrep`, `fd-find`, `jq`), unattended security upgrades, a cap on the systemd journal |
| `firewall` | ufw; with `firewall_cloudflare_only` it admits 80/443 only from Cloudflare ranges and refreshes them on a weekly timer |
| `fail2ban` | fail2ban with the `sshd` jail |
| `php` | PHP-FPM from the ondrej PPA; slowlog, access log with timings. A packaged `www.conf` on the same socket is renamed aside, since two pools cannot share one |
| `postgresql` | PostgreSQL from pgdg, csvlog with a slow-query log, `pg_stat_statements`. The server only, no databases |
| `nginx` | nginx.conf, permissions, log retention, basic auth. Leaves per-site vhosts, log_format and real-IP alone |
| `docker` | Docker + the compose plugin, a cap on container log growth |
| `deploy_keys` | A separate SSH key per private repository plus host aliases, so git presents the right one |
| `deploy` | Runs the project's Deployer from the control machine. Releases and rollback stay in `deploy.php` |
| `cron` | Periodic application jobs as systemd timers: output to the journal, exit code visible to `systemctl` |

Every role is atomic and applicable on its own. All parameters live in
`roles/<role>/defaults/main.yml`.

**`fd` is called `fdfind` on the machine.** The `fd-find` package cannot claim the name `fd` — it
belongs to another Debian package. The role does not add an alias: what a login shell contains is
the operator's business, not the machine's.

### What the roles deliberately do NOT do

- **Vhosts for specific sites** — the project generates those itself; the `nginx` role owns only
  the `sites-available`/`sites-enabled` directories and their permissions.
- **Databases for specific applications** — the `postgresql` role installs the server only.
- **Code deployment** — that is the project's Deployer/CI. There is exactly one overlap: the role
  creates the user and the directory with permissions where releases are later placed.

## Deployment

The `deploy` role is a thin wrapper: Deployer runs **on the control machine** and reaches the
server over SSH itself. No CI is needed for deployment; this is the manual path.

```bash
ansible-playbook deploy.yml
ansible-playbook deploy.yml -e deploy_task=rollback
ansible-playbook deploy.yml -e deploy_branch=some-branch
```

The role deliberately does not reinvent releases, symlinks and rollback — the project's
`deploy.php` already handles those.

**Two pitfalls, both real:**

- **One deploy key cannot be used in two GitHub repositories.** A machine pulling several private
  repos gets a key for each (`deploy_keys`) plus a host alias: clone with
  `git@<name>.github.com:owner/repo.git`. Without the alias, ssh presents the first key that fits
  and GitHub answers for the wrong repository.
- **The role does not write `log_format` or real-IP** — the project's vhost generator owns those:
  it knows which format name its own configs refer to, and refreshes the CF ranges on every
  generation rather than once per Ansible run. Two writers on one setting inevitably drift apart,
  and a stale `set_real_ip_from` silently logs the CDN's address instead of the visitor's.

## Periodic application jobs

Jobs are declared by the inventory, and the role expands each into a `krot-<name>.service` +
`krot-<name>.timer` pair:

```yaml
cron_jobs:
  - name: traffic
    description: Visitor figures for every site, copied out of Analytics
    command: bin/console colony:traffic
    schedule: hourly
    working_directory: /var/www/busel/current
    environment:
      APP_ENV: prod
```

Krot knows no job name at all: the list is a project variable, and the next server will declare
its own.

**Why systemd timers rather than a crontab line.** On busel an hourly job did not run once in five
days, and this was visible from nowhere. Its output was redirected into `/var/log/`, where `km`
has no write permission — the redirection failed **before** PHP started, so the error message had
nowhere to land either. Meanwhile `journalctl -u cron` cheerfully printed `(km) CMD (...)` every
hour: cron reports that it **started** the line and does not know how it ended.

What the replacement changes:

| | crontab | systemd timer |
|---|---|---|
| output | to a file you need permissions for | journal, no permissions needed |
| exit code | nowhere | `systemctl status` |
| failure visible without knowing the path | no | `systemctl --failed` |
| rotation | your own, which you must remember to write | system-wide |
| survives machine re-creation | no | yes |

Output is found by job name rather than by file path, and **is readable by the operator without
sudo**:

```bash
systemctl list-timers 'krot-*'      # which jobs exist and when the next one runs
journalctl -u krot-traffic          # what it printed
systemctl status krot-traffic       # which code it ended with
systemctl --failed                  # what is broken on the machine at all
```

The last line is what this was all for: an unsuccessful run is visible to whoever looks at the
machine for the first time and does not know the job exists.

**`APP_ENV` and other variables are declared explicitly.** systemd has exactly the same trait as
cron: a unit starts with an empty environment and inherits nothing from the login shell.

**The command needs no escaping** — the role does it itself, and not out of tidiness but because
both cases fail silently. A `%` in a unit file is a specifier: `date +%Y-%m-%d` without doubling
printed `/etc/systemd/system-<machine-id>-/run/credentials/<unit>` and **exited with code 0**
(measured). A single quote inside the command tears argv apart the same way string joining does in
`ssh`: `-c` takes the first word, the rest goes to `$0` and `$1` — half the work done, exit code
zero. The role doubles `%` and quotes the command as a whole, so the inventory carries a plain
string.

**No need to pick a minute.** `RandomizedDelaySec` spreads jobs apart on its own. Picking a minute
by hand works until the second job, whose author has to work out afresh which minutes are already
taken — knowledge recorded nowhere.

The offset is **constant** (`cron_fixed_random_delay: true`, the default): it is derived from the
machine and unit names, so jobs are spread apart from each other while a given job runs at the same
minute every time. A job declared `hourly` should run once an hour — the point of the offset is to
avoid the crowd, not to wander. Turning it off (`fixed_random_delay: false`) restores recomputation
on **every** trigger, and the gap between consecutive runs of an hourly job starts drifting between
45 and 75 minutes at `cron_randomized_delay: 15m`.

File output is possible (`log_file`) but not the default: the role then creates the file with the
right owner **and** writes `/etc/logrotate.d/krot-cron`, because half of that pair reproduces the
original defect.

**`working_directory` is a release symlink, and after a botched deploy it points nowhere.** Such a
run fails with `status=200/CHDIR` and lands in `systemctl --failed`, rather than running from `/`
where the command would find neither `bin/console` nor `vendor`. It is the `WorkingDirectory=` line
itself that fails the unit; `AssertPathIsDirectory=` will not do, for two reasons, both measured on
busel (systemd 255): a failed assert **does not fail the unit** but skips the run, leaving
`Result=success` and an empty `--failed`; and it checks the path **as root**, whereas the work in
that directory will be done by `User=`. On a directory `km` cannot enter, the assert passed and the
command ran from someone else's directory. systemd performs `chdir` after switching users, so
`WorkingDirectory=` catches this too.

**What this does not fix.** A job that returns 0 without doing its work stays green under any
transport. The answer to that lives in the job itself: it must fail when it has not done what it
was run for.

## Locking unpublished sites

A site must not be reachable, indexed or crawled before someone has looked at it. Therefore
**locked is the default state**, and publishing is an explicit act.

Krot provides the mechanism only: the password file `/etc/nginx/.htpasswd` (the password is taken
from the secret store at runtime) and a snippet:

```nginx
# /etc/nginx/snippets/krot-auth.conf
auth_basic "Preview";
auth_basic_user_file /etc/nginx/.htpasswd;
```

**Which sites are locked is decided by the project's vhost generator, not by Krot.** It adds one
line to the template while a site is not marked as published:

```nginx
server {
    server_name {{ domain }};
{% raw %}{% if not published %}{% endraw %}
    include /etc/nginx/snippets/krot-auth.conf;
{% raw %}{% endif %}{% endraw %}
    ...
```

This way sites open one at a time rather than all at once. Enabled via `nginx_auth_enabled: true`
plus `nginx_auth_password` from the secret store.

## The Cloudflare lock

`firewall_cloudflare_only: true` closes 80/443 to everything except the published Cloudflare
ranges — the origin address stops answering directly.

The ranges are fetched from `cloudflare.com/ips-v4`/`ips-v6`, stored in
`/etc/krot/cloudflare-ranges.txt` and refreshed by the `krot-cf-ranges.timer` unit (weekly). The
`nginx` role does not read this list: real-IP is configured by the project's vhost generator, which
refreshes the ranges on every generation.

The `/usr/local/sbin/krot-cf-ranges` script refuses to change the rules if CF's answer is empty or
suspiciously short: a truncated list would silently cut the sites off from the world.

**About SSH:** the rule for port 22 is created before ufw is enabled and before the CF lock, so
access to the machine is not lost. For the same reason the `bootstrap` role refuses to disable
password login until it has confirmed a valid key is in place.

## Logs

Configured for collection (Loki/Alloy and the like), but no agent is installed — that is a separate
role.

- **nginx** — the format is set by the project's vhost generator; the role is responsible for
  rotation and for `conf.d` being included before the vhosts that rely on it.
- **php-fpm** — `/var/log/php/`: access with timings, slowlog with a stack trace of slow requests,
  a separate error log.
- **postgresql** — csvlog, slow queries, `log_lock_waits`, `log_checkpoints`, plus
  `pg_stat_statements` (see below).

nginx and php are rotated through logrotate; PostgreSQL rotates itself.

**The systemd journal is capped at 500 MB** (`common_journal_max_use`, the drop-in
`/etc/systemd/journald.conf.d/krot-journal.conf`). Uncapped, journald takes 10% of the partition
but no more than 4 GB — on busel's 77 GB disk it is that ceiling which applies, since 10% would
be 7.6 GB — and it keeps everything: the journal had grown to 1 GB, holding every message since
the machine was installed a month and a half earlier.

It is the size that is capped, not the retention window: a ceiling holds the price of the journal
however talkative the machine gets, whereas a window bounds age and lets a single bad day fill the
disk. At busel's rate, 500 MB is about three weeks.

**The role shrinks future records only, not a journal that has already grown.** A change of limit
is applied by restarting journald, and the restart does not touch what is accumulated — the old
records go at the next rotation. To cut it immediately:

```bash
# the same size as in common_journal_max_use
sudo journalctl --rotate --vacuum-size=500M
```

`--rotate` is not decoration here: vacuum deletes archived files only, so the one the journal is
being written to right now stays whatever its size. Rotation closes it into the archive, and only
then does it fall under the same command.

The role does not do this itself, because deleting history on a machine that still has room is the
operator's call, not a side effect of a run.

**One log, one logrotate entry.** The `nginx` role no longer installs its own file: the package
owns nginx rotation, and the role edits only the number on the `rotate` line in its config. Two
configs for one log is not "last one wins": logrotate declares `duplicate log entry`, exits with
code 1 and **processes nothing on the machine at all**, including the unrelated php and postgresql.
On busel this lasted three days, was discovered through `systemctl --failed` and cost the rotation
of every log at once. The duplicate is detected by the resolved path rather than by the template
text, so rewriting the glob differently does not help.

Two subtleties of this edit, both verified:

- **If the `rotate` line is missing, the run fails** rather than appending it to the end of the
  file. A directive past the closing brace causes no logrotate error: it is silently discarded and
  the log is rotated **with no retention at all**, deleting yesterday's log instead of keeping
  fourteen. The role refuses and states the reason, because a second config is the first paragraph
  of this section.
- **The file is a `conffile` of the `nginx-common` package.** On upgrade, dpkg sees the local edit
  and does not overwrite it silently (in non-interactive mode it keeps our version). Should the
  edit be reverted anyway, the next role run restores it.

## The major PostgreSQL version

`postgresql_version` is the version the role installs, **not** an upgrade of a running one.
PostgreSQL does not read the data directory of a previous major version: raising the variable from
16 to 18 installs **a second cluster alongside** rather than upgrading the first.

What happens next goes unnoticed: `pg_createcluster` takes the first port not occupied by an
existing cluster, that is 5433, while the role's config declares 5432 — the new cluster does not
start, the application keeps working with the old one, and everything looks fine. Therefore the
role **refuses** to run alongside a cluster of a different version and states the reason.

The upgrade order:

1. move the data — `pg_upgrade`, or `pg_dumpall` with a restore;
2. `postgresql_remove_other_versions: true` — **deletes the old cluster along with its databases**;
3. run the role, then set the flag back to `false`.

The flag exists precisely because deleting data must not be a side effect of changing a version
number.

A separate subtlety: `postgresql-common` creates a cluster in postinst only if the port is free.
Installing alongside a running old cluster leaves the new version **without a cluster at all**, and
removing the old one afterwards does not create it retroactively — which is why the role creates
the cluster explicitly instead of relying on the package.

## PostgreSQL query statistics

The slow log (`log_min_duration_statement = 500`) catches a query that is slow **once**. But a 20 ms
query called 100,000 times a day will never appear in it — while by total time it may be the top
query in the database, and it is the one asking for an index. This is only visible through
`pg_stat_statements`, which aggregates by normalised query text.

Enabled by default (`postgresql_stat_statements: true`). The extension is installed into the
`postgres` maintenance database: the view shows statistics for **the whole cluster** regardless of
which database you look from, so the role still knows nothing about specific sites' databases.

Top by total time:

```sql
SELECT calls,
       round(total_exec_time::numeric)     AS total_ms,
       round(mean_exec_time::numeric, 2)   AS mean_ms,
       rows,
       left(query, 120)                    AS query
FROM pg_stat_statements
ORDER BY total_exec_time DESC
LIMIT 20;
```

From the server, in one command:

```bash
sudo -u postgres psql -d postgres -c "SELECT calls, round(total_exec_time::numeric) AS total_ms, \
round(mean_exec_time::numeric, 2) AS mean_ms, rows, left(query, 120) AS query \
FROM pg_stat_statements ORDER BY total_exec_time DESC LIMIT 20;"
```

Two catches, either of which would cost a minute on the server:

- the columns are named `total_exec_time`/`mean_exec_time`, not `total_time` as in older recipes
  found online: they were renamed in PG 13, and the role installs 18 (`postgresql_version`);
- the `::numeric` cast is mandatory: times are stored as `double precision`, and PostgreSQL has no
  two-argument `round(double precision, integer)` — without the cast the query fails.

`pg_stat_statements.save` defaults to `on`, so statistics survive a restart and accumulate from the
last reset. After adding an index, the old numbers will keep dragging the picture backwards — reset
them to get a clean baseline for measurement:

```sql
SELECT pg_stat_statements_reset();
```

**`shared_preload_libraries` is a list parameter, and PostgreSQL takes the last assignment as a
whole** — it has no "append" syntax. The role therefore writes the entire list at once rather than
one line per library. A second consumer (`auto_explain`, `pg_cron`) is added to
`postgresql_shared_preload_libraries` rather than in a second config — otherwise it would silently
evict `pg_stat_statements`.

**About restarts.** The role restarts PostgreSQL on any change to its `99-krot.conf`, not just to
this line: some of the parameters in that file (`shared_preload_libraries`, `shared_buffers`,
`max_connections`, `logging_collector`) are postmaster-level, and `reload` accepts them silently
without applying them. The role does not try to separate reload from restart by parameter type: the
cost of getting it wrong is a setting that is applied on paper but not in fact. A restart takes a
couple of seconds, but it is downtime for every site on the machine, so a run with no config changes
does not touch the database at all.

## Secrets

Roles take passwords from Bitwarden at runtime; there are no secrets in the repository. Before a
run the vault must be unlocked, **and the token must be handed to the playbook through the
environment**:

```bash
BW_SESSION="$(cat /tmp/bw-$USER/session)" ansible-playbook site.yml
```

The lookup plugin runs `bw` itself and knows nothing about the session cache. Without the variable
it sees the vault as locked and fails the run — even when `bw status --session` from that same cache
answers `unlocked`. The message then complains about the lock rather than the missing variable.

A role that needs a password fails on an `assert` rather than installing an empty one: an empty
`htpasswd` would let anyone into a locked site.

## Wiki

Knowledge of **how to work with this and what bites** lives in [`wiki/`](wiki/README.md): why it is
done this way, what fails silently and by which sign to notice it. A role describes itself through
its tasks and `defaults/main.yml` — the wiki answers something else. The wiki is written in Russian.

```bash
python3 scripts/wiki-lint.py                    # links, frontmatter, secrets
python3 scripts/wiki-index.py                   # rebuild wiki/index/
python3 scripts/wiki-triage.py                  # sort out wiki/raw/
python3 scripts/wiki-after-archive.py <change>  # after archiving — what went stale
```

No dependencies: python3 only. The first two run in CI, along with `secret-lint.py` (the same
patterns over everything git tracks) and `coverage.py` (which role has a scenario). The conventions
are in [`wiki/CONVENTIONS.md`](wiki/CONVENTIONS.md).

## Development

Architecture and settled decisions are in `openspec/ARCHITECTURE.md`. Changes are tracked as in
busel and matilda: `openspec/changes/<date>-<slug>/` with `proposal.md` (why and what changes) and
`tasks.md`; finished ones move to `changes/archive/`. Both are written in Russian.

```bash
yamllint .        # YAML formatting
ansible-lint      # the production profile — the strictest one
```

CI (`.github/workflows/lint.yml`) runs both on every PR, alongside the collection build,
`wiki-lint`, `secret-lint`, a check that `wiki/index/` still matches its sources, and
`coverage.py`. The role tests are separate jobs — see below.

### Running the role tests

Roles are tested with Molecule; scenarios live under `molecule/<name>/`, and a role may have more
than one (`firewall` has `firewall` and `firewall_cloudflare`, whose configurations contradict each
other). Each brings up a systemd container, runs the role, runs it again to check idempotence, then
verifies the machine.

```bash
pip install molecule 'molecule-plugins[docker]' ansible-core
ansible-galaxy collection install -r molecule/requirements.yml
ansible-galaxy collection install -r requirements.yml

molecule test --all          # every scenario in turn, locally; CI does not run this
molecule test -s php         # one scenario
molecule converge -s php     # run the role and leave the container up
molecule verify -s php       # re-run just the checks against it
molecule destroy -s php      # clean up afterwards
```

`converge` leaves the container running, which is the fast loop while writing a scenario:
`converge` once, then `verify` as many times as needed. `test` always destroys at the end — a
cancelled run does not, so `molecule destroy -s <name>` (or `docker rm -f krot-<name>`) is worth
knowing.

Docker must be running: on macOS these were developed against Colima, and `colima start` is the
usual fix when `create` fails complaining about the socket.

**A scenario is only worth what it catches.** Every one here was checked by deliberately breaking
the role it covers — a correct scenario keeps `converge` and `idempotence` green while `verify`
goes red. Three defects in the roles were found this way, and six in the checks themselves.

`scripts/coverage.py` prints which roles have a scenario and fails if a role appears in no list at
all, or if coverage drops below the floor recorded in it. Raising that floor is a manual edit, on
purpose.

Before writing a scenario, read [тесты ролей](wiki/operations/testing-roles.md) in the wiki: which
traps have already been measured — starting from a clean machine, values that match the defaults,
checks that ask the filesystem instead of the daemon — and why each one made a scenario pass
against a role that had never run.

All roles are idempotent: a repeat run yields `changed=0`. This is not a declaration — it is
verified by running against a live machine.

The target platform is Ubuntu 24.04 (noble).
