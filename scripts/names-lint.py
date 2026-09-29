#!/usr/bin/env python3
"""Keeps the projects that consume this collection out of its code.

krot is a collection, not the configuration of one network: a comment that says
"measured on <project>" makes the reader know somebody else's project to follow
it, and a real site in a fixture tells anyone reading the repository which sites
its author runs. The rule held by attention alone until 2026-09-29, when a
review found a hundred such lines across roles, modules, tests and scenarios.

The words, and how a line is split into them, are in forbidden_names.py. File
paths are read the same way as lines.

Left out: openspec/changes/, the record of decisions as they were taken, and
wiki/index/, which is generated from it and masks the words as it goes.
"""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

from forbidden_names import forbidden

ROOT = Path(__file__).resolve().parent.parent

SKIP_PREFIXES = ("openspec/changes/", "wiki/index/")
BINARY_SUFFIXES = {".png", ".jpg", ".jpeg", ".gif", ".pdf", ".gz", ".tar", ".zip", ".ico"}


def tracked_files() -> list[Path]:
    """Git's index, so untracked scratch files and ignored trees stay out."""
    out = subprocess.run(
        ["git", "-C", str(ROOT), "ls-files", "-z"],
        capture_output=True,
        text=True,
        check=True,
    )
    return [ROOT / name for name in out.stdout.split("\0") if name]


def main() -> int:
    errors: list[str] = []
    checked = 0
    for path in tracked_files():
        relative = path.relative_to(ROOT).as_posix()
        if relative.startswith(SKIP_PREFIXES):
            continue
        # The path first: a file named after a project says so before a line does.
        if forbidden(relative):
            errors.append(f"{relative}: the file's own path")
        if path.suffix.lower() in BINARY_SUFFIXES or not path.is_file():
            continue
        try:
            contents = path.read_text()
        except UnicodeDecodeError:
            continue
        checked += 1
        for number, line in enumerate(contents.split("\n"), start=1):
            if forbidden(line):
                errors.append(f"{relative}:{number}: {line.strip()}")

    if errors:
        print(f"Код называет проект-потребителя или его сайт ({len(errors)}):")
        for error in errors:
            print(f"  {error}")
        print()
        print("Коллекция не знает, кто её подключает: назовите это «проект», «рабочая машина», "
              "выдуманный домен.")
        return 1
    print(f"Чужих проектов не найдено: проверено {checked} файлов вне openspec/changes/ и wiki/index/.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
