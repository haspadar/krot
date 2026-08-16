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

## Work
- [ ] `cache: pip` in `actions/setup-python`
- [ ] A cache of the collections directory keyed on the hash of `requirements.yml`
- [ ] `concurrency` grouped by `ref` with `cancel-in-progress: true`
- [ ] A comment in the workflow: `concurrency` is introduced in advance for Molecule, its
      contribution today is 1.7% — so the next reader does not mistake it for a savings measure
- [ ] `.openspec.yaml` with `skip_specs: true`
- [ ] `CHANGELOG.md` — decide how to version a change that alters no role

## Verification
- [ ] The cache takes effect on the second run: the install steps are faster than 8s
- [ ] Changing `requirements.yml` **invalidates** the collections cache — otherwise a stale cache
      gives a green CI on a broken dependency
- [ ] A second push to a branch **cancels** an unfinished run — verified in fact, not by the
      config: a SHA-based group cancels nothing, and the mistake looks like a working setting
- [ ] An edit to `wiki/` alone still runs `wiki-lint` (a check that `paths-ignore` did not slip in)
- [ ] `push: [main]` is in place and a run happens after a merge

## Not done here
- Removing `push: [main]` — considered and rejected: there is nothing to save, and the direct
  record that a state of main was checked has value of its own
- `paths-ignore` — the risk of disabling the wiki check
- gitleaks — krot has none; introducing a secret scanner is a separate decision
- Changing main's protection settings — checked and sufficient
