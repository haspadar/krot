# Proposal: scanners that do not call themselves bots

## Why

`/traffic/humans/berlindame.de` showed **41 unique visitors** against roughly ten live people.
`--ignore-crawlers` filters out only those that **called themselves** a bot — the User-Agent
contains `bot`, `crawler` or `spider`. Half of the scanners do not call themselves that.

Measurement on berlindame.de (1116 lines, 2026-08-02):

```
UptimeRobot     462 requests   ← our own monitor, more than all the rest combined
curl            118
GoogleOther      94            ← this is Google, there is no word "bot" in the string
Dataprovider     46            ← a commercial scanner
HeadlessChrome   25            ← a browser driven by a script
```

A figure inflated fourfold is worse than a missing one: it looks trustworthy, and decisions are
made on it.

## What Changes

### Our own list on top of the stock one

GoAccess 1.8.1 accepts `-b <file>` — lines of the form `name<TAB>Crawlers`. The list lives in the
variable `goaccess_extra_crawlers` and is expanded into `/etc/goaccess/krot-crawlers.list`: it
will grow, and adding to it must not require editing the role's template.

### Only the human report

The flag is passed to the second GoAccess run rather than written into the parser config: the
config is shared by both reports, and the full one counts crawlers deliberately — it answers the
question "is the site being crawled at all".

### Changing the list rebuilds the reports immediately

Otherwise the new filter would wait for the timer for up to an hour, and until then the report
would show the old figures while looking fresh.

## Impact

- berlindame.de: 41 → **36**, stadtdame.de: 26 → **20**.
- `GoogleOther`, `Dataprovider`, `UptimeRobot`, `HeadlessChrome`, `curl` disappeared from the
  human report; the browser list is left with Chrome, Safari, Firefox, Edge.
- In the full report they are all still visible.
- **The task expected ~30, the result was 36.** The difference is not in the list: some scanners
  travel disguised as an ordinary Chrome, and by User-Agent they cannot be told apart in
  principle. This is the limit of the method, not an omission; going further would mean counting
  browsing depth, and that is no longer an agent filter.
- The file is included only if it is readable. An unreadable one would make GoAccess exit, and
  losing the human report because of a missing list is worse than a report with extra bots.
