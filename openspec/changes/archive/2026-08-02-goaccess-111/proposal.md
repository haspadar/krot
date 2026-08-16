# Proposal: GoAccess 1.11 and cities in geolocation

## Why

Ubuntu 24.04 gives GoAccess 1.8.1, the project has released 1.11 (19 July 2026). The upgrade is
needed not for the version number, but for two things:

- **cities in geolocation** — they appeared in 1.10, on 1.8.1 the City database gives nothing
  beyond the country;
- per the changelog — parsing 35% faster, 20% less memory; this will come in handy once there are
  thirty sites.

Crawlers are not touched by 1.11 at all — our filter stays.

## What Changes

### The official repository, key embedded

`goaccess_upstream_repository`, enabled by default. The signing key lives in the role's files
(fingerprint `C03B48887D5E56B046715D3297BD1A0133449C3D`, Gerardo Orellana — the author of
GoAccess), rather than being downloaded at runtime: provisioning must not depend on a keyserver
being reachable. The same scheme as ondrej in the `php` role.

### `state: latest`, while the repository is enabled

Discovered by a run: with `present` the role, on a machine with 1.8.1 already installed, added
the repository, reported success — and left the old version in place. `present` means "the
package exists", not "the package is fresh". Without the repository it stays `present`, so that
the role does not silently upgrade the distribution's package.

### `GeoLite2-City` instead of `GeoLite2-Country`

City carries both levels — a separate Country database is not needed. 64 MB against 8.4: that is
the whole price of cities.

### `geoip` removes databases that are not on the list

Switching editions left the old file lying around. A copy of exactly the file someone may be
looking at, which has stopped being updated, is worse than a missing one: it answers, but
incorrectly, and there is no way to tell from it how stale it is.

## Impact

- **Cities in the reports**: on busel's logs — London, Amsterdam, Warsaw, Minsk, Berlin,
  Frankfurt, Hamburg. Countries were preserved as well.
- The reports grew from ~620 KB to ~2 MB: 1.11 has its own markup and a dark theme.
- Measurement on 1.11: three sites, 2673 lines — 1.3 s; peak memory of a single report — 12 MB.
  **The claimed speed-up is neither confirmed nor refuted**: no comparable measurement on 1.8.1
  was kept, there it was "under a second" on 1919 lines with no memory data.
- `-o json` in 1.11 returns nothing when reading from stdin — this does not affect the reports
  themselves, but the measurement scripts that read JSON had to be replaced with an HTML check.
- **Disabling the repository does not downgrade the version.** Apt does not downgrade on its own,
  and the role does not do it deliberately: silently replacing a working binary with an older one
  is not what was asked for.
