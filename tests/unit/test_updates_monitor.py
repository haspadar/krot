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
    assert check.restart_services('NEEDRESTART-VER: 3.6\nNEEDRESTART-KSTA: 1\nNEEDRESTART-SVC: nginx.service\nNEEDRESTART-SVC: dbus.service\n') == ['nginx.service', 'dbus.service']


def test_unknown_needrestart_output_fails():
    with pytest.raises(ValueError):
        check.restart_services('')


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


def test_collection_keeps_legacy_text_service_count(tmp_path, monkeypatch):
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


def snapshot():
    return {'at': 100, 'message': 'alert updates=2 services=1', 'reboot_required': True,
            'reboot_packages': ['libc6', 'linux-base'], 'running_kernel': '6.8.0-147-generic',
            'restart_services': ['dbus.service'], 'pending_updates': 2}


def test_json_retains_all_facts_when_stale(tmp_path):
    path = tmp_path / 'stale'
    path.write_text(json.dumps(snapshot()))
    expected = {'collected_at': '1970-01-01T00:01:40Z', 'stale': True, 'collection_failed': False,
                **{key: snapshot()[key] for key in check.FACTS}}
    assert check.cached_json(path, 20, 121) == expected


def test_json_is_fresh_at_deadline(tmp_path):
    path = tmp_path / 'deadline'
    path.write_text(json.dumps(snapshot()))
    assert check.cached_json(path, 20, 120)['stale'] is False


@pytest.mark.parametrize('data', [None, '{', '[]', '{"at": true}', '{"at": NaN}',
                                 '{"at": 100, "message": "ok"}',
                                 '{"at": 100, "message": "alert collection-failed"}'])
def test_missing_or_failed_json_does_not_invent_healthy_facts(tmp_path, data):
    path = tmp_path / 'unavailable'
    if data is not None:
        path.write_text(data)
    result = check.cached_json(path, 20, 100)
    assert (result['collection_failed'], [result[key] for key in check.FACTS]) == (True, [None] * 5)


def test_collection_reads_reboot_markers_kernel_and_service_names(tmp_path, monkeypatch):
    monkeypatch.setattr(check, 'ROOT', tmp_path)
    marker = tmp_path / 'reboot'
    marker.touch()
    packages = tmp_path / 'packages'
    packages.write_text('libc6\nlinux-image-6.8.0-149-generic\nlinux-base\n')
    monkeypatch.setattr(check, 'REBOOT', marker)
    monkeypatch.setattr(check, 'REBOOT_PACKAGES', packages)
    monkeypatch.setattr(check.platform, 'release', lambda: '6.8.0-147-generic')
    monkeypatch.setattr(check, 'allowed_updates', lambda: set())
    monkeypatch.setattr(check.subprocess, 'run', lambda *args, **kwargs: NeedrestartResult())
    check.collect(172800)
    data = json.loads((tmp_path / 'status.json').read_text())
    assert {key: data[key] for key in check.FACTS} == {
        'reboot_required': True,
        'reboot_packages': ['libc6', 'linux-image-6.8.0-149-generic', 'linux-base'],
        'running_kernel': '6.8.0-147-generic', 'restart_services': ['php-fpm.service'], 'pending_updates': 0}


@pytest.mark.parametrize('header,expected', [
    ('', False), ('*/*', False), ('application/json', True),
    ('application/json;q=0', False), ('application/json;q=garbage', False),
    ('application/json;q=NaN', False), ('application/json;q=2', False),
    ('text/plain, application/json;q=0.1', False),
    ('text/*, application/json;q=0.4', False),
    ('application/json;q=0.8, text/plain;q=0.2', True),
    ('Application/JSON; charset=utf-8', True),
])
def test_only_acceptable_explicit_json_opts_into_names(header, expected):
    assert check.accepts_json(header) is expected
