# Tasks: second "humans only" report

## Role
- [x] `goaccess_humans_report` (**enabled** by default) and `goaccess_humans_subdir`
- [x] The variables go into the unit (`Environment=`) and into the role's one-off build —
      otherwise the timer and Ansible would build different things
- [x] The `humans/` directory is created by the builder under `REPORT_DIR`, inheriting setgid and
      the group
- [x] The parsed lines are written to a temporary file and fed to both runs — the logs are read
      once
- [x] The full report is put in place first, the humans one after it: a fresh "humans" page next
      to yesterday's full one invites exactly the wrong comparison
- [x] Switching the flag off removes the directory — otherwise the pages would freeze at the day
      it was switched off while still being served

## Deletion (the main risk of this task)
- [x] The cleanup loop for removed domains walks **both** directories. Verified: planted
      `retired.example.html` files in both were removed, the six real ones untouched
- [x] `parseable = 0` and `report failed` remove the pair as a whole. Verified: stadtdame.de's log
      was taken away — both pages disappeared, and after it was returned both came back
- [x] A failure of only the second run does not bring down the full report: it is built from the
      same lines and is not in doubt, only the humans one is deleted

## Verification on a live machine
- [x] The figures match the task: berlindame 94/37 (57 crawlers), stadtdame 47/25
- [x] `humans/` — `drwxrwsr-x goaccess:www-data`, files `0640`; `www-data` reads, `nobody` is
      refused
- [x] Build via the systemd unit: `Result=success`, `ExecMainStatus=0`, all six reports at one
      timestamp — `RestrictSUIDSGID` and `ProtectSystem=strict` do not hinder the new directory
- [x] Repeat role run — `changed=0`
- [x] `shellcheck`, `yamllint`, `ansible-lint` (profile production) clean

## Decisions
- [x] **A subdirectory instead of a `-humans` suffix.** Busel parses the names with the glob
      `*.html`; with a suffix the second file would become a separate "site" row, and a domain
      ending in `-humans` would break the parsing. A subdirectory does not match the glob — the
      busel code needs no changes
- [ ] `--unknowns-as-crawlers` — rejected: one visit of difference out of 37 is not worth a
      variable whose meaning would have to be worked out
- [ ] A separate parser config for the second report — rejected: two configs would drift apart,
      and `--ignore-crawlers` filters lines, not sections

## From review (codex)
- [x] **The `humans/` directory was world-readable.** `mkdir` left the mode to the umask —
      `2775` under the builder, `2755` on a host with the typical `022` — whereas the parent is
      closed with `0750` precisely so that the file names (that is, the domain list) are not read
      by anyone from outside. The directory is created by Ansible with `2750`
- [x] **On an update the reports did not appear until the timer.** On a machine with the old
      version the full reports were in place and the site list had not changed, so the one-off
      build was skipped and `humans/` was absent for up to an hour — even though the feature is
      enabled by default. A separate search for the humans reports was added to the condition.
      Verified: the directory was destroyed, a role run rebuilt it immediately (2.26s)
- [x] **The fix for the first point turned out to be worse than the defect.** `chmod 2750` from
      the builder did not set the bit but **cleared the inherited one**: the user is not in the
      owning group, and the kernel drops `S_ISGID` on any `chmod`, returning success. Measured:
      `chmod o-rwx`, which does not name the bit at all, turned `2750` into `750`. After that the
      reports would have been written into a group nobody reads. The mode is set only by Ansible,
      as root

## False alarms during verification
- [x] "The real reports have disappeared" — a test error: `sudo ls *.html` does not expand the
      glob, the pattern went through literally. The files were in place
- [x] The worry that `RestrictSUIDSGID=true` in the unit would prevent setgid inheritance — not
      confirmed: the directive forbids **setting** the bit, not inheriting it from a directory
