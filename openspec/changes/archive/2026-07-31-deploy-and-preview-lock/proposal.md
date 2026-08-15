# Proposal: manual deploy, a key per repository and a lock on unpublished sites

## Why

The busel machine was brought up by hand and had drifted from the repository, while the rollout ran
into two things at once.

- **CI is off** (limits burned through), and Deployer in busel is configured without `host()` —
  there is nothing to deploy with. A manual path is needed, one that does not reinvent releases.
- **One deploy key does not serve two GitHub repositories.** The machine pulls both busel and
  (later) matilda; without host aliases ssh presents the first key that fits, and GitHub answers
  for the wrong repository — the error looks like "repository not found", even though the key is
  valid.
- **Sites are open to the world before anyone has looked at them.** An unpublished site must not be
  reachable, indexed or crawled. The closed state must be the default, and publication an explicit
  action, done per site rather than for all of them at once.
- **Krot and busel were writing the same setting.** The `nginx` role laid down `log_format` and
  `set_real_ip_from`, and busel commit `f260b46` started laying down the same thing in
  `busel-shared.conf`. Two writers on one setting drift apart, and a stale `set_real_ip_from`
  silently writes the CDN address into the logs instead of the visitor's.

## What Changes

### The `deploy` role — a thin wrapper

Deployer runs **on the control machine** and goes to the server over SSH itself (`delegate_to:
localhost`). The role does not reinvent releases, the symlink or rollback — that is the job of the
project's `deploy.php`. What is set is the task (`deploy`, `rollback`) and the branch.

### The `deploy_keys` role — a key per repository

It generates a separate key for each private repo and writes host aliases into `~/.ssh/config` so
that git presents the right one: cloning must use `git@<name>.github.com:owner/repo.git`.

### Basic auth: the mechanism in Krot, the decision in busel

Krot installs `/etc/nginx/.htpasswd` (password from Bitwarden at run time) and the snippet
`/etc/nginx/snippets/krot-auth.conf`. **Which sites are closed is decided by the busel vhost
generator**, which includes the snippet until the site is marked published. Krot does not keep the
list of sites: otherwise the machine playbook would start knowing about specific sites.

The htpasswd sync was moved out into `files/htpasswd-sync.sh`: the inline variant broke on `$`
substitution in the shell before the string ever reached the host, and the file was rewritten on
every run.

### `log_format` and real-IP handed over to busel

The `nginx` role stops writing them and **removes what it wrote before** (`krot-real-ip.conf`,
`*-log-format.conf`). The owner is the vhost generator: it knows the format name its own configs
refer to, and it updates the CF ranges on every generation rather than once per Ansible run.

## Impact

- Breaking for anyone who relied on `log_format` from Krot: the format name must now be defined by
  the project. In busel this is already done (`busel-shared.conf`).
- `nginx.conf` no longer names the format at the `http` level — `access_log off`, each vhost logs
  for itself. Otherwise the file would refer to a definition it does not own, and would break on
  any change of the name.
