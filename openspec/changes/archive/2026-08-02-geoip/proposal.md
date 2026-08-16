# Proposal: geography in traffic reports

## Why

The report shows how many people came and where from by referrer, but does not show **where from
geographically**. For a network of sites targeting specific cities this matters: berlindame is a
Berlin site, and the share of visitors from Germany answers the question of whether the site is
reaching its own audience.

## What Changes

### A separate `geoip` role, not part of `goaccess`

The address → country lookup database is needed not only by reports, and a machine may well want
one without the other. The role installs `geoipupdate`, drops in a config with the key and sets
up a timer: MaxMind updates GeoLite2 twice a week, a daily check costs one conditional request.

The package's stock Ubuntu timer is disabled — two schedules over the same files would mean that
with a stale database you would have to work out which of them ran.

### The key comes from the project

`geoip_account_id` and `geoip_license_key` are empty in the role and are filled in from the
project's secret store — the same scheme as `nginx_auth_password`. The role knows it needs a key,
but does not know where it is kept, and stays portable.

The config `/etc/GeoIP.conf` is `0600 root`, the task is marked `no_log`: otherwise the key would
be printed into the output of every run.

### Country from the database, not from the Cloudflare header

The logs already carry `cf=XX` from Cloudflare, and the temptation to take what is ready is
strong. But GoAccess has no field to accept a country code into: the only way is to occupy a
column with a different meaning (for example `%v`, the virtual host), and then the panel would be
called "Virtual Hosts" while showing countries, and the real host would disappear from the
report. So `cf=` is still skipped via `%^`.

### Refusal instead of silent breakage

GoAccess does not start if the database is named in the config and missing from disk. That would
take down **all** of the machine's reports at once, and the already built ones would keep lying
around looking fresh. The role checks the file before writing the config and stops, naming the
path.

## Impact

- A geolocation panel in both reports: the full one and the human one. It is shared —
  `--ignore-crawlers` filters lines, not sections.
- Measurement on berlindame.de: Europe 139 visits, North America 115, Asia 31. By country —
  USA 114, Switzerland 68, Poland 30, China 27, Finland 26, plus Belarus, Germany, Japan.
- **Correct only because the project configures real-IP** from the Cloudflare headers. Without
  that the log would carry the CDN's address, and the panel would show its data centres —
  plausible and wrong. Verified by cross-checking against `cf=`: the orders of magnitude match.
- 8.4 MB of database on disk, updated once a day with a single conditional request.
- The `goaccess` role is finally wired into busel's `site.yml` — until now it stood on the machine
  from a manual run, and on a new machine it would not have been there.
