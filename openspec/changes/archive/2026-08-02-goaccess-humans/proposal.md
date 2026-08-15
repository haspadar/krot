# Proposal: a second GoAccess report — "humans only"

## Why

The full report does not answer the question the statistics are opened for: **how many people
came**. Measurement on the live berlindame.de (2026-08-02):

| mode | Unique Visitors |
|------|-----------------|
| as it stands (`ignore-crawlers false`) | **94** |
| `--ignore-crawlers` | **37** |
| `--ignore-crawlers --unknowns-as-crawlers` | 36 |

57 of the 94 "visitors" are crawlers. On stadtdame.de the picture is the same: 47 against 25.

At the same time `ignore-crawlers false` stays in the main report: on a site behind Cloudflare
most of the early traffic is bots, and a report without them looks like an absence of traffic
rather than the traffic that is actually there. For a young site "does Googlebot come and what is
it indexing" is worth more than the number of people.

So both are needed, not one replacing the other.

## What Changes

### A second file, the same parser config

`--ignore-crawlers` filters **log lines**, it does not select panels. Referrers, geography, pages
— the same sections in both reports, computed over a different set of visitors. There is
deliberately no second parser config: two configs drift apart.

### A subdirectory, not a suffix in the name

`humans/<domain>.html`, not `<domain>-humans.html`. Busel serves the reports at the route
`/traffic` and parses the file names with the glob `*.html`, treating the result as a domain. With
a suffix the second file would appear in the list as a separate "site" row, and busel would have
to strip a substring — and a domain that itself ends in `-humans` would break the parsing. A
subdirectory does not match `*.html` at all, so the existing busel code keeps working unchanged.

Permissions are inherited by the same mechanism as for `.build/`: setgid on the reports directory
supplies the reader group, because the writing account is deliberately not a member of it.

### The logs are read once

The parsed lines are collected into a temporary file and fed to both GoAccess runs. There is no
point unpacking two weeks of rotated `.gz` files a second time.

### `--unknowns-as-crawlers` is not taken

In the measurement it shifted the count by one visit out of 37. That is not worth a variable whose
meaning the reader would have to work out.

## Impact

- Twice as many reports on disk. Space: ~640 KB for the second file at 1082 log lines.
- The build takes twice as long in GoAccess (log reading does not double) — at the current volume
  still under a second for all sites.
- **Report deletion now walks both directories.** The report of a removed domain in `humans/`
  would otherwise lie there forever, continuing to name the domain and its traffic — precisely
  what the cleanup loop protects against. The same on `parseable = 0` or a failed build: the pair
  is deleted as a whole, so that no half frozen at the previous run hangs next to a fresh page.
- Switching off `goaccess_humans_report` removes the directory: the pages in it would otherwise
  stop being updated but keep being served.
