#!/usr/bin/env python3
"""Looks for secret-shaped strings everywhere in the repository, not only wiki/.

wiki-lint.py has carried these patterns since the wiki was set up, but it walks
`wiki/**/*.md` and nothing else. That blind spot was found by review, the hard
way: the first hardcoded credential in this repository's history landed in
`molecule/nginx_auth/molecule.yml`, and wiki-lint's own regex matches that line
exactly — it just never looks at the file. A rule nothing enforces outside one
directory is a rule that will be broken outside that directory.

The patterns themselves are imported from wiki-lint rather than copied. Two
lists of secret regexes drift apart, and the one that drifts is always the one
nobody is looking at.

An intentional example is marked the same way as in the wiki: mention Bitwarden
or a variable substitution on the line, or add `secret-lint: allow` with the
reason it is not a secret.
"""

from __future__ import annotations

import importlib.util
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent

# Loaded by path because the file has a hyphen in its name and cannot be
# imported as a module.
_spec = importlib.util.spec_from_file_location("wiki_lint", ROOT / "scripts" / "wiki-lint.py")
_wiki_lint = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(_wiki_lint)

SECRET_PATTERNS = _wiki_lint.SECRET_PATTERNS
looks_intentional = _wiki_lint.looks_intentional

# wiki/ has its own linter, which checks these patterns and more.
SKIP_PREFIXES = ("wiki/", "collections/", ".ruff_cache/")

# Files whose entire purpose is to describe the shape of a secret.
SKIP_FILES = {"scripts/wiki-lint.py", "scripts/secret-lint.py"}

BINARY_SUFFIXES = {".png", ".jpg", ".jpeg", ".gif", ".pdf", ".gz", ".tar", ".zip", ".ico"}

ALLOW_MARKER = "secret-lint: allow"

# An armoured PUBLIC key is base64 from top to bottom, so every line of it looks
# like a leaked secret to a line-based check. Publishing it is the entire point:
# apt uses it to verify that packages were signed by the repository owner, and
# the roles ship it precisely so nobody has to fetch it over plain HTTP.
#
# Recognised by the armour header rather than by filename, and only for the
# PUBLIC variant: `BEGIN PGP PRIVATE KEY BLOCK` is not in this list, so a
# private key committed by accident is still reported line by line.
PUBLIC_ARMOUR = "-----BEGIN PGP PUBLIC KEY BLOCK-----"


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
        if relative.startswith(SKIP_PREFIXES) or relative in SKIP_FILES:
            continue
        if path.suffix.lower() in BINARY_SUFFIXES or not path.is_file():
            continue

        try:
            contents = path.read_text()
        except UnicodeDecodeError:
            continue

        if contents.lstrip().startswith(PUBLIC_ARMOUR):
            continue

        checked += 1
        lines = contents.split("\n")
        for number, line in enumerate(lines, start=1):
            # The marker is honoured on the line above as well, so it can live
            # in the comment that explains the exception rather than trailing
            # the value it excuses — which is where anyone would write it, and
            # where a reviewer would look for the reasoning.
            previous = lines[number - 2] if number >= 2 else ""
            if looks_intentional(line) or ALLOW_MARKER in line or ALLOW_MARKER in previous:
                continue
            for pattern, description in SECRET_PATTERNS:
                if pattern.search(line):
                    errors.append(f"{relative}:{number}: {description} — {line.strip()}")
                    break

    if errors:
        print(f"Похоже на секреты ({len(errors)}):", file=sys.stderr)
        for error in errors:
            print(f"  {error}", file=sys.stderr)
        print(
            f"\nЕсли значение секретом не является, пометьте строку `{ALLOW_MARKER}` "
            "и напишите рядом, почему.",
            file=sys.stderr,
        )
        return 1

    print(f"Секретов не найдено: проверено {checked} файлов вне wiki/.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
