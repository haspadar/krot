# Outcome: the "humans only" report is switched off

This change was delivered and then **reverted the same day** — 2026-08-02, collection 3.0.0,
`goaccess_humans_report: false`. Written down here because the `proposal.md` above argues that
"both reports are needed", and without this note it reads as a standing decision.

## What turned out to be wrong

Not the implementation: the report was built and filtered exactly as intended. What turned out to
be wrong was the **figure**.

Three attempts, each filter reasonable in its own way:

| filter | "visitors" on berlindame.de |
|--------|-----------------------------|
| `--ignore-crawlers` (this change) | 41 |
| \+ a name list (`goaccess_extra_crawlers`) | 36 |
| \+ behaviour: internal referer, threshold 2 | 6 out of 103 addresses |

Of those last six, three loaded `/media/` with referers exactly like a browser — from the log they
are in principle indistinguishable from people. The honest answer is **two**: the owner over VPN
and his brother.

A number that goes from 41 to 6 under equally well-founded filters is not a measurement. Yet it
reads as one, and that is the harm: a missing figure is more honest than an invented one. The
original proposal called 37 "how many people came" — a twentyfold discrepancy with two.

## What follows from this

Telling people from machines by the pattern of requests alone can be taken to a limit, and the
limit has been reached. Beyond it you need a mark that the browser executes — the log cannot
provide it.

The full report is untouched and remains the point of the role: it answers the question "is the
site being crawled, by whom, and what is being indexed", and for that question its data is
complete.

## What is left in the role

The filter code and `goaccess_extra_crawlers` have **not been cut out**: the list was calibrated
on live traffic and would have to be obtained again from scratch. `goaccess_humans_report: true`
brings the report back, and it is rebuilt within the same run, without waiting for the timer.
