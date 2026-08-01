# Tasks: PostgreSQL 18

## Переменные
- [x] `postgresql_version` 16 → 18
- [x] `postgresql_remove_other_versions` (дефолт `false`) с объяснением, почему не `true`

## Защита
- [x] `pg_lsclusters --no-header` → `vars/main.yml` вычисляет `postgresql_other_versions`
- [x] `assert` с сообщением, называющим найденную версию и пути вперёд
- [x] Удаление старой версии — сервер **и** клиент, `purge`
- [x] Удаление `/etc/postgresql/<old>` — собственный drop-in роли, purge его не трогает
- [x] `pg_createcluster ... --start` с `creates:`, чтобы на чистой машине не дублировать пакет

## Проверка на живой машине
- [x] Прогон **без** флага отказался: `PostgreSQL 16 already has a cluster on this host...`
- [x] Прогон с флагом: PG 16 удалён, кластер 18 создан на 5432
- [x] `PostgreSQL 18.4 (Ubuntu 18.4-1.pgdg24.04+1)`, `shared_preload_libraries` на месте
- [x] 9 миграций Doctrine накатились без ошибок, 7 таблиц на месте
- [x] Три сайта отдают 200 по HTTPS
- [x] Повторный прогон — `changed=0`, `skipped=2` (защита не мешает обычной работе)
- [x] После уборки: ноль пакетов PG 16, только `/etc/postgresql/18`, один кластер
- [x] `yamllint` и `ansible-lint` чистые

## Данные
- [x] Дамп снят и проверен: все таблицы пусты, кроме журнала миграций Doctrine
- [x] Удаление подтверждено владельцем
- [x] Роль и база `busel` пересозданы, пароль из Bitwarden (`busel-postgres-app`)
- [x] Дамп удалён с машины после проверки

## Отдельно замечено
- [x] `-e postgresql_remove_other_versions=true` передаёт **строку**, Ansible отклоняет её как
      не-булево. Нужен JSON: `-e '{"postgresql_remove_other_versions": true}'`
- [x] Флага нет в inventory busel — он передавался разово, постоянного разрешения удалять базы
      на машине не осталось
