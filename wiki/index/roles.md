---
kind: index
title: Роли коллекции
owner: generated
verified: 2026-09-26
roles: []
---

# Роли коллекции

> **Сгенерировано.** Руками не править — правка будет затёрта.
> Обновить: `python3 scripts/wiki-index.py`

Всего **26**. Источник — `roles/`. Роль отвечает на вопрос «что ставится на машину»; страница вики — «как с этим работать и что кусается».

| Роль | Ручек в `defaults` | Объясняет страница |
|---|---|---|
| [`backup`](../../roles/backup/) | 17 | [operations/database-backups.md](../operations/database-backups.md), [operations/secrets.md](../operations/secrets.md), [operations/testing-roles.md](../operations/testing-roles.md), [runbooks/provision-a-machine.md](../runbooks/provision-a-machine.md) |
| [`bootstrap`](../../roles/bootstrap/) | 7 | [operations/cloudflare.md](../operations/cloudflare.md), [operations/testing-roles.md](../operations/testing-roles.md), [runbooks/provision-a-machine.md](../runbooks/provision-a-machine.md) |
| [`common`](../../roles/common/) | 5 | [operations/logging.md](../operations/logging.md), [operations/testing-roles.md](../operations/testing-roles.md), [research/apt-allowed-origins-appends.md](../research/apt-allowed-origins-appends.md), [runbooks/provision-a-machine.md](../runbooks/provision-a-machine.md) |
| [`cron`](../../roles/cron/) | 8 | [operations/cron-jobs.md](../operations/cron-jobs.md), [operations/logging.md](../operations/logging.md), [operations/silent-failures.md](../operations/silent-failures.md), [operations/testing-roles.md](../operations/testing-roles.md), [runbooks/provision-a-machine.md](../runbooks/provision-a-machine.md) |
| [`deploy`](../../roles/deploy/) | 6 | [operations/deploy.md](../operations/deploy.md) |
| [`deploy_keys`](../../roles/deploy_keys/) | 2 | [operations/deploy.md](../operations/deploy.md), [runbooks/provision-a-machine.md](../runbooks/provision-a-machine.md) |
| [`docker`](../../roles/docker/) | 3 | [operations/docker.md](../operations/docker.md), [runbooks/provision-a-machine.md](../runbooks/provision-a-machine.md) |
| [`fail2ban`](../../roles/fail2ban/) | 5 | [operations/testing-roles.md](../operations/testing-roles.md), [runbooks/provision-a-machine.md](../runbooks/provision-a-machine.md) |
| [`firewall`](../../roles/firewall/) | 9 | [operations/cloudflare.md](../operations/cloudflare.md), [operations/testing-roles.md](../operations/testing-roles.md), [runbooks/provision-a-machine.md](../runbooks/provision-a-machine.md) |
| [`nginx`](../../roles/nginx/) | 21 | [operations/cloudflare.md](../operations/cloudflare.md), [operations/logging.md](../operations/logging.md), [operations/secrets.md](../operations/secrets.md), [operations/silent-failures.md](../operations/silent-failures.md), [operations/testing-roles.md](../operations/testing-roles.md), [runbooks/provision-a-machine.md](../runbooks/provision-a-machine.md) |
| [`php`](../../roles/php/) | 20 | [operations/logging.md](../operations/logging.md), [operations/silent-failures.md](../operations/silent-failures.md), [operations/testing-roles.md](../operations/testing-roles.md), [research/fpm-pools-cannot-share-a-socket.md](../research/fpm-pools-cannot-share-a-socket.md), [runbooks/provision-a-machine.md](../runbooks/provision-a-machine.md) |
| [`postgresql`](../../roles/postgresql/) | 17 | [operations/logging.md](../operations/logging.md), [operations/postgresql.md](../operations/postgresql.md), [operations/silent-failures.md](../operations/silent-failures.md), [operations/testing-roles.md](../operations/testing-roles.md), [runbooks/provision-a-machine.md](../runbooks/provision-a-machine.md) |
| [`site`](../../roles/site/) | 48 | — *не объяснена* |
| [`site_analytics`](../../roles/site_analytics/) | 0 | — *не объяснена* |
| [`site_check`](../../roles/site_check/) | 0 | — *не объяснена* |
| [`site_database`](../../roles/site_database/) | 0 | — *не объяснена* |
| [`site_dns_records`](../../roles/site_dns_records/) | 0 | — *не объяснена* |
| [`site_dns_zone`](../../roles/site_dns_zone/) | 0 | — *не объяснена* |
| [`site_domain`](../../roles/site_domain/) | 0 | — *не объяснена* |
| [`site_monitor`](../../roles/site_monitor/) | 0 | — *не объяснена* |
| [`site_preflight`](../../roles/site_preflight/) | 0 | — *не объяснена* |
| [`site_search`](../../roles/site_search/) | 0 | — *не объяснена* |
| [`site_serve_check`](../../roles/site_serve_check/) | 0 | — *не объяснена* |
| [`site_serve_precheck`](../../roles/site_serve_precheck/) | 0 | — *не объяснена* |
| [`site_tls`](../../roles/site_tls/) | 0 | — *не объяснена* |
| [`umami`](../../roles/umami/) | 18 | [operations/analytics-counter.md](../operations/analytics-counter.md), [operations/secrets.md](../operations/secrets.md), [operations/testing-roles.md](../operations/testing-roles.md), [runbooks/provision-a-machine.md](../runbooks/provision-a-machine.md) |

## Не объяснены ни одной страницей — 13

Нормальное состояние для новой роли. Ненормальное — если так остаётся долго.

- `site`
- `site_analytics`
- `site_check`
- `site_database`
- `site_dns_records`
- `site_dns_zone`
- `site_domain`
- `site_monitor`
- `site_preflight`
- `site_search`
- `site_serve_check`
- `site_serve_precheck`
- `site_tls`
