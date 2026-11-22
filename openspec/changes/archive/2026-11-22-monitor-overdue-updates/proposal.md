# Make overdue machine updates visible

## Why

Unattended upgrades can silently stop while the machine and its sites remain reachable.

## What Changes

An opt-in machine role will collect permitted unattended-origin updates and needrestart
service requests hourly, exposing only a fresh cached summary at a secret HTTPS path.
A keyword monitor will use the existing UptimeRobot module and its active contacts.

The grace period is 48 hours from the first observation of a continuously pending package,
regardless of candidate version changes. Collection failures and stale results fail closed.
The consumer owns the HTTPS vhost and includes the generated nginx snippet before enabling
monitor registration. No production provisioning is part of this change.

Observation covers published newer versions from allowed origins even when a pin, hold,
phased rollout or failed download prevents installation. This is deliberately a debt alert,
not an override of APT policy. Hourly samples cannot distinguish an intermediate upgrade
followed by another publication from continuously pending debt.

Transient APT collection failures receive three bounded attempts before an error summary
replaces health; stale cached results still fail closed independently of the collector.
