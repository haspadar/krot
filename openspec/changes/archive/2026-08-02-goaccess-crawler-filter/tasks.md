# Tasks: a scanner filter for the human report

## Role
- [x] `goaccess_extra_crawlers` — the list in a variable, not in the template: it will grow
- [x] Template `crawlers.j2` → `/etc/goaccess/krot-crawlers.list`
- [x] The `-b` flag only on the human run; the parser config untouched — it is shared by both
      reports
- [x] The file is included only if readable: an unreadable one takes GoAccess down, and a report
      with extra bots is better than no report at all
- [x] Changing the list triggers a rebuild within the same run

## Verification on a live machine
- [x] berlindame.de **41 → 36**, stadtdame.de **26 → 20**
- [x] Verified against the reports themselves, not against the config: `GoogleOther`,
      `Dataprovider`, `UptimeRobot`, `HeadlessChrome`, `curl` are absent from the human report
- [x] In the full report `GoogleOther` and `UptimeRobot` are in place — `ignore-crawlers false`
      untouched
- [x] Repeat run of the role — `changed=0`
- [x] `shellcheck`, `yamllint`, `ansible-lint` (profile production) clean

## Found by testing, not by reading
- [x] **The type is written `Crawlers`, not `crawler`.** The task suggested lowercase in the
      singular; in the stock `/etc/goaccess/browsers.list` it is `Crawlers`. With the wrong
      spelling GoAccess creates a new browser category, and the counter **grows**: measured, 41
      turned into 78. The list from the task taken literally would have had the opposite effect
- [x] **`-b` supplements the stock list rather than replacing it.** Verified by merging: stock +
      ours gives the same 36 as our file alone. There is no need to concatenate
- [x] **Two that were not in the task.** `UptimeRobot` — 462 requests out of 1116, more than all
      the rest combined, this is our own monitor; `HeadlessChrome` — a browser under a script,
      masquerading as an ordinary one

## Decisions
- [x] `UptimeRobot` on the list: our own monitor is not a reader, and its share is higher than
      that of all the real bots
- [ ] Getting down to ~30, as the task expected — **impossible by this means**: the remainder
      travels disguised as an ordinary Chrome. It would require filtering by browsing depth, and
      that is no longer an agent filter
- [ ] `--unknowns-as-crawlers` — still rejected, the decision from the previous task stands
- [ ] Upgrading to GoAccess 1.11 — **as a separate pass**. Per the changelog 1.9–1.11 do not
      touch crawlers at all (geolocation, persistence, translations, crashes), but memory is 20%
      lower and parsing 35% faster. It requires wiring in the official GoAccess repository, like
      ondrej for PHP — a change of its own with its own risk
