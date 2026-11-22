#!/usr/bin/python3
"""Collect locally; HTTP only reads the cached, non-identifying summary."""
import argparse
import functools
import http.server
import json
import os
from pathlib import Path
import runpy
import subprocess
import time

ROOT = Path('/var/lib/krot-updates')


def age_pending(pending, previous, now, grace):
    """A newer candidate must not grant an already pending package a new grace."""
    seen = {name: previous.get(name, now) for name in pending}
    return seen, sum(now - first >= grace for first in seen.values())


def allowed_updates():
    import apt
    import apt_pkg
    subprocess.run(['/usr/bin/apt-get', 'update', '-o', 'APT::Update::Error-Mode=any'],
                   check=True, timeout=300, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    uu = runpy.run_path('/usr/bin/unattended-upgrade', run_name='krot_unattended')
    origins = uu['get_allowed_origins']()
    if not origins:
        raise ValueError('no unattended origins')
    cache = apt.Cache()
    return pending_packages(cache, lambda ver: uu['is_in_allowed_origin'](ver, origins),
                            apt_pkg.version_compare)


def pending_packages(cache, allowed, compare):
    # Track debt even when held, pinned or otherwise kept back. Download/install
    # failures must not remove a published allowed update from observation.
    return {pkg.fullname for pkg in cache if pkg.is_installed and any(
        compare(ver.version, pkg.installed.version) > 0 and allowed(ver)
        for ver in pkg.versions)}


def restart_count(output):
    if not any(line.startswith('NEEDRESTART-VER:') for line in output.splitlines()):
        raise ValueError('unrecognised needrestart output')
    return sum(line.startswith('NEEDRESTART-SVC:') for line in output.splitlines())


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
        restarts = restart_count(result.stdout)
        atomic(ROOT / 'pending.json', seen, 0o600)
        message = 'ok' if not overdue and not restarts else f'alert updates={overdue} services={restarts}'
    except Exception as error:
        # Never expose exception messages, package names, URLs or subprocess output.
        print(type(error).__name__, flush=True)
        message = 'alert collection-failed'
    atomic(ROOT / 'status.json', {'at': now, 'message': message}, 0o644)


def cached(path, stale_after, now):
    try:
        data = json.loads(path.read_text())
        if not 0 <= now - data['at'] <= stale_after:
            return 'alert stale'
        return data['message']
    except (OSError, ValueError, KeyError, TypeError):
        return 'alert unavailable'


class Handler(http.server.BaseHTTPRequestHandler):
    def __init__(self, *args, stale_after, **kwargs):
        self.stale_after = stale_after
        super().__init__(*args, **kwargs)

    def do_GET(self):
        if self.path != '/':
            self.send_error(404)
            return
        body = (cached(ROOT / 'status.json', self.stale_after, time.time()) + '\n').encode()
        self.send_response(200)
        self.send_header('Content-Type', 'text/plain')
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
