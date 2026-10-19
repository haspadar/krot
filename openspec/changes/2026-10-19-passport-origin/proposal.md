# Report the inventory's domain origin in the site passport

## Why

The consumer's inventory owns whether a domain is new or a drop. The site's
existing passport must carry that declaration to its reader without a second
registry or a classification inferred from country, profile or dates.

## What Changes

- Accept `site_passport_origin` as exactly the string `new`, the string `drop`,
  or null. Omission defaults to null for legacy inventory.
- Reject all other values and types before any file operation.
- Append JSON `origin` as `new`, `drop`, or null. Preserve country, profile,
  launched, the secret, path formula, nginx snippet and date handling.
- Verify valid values, omitted/null compatibility, refusal before writes and
  unchanged existing passport fields in the role's container scenario.

## Boundaries

No new registry, consumer changes or application on live hosts. Installing the
collection alone leaves existing passports untouched; consumers decide when to
pass inventory values and apply the role.
