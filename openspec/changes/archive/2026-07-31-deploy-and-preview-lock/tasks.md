# Tasks: deploy, keys, lock on sites

## The `deploy` role
- [x] `delegate_to: localhost` — Deployer lives on the control machine, not on the server
- [x] Positional host selector (Deployer 8 has no `--hosts`)
- [x] Variables `deploy_task` / `deploy_branch`

## The `deploy_keys` role
- [x] A key per repository, `~/.ssh/config` with host aliases
- [x] Verified on a live machine: busel cloned via `git@busel.github.com:haspadar/busel.git`

## Basic auth
- [x] `htpasswd` from Bitwarden at run time, `assert` fails if there is no password (we do not
      install an empty one)
- [x] The `krot-auth.conf` snippet; enabling it is on the vhost generator's side
- [x] `files/htpasswd-sync.sh` instead of inline shell: exit 0 when unchanged, 10 on rewrite
- [x] Idempotency: the file is not rewritten on every run

## Hand `log_format` and real-IP to the project
- [x] Removed `log-format.conf.j2`, `real-ip.conf.j2`, `real-ip.yml`, `vars/main.yml`
- [x] The role removes its own former files from the machine
- [x] `access_log off` at the `http` level, with an explanation in the template

## Verification on a live machine
- [x] Full playbook `ok=66 changed=0`
- [x] Three sites return 200 with real content
- [x] `yamllint` and `ansible-lint` (profile production) clean

## Uncovered and fixed along the way
- [x] hostname was `matilda` on the busel machine
- [x] The origin was exposed: `Nginx Full ALLOW Anywhere` in ufw → CF lock (44 rules), verified
      from outside: port 80 does not answer from a non-CF address, SSH alive
- [x] `PermitRootLogin yes` → `no`, removed the cloud-init drop-in that turned it back on
- [x] vhost permissions 0666 → 0644
- [x] The legacy name `felix` ripped out; `/var/www/felix` (206 MB) deleted, the vhosts already
      pointed at `/var/www/busel`, which did not exist — the sites were broken before the
      intervention
- [x] `.env.local` 600 → 640 with group `www-data` (php-fpm could not read it)
- [x] ACL on `shared/var` for `www-data` — the application could not write logs
- [x] There was neither a role nor a database in PostgreSQL: created, 9 migrations applied
