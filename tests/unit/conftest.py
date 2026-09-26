"""Runs the collection's modules in-process against fake services.

The modules import each other as `ansible_collections.haspadar.krot...`, so the
repository has to be importable under that name. A symlink in a temporary
directory does it without installing the collection or moving the checkout,
and keeps the tests on the files being edited rather than on an installed copy.
"""

import importlib
import json
import os
import sys
import tempfile

import pytest

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
_NAMESPACE = tempfile.mkdtemp(prefix="krot-units-")
os.makedirs(os.path.join(_NAMESPACE, "ansible_collections", "haspadar"))
os.symlink(ROOT, os.path.join(_NAMESPACE, "ansible_collections", "haspadar", "krot"))
sys.path.insert(0, _NAMESPACE)
sys.path.insert(0, os.path.join(ROOT, "tests"))

from ansible.module_utils.testing import patch_module_args  # noqa: E402

from fakes.server import FakeServer  # noqa: E402


@pytest.fixture(autouse=True)
def pauses(monkeypatch):
    """Every sleep the modules take, in seconds, without taking it."""
    taken = []
    monkeypatch.setattr("time.sleep", taken.append)
    return taken


@pytest.fixture
def serve():
    started = []

    def start(app):
        server = FakeServer(app)
        started.append(server)
        return server

    yield start
    for server in started:
        server.close()


@pytest.fixture
def run(capsys):
    """Runs a module's main() and returns what it reported to Ansible."""

    def call(name, args, check=False):
        module = importlib.import_module("ansible_collections.haspadar.krot.plugins.modules." + name)
        args = dict(args, _ansible_check_mode=check)
        with patch_module_args(args):
            with pytest.raises(SystemExit):
                module.main()
        return json.loads(capsys.readouterr().out)

    return call
