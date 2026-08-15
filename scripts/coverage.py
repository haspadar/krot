#!/usr/bin/env python3
"""How much of the collection has a Molecule scenario behind it.

Not code coverage — Molecule has no mechanism for that, and `ansible-test
coverage` measures the Python of modules and plugins, of which krot has none.
This counts reach instead: which roles are exercised by a scenario, and what
share of the collection's tasks live in them. A task is a `- name:` line under
roles/<role>/tasks/.

Also fails when a role is in neither the covered nor the uncovered list, because
a role nobody named is the defect this whole effort is against: it reads as
checked while nothing checks it.
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
PLANNED = ["firewall", "nginx", "postgresql", "common", "fail2ban", "php"]


def count_tasks(role: Path) -> int:
    tasks = role / "tasks"
    if not tasks.is_dir():
        return 0
    return sum(len(TASK_LINE.findall(f.read_text())) for f in tasks.rglob("*.yml"))


def main() -> int:
    roles = sorted(p for p in (ROOT / "roles").iterdir() if p.is_dir())
    scenarios = (
        {p.name for p in (ROOT / "molecule").iterdir() if p.is_dir()}
        if (ROOT / "molecule").is_dir()
        else set()
    )

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

    return 0


if __name__ == "__main__":
    sys.exit(main())
