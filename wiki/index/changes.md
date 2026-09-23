---
kind: index
title: Changes
owner: generated
verified: 2026-09-23
roles: []
---

# Changes

> **Сгенерировано.** Руками не править — правка будет затёрта.
> Обновить: `python3 scripts/wiki-index.py`

В работе — **0**, заархивировано — **17**.

Номер PR восстановлен из merge-коммита по совпадению имени ветки с именем change после отбрасывания даты и префикса типа (`feat/`, `fix/`). Сравнение остаётся строгим, поэтому не восстановлен у **8** из 17: нестрогое приписало бы change чужой PR — прочерк честнее неверного номера.

**Строка «влит, не заархивирован» — это долг**: работа в `main`, а `openspec archive` не выполнен, значит вики не узнала, что устарело.

| Change | Состояние | PR | О чём |
|---|---|---|---|
| [`nginx-machine-defaults`](../../openspec/changes/archive/2026-09-23-nginx-machine-defaults/proposal.md) | 2026-09-23 | — | Настройки nginx, которых на машине может быть только одна копия, ставит роль |
| [`a-copy-nobody-can-restore-is-a-hope`](../../openspec/changes/archive/2026-08-29-a-copy-nobody-can-restore-is-a-hope/proposal.md) | 2026-08-29 | [#50](https://github.com/haspadar/krot/pull/50) | Копия, которую некому развернуть, — это надежда, а не резервная копия |
| [`the-boundary-with-busel`](../../openspec/changes/archive/2026-08-24-the-boundary-with-busel/proposal.md) | 2026-08-24 | — | Граница с busel описана неверно |
| [`operator-reads-the-logs`](../../openspec/changes/archive/2026-08-23-operator-reads-the-logs/proposal.md) | 2026-08-23 | [#47](https://github.com/haspadar/krot/pull/47) | Оператор читает логи машины, а не только правит её |
| [`umami-role`](../../openspec/changes/archive/2026-08-20-umami-role/proposal.md) | 2026-08-20 | [#42](https://github.com/haspadar/krot/pull/42) | Proposal: the analytics counter is a service of the machine |
| [`ci-faster-feedback`](../../openspec/changes/archive/2026-08-15-ci-faster-feedback/proposal.md) | 2026-08-15 | — | Proposal: CI waits longer than it works |
| [`molecule-role-tests`](../../openspec/changes/archive/2026-08-15-molecule-role-tests/proposal.md) | 2026-08-15 | — | Proposal: a role meets reality for the first time in production |
| [`app-cron`](../../openspec/changes/archive/2026-08-13-app-cron/proposal.md) | 2026-08-13 | [#20](https://github.com/haspadar/krot/pull/20) | Proposal: application periodic jobs are a property of the machine |
| [`cron-assert-silent-skip`](../../openspec/changes/archive/2026-08-13-cron-assert-silent-skip/proposal.md) | 2026-08-13 | [#21](https://github.com/haspadar/krot/pull/21) | Proposal: a failed assert skipped the job silently |
| [`geoip`](../../openspec/changes/archive/2026-08-02-geoip/proposal.md) | 2026-08-02 | [#11](https://github.com/haspadar/krot/pull/11) | Proposal: geography in traffic reports |
| [`goaccess`](../../openspec/changes/archive/2026-08-02-goaccess/proposal.md) | 2026-08-02 | [#6](https://github.com/haspadar/krot/pull/6) | Proposal: traffic statistics from nginx logs |
| [`goaccess-111`](../../openspec/changes/archive/2026-08-02-goaccess-111/proposal.md) | 2026-08-02 | — | Proposal: GoAccess 1.11 and cities in geolocation |
| [`goaccess-crawler-filter`](../../openspec/changes/archive/2026-08-02-goaccess-crawler-filter/proposal.md) | 2026-08-02 | [#10](https://github.com/haspadar/krot/pull/10) | Proposal: scanners that do not call themselves bots |
| [`goaccess-humans`](../../openspec/changes/archive/2026-08-02-goaccess-humans/proposal.md) | 2026-08-02 | — | Proposal: a second GoAccess report — "humans only" |
| [`postgresql-18`](../../openspec/changes/archive/2026-08-01-postgresql-18/proposal.md) | 2026-08-01 | — | Proposal: PostgreSQL 18 and refusing to install it silently |
| [`deploy-and-preview-lock`](../../openspec/changes/archive/2026-07-31-deploy-and-preview-lock/proposal.md) | 2026-07-31 | — | Proposal: manual deploy, a key per repository and a lock on unpublished sites |
| [`pg-stat-statements`](../../openspec/changes/archive/2026-07-31-pg-stat-statements/proposal.md) | 2026-07-31 | [#2](https://github.com/haspadar/krot/pull/2) | Proposal: PostgreSQL query statistics |
