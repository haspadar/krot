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
- [x] First wave complete: `cron`, `firewall` (two scenarios), `nginx` (two scenarios),
      `postgresql`
- [x] **`firewall` needed two scenarios, not one.** Its branches configure the web ports in
      opposite ways — one opens 80/443 to everyone, the other closes them — so a single converge
      cannot exercise both. `firewall` covers the default, `firewall_cloudflare` the lock
- [x] **The Cloudflare branch is tested against a local HTTP server, not cloudflare.com.** A test
      that calls a third party reports that party's outage as a defect here; and the real ranges
      change without notice, so no assertion could name what the ruleset must contain. With a
      fixed list the scenario asserts exact rule counts — which is what catches a range that
      silently went missing. Ranges are RFC 5737 / RFC 3849 documentation blocks, so a rule that
      ever escapes points at addresses reserved for examples
- [x] **Explicit variables in every scenario** wherever a default makes the role a no-op:
      `cron_jobs` with a job, `nginx_auth_enabled: true` with a test password (otherwise the
      `auth.yml` branch with its hand-written `rc == 10` idempotence never executes). One more
      case turned up while writing the nginx scenario, and it is the sharper one: the package
      ships `rotate 14`, which is also the role's default — running on defaults would leave the
      file byte-identical whether the role edited it or did nothing, so the scenario asks for 21
- [x] `converge.yml` and an `idempotence` run in every scenario
- [x] Container cleanup that works **after a cancelled run** as well — `molecule destroy -s <name>`,
      verified against the actual case: a container left by an interrupted `create` is removed and
      `docker ps -a` comes back empty. `docker rm -f krot-<name>` is the blunt fallback. Both are
      in the README section, because the fast loop while writing a scenario is `converge` once and
      `verify` repeatedly, and that deliberately leaves the machine up
- [x] A Molecule job in `.github/workflows/` — a separate job, so that a linter failure stays
      distinguishable from a role failure. It runs `molecule test --all`, so a new scenario
      directory is picked up without touching the workflow
- [x] **Add the `molecule` job to main's required status checks** — otherwise a red Molecule beside
      a green `lint` will not stop a merge, and the gate turns out decorative. Added after the job
      had passed twice on the runner: `contexts: ["lint","molecule"]`, `strict: true`,
      `enforce_admins: true`
- [x] A reach-counter script next to `wiki-index.py`: the share of roles with a scenario, the share
      of tasks, and a check that covered plus uncovered equals the contents of `roles/`
- [x] README: a section on running the tests locally — install, `test --all`, the
      `converge`/`verify` loop that leaves the container up, and cleanup after a cancelled run.
      Says plainly that a scenario is worth only what it catches, and that every one here was
      checked by breaking its role
- [x] `.openspec.yaml` with `skip_specs: true` — so archiving does not need the flag. The format
      was measured rather than guessed: `schema:` is required for the marker to be honoured, and
      `spec-driven` is the only schema openspec 1.9.0 ships. With `schema: change` validation
      fails with "unknown schema 'change'" and silently ignores skip_specs. `openspec validate`
      now passes on this change with no `specs/` at all
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

### Found while writing the nginx and postgresql scenarios (2026-08-15)

- [x] **A check that passed on a machine the role never touched.** `nginx -T` prints every file
      verbatim, comments included, and the packaged nginx.conf carries `# server_tokens off;`.
      A substring test for `server_tokens off` therefore passed on a container with the untouched
      package config — measured. Now matched as a directive at the start of a line. The same trap
      the retention value avoided (14 vs 21), missed one line away from it
- [x] **A scenario starting from a clean machine cannot tell `restart` from `reload`.** On a bare
      host the package creates the cluster, the role writes 99-krot.conf, and the server starts
      afterwards — reading the finished file on its first boot. Swapping the handler's
      `state: restarted` for `reloaded` left the whole scenario green. On a machine that is
      already running, the difference is exactly what the handler's comment claims: measured,
      `max_connections` stayed 123 in effect while the file said 177, and a restart applied it.
      `prepare` now installs and starts the cluster before the role runs, and with that the
      reload break is caught
- [x] **The repository's own secret detector never looked at `molecule/`.** wiki-lint has carried
      secret patterns since the wiki was set up, and its regex matches this scenario-only
      value (secret-lint: allow — quoted here as the example that made the gap visible)
      `nginx_auth_password: molecule-scenario-only` exactly — but it walks `wiki/**/*.md` and
      nothing else. So the first hardcoded credential in this repository's history landed in the
      one directory nothing was watching. Added `scripts/secret-lint.py`, which imports the same
      patterns (two lists drift apart) and runs them over everything git tracks, with an explicit
      `secret-lint: allow` marker for the throwaway value. Verified both ways: the marked line
      passes, an unmarked `db_password: ...` fails the run
