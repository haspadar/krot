# Proposal: a role meets reality for the first time in production

## Why

Idempotence is declared a mandatory property of all eleven roles — CLAUDE.md says "a repeat run
yields `changed=0`", and then: "verified by running against a live machine". The second half of that
sentence is the defect. The only machine where a role is verified is a working one: busel serves
sites, matilda runs Docker Compose. The first answer to "does this role work at all?" arrives from
where a mistake costs the most.

What CI carries today, and what it does not answer:

| Check | The question it answers |
|---|---|
| `yamllint`, `ansible-lint` (production) | the syntax and style are correct |
| `ansible-galaxy collection build` | the collection builds and installs for a consumer |
| `wiki-lint`, `wiki-index` | the documentation has not drifted from the roles |

None of them runs a role. `ansible-lint` does not know whether a package will install, whether a unit
will start, or whether a second run yields `changed=0` — it reads YAML rather than executing it.
Between "the file is written correctly" and "the machine reached the required state" lies the whole
class of failures the roles are written for.

It is the same class `wiki/operations/silent-failures.md` is devoted to: exit code zero, work not
done. The `cron` role already contained such a defect inside itself — `AssertPathIsDirectory=`
promised a loud failure and silently skipped the job (change `2026-08-13-cron-assert-silent-skip`).
It was found by hand, on a live machine, after some time had passed.

### Measured: a krot role runs to completion inside a container

Verified locally on 2026-08-15, not inferred from documentation. Image
`geerlingguy/docker-ubuntu2404-ansible`, Docker 29.7.2, `--privileged --cgroupns=host`, with
`/sys/fs/cgroup` mounted:

| What was checked | Result |
|---|---|
| OS | Ubuntu **24.04.4 LTS (Noble Numbat)** — the target platform |
| systemd | **`running`**, version **255** — the same one every measurement in the wiki was taken on |
| role `cron`, first run | `ok=11 changed=3`, unit and timer installed |
| role `cron`, second run | **`ok=10 changed=0`** — idempotence measured rather than declared |
| the timer itself | `enabled`, present in `list-timers` with a next start |

The `daemon-reload` handler ran too, so systemd in the container is not decorative.

The firewall was checked separately, because "ufw does not work in a container" is a common belief
and it is wrong for privileged mode:

| What was checked | Result |
|---|---|
| `ufw enable` | `Firewall is active and enabled on system startup` |
| `ufw status verbose` | `active`, `deny (incoming)` |
| rules in the kernel (`iptables -L INPUT -n`) | **`policy DROP`**, the `ufw-before-input` chain and the rest |

The rules land in netfilter for real, which is why `firewall` goes into the first wave rather than
the uncovered list.

The timings of one cycle were measured there too: bringing the container up **2s**, `converge`
**21s**, the second run **19s**. That is the `cron` role, which installs no packages; roles with
external repositories (`postgresql` from pgdg, `php` from ondrej, `nginx`) will be noticeably
slower — their time gets measured when their scenario is written, not predicted here.

## What Changes

Molecule is introduced — a scenario per role that brings up a noble container, runs the role
(`converge`), runs it a second time (`idempotence`) and cleans up after itself.

Molecule, not `ansible-test`. This is not a choice between two equals: `ansible-test` tests the
contents of collections **as Python code** — sanity, unit and integration tests for modules and
plugins. krot has none of those: eleven roles in YAML and not a single `plugins/`.
`validate-modules` stays silent without modules, and the rest is already covered by the
`ansible-lint` + `collection build` pair in CI. Molecule, by contrast, checks a role's behaviour on
a machine — the one thing nothing checks today. It is community-maintained inside the `ansible/`
organisation under Ansible by Red Hat, its latest release is from 12.08.2026, and it supports N/N-1
major Ansible versions; for roles it has no competitor.

### All eleven roles named explicitly

A list with no remainder — otherwise it does not do its job. The sum of the three columns equals the
contents of `roles/`, and that is checked by a script (see below).

| Wave | Roles | Tasks | Why |
|---|---|---|---|
| **First** | `cron`, `firewall`, `nginx`, `postgresql` | 76 | a silent failure already happened, or measurement showed it is checkable |
| **Second** | `common`, `fail2ban`, `php` | 17 | no obstacles, but less urgency |
| **Not covered** | `bootstrap`, `deploy`, `deploy_keys`, `docker` | 24 | reasons below, one per role |

`bootstrap` is deliberately placed among the uncovered, though the temptation was the opposite. The
role closes password login and edits sshd — that is, its characteristic failure is "locking yourself
out". Inside a container Molecule connects through `community.docker.docker`, **bypassing sshd**, so
a broken `99-krot.conf` would pass unnoticed: the scenario would be green in exactly the case it is
needed for. There is nothing to check here until the transport is SSH; that is separate work.

