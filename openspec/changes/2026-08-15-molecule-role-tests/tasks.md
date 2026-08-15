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
- [x] `molecule/` with a scenario per role: docker driver, noble platform, `privileged`,
      `cgroupns_mode: host`, cgroup mount
- [ ] First wave: `cron` (done), `firewall` (done, two scenarios), `nginx`, `postgresql`
- [x] **`firewall` needed two scenarios, not one.** Its branches configure the web ports in
      opposite ways — one opens 80/443 to everyone, the other closes them — so a single converge
      cannot exercise both. `firewall` covers the default, `firewall_cloudflare` the lock
- [x] **The Cloudflare branch is tested against a local HTTP server, not cloudflare.com.** A test
      that calls a third party reports that party's outage as a defect here; and the real ranges
      change without notice, so no assertion could name what the ruleset must contain. With a
      fixed list the scenario asserts exact rule counts — which is what catches a range that
      silently went missing. Ranges are RFC 5737 / RFC 3849 documentation blocks, so a rule that
      ever escapes points at addresses reserved for examples
- [ ] **Explicit variables in every scenario** wherever a default makes the role a no-op:
      `cron_jobs` with a job, `nginx_auth_enabled: true` with a test password (otherwise the
      `auth.yml` branch with its hand-written `rc == 10` idempotence never executes)
- [x] `converge.yml` and an `idempotence` run in every scenario
- [ ] Container cleanup that works **after a cancelled run** as well
- [x] A Molecule job in `.github/workflows/` — a separate job, so that a linter failure stays
      distinguishable from a role failure. It runs `molecule test --all`, so a new scenario
      directory is picked up without touching the workflow
- [x] **Add the `molecule` job to main's required status checks** — otherwise a red Molecule beside
      a green `lint` will not stop a merge, and the gate turns out decorative. Added after the job
      had passed twice on the runner: `contexts: ["lint","molecule"]`, `strict: true`,
      `enforce_admins: true`
- [x] A reach-counter script next to `wiki-index.py`: the share of roles with a scenario, the share
      of tasks, and a check that covered plus uncovered equals the contents of `roles/`
- [ ] README: a section on running the tests locally
- [ ] `.openspec.yaml` with `skip_specs: true` — so archiving does not need the flag
- [ ] `CHANGELOG.md` — decide how to version an infrastructure change: it alters no role, and role
      semver gives no answer for it

## Found by the scenarios (2026-08-15)

- [ ] **`firewall` uses `curl` without declaring it** — hygiene, not an outage. The refresh script
      calls `curl` while `meta/main.yml` has `dependencies: []` and the role installs nothing but
      ufw. The scenario hit it as a real failure (`curl: command not found`, then **"keeping
      current rules"** and exit 1), and the first conclusion drawn was that the weekly refresh
      would silently break on any host provisioned without `common`. **That conclusion was wrong,
      and review caught it:** curl ships in Ubuntu 24.04 itself — cloud image
      `8.5.0-2ubuntu10.11`, live-server `8.5.0-2ubuntu10.6`, verified against both manifests. What
      lacks curl is the Docker base image (`ubuntu:24.04` has none), so the failure was an
      artefact of the test environment. The undeclared dependency is still worth fixing, in its
      own change; the scenario installs curl in `prepare` to match a real host
- [x] The lesson worth more than the finding: **a container is not the machine.** A package
      missing from a minimal image reads exactly like a package the role forgot, and the
      difference is one manifest lookup away — which was not done before writing the conclusion
      down
- [x] **A scenario starting from a clean machine cannot test the lock at all.** Deleting the
      role's "close the web ports" tasks left the whole scenario green: on a host that was never
      open there is nothing for them to delete. `prepare` now opens 80/443 first, both by port and
      through the `Nginx Full` application profile — the state a machine is actually in when the
      lock is applied to it. Re-verified after the change: with the delete loop disabled the
      scenario fails and names both ports
- [x] The first break attempt was the misleading kind — it *looked* like the test had a hole. It
      did not; the break was unreachable from that starting state. Worth recording because the
      conclusion "the test does not catch it" was wrong for a reason easy to repeat

## Verification
- [x] `molecule test` green locally for `cron`, `firewall`, `firewall_cloudflare` — 7/7 actions
      each, idempotence included
- [ ] The second run yields `changed=0` inside the scenario, not only in the manual probe.
      A finding is separately expected in `postgresql`: `meta: flush_handlers` mid-role and
      `postgresql_ext` over a live connection make idempotence there questionable — which is
      exactly what Molecule is being introduced for
- [x] A deliberately broken role **fails** the scenario — checking the check: without this a green
      CI means nothing. Done per scenario, each break chosen to be one the role exists to prevent:
      `cron` — `ExecStart=-` swallowing a failure; `firewall` — port 443 dropped from the allow
      loop; `firewall_cloudflare` — the open-to-everyone rules left in place. In all three
      `converge` and `idempotence` stayed green while `verify` went red, which is the only
      arrangement that proves the checks read the machine rather than Ansible's report
- [ ] **A PR with a red Molecule does not merge** — verified in fact, not by the setting: that is
      the only proof the required check was added correctly
- [ ] The reach counter prints 4/11 roles and 76/117 tasks after the first wave — **2/11 and
      39/117 (33%)** with `cron` and `firewall` done. The counter maps scenario directories to
      roles by prefix, so `firewall_cloudflare` counts towards `firewall` rather than reading as
      an eleventh role that does not exist
- [ ] `wiki-lint.py` does not object to test values in `molecule/*/converge.yml` — it fails the
      build on strings that look like secrets, examples included
- [x] `yamllint`, `ansible-lint` clean on the Molecule files themselves — 0 failures. The
      `command-instead-of-module` warnings the verification files raise are left visible through
      `.ansible-lint-ignore` rather than silenced globally. The measured reason — the module's
      `status` is a snapshot taken before it acts — is written up on its own wiki page, which
      lands in a separate PR; until that merges, the explanation lives in the ignore file itself
- [ ] Molecule's run time in CI measured — the figure is needed before conclusions about it, not
      after

## Not done here
- `ansible-test` — nothing to check while there is no `plugins/` (reasoning in the proposal)
- pytest for `scripts/*.py` — its own change
- Checking the lockout in `bootstrap` — needs SSH transport, separate work
- The `postgresql_remove_other_versions: true` branch — a separate scenario
- The second wave (`common`, `fail2ban`, `php`) — after the first
