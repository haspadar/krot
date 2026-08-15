# Proposal: PostgreSQL 18 and refusing to install it silently

## Why

The server needs PostgreSQL 18: Matilda is already on 18, and keeping the recipients on 16 means
diverging within a single network.

But **changing `postgresql_version` does not upgrade the cluster**, and this is a trap that
springs silently:

- PostgreSQL does not read the data directory of the previous major version, so raising the
  variable puts **a second cluster alongside** rather than upgrading the first;
- `pg_createcluster` takes the first free port, that is 5433, while the role's config declares
  5432;
- the new cluster does not start, the application keeps working with the old one — and
  everything looks healthy.

A role that behaves this way is more dangerous than a role that refuses to work.

## What Changes

### Refusal instead of guesswork

The role lists the existing clusters and **refuses** to run next to a cluster of a foreign
version, naming that version and the ways forward (`pg_upgrade`, dump/restore, or deliberately
discarding the data).

Removing the old cluster is only possible through an explicit `postgresql_remove_other_versions`
(default `false`): destroying data must not be a side effect of editing a version number.

### Clusters are determined by `pg_lsclusters`, not by directories

Found on a live machine: `postgresql-18` installed but **created no cluster** — the port was
taken. Meanwhile the directories under `/etc/postgresql` remain from the package whose postinst
could not create a cluster. That is, directories answer the question "which versions are
installed", not "which clusters exist".

### The cluster is created explicitly

`postgresql-common` creates a cluster in postinst only if the port is free, and removing the old
one after the fact does not create the missing one. The role creates it itself, with `creates:`
on `postgresql.conf`, so on a clean machine the task is skipped — there the cluster has already
been made by the package.

### Cleaning up after itself

`purge` removes what the package owns. It does **not** remove two things: the client package
`postgresql-client-<old>` (a separate package nobody depends on) and the role's own drop-in
`99-krot.conf`, which belongs to no package. A leftover config would silently reconfigure that
version if it were ever installed again.

## Impact

- **Breaking:** the `postgresql_version` default changes from 16 to 18. An existing machine will
  require a deliberate transition, not just a collection update — that is exactly what the role
  is designed for.
- There was no data on busel: all tables at zero rows, the only content was the Doctrine
  migration log, restored by running the migrations. A dump was taken and verified before removal.
