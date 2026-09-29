#!/usr/bin/env python3
"""Keeps the projects that consume this collection out of its code.

krot is a collection, not the configuration of one network: a comment that says
"measured on <project>" makes the reader know somebody else's project to follow
it, and a real site in a fixture tells anyone reading the repository which sites
its author runs. The rule held by attention alone until 2026-09-29, when a
review found a hundred such lines across roles, modules, tests and scenarios.

The words are compared by hash, so this file does not name what it forbids —
it would otherwise be the one place in the tree that still did. A word is any
run of [a-z0-9] after lowercasing, which catches `acc-<name>`, `<name>'s` and
`<name>.de` alike.

wiki/ and openspec/ are left out on purpose: the wiki explains how projects
plug the collection in and names them where that is the point, and the change
archive is history. To forbid another word, add the sha256 of its lowercase
spelling below — `printf '%s' word | shasum -a 256`.
"""

from __future__ import annotations

import hashlib
import re
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent

FORBIDDEN = {
    "47fa91115b212214dbd018f357ab5883424f82b3e6d3de1bc20f04b2b319aac2",
    "61e8809900baf42d0287463b31aef80a422b3a8959fd49496cd1f230e3739799",
    "1372c63b35ea72a55bc5afac621482ea61a41dea630ba19583412545d4197641",
    "5862369d4456977e94676b7376cd3de71cb3c3c891aae27f445e56e08e3c41ad",
    "fa10c03906f12c3ff779c33079afb15e52b14ade96804f35fb6025619b826774",
    "5448199fe71a15959b536279d873c729da5088b31098eee83173bbac06738297",
    "13ac368599ba03b93a72142138bdfd4610ec7896d2ab2f66e62541d24b7183e5",
    "eb5219a9a50bdb51760481c6c642523a78c3555812b600b9769bcdce17403a47",
    "6e5e1ccf88c88d70a81707c0d74c7bbed5cfa0dc47d3dbf31f5c6979d6127720",
    "9e898946dec8daa8916e363d99bd1bd22d188d3f59c53df00d8e1effa500e0cc",
    "8566db9ce3b9c7aaf81f1d2e7ad7df8e0588efd1431c29a927d9d6401700cec0",
}

SKIP_PREFIXES = ("wiki/", "openspec/", "collections/", ".ruff_cache/")
BINARY_SUFFIXES = {".png", ".jpg", ".jpeg", ".gif", ".pdf", ".gz", ".tar", ".zip", ".ico"}
WORD = re.compile(r"[a-z0-9]+")


def tracked_files() -> list[Path]:
    """Git's index, so untracked scratch files and ignored trees stay out."""
    out = subprocess.run(
        ["git", "-C", str(ROOT), "ls-files", "-z"],
        capture_output=True,
        text=True,
        check=True,
    )
    return [ROOT / name for name in out.stdout.split("\0") if name]


def forbidden(line: str) -> bool:
    return any(hashlib.sha256(word.encode()).hexdigest() in FORBIDDEN for word in WORD.findall(line.lower()))


def main() -> int:
    errors: list[str] = []
    checked = 0
    for path in tracked_files():
        relative = path.relative_to(ROOT).as_posix()
        if relative.startswith(SKIP_PREFIXES):
            continue
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
    print(f"Чужих проектов не найдено: проверено {checked} файлов вне wiki/ и openspec/.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
