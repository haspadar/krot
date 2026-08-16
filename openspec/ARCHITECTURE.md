# Krot architecture

The `haspadar.krot` Ansible collection — portable roles for provisioning the network's servers.
A mole (*krot*) digs under the services and fixes the plumbing unseen.

Neighbours on the network: **Matilda** (the donor — parses, normalises and serves profiles over an
API) and **Busel** (the recipients — sites that take profiles from Matilda's API). Krot holds up
the machines of both.

## What this is

A collection of roles, not a playbook. The repository has **no inventory and no site.yml** for
particular machines: those live in busel and matilda, each with its own hosts and variables. Krot
is the source of roles, and projects wire it in as a dependency:

```yaml
# the project's requirements.yml
collections:
  - name: git+https://github.com/haspadar/krot.git
    type: git
    version: main   # or a tag, to freeze the infrastructure
```

This is the "composer way": `ansible-galaxy collection install` lays the collection out locally the
way `composer install` fills `vendor/`. Not a submodule and not a symlink — updating a role means
changing `version`.

Why a collection rather than a set of roles: `ansible-galaxy` can install a git source as **one
role**, not as a directory of roles. A collection is the only form in which a set of roles installs
with a single command and is versioned as a whole.

## The main principle: a role knows about the host, not about the applications on it

This is not a matter of style; it is what keeps the roles portable. The moment a role learns the
name of a site or a database, it stops being general and turns into the config of one machine.

| Layer | What it does | Tool |
|------|-----------|-----------|
| Provisioning the **machine** | user, packages, firewall, fail2ban, (docker \| php+pg+nginx) | **Krot (Ansible)** |
| Provisioning the **site** | domain, CF zone, vhost, the site's database, Bearer token to Matilda | **`recipient:*` console commands** in busel |
| Deploying the **code** | releases, symlink, reload | **Deployer** (`deploy.php`) in each project |

Ansible and Deployer overlap in exactly one place: Ansible creates the `km` user and the
`/var/www/<project>` directory with permissions, where Deployer later puts releases.

### What the roles deliberately do NOT do

- **Vhosts for particular sites.** A busel console command generates them. The `nginx` role owns
  only the `sites-available`/`sites-enabled` directories and their permissions.
- **`log_format` and real-IP.** The owner is that same vhost generator: it knows which format name
  its configs refer to, and refreshes the CF ranges on every generation rather than once per Ansible
  run. Two writers on one setting inevitably drift apart, and a stale `set_real_ip_from` silently
  logs the CDN's address instead of the visitor's.
- **Databases of particular applications.** The `postgresql` role installs the server only; the
  site's database and role are created by site provisioning.
- **Code deployment.** The `deploy` role only launches the project's Deployer — releases, symlink
  and rollback stay in `deploy.php`.

## Roles

| Role | What it does | For whom |
|------|-----------|------|
| `bootstrap` | User + sudo, `authorized_keys`, `PermitRootLogin no`, disabling password login | all |
| `common` | hostname, timezone, base packages, unattended security upgrades, a cap on the systemd journal | all |
| `firewall` | ufw; the Cloudflare lock and a weekly range refresh | all |
| `fail2ban` | fail2ban with the `sshd` jail | all |
| `php` | PHP-FPM from the ondrej PPA; slowlog, access log with timings | busel |
| `postgresql` | PostgreSQL from pgdg, csvlog, `pg_stat_statements`. The server only | busel |
| `nginx` | nginx.conf, permissions, log retention, basic auth | busel |
| `docker` | Docker + the compose plugin, a cap on container log growth | matilda |
| `deploy_keys` | A separate SSH key per private repository + host aliases | all |
| `deploy` | Runs the project's Deployer from the control machine | all |
| `cron` | Periodic application jobs as systemd timers; the job list is an inventory variable | all |

Two sets: busel — `common + php + postgresql + nginx + firewall + fail2ban` (several sites on one
machine behind Cloudflare); matilda — `common + docker + firewall + fail2ban` (a bare host for
Docker Compose, where compose itself solves the application's reproducibility).

Every role is atomic and applicable on its own. All parameters live in
`roles/<role>/defaults/main.yml`.

## Decisions that cost mistakes

Each one below is not theory but something that broke, or nearly broke, on a live machine.

### The origin is hidden behind Cloudflare, and that concerns two roles

busel has several sites on one machine behind Cloudflare, with the origin IP hidden from day one.
`firewall_cloudflare_only` admits 80/443 only from CF's published ranges; the list lives in
`/etc/krot/cloudflare-ranges.txt` and is refreshed by the `krot-cf-ranges.timer` timer.

The script refuses to change the rules if CF's answer is empty or suspiciously short: a truncated
list would silently cut the sites off from the world.

The SSH rule is created **before** ufw is enabled and before the lock, otherwise the run cuts itself
off from the machine. For the same reason the `bootstrap` role does not disable password login until
it has confirmed a valid key is in place.

### A locked site is the default state

A site must not be reachable, indexed or crawled before someone has looked at it. Krot provides the
mechanism only: `/etc/nginx/.htpasswd` (the password from the secret store at runtime) and the
`/etc/nginx/snippets/krot-auth.conf` snippet. **Which sites are locked is not decided by Krot** but
by the vhost generator: it includes the snippet while a site is not marked as published. This way
sites open one at a time rather than all at once.

### A major PostgreSQL version is not raised by changing a variable

`postgresql_version` is the version the role **installs**, not an upgrade of a running one.
PostgreSQL does not read the data directory of a previous major version, so raising the variable
installs a second cluster alongside. What follows goes unnoticed: `pg_createcluster` takes the first
port not occupied by an existing cluster (5433), the role's config declares 5432 — the new cluster
does not start, the application keeps working with the old one, and everything looks fine.

The role refuses to run alongside a cluster of a different version and names it. Removing the old
databases is possible only through an explicit `postgresql_remove_other_versions`: destroying data
must not be a side effect of editing a version number.

Clusters are identified through `pg_lsclusters` rather than through `/etc/postgresql` directories —
a package whose postinst failed to create a cluster (the port was taken) still leaves a config
directory behind.

### `shared_preload_libraries` is a list people fight over

PostgreSQL takes the last assignment as a whole and cannot append. The role therefore writes the
entire list at once from a variable: a future `auto_explain` added through a second config would
silently evict `pg_stat_statements`. When there is nothing to preload, the line is not written at
all — the parameter stays `default` rather than being pinned to `''`, which would overwrite someone
else's value.

### One deploy key cannot be used in two GitHub repositories

A machine pulling several private repos gets a key for each (`deploy_keys`) plus a host alias: clone
with `git@<name>.github.com:owner/repo.git`. Without the alias, ssh presents the first key that fits
and GitHub answers for the wrong repository.

### A run you cannot learn has failed

On busel an hourly job did not run once in five days. Its output went to `/var/log/`, where `km` has
no write permission: the redirection failed **before** PHP started, and the error message had
nowhere to land.

The defect is not the wrong path — a path is fixed in a minute. The defect is that there was no way
to learn about it: `journalctl -u cron` printed `(km) CMD (...)` every hour, because cron reports
that a line was **started** and does not know how it ended. There was no log, so there was nothing
to read, and a missing file is indistinguishable from "nothing written yet".

Hence the `cron` role and its transport: a systemd timer records the exit code, puts the output in
the journal under the unit's name, and surfaces failure in `systemctl --failed` — the command people
type when looking at a machine for the first time. Verified on busel: the same permission failure,
reproduced on the new mechanism, became visible three ways without sudo.

The jobs themselves are declared by the inventory. A role that knew the name `colony:traffic` would
stop being general by exactly the rule above.

What this does not fix: a job that returns 0 having done nothing stays green under any transport.
That is the job's responsibility, not the machine's.

**The unit file itself can fail just as silently**, which is why the role escapes the command on the
author's behalf. Measured on busel: `date +%Y-%m-%d` in `ExecStart` printed
`/etc/systemd/system-<machine-id>-/run/credentials/<unit>` and exited with code 0 — a `%` in a unit
file is a specifier and must be doubled. A single quote inside the command tears argv apart exactly
the way argument joining does in `ssh`: `-c` receives the first word, the rest goes to `$0` and
`$1`, the work is half done and the exit code is zero. The role closes both cases itself, because
both are precisely the failure it was written for.

### One log, one logrotate entry, or nothing rotates at all

The `nginx` role used to install `/etc/logrotate.d/krot-nginx` with the same glob as the packaged
nginx file. logrotate picks no winner: it prints `duplicate log entry`, exits with code 1 and
**processes not a single file on the machine** — php and postgresql, entirely uninvolved, stop
rotating too.

On busel this lasted three days and was only discovered through `systemctl --failed`. The duplicate
is determined by the resolved path rather than by the template text (verified by experiment: an
explicit `access.log` against `*.log` gives the same error), so a differently worded glob does not
help. The role now edits `rotate` in the packaged config and installs no file of its own.

What this shares with the previous point: the cost lay not in the breakage itself but in its being
visible only to a command nobody was typing.

### Validating a config in a temp directory does not work

The nginx template has no `validate:`: it would test the file from Ansible's temporary directory,
while nginx resolves relative includes (`fastcgi_params` in generated vhosts) relative to the config
file's own directory — a healthy config would fail. Instead there is `backup: true` plus a handler
that checks the assembled config in place and fails the run before a reload.

php-fpm is the opposite story: `reloaded` **silently succeeds** on a broken pool, so the handler runs
`php-fpm --test` first.

## Secrets

Through **Bitwarden at runtime** (`community.general.bitwarden`); there are no secrets in the
repository. Ansible Vault is not used. An unlocked `bw` is required before a run — otherwise a role
that needs a password fails honestly on an `assert` rather than installing an empty one.

Unlocking is not enough: **the token must be handed to the playbook through the environment**.

```bash
BW_SESSION="$(cat /tmp/bw-$USER/session)" ansible-playbook site.yml
```

The lookup plugin runs `bw` itself and knows nothing about the session cache, so without the variable
it sees the vault as locked and fails the run — even when `bw status --session` from that same cache
answers `unlocked`. The error then complains about the lock rather than the missing variable, and
sends you looking in the wrong place.

## Logs

Configured for collection (Loki/Alloy and the like), but no agent is installed — that is a separate
role.

- **nginx** — the format is set by the vhost generator; the package owns rotation, and the role edits
  only retention in its config and makes sure `conf.d` is included before the vhosts that depend on
  it.
- **php-fpm** — `/var/log/php/`: access with timings, slowlog with a stack trace, a separate error log.
- **postgresql** — csvlog, slow queries, `log_lock_waits`, `log_checkpoints`, plus
  `pg_stat_statements` for the queries that never cross the slow log's threshold.

- **periodic jobs** — the journal under the unit's name; a file only on an explicit `log_file`, and
  then the role writes an entry in `/etc/logrotate.d/` as well.

nginx and php are rotated through logrotate; PostgreSQL rotates itself. The `nginx` role edits the
packaged rotation config rather than installing a second one: two configs for one log bring
logrotate down entirely.

## Quality

```bash
yamllint .        # YAML formatting
ansible-lint      # the production profile — the strictest one
```

CI (`.github/workflows/lint.yml`) runs both on every PR, plus `ansible-galaxy collection build`.

All roles are idempotent: a repeat run yields `changed=0`. This is not a declaration — it is
verified by running against a live machine, and every role change is verified the same way.

The target platform is Ubuntu 24.04 (noble).
