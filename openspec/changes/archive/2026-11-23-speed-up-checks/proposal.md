# Check a role before merging it, not after pushing it

## Why

A change waited about sixteen minutes for checks: roughly eight on the branch and eight more on
`main` before a tag. Most of that was the Molecule matrix, which runs real containers, while the
question a reviewer has is narrower: what changes on the machines. One person works here, so the
matrix is spent where nobody is waiting on it, and the wait is spent where somebody is.

## What changes

- A pull request and a push to `main` run `lint` only: yamllint, ansible-lint, the collection
  build, unit tests, wiki and name checks. Scenarios run weekly and by hand (`workflow_dispatch`),
  in full, as before.
- `molecule` stops being a required check on `main`; the scenario jobs stay in the workflow for the
  weekly and manual run.
- A role is checked before merge locally: `scripts/molecule-fast.py` picks the scenarios the
  branch can reach (the same selector CI used) and runs them in parallel; `--quick` drops the
  idempotence pass and `--full` is `molecule test`. Measured: trimming steps buys little, so the
  gain is in not running unreachable scenarios and in running the rest side by side.
- `lint` gets faster too: unit tests run in parallel except the three files sharing one database
  (134 s serial → about 27 s), and the `indexing` scenario's simulated running night is 40 s, not 150.
- Release order: the tag goes on the merged SHA straight after the merge when the branch's `lint`
  was green and the branch was current with `main`; nothing waits for a second run on `main`.

## What stops being checked on every pull request

Scenarios run in CI only weekly and on request. What the lighter local sequence leaves out, and
where that is caught instead, is recorded in `wiki/operations/testing-roles.md`.

## Not changed

No role, default or module changes, so no tag for consumers.
