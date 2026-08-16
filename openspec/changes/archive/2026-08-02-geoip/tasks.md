# Tasks: the geoip role and geography in reports

## Role `geoip`
- [x] `geoipupdate` from the Ubuntu repository (6.1.0), `libmaxminddb0` was already there
- [x] `assert` on empty keys: without them `geoipupdate` writes an error instead of the database,
      and this is discovered only as a report without geography
- [x] `/etc/GeoIP.conf` — `0600 root`, task `no_log`, otherwise the key goes into every run's
      output
- [x] A one-off download during the role run, not a wait for the timer (it may be a day away)
- [x] systemd timer (daily) + oneshot service with `ProtectSystem=strict`
- [x] The package's stock timer is disabled — two schedules over the same files

## Role `goaccess`
- [x] `goaccess_geoip_database`, empty by default — the database is installed by a different role
- [x] **Refusal if the database file does not exist.** GoAccess would not start in that case, all
      reports would stall, and the built ones would keep looking fresh. Verified: with a
      non-existent path the run fails naming the file, before the config is written
- [x] The `cf=` header is still skipped: GoAccess has no field for a ready-made country code
- [x] The role description in `meta` fixed — it still promised loopback and basic auth

## Project busel
- [x] `geoip_account_id` / `geoip_license_key` from Bitwarden (Secure Note `maxmind`), parsed by a
      case-insensitive regex — the labels were typed by hand
- [x] The `geoip` role in `site.yml` **before** `goaccess`
- [x] **The `goaccess` role wired into `site.yml`** — until now it was not there at all, it stood
      on the machine from a manual run

## Verification on a live machine
- [x] Database `/var/lib/GeoIP/GeoLite2-Country.mmdb`, 8.4 MB
- [x] `/etc/GeoIP.conf` — `600 root:root`
- [x] `krot-geoipupdate.timer` active, next run visible; `geoipupdate.timer` — `disabled`
- [x] Panel in the report: Europe 139, North America 115, Asia 31
- [x] By country: USA 114, Switzerland 68, Poland 30, China 27, Finland 26, Belarus, Germany,
      Netherlands, France, Japan, Indonesia, Canada
- [x] **Cross-checked against `cf=`**: the orders of magnitude match, so real-IP works and the
      geography is genuine, not Cloudflare data centres
- [x] Repeat run of both roles — `changed=0`
- [x] `yamllint`, `ansible-lint` (profile production) clean

## False alarms
- [x] `grep -c '"geolocation"'` in the HTML returned 0 — a faulty search pattern, the panel is
      there
- [x] "Download the databases" in 1.38s looked suspiciously fast for 4 MB — on disk it turned out
      to be 8.4 MB, the download was genuine

## Deliberately not done
- [ ] `GeoLite2-City` — heavier to download, and cities are not shown in 1.8.1 anyway (they
      appeared in 1.10). Revisit together with the upgrade to 1.11
- [ ] Taking the country from `CF-IPCountry` — would require occupying a column with a different
      meaning, and the panel would be called "Virtual Hosts" while showing countries
