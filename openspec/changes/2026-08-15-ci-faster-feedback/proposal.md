# Proposal: CI waits longer than it works

## Why

This change began as "cut the Actions quota spend" and in that form was **wrong from its premise**.
The mistake is recorded here rather than erased, because it is more instructive than the conclusion.

**krot is a public repository.** `gh api repos/haspadar/krot` answers `private: false`, and Actions
minutes for public repositories on standard runners are free and do not draw on the account quota.
All 65 runs over 17 days cost nothing.

So the original "krot pays out of the same purse" is false, and the evidence quoted beside it was
read backwards: krot kept running while busel stood idle from July not by luck, but because it is
public. The private ones are busel and matilda — that is where the quota actually ran out, and where
the savings measures belong (`busel`, change `2026-08-15-ci-runs-once-per-change`).

### The second mistake: a conclusion presented as a measurement

The first revision said: "**`concurrency` would have cancelled 20 runs** (31%)", with a checkmark in
the "Measured" section. What had been counted was something else — the number of **repeat** runs per
branch (43 PR runs across 23 branches, the sum of the excesses being 20). Between "repeat" and
"cancellable" sits an unstated assumption: that a new push arrives **while the previous run is still
going**. It was never checked.

Checking it against start and finish times:

| | |
|---|---|
| PR runs | 43 |
| repeats (beyond the first per branch) | 20 |
| **actually overlapped in time** | **2** |
| seconds `concurrency` would have cancelled | **58** out of 3419 (**1.7%**) |

Typical gaps between pushes are hundreds of seconds, and twice more than a day. At a 49s median run,
the previous one has long finished; there is nothing to cancel. The claimed effect was overstated
tenfold, and it rested on plausibility rather than on data.

This is the same class of defect as in the `cron` role: the statement looked measured because real
numbers stood next to it.

### What is left after subtracting both mistakes

The spend in minutes does not matter — it is free. What matters is **waiting time** and what it is
made of. The breakdown of the last run (job steps summing to 34s, run wall clock 39s):

| Step | |
|---|---|
| `Install linters` (pip) | **8s** |
| `Install collections` (ansible-galaxy) | **8s** |
| `ansible-lint` | 15s |
| `yamllint`, `wiki-lint`, build, wiki-index | 0–1s each |

**16 seconds out of 34 go on installing dependencies**, the same ones from run to run. There is
spread, too: on an adjacent run `Install collections` took 16s rather than 8s.

This is the only item worth fixing, and it costs waiting rather than money — waiting that is about
to grow: change `2026-08-15-molecule-role-tests` adds a role run inside a container, which is minutes
rather than seconds.

## What Changes

**A pip and collections cache.** `actions/setup-python` with `cache: pip`, and a cache of the
collections directory keyed on the hash of `requirements.yml`. Saves roughly 16 seconds out of 34 on
every run.

**`concurrency` with `cancel-in-progress`, and honesty about its contribution.** Over the measured
window it saves 58 seconds — next to nothing. It is introduced not for that but for what is coming:
Molecule turns a 49-second run into minutes, and a burst of pushes will start forming a queue that
does not exist today. Group by `ref` rather than by SHA: a SHA-based group never matches across two
pushes and therefore cancels nothing. The flip side is recorded in the Molecule change — a scenario
cancelled halfway leaves containers behind.

**`push: [main]` stays.** The first revision removed it for savings; there are no savings to be had,
and it carries a value of its own: it is the only direct record that a given state of main was
checked. Branch protection is a complement to that, not a substitute.

What that cancelled measure rested on was checked along the way — and the ground turned out firmer
than the text claimed: `strict: true` (a branch must be up to date), `enforce_admins: true` (the rule
applies to the owner as well), force-push and branch deletion forbidden, required check `lint`. There
is no direct path into main for anyone, the admin included.

> Read on 2026-08-15 and left as read. `molecule` was added to the required checks when that change
> landed, so the list is `["lint", "molecule"]` today — checked through the API on 2026-08-17, and it
> matters, because a matrix reports one check per leg and would have retired the name `molecule`
> outright. The measurement is not rewritten; what changed after it is noted here.

**`paths-ignore` is not carried over from busel.** Its list holds `wiki/**` and `**.md`, and for
busel that is correct: its CI does not read the wiki. In krot **CI checks the wiki** — `wiki-lint.py`
and the reconciliation of `wiki/index/` against its sources — and wiki pages are `.md`. Copying it
would disable the wiki check on exactly the edits it exists for.

## Impact

- **A run is faster by roughly 16 seconds out of 34.** That is all this change buys in time.
- **There is no monetary effect and never was.** Public repository, free minutes.
- **`concurrency` is introduced in advance.** Its contribution today is 1.7%; the point of it arrives
  with Molecule.
- **The cache can go stale** and produce "works in CI, breaks for the consumer" — the key hangs on the
  hash of `requirements.yml` so that changing a dependency invalidates it.
- **Not a single check is lost**, and `push: [main]` is retained.
- **If krot ever becomes private**, the spend question returns — and it returns to busel's numbers,
  not to these.

## Out of scope

- **Removing `push: [main]`** — considered and rejected above.
- **`paths-ignore`** — reasoning above; the saving is small and the risk of disabling the wiki check
  is real.
- **Molecule** — its own change. Here it is only the reason to introduce `concurrency` early.
- **gitleaks.** busel has it, krot has none at all. Introducing a secret scanner is a separate
  decision, not a side effect of editing run time.
- **Main's protection settings.** Checked and found sufficient; this change does not propose changing
  them.
