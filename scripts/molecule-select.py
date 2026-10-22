#!/usr/bin/env python3
"""Which Molecule scenarios a change has to run.

CI used to run every scenario on every pull request. A pull request that only
touches wiki/ gained nothing from that, and one that changes a single role
waited for nine others. This decides, from the list of changed files, which
scenarios can be affected — and when in doubt, runs all of them.

    molecule-select.py --all                      every scenario (push to main)
    git diff --name-only --no-renames A...B | molecule-select.py --base A
                                                  the scenarios those files reach

Prints one JSON object: {"full": bool, "scenarios": [...], "empty": bool}.
`empty` means nothing needs a scenario, which the CI gate accepts only because
this script said so — a matrix skipped for any other reason is still a failure.

What reaches a scenario:

  * its own directory, molecule/<scenario>/;
  * a role it runs, or a role that role runs, in turn — found by parsing the
    YAML for include_role / import_role, `roles:` lists and `dependencies:`,
    whatever order or spelling they use;
  * a role whose variables another role reads. fail2ban takes the SSH port from
    firewall through `| default(22)`, which no include shows: change firewall's
    defaults and fail2ban is affected without ever running it. The variables
    counted are those of the checkout AND of the base the pull request started
    from (--base): a variable that was renamed or deleted still names its
    readers, and an interface change is exactly when they need checking;
  * a playbook it imports by name (`import_playbook: haspadar.krot.<name>`),
    whose roles count as the scenario's own;
  * a module under plugins/modules/, by the `haspadar.krot.<module>` name the
    roles call it with;
  * tests/fakes/, which the site_launch scenario serves from a container.

A reference the script cannot resolve — a role named by a template, a file it
cannot parse — makes that unit lean on every role rather than on none.

Files that cannot reach a scenario are listed in INERT, and everything else —
galaxy.yml, requirements, the workflow, module_utils, a path nobody has named —
selects all of them. The list of what is safe to skip is the short one on
purpose: forgetting to add a path costs minutes, forgetting to run a scenario
costs a defect that reaches main unseen.
"""

from __future__ import annotations

import json
import re
import subprocess
import sys
from pathlib import Path

import yaml

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
YAML_SUFFIXES = {".yml", ".yaml"}
NAMESPACE = "haspadar.krot."
TOP_LEVEL_KEY = re.compile(r"^([A-Za-z_]\w*)\s*:", re.M)
VARIABLE_FILE = re.compile(r"^roles/([^/]+)/(?:defaults|vars)/.+\.ya?ml$")


