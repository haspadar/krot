# Proposal: the analytics counter is a service of the machine

## Why

The busel network measures its sites with Google Analytics, and the tag it prints names
one host on all nine of them:

```html
<script src="https://www.googletagmanager.com/gtag/js?id=G-…"></script>
```

That string sits in the markup of every page and is searchable by anybody — BuiltWith and
PublicWWW index exactly this. Nine sites carrying one host is the plainest public evidence
that they are one network, and busel's own specification has required since 2026-08-07 that
the counter be served from the site's own domain. The requirement has stood unmet the whole
time, and not through neglect: **Google serves its tag from one host and offers no other**,
so with a rented counter there is nothing to implement.

A counter running on the machine can be reached through each site's own nginx, and then the
shared string is gone.

Two further reasons, both measured:

- **the external counter answers late.** Measured 2026-08-08: at 11:00 Berlin time the newest
  hour it would report was 6:00. "What is happening now" is not a question it can answer, and
  no configuration changes that — the lag belongs to the source;
- **it does not keep the history it is trusted with.** Google thins detailed data with age;
  the operator's own tables do not. The history is already local, which is why replacing the
  collector loses nothing.

## What Changes

A new role, `umami`, installing the counter as a **system service** — the same layer as php,
postgresql and nginx.

- **Built on the machine, not fetched.** Measured 2026-08-20: the project's latest release
  carries `"assets": []` and publishes source only; what upstream ships instead is a Docker
  image, and these machines run no Docker (`wiki/domains/collection-layout.md` says why, and
  the target has 3.8 GB of RAM).
- **Node from NodeSource.** Ubuntu 24.04 ships 18.19.1; `next@16` requires >= 20.9 and
  `prisma@7` requires ^20.19 || ^22.12 || >= 24.
- **Bound to the loopback**, reached through the site's nginx. Upstream's start script
  defaults to `0.0.0.0`, so this is asserted rather than defaulted.
- **The role knows no names.** Database URL, secret, port and account all arrive from the
  inventory — `wiki/domains/collection-layout.md`: a role that learns a project's names stops
  being a role and becomes one machine's configuration. It installs no database either; the
  connection string is a parameter.
- **A molecule scenario that does not build.** It plants a small server at the release path
  instead, so the unit, the bind address, the port and the environment file are checked
  against a running process rather than against a template. A scenario that spent fifteen
  minutes compiling would be testing pnpm.

## Impact

- New role `roles/umami`, new scenario `molecule/umami`.
- No existing role changes. Nothing on any machine changes until an inventory adds it.
- `coverage.py` counts the role as covered; the floor rises with it.

⚠️ **What the scenario does not prove.** It never runs the build, so nothing here shows that
the build produces a runnable tree — recorded rather than papered over. That is closed by a
run on a real machine, which is where this repository's other measurements come from too.