`deploy` runs Deployer from the control machine, `deploy_keys` works with private repositories, and
`docker` installs Docker inside a container. Their scenarios are either meaningless or require a
separate conversation.

### Coverage is counted, because Molecule does not count it

**Molecule has no coverage mechanism** — it is not a unit-test framework; it checks the state of a
machine, not the execution of lines. `ansible-test coverage` exists, but it measures coverage of the
Python code of modules and plugins, of which krot has none. Neither of the two yields the familiar
"N% covered" metric.

So a reach counter of our own is introduced: the share of roles with a scenario and the share of
tasks living in them. A task is a `- name:` line under `roles/<role>/tasks/`. The repository
currently holds **117 tasks across 11 roles**, with a reach of **0/11 roles and 0/117 tasks**. After
the first wave — 4/11 roles and 76/117 tasks (64%). The script lives next to `wiki-index.py`, a
genre the repository already has, and it also watches that the sum of the covered and uncovered
lists equals `roles/`.

This is reach, not code coverage, and it must be called that. It answers "which roles are checked at
all", but not "which branches inside a role executed".

### The quality of a scenario is not measured by a number

The only honest check: deliberately break a role and confirm the scenario turns red. Without it a
green Molecule means nothing, and no percentage substitutes for it. It stands in `tasks.md` as a
separate item.

The second condition of quality is **the scenario's variables**. On defaults `cron_jobs` is empty and
the role becomes a no-op: `converge` would pass while nothing was checked — the same "exit code 0,
work not done", only inside a test. Each scenario sets its variables explicitly, and wherever a
default nulls the role (`cron_jobs`, `nginx_auth_enabled`, `postgresql_remove_other_versions`), it is
overridden.

### The objection "Docker was rejected in production" — dismissed

ARCHITECTURE.md words the decision narrowly: "**Docker is NOT used in busel production**", and the
reasoning there is about the application's runtime on a live machine. Docker as an ephemeral test
bed in CI has nothing to do with that decision: it never reaches a production machine and does not
compete with Ansible for the role of deployment mechanism. The collection also contains a `docker`
role for matilda — Docker is not forbidden in the project as such. Recorded here so the objection
does not resurface at every review.

## Impact

- **Idempotence stops being discipline and becomes a gate.** Today `changed=0` is a promise in
  CLAUDE.md that nobody can check; afterwards it is a step that fails CI.
- **A role meets reality before production.** Package, unit, permissions and template are checked on
  a clean noble rather than on a machine serving sites.
- **Molecule on its own will not block a merge.** The required status check on main's protection is
  the string `lint` — that is a job name. A new `molecule` job will **not** enter the required list
  automatically: a red Molecule beside a green `lint` will not stop a merge. It has to be added to
  `contexts` by hand, otherwise the gate turns out to be decorative exactly when it fires.
- **CI gets slower, and nothing compensates for it.** Running a role takes minutes against today's
  49-second median, multiplied by the number of scenarios. For a public repository that is not money
  (Actions minutes are free), but it is waiting time on every PR.
- **A dependency on external networking appears on every run.** `postgresql` pulls a key and packages
  from pgdg, `php` from ondrej. The slowest and most brittle scenarios of the set.
- **A dependency on Docker appears** in CI and locally. On a GitHub runner it is there by default.
- **A cancelled run leaves containers behind.** Molecule takes minutes, and `cancel-in-progress` may
  kill it halfway — cleanup has to work after a cancellation too.

## Out of scope

- **`ansible-test`.** Reasoning above: there is nothing to check while krot has no `plugins/`. Once
  there is a filter, lookup or module of our own, sanity and units will stand beside Molecule, and
  that will be a separate decision rather than an extension of this one.
- **pytest for `scripts/*.py`.** Four wiki scripts, two of which — `wiki-lint.py` and
  `wiki-index.py` — serve as CI gates themselves, meaning CI trusts unverified code. The defect is
  real and of the same kind, but it is cured by ordinary pytest rather than by Molecule, and it lives
  in its own change.
- **Checking the lockout in `bootstrap`.** Requires SSH transport in the scenario — separate work
  with its own justification.
- **The `postgresql_remove_other_versions: true` branch.** The most dangerous one in the role (it
  destroys data) and the subtlest — with the `pg_createcluster --creates` fallback on a taken port.
  It is checkable by a scenario that installs PG 16 and then runs the role with version 18, but that
  is a separate scenario and a separate conversation about what to do with what it finds.