- [x] **The built collection carried 5462 entries, of which 5283 had no business being there** —
      `collections/` (a vendored copy of other people's collections), `CLAUDE.md` (instructions
      for an agent working ON this repository) and `.ruff_cache`. All three are in `.gitignore`,
      which `ansible-galaxy` does not read, and the CI build step only checks that the build
      succeeds. Added to `build_ignore`; the tarball is now 179 entries

## Verification
- [x] `molecule test` green locally for `cron`, `firewall`, `firewall_cloudflare`, `nginx`,
      `nginx_auth` — 7/7 actions each, idempotence included
- [x] The second run yields `changed=0` inside the scenario, not only in the manual probe.
      **The finding expected in `postgresql` did not materialise:** `meta: flush_handlers`
      mid-role and `postgresql_ext` over a live connection were predicted to break idempotence,
      and they do not — the second run is clean. Recorded because a prediction that failed is
      worth as much as one that held: the reasoning behind it was plausible and wrong
- [x] A deliberately broken role **fails** the scenario — checking the check: without this a green
      CI means nothing. Done per scenario, each break chosen to be one the role exists to prevent:
      `cron` — `ExecStart=-` swallowing a failure; `firewall` — port 443 dropped from the allow
      loop; `firewall_cloudflare` — the open-to-everyone rules left in place; `nginx` — the
      duplicate logrotate config left behind; `nginx_auth` — the htpasswd never rewritten, so an
      old password keeps working; `postgresql` — the handler reloading instead of restarting, so
      a postmaster-level setting stays in the file and never reaches the server. In all six
      `converge` and `idempotence` stayed green while `verify` went red, which is the only
      arrangement that proves the checks read the machine rather than Ansible's report
- [ ] **A PR with a red Molecule does not merge** — verified in fact, not by the setting: that is
      the only proof the required check was added correctly
- [x] The reach counter prints **4/11 roles and 76/117 tasks (64%)** after the first wave —
      exactly the figure this change set as the target. The counter maps scenario directories to
      roles by prefix, so `firewall_cloudflare` counts towards `firewall` rather than reading as
      an eleventh role that does not exist
- [x] `wiki-lint.py` does not object to test values in the scenarios — checked with
      `nginx_auth_password` present in `molecule/nginx_auth/molecule.yml`: 18 pages, no errors.
      The linter reads `wiki/` only, so scenario files are outside its reach entirely; the value
      is a throwaway for a container destroyed at the end of the run and guards nothing
- [x] `yamllint`, `ansible-lint` clean on the Molecule files themselves — 0 failures. The
      `command-instead-of-module` warnings the verification files raise are left visible through
      `.ansible-lint-ignore` rather than silenced globally. The measured reason — the module's
      `status` is a snapshot taken before it acts — is in
      `wiki/research/systemd-service-status-is-stale.md`, with the probe as a runnable asset
- [ ] Molecule's run time in CI measured — the figure is needed before conclusions about it, not
      after
- [x] **Second review found four things in the postgresql scenario, all confirmed by measurement.**
      One was a live regression: quoting the scenario's throwaway password (secret-lint: allow —
      the value itself is quoted, marked, a few items above)
      in the prose of this very file tripped `secret-lint.py`, the linter the same commit adds — the
      item describing the escape marker had not applied it, so CI would have gone red on the
      commit claiming CI was green. `log_destination` was selected in verify's query and missing
      from its assert loop, checking nothing; added, and it is meaningful — without the drop-in
      the server answers `stderr`. The apt check carried three clauses of which one worked:
      measured all three failure modes on noble (duplicate source, garbage keyring, missing
      keyring) and every one exits 100, while `is misconfigured` is emitted by none of them —
      cut to the exit code, with the measurements written down. And the restart-vs-reload guard
      rests on exactly two of the eight settings read back, because the other six are either
      SIGHUP-applied or already at the asked-for value; that was true but written nowhere, so
      deleting one host_var would have silently disarmed the scenario. Noted in both files.
      Re-verified after the changes: 7/7 green, and swapping `restarted` for `reloaded` still
      fails verify on `max_connections` with converge and idempotence clean

## Not done here
- `ansible-test` — nothing to check while there is no `plugins/` (reasoning in the proposal)
- pytest for `scripts/*.py` — its own change
- Checking the lockout in `bootstrap` — needs SSH transport, separate work
- The `postgresql_remove_other_versions: true` branch — a separate scenario
- The second wave (`common`, `fail2ban`, `php`) — after the first
