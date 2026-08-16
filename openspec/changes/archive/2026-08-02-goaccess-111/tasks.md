# Tasks: GoAccess 1.11 and cities

## Role `goaccess`
- [x] `goaccess_upstream_repository`, enabled by default; the key embedded in `files/`
- [x] The key fingerprint verified before putting it into the repository:
      `C03B4888 7D5E56B0 46715D32 97BD1A01 33449C3D`, Gerardo Orellana — the author of GoAccess
- [x] `state: latest` only while the repository is enabled
- [x] Disabling removes the repository; it does not downgrade the version — written down in
      defaults and README

## Role `geoip`
- [x] `GeoLite2-City` instead of `GeoLite2-Country` (the edition carries both levels)
- [x] Removal of databases that are not in `geoip_editions`

## Verification on a live machine
- [x] The repository serves `1:1.11-noble` for noble — checked before the changes
- [x] `goaccess --version` → 1.11
- [x] **Cities in real reports**: London 6, Amsterdam 5, Warsaw 5, Minsk 4, Berlin 2,
      Frankfurt 2, Hamburg 2
- [x] Countries in place, the crawler filter intact (`GoogleOther` filtered out)
- [x] The old Country database removed by the run, one City database left
- [x] Pointing at a removed database stops the run with a clear message
- [x] Disabling the repository removes its file; 1.11 remains — as expected
- [x] Repeat run of both roles — `changed=0`
- [x] `yamllint`, `ansible-lint` (profile production) clean

## Found by a run
- [x] **`state: present` did not update the version.** The repository was added, the role reported
      success, and `goaccess --version` showed 1.8.1 with 1.11 as the candidate. A silent failure:
      everything "went through", but no upgrade happened
- [x] **`-o json` from stdin in 1.11 returns zero bytes.** The measurement scripts that read JSON
      stopped working; the reports are unaffected — the check was moved to HTML
- [x] **The HTML markup changed**: the previous search patterns stopped finding the numbers and
      panels. The reports are intact though — `unique_visitors: 40`, countries and cities in place
- [x] The reports grew from ~620 KB to ~2 MB — new markup and a dark theme

## Not confirmed
- [ ] **A 35% parsing speed-up and 20% less memory** from the changelog. There is a measurement on
      1.11 (1.3 s on 2673 lines, 12 MB peak), there is no comparable measurement on 1.8.1 — there
      it was "under a second" on 1919 lines with no memory data. Neither confirmed nor refuted
