# Declare the engines a site is offered to

## Why

`indexing_projects.<project>` holds one key per engine, so every engine unit walks every site of the
project. A site whose engine account is a different one than the key's (a separate Bing Webmaster
account per site is a deliberate choice) is refused every night: the units turn red for a condition
that repairs itself only by someone adding that site's own key, and the red hides the failures that
need a person. Worse, Bing's allowance question is abandoned after three failing sites, so every
site walked after them is planned against the smallest number instead of the real one.

## What changes

- A site may carry `engines`, a non-empty subset of the project's `engines`. Absent, the site is
  offered to every engine of the project, as before
- `krot-index` skips a site for an engine it does not list, and says so in one line, exit code
  unaffected; the daily counts unit skips it the same way
- The role refuses, before anything on the machine changes, a site engine list that is not a unique
  subset of the project's, and a project engine that no site uses

## Scope

Role `indexing` and its program only. A key per account (the other way to treat such sites) is not
built: it needs keys the machine does not hold and an owner decision about offering those sites at all.
