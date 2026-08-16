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
- [x] A pip cache in both jobs — **not** `cache: pip` on `actions/setup-python`, which was tried
      first and is what the task originally said. It looks for `requirements.txt` or
      `pyproject.toml`; this repository has neither, since the linters are named on the pip
      command line, and the `requirements.yml` files are galaxy manifests. Given nothing to key
      on, setup-python **errors** rather than warning — and it is the second step, so run
      31973846564 went red in all twelve checks without running yamllint, ansible-lint,
      secret-lint or a single scenario. Replaced with `actions/cache` on `~/.cache/pip`, keyed on
      the workflow file, which is where the package names live
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
- [x] The cache takes effect on the second run — **partly, and the split is worth recording.**
      Run 31974685244 against 31974272512, `lint` job: `Install collections` **9s → 1s**, but
      `Install linters` **8s → 7s**. Both caches were hit (all four entries exist and show a
      `last_accessed_at` inside the second run), so this is not a miss — `~/.cache/pip` holds the
      downloaded wheels, and downloading was never the slow part; unpacking and installing them
      is. The original item expected "faster than 8s" from both and would have been ticked on the
      collections figure alone, which is how a half-working cache passes for a working one
- [ ] Changing `requirements.yml` **invalidates** the collections cache — otherwise a stale cache
      gives a green CI on a broken dependency
- [ ] A second push to a branch **cancels** an unfinished run — verified in fact, not by the
      config: a SHA-based group cancels nothing, and the mistake looks like a working setting
- [ ] An edit to `wiki/` alone still runs `wiki-lint` (a check that `paths-ignore` did not slip in)
- [ ] `push: [main]` is in place and a run happens after a merge
- [x] **All nine scenarios appear as matrix legs** and each is green — counted on run
      31974272512: common, cron, fail2ban, firewall, firewall_cloudflare, nginx, nginx_auth, php,
      postgresql, plus the `molecule` gate reporting separately. Counted rather than read off the
      colour, which is what this item was for
- [x] **The wall clock drops** — 14m07s → **3m43s** (run 31974272512). More than the ~2.5 minutes
      predicted, and not because of matrix overhead: dependency installation in the slowest leg
      took 25s, while `firewall_cloudflare` itself ran **177s against the 136s** measured a day
      earlier. Scenario-to-scenario spread is of the same order as what is left to win here
- [x] `scenarios` fails outright when the list comes back empty — the guard was exercised locally
      against a directory with no scenarios in it: the pipeline yields `[]` with rc=0, and the
      guard turns that into exit 1. Checked because the failure it prevents (an empty matrix
      skipping the legs and reporting green) is invisible in a passing run
- [x] **The legs run in parallel, not queued** — all nine started within one second of each other
      on the same run, so the wall clock is the slowest scenario rather than a runner queue

      > True of that run, and **not true in general** — measured on the very next one
      > (31975109782, the archiving branch): eight legs started at 22:00:14 and the ninth, `cron`,
      > at **22:05:14**, waiting five minutes for a free runner. Wall clock 7m21s rather than
      > 3m43s, set by the leg that queued longest instead of the slowest scenario. The scenarios
      > themselves also ran slower that time (`firewall_cloudflare` 272s against 177s), so the
      > runners were slower throughout. What the matrix buys is "sum" → "maximum **plus runner
      > wait**", and the second term is not ours to control. The earlier measurement stands as
      > taken; this is what the next one showed.

## Review (two passes, different angles — Codex is out of service until 2026-08-18)

- [x] **Accepted: `cache: pip` was broken** — found by both passes and by the run itself. Above
- [x] **Accepted: the cache key promises more than it delivers.** The comment said an unchanged
      key could not give a green CI on a dependency a consumer cannot install. But the
      requirements pin ranges (`>=1.5.4`), so the hash holds still while the resolved version
      moves: a hit keeps yesterday's resolution. That is the ordinary price of caching; the
      comment no longer claims otherwise
- [x] **Accepted: "GitHub waits forever" was too categorical.** A skipped required check either
      hangs pending or reports success, depending on how it was skipped. Both are worse than red,
      so the gate stands — but the wiki and the comment now say which two ways it goes wrong
      rather than asserting one
- [x] **Accepted: quote `${{ matrix.scenario }}`**, and `SC2038` on the `find | xargs` pipeline —
      actionlint reports it, so it was not hypothetical. Rewritten as a read loop rather than
      `-print0 | xargs -0`, because the latter needs `xargs -d` for `basename`, which is GNU-only
      and therefore unverifiable on the machine this was written on. That is the same mistake as
      the one above, one step earlier: the read loop was run here and produced the nine names
- [x] **Rejected: "the page's frontmatter should list nine, not seven."** `roles:` takes roles,
      and `firewall_cloudflare` / `nginx_auth` are scenarios of `firewall` and `nginx`. Checked
      rather than argued: adding `firewall_cloudflare` makes `wiki-lint` fail with «объявлена
      несуществующая роль». Seven is correct
- [x] **Noted, not rewritten: `proposal.md` says the required check is `lint`.** True when read on
      2026-08-15; `molecule` joined the list later. The measurement stays, with a note beside it
      saying what changed — the project's rule is that measurements are not rewritten

## Not done here
- Removing `push: [main]` — considered and rejected: there is nothing to save, and the direct
  record that a state of main was checked has value of its own
- `paths-ignore` — the risk of disabling the wiki check
- gitleaks — krot has none; introducing a secret scanner is a separate decision
- Changing main's protection settings — checked and sufficient
