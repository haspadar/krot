#!/usr/bin/env python3
"""Check the roles a branch touches, locally, before it is merged.

CI no longer runs Molecule on a pull request. This is what stands in for it:
the same selector CI used (scripts/molecule-select.py) picks the scenarios a
branch can reach, and each runs destroy, converge, idempotence, verify, destroy,
several at a time.

    scripts/molecule-fast.py                 scenarios the branch reaches, against main
    scripts/molecule-fast.py php nginx       these scenarios
    scripts/molecule-fast.py --quick         without the idempotence pass
    scripts/molecule-fast.py --full          `molecule test`, every step of the scenario
    scripts/molecule-fast.py --keep php      leave the container up for the next run
    scripts/molecule-fast.py --jobs 2        how many at once (default 4)
    scripts/molecule-fast.py --list          only print what would run

Against `molecule test` the default leaves out one thing: `check`, a dry run on
a fresh machine, which only indexing, collecting and site_launch carry. It is
about twenty seconds in indexing. Measured on five roles (wiki/operations/
testing-roles.md), idempotence costs 4 to 24 seconds a scenario, so it is kept
by default and `--quick` drops it. A change to check-mode handling needs `--full`.

Exit status is 0 only when every scenario passed.
"""

from __future__ import annotations

import argparse
import importlib.util
import json
import os
import shutil
import subprocess
import sys
import time
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
# Every molecule command begins by reinstalling this collection into
# ~/.ansible/collections, deleting it first, so two scenarios at once break each
# other (measured: five started together, three died in the first seconds on a
# missing directory). Each scenario therefore gets an ANSIBLE_HOME of its own and
# nothing is shared but the container runtime.
HOMES = Path("/tmp/krot-molecule-home")
SELECT = ROOT / "scripts" / "molecule-select.py"


def scenarios_on_disk(root: Path = ROOT) -> list[str]:
    return sorted(p.parent.name for p in (root / "molecule").glob("*/molecule.yml"))


def sequence(scenario: str, full: bool, keep: bool, idempotence: bool = True) -> list[list[str]]:
    """The molecule commands for one scenario, in order."""
    if full:
        return [["molecule", "test", "-s", scenario]]
    # `converge` creates and prepares by itself when the container is not there.
    # Without --keep the run starts from nothing and ends with nothing; with it,
    # a container left by the last run is reused, which is the quick loop.
    middle = ("converge", "idempotence", "verify") if idempotence else ("converge", "verify")
    steps = [["molecule", step, "-s", scenario] for step in middle]
    if not keep:
        steps = [["molecule", "destroy", "-s", scenario], *steps,
                 ["molecule", "destroy", "-s", scenario]]
    return steps


def choose(listing: str, names: list[str]) -> list[str]:
    """The scenarios to run: those named, checked against what exists, or what the
    selector printed."""
    existing = set(scenarios_on_disk())
    if names:
        unknown = sorted(set(names) - existing)
        if unknown:
            raise SystemExit("unknown scenario: " + ", ".join(unknown))
        # In order, once each: the same scenario twice would race on one container.
        return list(dict.fromkeys(names))
    return json.loads(listing)["scenarios"]


def git(*args: str) -> str:
    return subprocess.run(
        ["git", *args], cwd=ROOT, check=True, capture_output=True, text=True
    ).stdout


def selector_python() -> str:
    """An interpreter that can read YAML. The selector needs PyYAML, which this
    interpreter may lack while the one `molecule` itself runs under has it."""
    if importlib.util.find_spec("yaml"):
        return sys.executable
    molecule = shutil.which("molecule")
    if molecule:
        # pipx and a venv both put the interpreter next to the script.
        beside = Path(molecule).resolve().parent / "python"
        if beside.exists():
            return str(beside)
    raise SystemExit("the selector needs PyYAML: pip install pyyaml")


def selection(base_ref: str) -> str:
    """The selector's answer for what differs from `base_ref`, committed or not."""
    try:
        base = git("merge-base", base_ref, "HEAD").strip()
    except subprocess.CalledProcessError:
        try:
            base = git("merge-base", "origin/" + base_ref, "HEAD").strip()
        except subprocess.CalledProcessError:
            raise SystemExit(f"no `{base_ref}` to compare with: pass --base <ref>")
    changed = git("diff", "--name-only", "--no-renames", base).splitlines()
    changed += git("ls-files", "--others", "--exclude-standard").splitlines()
    if not changed:
        return json.dumps({"full": False, "scenarios": [], "empty": True})
    out = subprocess.run(
        [selector_python(), str(SELECT), "--base", base],
        cwd=ROOT, input="\n".join(changed) + "\n", capture_output=True, text=True,
    )
    if out.returncode != 0:
        raise SystemExit(out.stderr or "the selector failed")
    return out.stdout


def run_command(command: list[str], log, scenario: str) -> int:
    """One molecule command, its output into `log`, in the scenario's own home."""
    home = HOMES / scenario
    home.mkdir(parents=True, exist_ok=True)
    return subprocess.run(
        command, cwd=ROOT, stdout=log, stderr=subprocess.STDOUT,
        env={**os.environ, "ANSIBLE_HOME": str(home)},
    ).returncode


def run_one(scenario: str, full: bool, keep: bool, idempotence: bool, logdir: Path) -> tuple[str, bool, float]:
    started = time.monotonic()
    ok = True
    try:
        logdir.mkdir(parents=True, exist_ok=True)
        with (logdir / f"{scenario}.log").open("w") as log:
            for command in sequence(scenario, full, keep, idempotence):
                log.write("$ " + " ".join(command) + "\n")
                log.flush()
                if run_command(command, log, scenario):
                    ok = False
                    # The container is left up on purpose: that is what the log is about.
                    break
    except OSError as error:  # molecule not installed, log directory not writable
        print(f"{scenario}: {error}", file=sys.stderr)
        ok = False
    return scenario, ok, time.monotonic() - started


def main(argv: list[str]) -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument("scenarios", nargs="*")
    parser.add_argument("--full", action="store_true", help="molecule test instead of the default sequence")
    parser.add_argument("--quick", action="store_true", help="leave out the second converge that must change nothing")
    parser.add_argument("--keep", action="store_true", help="do not destroy the container at the end")
    parser.add_argument("--jobs", type=int, default=4)
    parser.add_argument("--base", default="main", help="what the branch is compared with")
    parser.add_argument("--list", action="store_true", help="print the scenarios and stop")
    parser.add_argument("--logs", default="/tmp/krot-molecule", help="where per-scenario logs go")
    args = parser.parse_args(argv)

    if args.full and args.keep:
        parser.error("--keep has no effect on --full: molecule test always destroys")
    chosen = choose("" if args.scenarios else selection(args.base), args.scenarios)
    if not chosen:
        print("nothing reaches a scenario: lint alone covers this change")
        return 0
    print(("full cycle" if args.full else "default sequence") + ": " + ", ".join(chosen))
    if args.list:
        return 0

    logdir = Path(args.logs)
    started = time.monotonic()
    with ThreadPoolExecutor(max_workers=max(1, args.jobs)) as pool:
        results = list(pool.map(lambda s: run_one(s, args.full, args.keep, not args.quick, logdir), chosen))
    for scenario, ok, seconds in results:
        print(f"{'ok  ' if ok else 'FAIL'} {scenario:<22} {seconds:6.0f}s  {logdir / (scenario + '.log')}")
    print(f"wall clock {time.monotonic() - started:.0f}s")
    return 0 if all(ok for _, ok, _ in results) else 1


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
