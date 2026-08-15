# Proposal: application periodic jobs are a property of the machine

## Why

On busel the hourly `colony:traffic` job **did not run once in five days**, and this was
invisible from both sides.

```
17 * * * * cd /var/www/busel/current && APP_ENV=prod /usr/bin/php bin/console colony:traffic >> /var/log/busel-traffic.log 2>&1
```

`/var/log` is `root:syslog`, `drwxr-xr-x`; `km` has no write access there. The redirection fails
**before** PHP starts, so the error message has nowhere to land: the file
`/var/log/busel-traffic.log` does not exist at all. The command itself is sound — a manual run as
`km` finished with code 0 and backfilled the missed days.

Why nobody noticed for five days — three independent layers of silence:

- `journalctl -u cron` cheerfully prints `(km) CMD (...)` every hour: cron honestly reports that
  it **started** the line, and knows nothing about how it ended;
- there is no log — so there is nothing to read, and a missing file is indistinguishable from
  "hasn't written yet";
- the data simply stops updating, which you only find out by looking into the table.

The point here is not "wrong path". A wrong path is a typo, a minute of work. The defect is that
**five days of green runs with zero result looked normal**, and no command you would type while
looking at the machine would have said otherwise.

### Why this is a krot defect, not a busel one

The cron entry was created by hand via `crontab -e`. It is neither in krot nor in the busel
repository. Hence:

- it will not survive a machine rebuild;
- it will not appear on the next server, and busel is a site factory, there will be more servers;
- it is found only through `crontab -l` under the right user — that is, unknown to anyone who
  does not know what to look for and under whom;
- there is no rotation: `/etc/logrotate.d/` holds `krot-nginx` and `krot-php`, but no
  `busel-traffic`.

Krot did not break this; krot simply does not do it. It sets up neighbouring services together
with their logs and rotation — application periodic jobs fell out of that row.

### What turned up along the way: the same defect had already fired on logrotate

While checking the machine (2026-08-13) `systemctl --failed` showed:

```
● logrotate.service loaded failed failed Rotate log files
```

For the third day in a row, starting on 11 August:

```
error: nginx:1 duplicate log entry for /var/log/nginx/access.log
error: found error in file nginx, skipping
```

The `nginx` role drops `/etc/logrotate.d/krot-nginx` with the glob `/var/log/nginx/*.log`, while
the stock package `/etc/logrotate.d/nginx` declares the very same glob. logrotate treats this as
a configuration error and **exits with code 1 without processing a single file** — including
`krot-php`, postgresql and everything else on the machine.

This is the same class of failure as in the assignment, and it confirms the choice of transport
below: the "own file + own logrotate" path on this machine is **already broken**, and broken
silently. Fixed within this same change (see "Impact").

## What Changes

### New role `cron`

It does not belong in `common`: the jobs have their own variable, their own list, their own unit
templates and their own tag for `--tags`. `common` is hostname, timezone and base packages;
application jobs would be alien there. It does not belong in `deploy` either: that one is a
deliberately thin wrapper over the project's Deployer.

The role knows about the **mechanism of periodic jobs**, but not about `colony:traffic`. The list
is an inventory variable:

```yaml
# busel: group_vars/all.yml
cron_jobs:
  - name: traffic
    description: Visitor figures for every site, copied out of Analytics
    command: bin/console colony:traffic
    schedule: hourly
    working_directory: "{{ busel_deploy_path }}/current"
    environment:
      APP_ENV: prod
```

The next server will declare its own. Krot knows nothing about the name `colony:traffic`.

### systemd timers instead of cron

The output transport is the journal, and that follows from the requirement "output must not
depend on file permissions", not from taste. What the replacement buys, verified on a live
machine:

| | cron today | systemd timer |
|---|---|---|
| where output goes | into a file there are no rights for | into the journal, no rights needed |
| is the exit code visible | no | `Main PID: … (code=exited, status=3)` |
| is a failure visible without knowing the path | no | `systemctl --failed` |
| rotation | its own, which nobody wrote | system-wide, already working |
| survives a machine rebuild | no | yes, the role installs it again |

Verified as `km` without sudo on busel (2026-08-13): a system unit with `User=km` writes stdout
and stderr to the journal, and `journalctl -u <unit>` **shows** them — despite `km` belonging to
neither `adm` nor `systemd-journal`. Entries from `systemd[1]` itself (`Deactivated successfully`)
are not visible, but the process's own lines are, because the process belongs to `km`. The full
picture is given by `systemctl status <unit>`, also without sudo: it takes the exit code not from
the journal.

That is, the requirement "output is found without knowing the path to a file" is met literally:
the unit name is derived from the job name, and the list of units is printed by
`systemctl list-timers 'krot-*'`.

