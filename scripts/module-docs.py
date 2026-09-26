#!/usr/bin/env python3
"""Every module's documentation parses, as ansible-doc reads it.

DOCUMENTATION is YAML inside a Python string, so nothing else in CI looks at it:
yamllint skips .py files, ansible-lint lints playbooks, pytest imports the module
and never parses the string. A colon followed by a space in a description is
enough to break it, and the only symptom is `ansible-doc` refusing the module —
which is what a consumer runs, not this repository. Found on 2026-09-26 in a
module already on main, after a review fix added one sentence.

The collection is exposed under its namespace through a symlink in a temporary
directory, the same way the unit tests import it.
"""

import json
import os
import subprocess
import sys
import tempfile

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
MODULES = os.path.join(ROOT, "plugins", "modules")


def main():
    names = sorted(name[:-3] for name in os.listdir(MODULES) if name.endswith(".py") and not name.startswith("_"))
    if not names:
        print("Модулей не найдено в plugins/modules/ — проверять нечего, а это само по себе ошибка.")
        return 1

    with tempfile.TemporaryDirectory(prefix="krot-docs-") as place:
        os.makedirs(os.path.join(place, "ansible_collections", "haspadar"))
        os.symlink(ROOT, os.path.join(place, "ansible_collections", "haspadar", "krot"))
        env = dict(os.environ, ANSIBLE_COLLECTIONS_PATH=place)
        broken = []
        for name in names:
            run = subprocess.run(["ansible-doc", "-j", "haspadar.krot." + name], env=env,
                                 stdin=subprocess.DEVNULL, capture_output=True, text=True)
            try:
                documented = run.returncode == 0 and "haspadar.krot." + name in json.loads(run.stdout)
            except ValueError:
                documented = False
            if not documented:
                broken.append((name, run.stderr.strip() or run.stdout.strip()))

    for name, reason in broken:
        print("Справка %s не разбирается:\n  %s" % (name, reason.replace("\n", "\n  ")))
    print("Справка модулей: %d из %d разбирается." % (len(names) - len(broken), len(names)))
    return 1 if broken else 0


if __name__ == "__main__":
    sys.exit(main())
