#!/usr/bin/env python3
"""Which Molecule scenarios a change has to run.

CI used to run every scenario on every pull request. A pull request that only
touches wiki/ gained nothing from that, and one that changes a single role
waited for nine others. This decides, from the list of changed files, which
scenarios can be affected — and when in doubt, runs all of them.

    molecule-select.py --all                      every scenario (push to main)
    git diff --name-only --no-renames A...B | molecule-select.py
                                                  the scenarios those files reach

Prints one JSON object: {"full": bool, "scenarios": [...], "empty": bool}.
`empty` means nothing needs a scenario, which the CI gate accepts only because
this script said so — a matrix skipped for any other reason is still a failure.

What reaches a scenario:

  * its own directory, molecule/<scenario>/;
  * a role it runs, or a role that role runs, in turn — found by reading
    include_role / import_role / `role:` entries and meta `dependencies:`;
  * a role whose variables another role reads. fail2ban takes the SSH port from
    firewall through `| default(22)`, which no include shows: change firewall's
    defaults and fail2ban is affected without ever running it;
  * a playbook it imports by name (`import_playbook: haspadar.krot.<name>`),
    whose roles count as the scenario's own;
  * a module under plugins/modules/, by the `haspadar.krot.<module>` name the
    roles call it with;
  * tests/fakes/, which the site_launch scenario serves from a container.

Files that cannot reach a scenario are listed in INERT, and everything else —
galaxy.yml, requirements, the workflow, module_utils, a path nobody has named —
selects all of them. The list of what is safe to skip is the short one on
purpose: forgetting to add a path costs minutes, forgetting to run a scenario
costs a defect that reaches main unseen.
"""

from __future__ import annotations

import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent

# Paths that no scenario reads. Documentation and the checks that only read the
# tree (lint, wiki, secrets) run in the `lint` job, which always runs.
INERT_DIRS = ("wiki/", "openspec/", "tests/unit/", ".idea/", ".claude/")
INERT_FILES = {
    ".yamllint",
    ".ansible-lint",
    ".ansible-lint-ignore",
    ".gitignore",
    ".worktreeinclude",
}
# Scripts that lint-time checks run; the selector itself is not among them —
# changing how scenarios are chosen has to be tested by choosing all of them.
INERT_SCRIPTS = {
    "coverage.py",
    "forbidden_names.py",
    "module-docs.py",
    "names-lint.py",
    "secret-lint.py",
    "wiki-after-archive.py",
    "wiki-index.py",
    "wiki-lint.py",
    "wiki-triage.py",
}

TEXT_SUFFIXES = {".yml", ".yaml", ".j2", ".py", ".sh", ".cfg", ".conf", ".json", ""}
PREFIX = r"(?:haspadar\.krot\.)?"
INCLUDED = re.compile(
    r"(?:include|import)_role\s*:\s*\n\s*name\s*:\s*['\"]?" + PREFIX + r"(\w+)", re.M
)
LISTED = re.compile(r"^\s*(?:-\s+)?role\s*:\s*['\"]?" + PREFIX + r"(\w+)", re.M)
IMPORTED_PLAYBOOK = re.compile(r"import_playbook\s*:\s*['\"]?haspadar\.krot\.(\w+)")
TOP_LEVEL_KEY = re.compile(r"^([A-Za-z_]\w*)\s*:", re.M)


def read_tree(directory: Path) -> str:
    """Everything textual under a directory, as one string."""
    if not directory.is_dir():
        return ""
    parts = []
    for path in sorted(directory.rglob("*")):
        if path.is_file() and path.suffix in TEXT_SUFFIXES:
            try:
                parts.append(path.read_text())
            except UnicodeDecodeError:
                continue
    return "\n".join(parts)