class Refs:
    """What a set of YAML files runs by name."""

    def __init__(self) -> None:
        self.roles: set[str] = set()
        self.playbooks: set[str] = set()
        # True when something is run by a name this script cannot read.
        self.dynamic = False

    def role(self, value: object) -> None:
        if not isinstance(value, str):
            return
        name = value.strip()
        if "{{" in name or "{%" in name:
            self.dynamic = True
            return
        name = name.removeprefix(NAMESPACE)
        if "." not in name:  # a dotted name is another collection's
            self.roles.add(name)

    def walk(self, node: object) -> None:
        if isinstance(node, dict):
            for key, value in node.items():
                short = str(key).rsplit(".", 1)[-1]
                if short in ("include_role", "import_role"):
                    self.role(value.get("name") if isinstance(value, dict) else value)
                elif short == "import_playbook" and isinstance(value, str):
                    if value.startswith(NAMESPACE):
                        self.playbooks.add(value.removeprefix(NAMESPACE))
                elif key in ("roles", "dependencies") and isinstance(value, list):
                    for item in value:
                        if isinstance(item, dict):
                            item = item.get("role", item.get("name"))
                        self.role(item)
                self.walk(value)
        elif isinstance(node, list):
            for item in node:
                self.walk(item)

    def read(self, directory: Path) -> None:
        for path in sorted(directory.rglob("*")):
            if path.is_file() and path.suffix in YAML_SUFFIXES:
                self.read_file(path)

    def read_file(self, path: Path) -> None:
        try:
            for document in yaml.safe_load_all(path.read_text()):
                self.walk(document)
        except (yaml.YAMLError, UnicodeDecodeError):
            self.dynamic = True


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
    """The roles and scenarios of a checkout, and what each one leans on.

    `earlier_variables` are variable names the roles defined before the change
    under test, keyed by role — kept so that deleting a definition does not
    also delete the knowledge of who read it."""

    def __init__(
        self, root: Path, earlier_variables: dict[str, set[str]] | None = None
    ) -> None:
        self.root = root
        self.roles = self._names(root / "roles")
        self.scenarios = sorted(
            p.parent.name for p in (root / "molecule").glob("*/molecule.yml")
        )
        self.role_text = {r: read_tree(root / "roles" / r) for r in self.roles}
        self.playbooks = {
            p.stem: p for p in sorted((root / "playbooks").glob("*.yml"))
        }

        earlier = earlier_variables or {}
        self.role_vars = {
            r: self._defined_variables(r) | earlier.get(r, set())
            for r in {*self.roles, *earlier}
        }

        self.dynamic: set[str] = set()
        self.uses: dict[str, set[str]] = {}
        for role in self.roles:
            refs = Refs()
            refs.read(root / "roles" / role)
            self.uses[role] = self._with_readers(role, self.role_text[role], refs.roles)
            if refs.dynamic:
                self.dynamic.add(role)

        self.scenario_playbooks: dict[str, set[str]] = {}
        self.scenario_text: dict[str, str] = {}
        self.scenario_uses: dict[str, set[str]] = {}
        self.scenario_dynamic: set[str] = set()
        for scenario in self.scenarios:
            refs = Refs()
            refs.read(root / "molecule" / scenario)
            imported = self._import_playbooks(refs)
            self.scenario_playbooks[scenario] = imported
            text = "\n".join(
                [read_tree(root / "molecule" / scenario)]
                + [self.playbooks[p].read_text() for p in sorted(imported)]
            )
            self.scenario_text[scenario] = text
            roles = refs.roles | ({scenario} if scenario in self.roles else set())
            self.scenario_uses[scenario] = self._with_readers(None, text, roles)
            if refs.dynamic:
                self.scenario_dynamic.add(scenario)

    @staticmethod
    def _names(directory: Path) -> list[str]:
        if not directory.is_dir():
            return []
        return sorted(p.name for p in directory.iterdir() if p.is_dir())

    def _import_playbooks(self, refs: Refs) -> set[str]:
        """The playbooks a scenario imports, and those they import, folding
        the roles and the unreadable references they bring into `refs`."""
        seen: set[str] = set()
        todo = [p for p in refs.playbooks]
        while todo:
            name = todo.pop()
            if name in seen:
                continue
            seen.add(name)
            if name not in self.playbooks:
                refs.dynamic = True  # imports something that is not here
                continue
            inner = Refs()
            inner.read_file(self.playbooks[name])
            refs.roles |= inner.roles
            refs.dynamic = refs.dynamic or inner.dynamic
            todo.extend(inner.playbooks)
        return {p for p in seen if p in self.playbooks}

    def _defined_variables(self, role: str) -> set[str]:
        found: set[str] = set()
        for name in ("defaults", "vars"):
            directory = self.root / "roles" / role / name
            if directory.is_dir():
                for path in sorted(directory.rglob("*")):
                    if path.is_file() and path.suffix in YAML_SUFFIXES:
                        found.update(TOP_LEVEL_KEY.findall(path.read_text()))
        return found

    def _with_readers(
        self, owner: str | None, text: str, named: set[str]
    ) -> set[str]:
        """The roles named, plus those whose variables this text reads."""
        used = set(named)
        for role, variables in self.role_vars.items():
            if role == owner:
                continue
            if any(re.search(rf"\b{re.escape(v)}\b", text) for v in variables):
                used.add(role)
        used.discard(owner)
        return used

    def closure(self, roles: set[str], dynamic: bool = False) -> set[str]:
        """The roles plus every role they run, transitively. A role that runs
        something unreadable, like `dynamic`, is taken to run them all."""
        everyone = set(self.roles)
        seen: set[str] = set()
        todo = list(everyone if dynamic else roles)
        while todo:
            role = todo.pop()
            if role in seen:
                continue
            seen.add(role)
            if role in self.dynamic:
                todo.extend(everyone)
            todo.extend(self.uses.get(role, ()))
        return seen


def classify(path: str) -> tuple[str, str]:
    """('role', name) | ('scenario', name) | ('module', name) |
    ('playbook', name) | ('fakes', '') | ('inert', '') | ('full', '')"""
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
            call = f"{NAMESPACE}{name}"
            roles.update(r for r, t in tree.role_text.items() if call in t)
            direct.update(s for s, t in tree.scenario_text.items() if call in t)
        elif kind == "fakes":
            direct.update(
                s for s, t in tree.scenario_text.items() if "tests/fakes" in t
            )

    chosen = set(direct)
    for scenario in tree.scenarios:
        reach = tree.closure(
            tree.scenario_uses[scenario], scenario in tree.scenario_dynamic
        )
        if reach & roles:
            chosen.add(scenario)
    ordered = sorted(chosen)
    return {"full": False, "scenarios": ordered, "empty": not ordered}


def everything(tree: Tree) -> dict:
    return {"full": True, "scenarios": list(tree.scenarios), "empty": False}


def earlier_variables(root: Path, base: str, changed: list[str]) -> dict[str, set[str]]:
    """Variable names that changed variable files defined at `base`."""
    found: dict[str, set[str]] = {}
    for path in changed:
        match = VARIABLE_FILE.match(path)
        if not match:
            continue
        shown = subprocess.run(
            ["git", "show", f"{base}:{path}"],
            cwd=root,
            capture_output=True,
            text=True,
            check=False,
        )
        if shown.returncode == 0:  # not there at base: a file the change added
            found.setdefault(match.group(1), set()).update(
                TOP_LEVEL_KEY.findall(shown.stdout)
            )
    return found


def main(argv: list[str]) -> int:
    base = None
    if len(argv) == 2 and argv[0] == "--base":
        base, argv = argv[1], []
    if argv not in ([], ["--all"]):
        print(__doc__, file=sys.stderr)
        return 2

    changed: list[str] = []
    if argv != ["--all"]:
        changed = [line.strip() for line in sys.stdin if line.strip()]
    earlier = earlier_variables(ROOT, base, changed) if base else {}
    tree = Tree(ROOT, earlier)
    if not tree.scenarios:
        # An empty matrix is green to GitHub; a broken find must not read as
        # "every scenario passed".
        print("no scenarios found under molecule/", file=sys.stderr)
        return 1
    # No list of changed files at all is a failure to learn them, not a change
    # that touches nothing.
    result = select(tree, changed) if changed else everything(tree)
    print(json.dumps(result))
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