File output remains possible (`log_file`), but **not by default** — and then the role creates the
file with the right owner and writes `/etc/logrotate.d/`, because half of that pair reproduces
exactly the original defect.

### `APP_ENV=prod` is not lost in the move

In the existing cron entry this is written with a reason, and the reason is preserved in the
role's defaults: cron carries no environment, without the variable dev comes up, accumulates
request logs and on a long sync ran into memory. systemd has exactly the same trait — a unit
starts with an empty environment — so variables are not "inherited", they are declared explicitly
via `Environment=`.

### The minute is not 0 — and now that is not the job author's concern

In cron the minute 17 was picked by hand so as not to collide with the machine's other hourly
jobs. The idea is preserved but carried out more reliably: `RandomizedDelaySec` spreads the jobs
out by itself, and `schedule: hourly` expands into `OnCalendar=*-*-* *:00:00` with an offset.
Whoever adds a second job no longer needs to remember which minutes are already taken — and that
is exactly the kind of knowledge that is lost first.

An explicit minute is available too: `schedule` accepts any `OnCalendar` expression.

### The command is escaped by the role, not by the inventory author

Discovered in review and confirmed by measurement: a unit file can fail just as quietly as the
original cron entry.

- **`%` is a systemd specifier.** `date +%Y-%m-%d` in `ExecStart` printed
  `/etc/systemd/system-<machine-id>-/run/credentials/<unit>` and exited **with code 0**. The role
  doubles `%`.
- **A single quote tears argv apart.** `--msg='hi there'` is for systemd not an opening quote but
  a literal one, so `-c` takes the first word and the rest goes into `$0` and `$1` — the same
  mechanism as when arguments are glued together in `ssh`, with the same signature: half the work
  done, code 0. The role quotes the command with the `quote` filter.
- **A quote in `Environment=`** made systemd discard the assignment with the entry
  `Ignoring invalid environment assignment` — the unit started **without the variable**. That is
  exactly the way of losing `APP_ENV` that requirement #2 protects against.

In the inventory you write an ordinary string; the job author does not need to know about
doubling and quoting.

### Silent failure becomes noticeable

There are three levels here, and the first two are part of this change:

1. **The exit code is recorded.** An unsuccessful run leaves the unit in `failed`, and that is
   visible in `systemctl --failed` — the command you type when first looking at a machine, not
   knowing the job exists. Today there is no such command at all.
2. **`Persistent=true`.** A machine switched off at the moment of firing catches up on the miss at
   start, instead of silently losing an hour.
3. **"Did not run N times in a row" — proposed, but not implemented** (see below).

## Impact

- **The existing cron entry on busel is not touched by hand.** The role declares
  `krot-<name>.timer`; the manual line is removed by a run, not by `crontab -e`. The role removes
  from the user's crontab only lines it did not put there itself — see tasks.md, the item about
  migration: by default it does **not** do this, so that a run does not carry off someone else's
  job it knows nothing about.
- **On busel the moment of firing changes.** It was `17 * * * *`, it becomes the hour with a
  random offset. For a job whose interval is dictated by the source (Analytics returns at most the
  previous hour) this is immaterial.
- **`logrotate.service` gets fixed.** The `nginx` role stops duplicating the package glob:
  `krot-nginx` is removed, and `nginx_log_retention_days` is applied by editing the `rotate` line
  in the package file. A drop-in is impossible here: logrotate allows exactly one entry per log
  and on a duplicate stops processing for the whole machine. The run fails if there is nothing to
  edit — appending the line is not allowed: past the closing brace it is silently discarded, and
  rotation proceeds **with no retention at all**.
- **The role is general.** matilda will get the same mechanism by declaring its own list; there is
  nothing busel-specific in the role.
- **Requires systemd ≥ 236** (`RandomizedDelaySec`, `Persistent`). On the target Ubuntu 24.04 it
  is systemd 255, verified.

## Out of scope

**"The command did not run N times in a row".** There is a cheap way, and it requires neither
monitoring nor an agent: `OnFailure=` on the job's unit pointing at a shared
`krot-job-failed@.service`, which writes to the journal under a separate tag and/or touches a
marker file in `/var/lib/krot/`. Then `systemctl --failed` catches a single failure, while the
marker accumulates a streak.

It is not implemented in haste, for the reason given in the assignment: this has an addressee, and
the addressee has not been chosen. A notification with nobody to read it is one more silent
failure, only with more code. While there is no addressee, `systemctl --failed` covers the main
gap: today a failure is visible through **nothing at all**, after the change it is visible through
a standard command.

It is worth noting separately that even this would not fully cover the original case: a command
that finished with code 0 but did no work stays green. The answer to that lies not in krot but in
the job itself: it must fail when it has not done what it was started for.
