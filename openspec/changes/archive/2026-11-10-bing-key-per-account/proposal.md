# One Bing key per account

## Why

A project holds one Bing key, so every Bing unit walks every site with it. Sites that live in another
Bing Webmaster account (a separate account per site group is deliberate) can only be declared out of
Bing (`engines` on the site, 12.1.0), which keeps their nights green but offers them to nobody, and
the owner needs these sites offered. Their account has its own key and its own allowance.

## What changes

- `indexing_projects.<project>` may carry `bing_accounts`, a mapping of account name (`[a-z0-9]+`) to
  that account's Bing key; a site may carry `bing_account`, the name of the account it lives in.
  Absent, a site uses the project's `bing_key`, as before
- The Bing night and the daily counts group the sites by account and run each group with its own key
  and its own engine, so the allowance question, its three-failures cut-off and the throttle belong
  to the account, not to the whole project; one account's missing key turns the unit red without
  stopping the others
- The env file gets `KROT_INDEX_BING_KEY_<ACCOUNT>` per account
- The role refuses, before anything on the machine changes: an account name that is not `[a-z0-9]+`,
  a key an environment file cannot carry, an account no site uses, a site naming an account the
  project does not hold or a site that names one while not offered to Bing, `bing_accounts` while
  `bing` is not declared, a `bing_key` missing while a Bing site uses no account, and one key used by
  two accounts or two projects
- Release 12.2.0

## Scope

Role `indexing` and its program. Where the keys come from (the project's secrets) and which sites
live in which account stay the project's inventory.
