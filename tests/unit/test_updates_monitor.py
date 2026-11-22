"""Deterministic policy tests, independent of the machine's package database."""
import importlib.util
import json
from pathlib import Path

import pytest

spec = importlib.util.spec_from_file_location(
    'updates_check', Path(__file__).resolve().parents[2] / 'roles/updates_monitor/files/check.py')
check = importlib.util.module_from_spec(spec)
spec.loader.exec_module(check)


def test_continuously_pending_package_keeps_age():
    assert check.age_pending({'php'}, {'php': 10}, 60, 50) == ({'php': 10}, 1)


def test_new_package_gets_grace():
    assert check.age_pending({'nginx'}, {}, 80, 50) == ({'nginx': 80}, 0)


def test_installed_updates_leave_history():
    assert check.age_pending(set(), {'openssl': 3}, 100, 50) == ({}, 0)


def test_just_before_deadline_is_healthy():
    assert check.age_pending({'curl'}, {'curl': 4}, 53, 50)[1] == 0


def test_restart_requests_are_not_kernel_or_session_lines():
    assert check.restart_count('NEEDRESTART-VER: 3.6\nNEEDRESTART-KSTA: 1\nNEEDRESTART-SVC: nginx.service\n') == 1


def test_unknown_needrestart_output_fails():
    with pytest.raises(ValueError):
        check.restart_count('')


@pytest.mark.parametrize('age,expected', [(0, 'ok'), (10800, 'ok'), (10801, 'alert stale'), (-1, 'alert stale')])
def test_cached_freshness(tmp_path, age, expected):
    path = tmp_path / 'status'
    path.write_text(json.dumps({'at': 20000 - age, 'message': 'ok'}))
    assert check.cached(path, 10800, 20000) == expected


def test_missing_cache_is_not_healthy(tmp_path):
    assert check.cached(tmp_path / 'absent', 60, 100) == 'alert unavailable'


def test_broken_history_does_not_reset_grace(tmp_path, monkeypatch):
    monkeypatch.setattr(check, "ROOT", tmp_path)
    (tmp_path / 'pending.json').write_text('{')
    check.collect(48)
    assert json.loads((tmp_path / 'status.json').read_text())['message'] == 'alert collection-failed'


class NeedrestartResult:
    stdout = 'NEEDRESTART-VER: 3.6\nNEEDRESTART-SVC: php-fpm.service\n'


def test_collection_reports_service_debt_without_names(tmp_path, monkeypatch):
    monkeypatch.setattr(check, 'ROOT', tmp_path)
    monkeypatch.setattr(check, 'allowed_updates', lambda: set())
    monkeypatch.setattr(check.subprocess, 'run', lambda *args, **kwargs: NeedrestartResult())
    check.collect(172800)
    assert json.loads((tmp_path / 'status.json').read_text())['message'] == 'alert updates=0 services=1'


def test_failed_apt_inspection_invalidates_old_health(tmp_path, monkeypatch):
    monkeypatch.setattr(check, 'ROOT', tmp_path)
    (tmp_path / 'status.json').write_text('{"at": 1, "message": "ok"}')

    def broken_repository():
        raise OSError('repository URL must never leak')

    monkeypatch.setattr(check, 'allowed_updates', broken_repository)
    check.collect(172800)
    assert json.loads((tmp_path / 'status.json').read_text())['message'] == 'alert collection-failed'


class Version:
    def __init__(self, number, origin):
        self.version = number
        self.origin = origin


class Package:
    def __init__(self, name, installed, versions):
        self.fullname = name
        self.installed = installed
        self.is_installed = installed is not None
        self.versions = versions


def test_only_newer_allowed_versions_of_installed_packages_are_pending():
    installed = Version(3, 'local')
    cache = [
        Package('curl', installed, [Version(4, 'security')]),
        Package('vim', installed, [Version(8, 'updates')]),
        Package('zlib', installed, [Version(2, 'security')]),
        Package('nano', None, [Version(9, 'security')]),
        # A newer disallowed candidate must not hide a still pending security update.
        Package('openssl', installed, [Version(6, 'ppa'), Version(5, 'security')]),
    ]
    assert check.pending_packages(cache, lambda v: v.origin == 'security',
                                  lambda left, right: left - right) == {'curl', 'openssl'}


class AptUpdate:
    def __init__(self, failures):
        self.failures = failures
        self.succeeded = False

    def __call__(self, *args, **kwargs):
        if self.failures:
            self.failures -= 1
            raise check.subprocess.CalledProcessError(100, 'apt-get')
        self.succeeded = True


def test_transient_apt_lock_is_retried():
    apt = AptUpdate(1)
    check.refresh_indexes(run=apt, pause=lambda seconds: None)
    assert apt.succeeded


def test_persistent_apt_failure_is_not_hidden():
    with pytest.raises(check.subprocess.CalledProcessError):
        check.refresh_indexes(run=AptUpdate(9), pause=lambda seconds: None)
