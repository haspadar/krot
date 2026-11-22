"""Exercise the installed unattended-upgrade matcher against the real Sury repository."""

import runpy
import sys

import apt
import apt_pkg


cache = apt.Cache()
candidate = cache["php8.5-common"].candidate
assert candidate is not None, "У PHP нет кандидата в apt"
ppa_origins = [
    origin
    for origin in candidate.origins
    if origin.origin == "deb.sury.org" and origin.codename == "noble"
]
assert ppa_origins, candidate.origins

unattended = runpy.run_path("/usr/bin/unattended-upgrade", run_name="krot_origin_probe")
allowed = unattended["get_allowed_origins"]()
# An already installed candidate also has the local dpkg origin, which
# unattended-upgrade always allows. Check its actual Sury origin, not `now`.
permitted = any(
    unattended["is_allowed_origin"](origin, allowed) for origin in ppa_origins
)
assert permitted == (sys.argv[1] == "enabled"), (permitted, allowed)
print(f"Кандидат PHP {candidate.version}: разрешён={permitted}; источники={allowed}")

# The collector uses the same real unattended matcher. Simulate an older
# installed version of the actual candidate to check pending debt without
# depending on an upstream patch being published during this test.
from types import SimpleNamespace

monitor = runpy.run_path("/srv/krot-probe/updates-check.py", run_name="krot_monitor_probe")
package = SimpleNamespace(
    fullname="php8.5-common", is_installed=True,
    installed=SimpleNamespace(version="0"),
    # A genuinely newer version has no local dpkg origin. The candidate is
    # installed already after converge, so retain only its repository origin.
    versions=[SimpleNamespace(version=candidate.version, origins=ppa_origins)],
)
pending = monitor["pending_packages"](
    [package], lambda version: unattended["is_in_allowed_origin"](version, allowed),
    apt_pkg.version_compare,
)
assert pending == ({"php8.5-common"} if sys.argv[1] == "enabled" else set()), pending
