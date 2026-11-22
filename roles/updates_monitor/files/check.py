#!/usr/bin/python3
"""Collect locally; HTTP only reads the cached machine facts."""
import argparse
from datetime import datetime, timezone
import functools
import http.server
import json
import os
import math
import platform
from pathlib import Path
import runpy
import subprocess
import time

ROOT = Path('/var/lib/krot-updates')
REBOOT = Path('/var/run/reboot-required')
REBOOT_PACKAGES = Path('/var/run/reboot-required.pkgs')
FACTS = ('reboot_required', 'reboot_packages', 'running_kernel', 'restart_services', 'pending_updates')


def age_pending(pending, previous, now, grace):
    """A newer candidate must not grant an already pending package a new grace."""
    seen = {name: previous.get(name, now) for name in pending}
    return seen, sum(now - first >= grace for first in seen.values())


def allowed_updates():
    import apt
    import apt_pkg
    refresh_indexes()
    uu = runpy.run_path('/usr/bin/unattended-upgrade', run_name='krot_unattended')
    origins = uu['get_allowed_origins']()
    if not origins:
        raise ValueError('no unattended origins')
    cache = apt.Cache()
    return pending_packages(cache, lambda ver: uu['is_in_allowed_origin'](ver, origins),
                            apt_pkg.version_compare)


def refresh_indexes(run=subprocess.run, pause=time.sleep):
    # APT's lists lock has no DPkg::Lock::Timeout equivalent. Retry transient
    # apt-daily contention, but bound the whole collection below its unit timeout.
    for delay in (5, 15, None):
        try:
            run(['/usr/bin/apt-get', 'update', '-o', 'APT::Update::Error-Mode=any'],
                check=True, timeout=120, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            return
        except (subprocess.SubprocessError, OSError):
            if delay is None:
                raise
            pause(delay)


def pending_packages(cache, allowed, compare):
    # Track debt even when held, pinned or otherwise kept back. Download/install
    # failures must not remove a published allowed update from observation.
    return {pkg.fullname for pkg in cache if pkg.is_installed and any(
        compare(ver.version, pkg.installed.version) > 0 and allowed(ver)
        for ver in pkg.versions)}


def restart_services(output):
    if not any(line.startswith('NEEDRESTART-VER:') for line in output.splitlines()):
        raise ValueError('unrecognised needrestart output')
    return [line.split(':', 1)[1].strip() for line in output.splitlines()
            if line.startswith('NEEDRESTART-SVC:')]


def atomic(path, value, mode):
    tmp = path.with_suffix('.tmp')
    with tmp.open('w') as stream:
        os.chmod(tmp, mode)
        json.dump(value, stream)
    tmp.replace(path)


def collect(grace):
    now = time.time()
    try:
        # Missing history grants the documented first-install grace; corrupt history
        # is an error, never a silent reset of every package's age.
        previous = json.loads((ROOT / 'pending.json').read_text()) if (ROOT / 'pending.json').exists() else {}
        pending = allowed_updates()
        seen, overdue = age_pending(pending, previous, now, grace)
        result = subprocess.run(['/usr/sbin/needrestart', '-b', '-r', 'l'],
                                check=True, capture_output=True, text=True, timeout=120)
        services = restart_services(result.stdout)
        reboot = REBOOT.exists()
        packages = REBOOT_PACKAGES.read_text().splitlines() if reboot and REBOOT_PACKAGES.exists() else []
        facts = {'reboot_required': reboot, 'reboot_packages': packages,
                 'running_kernel': platform.release(), 'restart_services': services,
                 'pending_updates': overdue}
        restarts = len(services)
        atomic(ROOT / 'pending.json', seen, 0o600)
        message = 'ok' if not overdue and not restarts else f'alert updates={overdue} services={restarts}'
    except Exception as error:
        # Never expose exception messages, package names, URLs or subprocess output.
        print(type(error).__name__, flush=True)
        message = 'alert collection-failed'
        facts = dict.fromkeys(FACTS)
    atomic(ROOT / 'status.json', {'at': now, 'message': message, **facts}, 0o644)


def cached(path, stale_after, now):
    try:
        data = json.loads(path.read_text())
        if not 0 <= now - data['at'] <= stale_after:
            return 'alert stale'
        return data['message']
    except (OSError, ValueError, KeyError, TypeError):
        return 'alert unavailable'


def cached_json(path, stale_after, now):
    payload = {'collected_at': None, 'stale': True, 'collection_failed': True,
               **dict.fromkeys(FACTS)}
    try:
        data = json.loads(path.read_text())
        at = data['at']
        if isinstance(at, bool) or not isinstance(at, (float, int)) or not math.isfinite(at):
            return payload
        payload['collected_at'] = datetime.fromtimestamp(at, timezone.utc).isoformat().replace('+00:00', 'Z')
        payload['stale'] = not 0 <= now - at <= stale_after
        if data['message'] == 'alert collection-failed':
            return payload
        # Legacy snapshots and malformed facts cannot masquerade as healthy JSON.
        if (type(data['reboot_required']) is not bool
                or not isinstance(data['running_kernel'], str) or not data['running_kernel']
                or type(data['pending_updates']) is not int or data['pending_updates'] < 0
                or any(not isinstance(data[key], list) or any(not isinstance(name, str) or not name
                       for name in data[key]) for key in ('reboot_packages', 'restart_services'))):
            return payload
        payload.update({key: data[key] for key in FACTS})
        payload['collection_failed'] = False
        return payload
    except (OSError, ValueError, KeyError, TypeError, OverflowError):
        return payload


def accepts_json(header):
    # Only explicit JSON requests opt in; honour exclusions and text preference.
    quality = {}
    for representation in header.lower().split(','):
        media, *parameters = representation.split(';')
        score = 1.0
        for parameter in parameters:
            key, _, value = parameter.partition('=')
            if key.strip() == 'q':
                try:
                    score = float(value.strip())
                except ValueError:
                    score = 0.0
        score = score if 0 <= score <= 1 else 0.0
        media = media.strip()
        quality[media] = max(quality.get(media, 0), score)
    text = quality.get('text/plain', quality.get('text/*', quality.get('*/*', 0)))
    return quality.get('application/json', 0) > 0 and quality['application/json'] >= text


class Handler(http.server.BaseHTTPRequestHandler):
    def __init__(self, *args, stale_after, **kwargs):
        self.stale_after = stale_after
        super().__init__(*args, **kwargs)

    def do_GET(self):
        if self.path != '/':
            self.send_error(404)
            return
        wants_json = accepts_json(self.headers.get('Accept', ''))
        now = time.time()
        value = (json.dumps(cached_json(ROOT / 'status.json', self.stale_after, now)) if wants_json
                 else cached(ROOT / 'status.json', self.stale_after, now))
        body = (value + '\n').encode()
        self.send_response(200)
        self.send_header('Content-Type', 'application/json' if wants_json else 'text/plain')
        self.send_header('Vary', 'Accept')
        self.send_header('Cache-Control', 'no-store')
        self.send_header('Content-Length', str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, *args):
        pass


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('mode', choices=['collect', 'serve'])
    parser.add_argument('--grace', type=int, default=172800)
    parser.add_argument('--stale', type=int, default=10800)
    parser.add_argument('--port', type=int, default=9854)
    args = parser.parse_args()
    if args.mode == 'collect':
        collect(args.grace)
    else:
        http.server.HTTPServer(('127.0.0.1', args.port),
                               functools.partial(Handler, stale_after=args.stale)).serve_forever()
