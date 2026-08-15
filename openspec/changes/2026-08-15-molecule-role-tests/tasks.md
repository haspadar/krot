# Tasks: a role meets reality for the first time in production

## Measured (locally, 2026-08-15, Docker 29.7.2)
Probe containers brought up and removed; image `geerlingguy/docker-ubuntu2404-ansible`,
`--privileged --cgroupns=host`, `/sys/fs/cgroup:rw`.

- [x] The OS in the container is Ubuntu **24.04.4 LTS (Noble Numbat)**, krot's target platform
- [x] systemd came up: `systemctl is-system-running` -> **`running`**, version **255**
      (`255.4-1ubuntu8.16`) — the same one the measurements in `wiki/operations/` were taken on
- [x] Role `cron` run through `connection: community.docker.docker` with a single job:
      **`ok=11 changed=3`**, `.service` and `.timer` installed, the `Reload systemd` handler fired
- [x] **Second run: `ok=10 changed=0`** — idempotence measured inside a container, without a live
      machine. This is the acceptance criterion for the whole undertaking
- [x] The timer exists in fact rather than in Ansible's output: `systemctl is-enabled
      krot-probe-job.timer` -> `enabled`, a line in `list-timers` with a next start
- [x] **ufw works inside the container** (checked because the opposite was expected):
      `ufw enable` -> active, `iptables -L INPUT -n` -> **`policy DROP`** and the
      `ufw-before-input` chain. That is why `firewall` goes into the first wave
- [x] Cycle timings on the `cron` role (it installs no packages): bringing the container up **2s**,
      `converge` **21s**, the second run **19s**. Roles with external repositories were not
      measured — their time gets measured when their scenario is written, not predicted
- [x] **Tasks in the repository: 117 across 11 roles.** First wave (`cron`, `firewall`, `nginx`,
      `postgresql`) — 76 tasks; second (`common`, `fail2ban`, `php`) — 17; uncovered
      (`bootstrap`, `deploy`, `deploy_keys`, `docker`) — 24. The sum adds up: 11/11 and 117/117
- [x] **Molecule does not count coverage** — not a unit-test framework, no coverage mechanism at
      all. `ansible-test coverage` exists but measures the Python code of modules and plugins, of
      which krot has none. Hence a reach counter of our own rather than a borrowed metric
- [x] **The required status check on main's protection is the string `lint`** (a job name):
      `gh api repos/haspadar/krot/branches/main/protection` -> `contexts: ["lint"]`,
      `strict: true`, `enforce_admins: true`, force-push forbidden. A new job **will not become
      required on its own**
- [x] Cleaned up: `docker rm -f`, no probe containers left behind

## Work
- [ ] `molecule/` with a scenario per role: docker driver, noble platform, `privileged`,
      `cgroupns_mode: host`, cgroup mount
- [ ] First wave: `cron`, `firewall`, `nginx`, `postgresql`
- [ ] **Explicit variables in every scenario** wherever a default makes the role a no-op:
      `cron_jobs` with a job, `nginx_auth_enabled: true` with a test password (otherwise the
      `auth.yml` branch with its hand-written `rc == 10` idempotence never executes)
- [ ] `converge.yml` and an `idempotence` run in every scenario
- [ ] Container cleanup that works **after a cancelled run** as well
- [ ] A Molecule job in `.github/workflows/` — a separate job, so that a linter failure stays
      distinguishable from a role failure
- [ ] **Add the `molecule` job to main's required status checks** — otherwise a red Molecule beside
      a green `lint` will not stop a merge, and the gate turns out decorative
- [ ] A reach-counter script next to `wiki-index.py`: the share of roles with a scenario, the share
      of tasks, and a check that covered plus uncovered equals the contents of `roles/`
- [ ] README: a section on running the tests locally
- [ ] `.openspec.yaml` with `skip_specs: true` — so archiving does not need the flag
- [ ] `CHANGELOG.md` — decide how to version an infrastructure change: it alters no role, and role
      semver gives no answer for it

## Verification
- [ ] `molecule test` green locally for every role with a scenario
- [ ] The second run yields `changed=0` inside the scenario, not only in the manual probe.
      A finding is separately expected in `postgresql`: `meta: flush_handlers` mid-role and
      `postgresql_ext` over a live connection make idempotence there questionable — which is
      exactly what Molecule is being introduced for
- [ ] A deliberately broken role **fails** the scenario — checking the check: without this a green
      CI means nothing
- [ ] **A PR with a red Molecule does not merge** — verified in fact, not by the setting: that is
      the only proof the required check was added correctly
- [ ] The reach counter prints 4/11 roles and 76/117 tasks after the first wave
- [ ] `wiki-lint.py` does not object to test values in `molecule/*/converge.yml` — it fails the
      build on strings that look like secrets, examples included
- [ ] `yamllint`, `ansible-lint` clean on the Molecule files themselves
- [ ] Molecule's run time in CI measured — the figure is needed before conclusions about it, not
      after

## Not done here
- `ansible-test` — nothing to check while there is no `plugins/` (reasoning in the proposal)
- pytest for `scripts/*.py` — its own change
- Checking the lockout in `bootstrap` — needs SSH transport, separate work
- The `postgresql_remove_other_versions: true` branch — a separate scenario
- The second wave (`common`, `fail2ban`, `php`) — after the first
