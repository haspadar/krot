# Name the site by a topic tag, not by a profile from a closed list

## Why

The passport said what a site is with `profile`, one of a closed list kept by the reader. A site that fits none of its entries (tourism) had to wait for the reader to add one, and the reader's list became the contract of every writer. The owner decided on 2026-11-18 that no reader dictates the contract: the passport carries a plain tag.

## What changes

- Add `site_passport_topic`, written as `topic`; a new site uses it
- Check both `topic` and the older `profile` by one format (lower-case letter first, then lower-case letters, digits and hyphens, at most 32), end-anchored with `\Z`
- Require exactly one of the two keys; remove `site_passport_profiles`
- Keep every passport written under `profile` byte for byte as it was
- Release as 13.0.0: a documented variable is removed, which this collection counts as breaking; no code of the old list fails and no old passport changes

## Scope

Only the `site_passport` role, its defaults, tests, molecule scenario and wiki. No consumer changes, no passport rewritten, no production application.
