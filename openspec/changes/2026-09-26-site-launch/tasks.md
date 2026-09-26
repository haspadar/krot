# Задачи

Цепочка PR, каждый мержится в `main` отдельно.

## PR 1 — change и модули, нужные обоим проектам

- [x] Подтверждение владельцем: переоткрытие двух решений (см. `proposal.md`)
- [ ] `plugins/module_utils/`: HTTP-клиент с ретраями, различение «нет» и «не смог спросить»
- [ ] Инфраструктура юнитов: pytest, поддельный HTTP-сервер, запуск в job'е `lint`
- [ ] `cloudflare_zone` + юниты
- [ ] `cloudflare_zone_settings` + юниты
- [ ] `cloudflare_origin_cert` + юниты
- [ ] `bing_site` + юниты
- [ ] Двойное ревью до push

## PR 2 — остальные модули

- [ ] `dynadot_ns` + юниты (включая проверку делегирования по DoH)
- [ ] `umami_website` + юниты
- [ ] `ga4_property` + юниты
- [ ] `uptimerobot_monitor` + юниты
- [ ] `gsc_site` + юниты
- [ ] `yandex_site` + юниты
- [ ] Двойное ревью до push

## PR 3 — роли и molecule

- [ ] `site_preflight`, `site_domain`, `site_dns`, `site_tls`, `site_database`
- [ ] `site_analytics`, `site_serve_check`, `site_monitor`, `site_search`, `site_check`
- [ ] Подключение task-файлов проекта; факт `site_launch_results`
- [ ] Molecule `site_launch`: контейнер-подделка API, `verify.yml` спрашивает подделку, `idempotence`
- [ ] Двойное ревью до push

## PR 4 — плейбук, вики, релиз

- [ ] `playbooks/site_launch.yml` — пример порядка
- [ ] Вики: страница про запуск сайта (порядок, переменные, что подключает проект)
- [ ] Вики: `collection-layout.md` — два набора ролей (машина / сайт), раздел про Terraform
- [ ] `openspec/ARCHITECTURE.md`, `README.md` — тот же пересмотр
- [ ] `galaxy.yml`: минорная версия, описание
- [ ] Двойное ревью до push
- [ ] Архивация change последним коммитом

## Приёмка

- [ ] `--check` на `tbl-telefon.de`
- [ ] Живой прогон на `tbl-telefon.de` — только с подтверждения владельца; ok, `changed=0`
