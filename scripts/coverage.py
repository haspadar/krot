#!/usr/bin/env python3
"""How much of the collection has a Molecule scenario behind it.

Not code coverage — Molecule has no mechanism for that, and `ansible-test
coverage` measures the Python of modules and plugins, of which krot has none.
This counts reach instead: which roles are exercised by a scenario, and what
share of the collection's tasks live in them. A task is a `- name:` line under
roles/<role>/tasks/.

Fails on three things:

  * a role in neither the covered nor the uncovered list — a role nobody named
    is the defect this whole effort is against: it reads as checked while
    nothing checks it;
  * a role listed as planned or uncovered that has since gained a scenario, so
    the lists stay honest;
  * coverage going backwards, against the floor below.

It does not fail on coverage being low. Nothing here demands a number be
reached — only that what was reached is not quietly given up.
"""

from __future__ import annotations

import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
TASK_LINE = re.compile(r"^\s*- name:", re.M)

# Roles with no scenario, each with the reason it has none. Kept here rather
# than in a document because a list that lives beside the counter cannot drift
# away from it unnoticed.
UNCOVERED = {
    "bootstrap": "Molecule connects through docker, bypassing sshd, so a broken "
                 "sshd config would pass unnoticed — green in the very case the "
                 "role exists for",
    "deploy": "runs Deployer from the control machine, not on the host",
    "deploy_keys": "needs real private repositories",
    "docker": "installs Docker inside a container",
}

# Roles that will get a scenario, in the order they are being written. Separate
# from UNCOVERED because the two mean opposite things: one is "never", the other
# is "not yet". Both count as named; a role in neither list fails the check.
PLANNED = []

# A role can have more than one scenario, and firewall does: its two branches
# configure the web ports in contradictory ways, so one converge cannot cover
# both. Extra scenarios are mapped to their role by name here.
#
# Listed one by one rather than derived from the directory name: a rule like
# "split on the first underscore" would quietly claim a scenario named after a
# role that does not exist, and this counter's whole job is to refuse to assume
# coverage. A new scenario that is not listed simply does not count — visible,
# and fixed by adding a line.
EXTRA_SCENARIOS = {
    "firewall_cloudflare": "firewall",
    "nginx_auth": "nginx",
}

# A ratchet: what has been covered stays covered. Raised by hand, in a commit,
# when the run says it can be — never lowered to make a build pass.
#
# Absolute counts rather than the percentage, deliberately. The percentage has a
# denominator nobody controls: measured on the current tree, adding two tasks to
# a role that has no scenario yet drops it from 33% to 32% and fails the build.
# That punishes writing code rather than skipping tests, and the predictable
# response is to edit the threshold down until it means nothing — which is how a
# gate becomes decorative.
#
# These two cannot be moved that way. Deleting a scenario, or gutting the roles
# it covers, drops covered_tasks below the floor; adding tasks anywhere does not.
MIN_COVERED_ROLES = 7
MIN_COVERED_TASKS = 94


def count_tasks(role: Path) -> int:
    tasks = role / "tasks"
    if not tasks.is_dir():
        return 0
    return sum(len(TASK_LINE.findall(f.read_text())) for f in tasks.rglob("*.yml"))


def main() -> int:
    roles = sorted(p for p in (ROOT / "roles").iterdir() if p.is_dir())
    directories = (
        {p.name for p in (ROOT / "molecule").iterdir() if p.is_dir()}
        if (ROOT / "molecule").is_dir()
        else set()
    )
    scenarios = {EXTRA_SCENARIOS.get(name, name) for name in directories}

    rows = [(r.name, count_tasks(r), r.name in scenarios) for r in roles]
    total_tasks = sum(t for _, t, _ in rows)
    covered_tasks = sum(t for _, t, c in rows if c)
    covered_roles = sum(1 for _, _, c in rows if c)

    for name, tasks, covered in sorted(rows, key=lambda row: -row[1]):
        if covered:
            mark, note = "x", ""
        elif name in PLANNED:
            mark, note = " ", "  planned"
        elif name in UNCOVERED:
            mark, note = "-", f"  not covered: {UNCOVERED[name]}"
        else:
            mark, note = "?", "  <- named nowhere"
        print(f"  [{mark}] {name:<12} {tasks:3d}{note}")

    pct = covered_tasks * 100 // total_tasks if total_tasks else 0
    print(f"\nRoles with a scenario: {covered_roles}/{len(rows)}")
    print(f"Tasks in them: {covered_tasks}/{total_tasks} ({pct}%)")

    # The sum of both lists has to equal roles/. A role missing from both is
    # silently presumed covered, which is exactly the failure being guarded
    # against.
    named = set(UNCOVERED) | set(PLANNED) | scenarios
    unnamed = [name for name, _, _ in rows if name not in named]
    if unnamed:
        print(
            f"\nERROR: {len(unnamed)} role(s) appear in no list: {', '.join(unnamed)}",
            file=sys.stderr,
        )
        print(
            "Add a scenario, put it in PLANNED, or record in UNCOVERED why it "
            "will never have one.",
            file=sys.stderr,
        )
        return 1

    stale = sorted((set(UNCOVERED) | set(PLANNED)) & scenarios)
    if stale:
        print(
            f"\nERROR: {', '.join(stale)} now has a scenario but is still listed as "
            "planned or uncovered — remove it from that list.",
            file=sys.stderr,
        )
        return 1

    # The ratchet. Phrased as "what was covered no longer is" rather than
    # "coverage is too low": the only way to trip it is to take something away.
    if covered_roles < MIN_COVERED_ROLES or covered_tasks < MIN_COVERED_TASKS:
        print(
            f"\nERROR: coverage went backwards. Floor is {MIN_COVERED_ROLES} role(s) "
            f"and {MIN_COVERED_TASKS} task(s); this tree has {covered_roles} and "
            f"{covered_tasks}.",
            file=sys.stderr,
        )
        print(
            "A scenario was removed, or the roles behind one lost tasks. Restore it "
            "rather than lowering the floor — the floor exists to make that choice "
            "deliberate.",
            file=sys.stderr,
        )
        return 1

    # Raising it is a decision, so the script asks rather than edits itself. A
    # counter that moved its own floor would ratchet on a fluke — a role
    # temporarily gaining tasks — and then block the commit that undoes it.
    if covered_roles > MIN_COVERED_ROLES or covered_tasks > MIN_COVERED_TASKS:
        print(
            f"\nCoverage is above the floor. Raise it in {Path(__file__).name}: "
            f"MIN_COVERED_ROLES = {covered_roles}, MIN_COVERED_TASKS = {covered_tasks}"
        )

    return 0


if __name__ == "__main__":
    sys.exit(main())