class Tree:
    """The roles and scenarios of a checkout, and what each one leans on."""

    def __init__(self, root: Path) -> None:
        self.root = root
        self.roles = self._names(root / "roles")
        self.scenarios = sorted(
            p.parent.name for p in (root / "molecule").glob("*/molecule.yml")
        )
        self.role_text = {r: read_tree(root / "roles" / r) for r in self.roles}
        self.scenario_text = {s: read_tree(root / "molecule" / s) for s in self.scenarios}
        self.role_vars = {r: self._defined_variables(r) for r in self.roles}
        self.uses = {r: self._used_roles(r, self.role_text[r]) for r in self.roles}
        self.playbooks = self._playbook_texts(root / "playbooks")
        self.scenario_playbooks = {
            s: set(IMPORTED_PLAYBOOK.findall(self.scenario_text[s]))
            for s in self.scenarios
        }
        self.scenario_uses = {
            s: self._used_roles(None, self._scenario_and_playbooks(s)) | self._own_role(s)
            for s in self.scenarios
        }

    @staticmethod
    def _playbook_texts(directory: Path) -> dict[str, str]:
        if not directory.is_dir():
            return {}
        return {p.stem: p.read_text() for p in directory.glob("*.yml")}

    def _scenario_and_playbooks(self, scenario: str) -> str:
        """A scenario's own files plus the playbooks it imports by name."""
        imported = [self.playbooks.get(n, "") for n in self.scenario_playbooks[scenario]]
        return "\n".join([self.scenario_text[scenario], *imported])

    @staticmethod
    def _names(directory: Path) -> list[str]:
        if not directory.is_dir():
            return []
        return sorted(p.name for p in directory.iterdir() if p.is_dir())

    def _defined_variables(self, role: str) -> set[str]:
        found: set[str] = set()
        for name in ("defaults", "vars"):
            main = self.root / "roles" / role / name / "main.yml"
            if main.is_file():
                found.update(TOP_LEVEL_KEY.findall(main.read_text()))
        return found

    def _used_roles(self, owner: str | None, text: str) -> set[str]:
        """Roles this text runs by name, or whose variables it reads."""
        used = set(INCLUDED.findall(text)) | set(LISTED.findall(text))
        for role, variables in self.role_vars.items():
            if role == owner:
                continue
            if any(re.search(rf"\b{re.escape(v)}\b", text) for v in variables):
                used.add(role)
        used.discard(owner)
        return used

    def _own_role(self, scenario: str) -> set[str]:
        return {scenario} if scenario in self.roles else set()

    def closure(self, roles: set[str]) -> set[str]:
        """The roles plus every role they run, transitively."""
        seen: set[str] = set()
        todo = list(roles)
        while todo:
            role = todo.pop()
            if role in seen:
                continue
            seen.add(role)
            todo.extend(self.uses.get(role, ()))
        return seen


def classify(path: str) -> tuple[str, str]:
    """('role', name) | ('scenario', name) | ('module', name) | ('fakes', '') |
    ('inert', '') | ('full', '')"""
    parts = path.split("/")
    if parts[0] == "roles" and len(parts) > 2:
        return "role", parts[1]
    if parts[0] == "molecule" and len(parts) > 2:
        return "scenario", parts[1]
    if parts[0] == "plugins" and len(parts) == 3 and parts[1] == "modules":
        return "module", Path(parts[2]).stem
    if parts[0] == "playbooks" and len(parts) == 2 and parts[1].endswith(".yml"):
        return "playbook", Path(parts[1]).stem
    if parts[0] == "tests" and parts[1:2] == ["fakes"]:
        return "fakes", ""
    if parts[0] == "scripts" and len(parts) == 2 and parts[1] in INERT_SCRIPTS:
        return "inert", ""
    # Prose is prose wherever it sits; roles/ and molecule/ were handled above,
    # so a README beside a role still runs that role.
    if path.endswith(".md") or path in INERT_FILES or path.startswith(INERT_DIRS):
        return "inert", ""
    return "full", ""


def select(tree: Tree, changed: list[str]) -> dict:
    roles: set[str] = set()
    direct: set[str] = set()
    for path in changed:
        kind, name = classify(path)
        if kind == "full":
            return everything(tree)
        if kind == "role":
            roles.add(name)
        elif kind == "scenario":
            if name in tree.scenarios:
                direct.add(name)
        elif kind == "playbook":
            direct.update(s for s, n in tree.scenario_playbooks.items() if name in n)
        elif kind == "module":
            call = f"haspadar.krot.{name}"
            roles.update(r for r, t in tree.role_text.items() if call in t)
            direct.update(s for s, t in tree.scenario_text.items() if call in t)
        elif kind == "fakes":
            direct.update(
                s for s, t in tree.scenario_text.items() if "tests/fakes" in t
            )

    chosen = set(direct)
    for scenario in tree.scenarios:
        if tree.closure(tree.scenario_uses[scenario]) & roles:
            chosen.add(scenario)
    ordered = sorted(chosen)
    return {"full": False, "scenarios": ordered, "empty": not ordered}


def everything(tree: Tree) -> dict:
    return {"full": True, "scenarios": list(tree.scenarios), "empty": False}


def main(argv: list[str]) -> int:
    tree = Tree(ROOT)
    if not tree.scenarios:
        # An empty matrix is green to GitHub; a broken find must not read as
        # "every scenario passed".
        print("no scenarios found under molecule/", file=sys.stderr)
        return 1
    if argv == ["--all"]:
        result = everything(tree)
    elif not argv:
        changed = [line.strip() for line in sys.stdin if line.strip()]
        result = select(tree, changed) if changed else everything(tree)
    else:
        print(__doc__, file=sys.stderr)
        return 2
    print(json.dumps(result))
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
