"""Exercise the installed unattended-upgrade matcher against the real PPA."""

import runpy
import sys

import apt


cache = apt.Cache()
candidate = cache["php8.5-common"].candidate
assert candidate is not None, "У PHP нет кандидата в apt"
ppa_origins = [
    origin
    for origin in candidate.origins
    if origin.origin == "LP-PPA-ondrej-php" and origin.codename == "noble"
]
assert ppa_origins, candidate.origins

unattended = runpy.run_path("/usr/bin/unattended-upgrade", run_name="krot_origin_probe")
allowed = unattended["get_allowed_origins"]()
# An already installed candidate also has the local dpkg origin, which
# unattended-upgrade always allows. Check its actual PPA origin, not `now`.
permitted = any(
    unattended["is_allowed_origin"](origin, allowed) for origin in ppa_origins
)
assert permitted == (sys.argv[1] == "enabled"), (permitted, allowed)
print(f"Кандидат PHP {candidate.version}: разрешён={permitted}; источники={allowed}")
