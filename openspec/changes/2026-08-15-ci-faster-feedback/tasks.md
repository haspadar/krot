# Tasks: CI waits longer than it works

## Measured (`gh run list`, 2026-08-15, window 2026-07-30 … 2026-08-15)

- [x] **krot is public**: `gh api repos/haspadar/krot` -> `private: false`. Actions minutes for
      public repositories are free — the change's original premise about quota spend is
      **refuted**. The private ones are busel and matilda, and that is where saving belongs
- [x] 65 runs over 17 days, 64 success / 1 failure
- [x] Duration: min 37s, **median 49s**, max 120s; 3419s in total
- [x] By event: `pull_request` 43, `push` 22
- [x] **20 repeat runs, but only 2 actually overlapped in time.** Counted from
      `startedAt`/`updatedAt` within each branch: `concurrency` would have cancelled **58 seconds
      out of 3419 (1.7%)**, not 31% as the first revision stated. Gaps between pushes are hundreds
      of seconds, twice more than a day; at a 49s median there is nothing to cancel
- [x] Step breakdown of the last run: `Install linters` **8s**, `Install collections` **8s**,
      `ansible-lint` 15s, the rest 0–1s. **16s out of 34s is installing dependencies**. The job's
      steps sum to 34s while the run's wall clock is 39s — different metrics; the 49s median is
      computed from the second
- [x] There is spread: on an adjacent run `Install collections` took 16s rather than 8s
- [x] **Main's protection is firmer than the first revision claimed**:
      `gh api repos/haspadar/krot/branches/main/protection` -> `strict: true`,
      `enforce_admins: true`, `allow_force_pushes: false`, `allow_deletions: false`,
      contexts `["lint"]`. There is no direct path into main for anyone, the owner included
- [x] busel for comparison: `protected: false`; `push: [main]` was removed there in `b04867e` and
      **restored** in `6cac47c` precisely because protection is absent — its current workflow
      cannot be copied into krot blindly
- [x] busel's `paths-ignore` is not carried over: krot's CI reads `wiki/` (`wiki-lint.py` plus the
      `wiki/index/` reconciliation), and wiki pages are `.md`

## Measured again, after Molecule landed (run 31960857886, 2026-08-16)

- [x] The premise of the "16s out of 34s" breakdown is **superseded, not refuted**: it described
      a run without Molecule. `lint` still takes 1m4s, but the run now waits on `molecule`, which
      took **14m7s** — the dependency install it was about is no longer what anyone waits for
- [x] Per scenario, from the `[<scenario> > <action>]` markers in the job log: nine scenarios,
      **783s in total**, slowest `firewall_cloudflare` **136s**, fastest `fail2ban` 61s. The other
      seven: common 90, php 90, postgresql 101, cron 80, firewall 68, nginx 78, nginx_auth 77
- [x] `molecule test --all` runs them **sequentially in one job**, so the wait is the sum. One job
      per scenario makes it the maximum instead: **~136s plus the install steps** rather than 14m
- [x] Container names differ per scenario (`krot-common`, `krot-firewall-cf`, …) and each matrix
      leg gets its own runner, so nothing is shared to collide over

## Work
- [x] `cache: pip` in `actions/setup-python` — in both jobs
- [x] A cache of the collections directory keyed on the hash of `requirements.yml`; the Molecule
      job keys on both requirements files, since a scenario needs the driver's collections too
- [x] `concurrency` grouped by `ref` with `cancel-in-progress: true`
- [x] A comment in the workflow: `concurrency` is introduced in advance for Molecule, its
      contribution today is 1.7% — so the next reader does not mistake it for a savings measure
- [x] **One job per scenario instead of `--all`** — not in the original plan, added once Molecule
      made the wait 14 minutes. The matrix is read from `molecule/` by a preceding `scenarios`
      job rather than listed in the workflow: a hand-kept list is edited twice when a scenario is
      added, and a forgotten entry means the scenario never runs while CI stays green
- [x] `fail-fast: false`, so one red scenario does not hide the state of the other eight
- [x] `.openspec.yaml` with `skip_specs: true` — already present
- [x] `CHANGELOG.md` — **decided: no entry and no version bump.** The changelog is read by whoever
      installs the collection, and `galaxy.yml`'s `build_ignore` keeps `.github` out of the
      artefact: nothing here reaches a consumer, so a version bump would announce a change they
      cannot observe. CI arrangements are recorded in the wiki instead

## Verification
- [ ] The cache takes effect on the second run: the install steps are faster than 8s
- [ ] Changing `requirements.yml` **invalidates** the collections cache — otherwise a stale cache
      gives a green CI on a broken dependency
- [ ] A second push to a branch **cancels** an unfinished run — verified in fact, not by the
      config: a SHA-based group cancels nothing, and the mistake looks like a working setting
- [ ] An edit to `wiki/` alone still runs `wiki-lint` (a check that `paths-ignore` did not slip in)
- [ ] `push: [main]` is in place and a run happens after a merge
- [ ] **All nine scenarios appear as matrix legs** and each is green. The failure this guards
      against is a shortened list that still reports success — count the legs, do not read the
      colour
- [ ] **The wall clock of the run drops to roughly 2–3 minutes** from 14m7s
- [ ] `scenarios` fails outright when the list comes back empty, rather than skipping the matrix
      and reporting green

## Not done here
- Removing `push: [main]` — considered and rejected: there is nothing to save, and the direct
  record that a state of main was checked has value of its own
- `paths-ignore` — the risk of disabling the wiki check
- gitleaks — krot has none; introducing a secret scanner is a separate decision
- Changing main's protection settings — checked and sufficient
