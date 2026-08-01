# Tasks: pg_stat_statements

## Переменные
- [x] `postgresql_stat_statements` (дефолт `true`, обоснование в комментарии)
- [x] `postgresql_stat_statements_max` (5000), `..._track` (`top`)
- [x] `postgresql_shared_preload_libraries` — **список**, чтобы второй потребитель не дрался
      за строку

## Шаблон
- [x] `shared_preload_libraries` собирается из списка + `pg_stat_statements`, через `unique`
- [x] Строка не пишется, когда преднагружать нечего (иначе роль зафиксировала бы `''`)
- [x] `pg_stat_statements.max` / `.track` пишутся только при включённой фиче
- [x] Проверено рендером: с `['auto_explain','pg_cron']` выходит
      `'auto_explain,pg_cron,pg_stat_statements'` — ничего не потеряно и не задвоено
- [x] Проверено рендером: при выключенной фиче и пустом списке строк нет вовсе

## Задачи
- [x] `meta: flush_handlers` перед созданием расширения — библиотека в памяти только после
      рестарта
- [x] `postgresql_ext` в базу `postgres`, `check_mode: false`
- [x] `state` следует за переменной (`present`/`absent`)

## Проверка на живой машине
- [x] `SHOW shared_preload_libraries` → `pg_stat_statements`
- [x] `SELECT count(*) FROM pg_stat_statements` отрабатывает
- [x] Повторный прогон — `changed=0`, ни одного `RUNNING HANDLER`
- [x] Рестарт потребовался, замерен: **3.7 с**
- [x] `pgbench`: 300 запросов по 0.052 мс — в медленный лог не попал бы ни один, в
      `pg_stat_statements` они первой строкой. Тестовые таблицы удалены, статистика сброшена
- [x] `yamllint` и `ansible-lint` чистые

## README
- [x] Раздел с готовым SQL для топа по `total_exec_time`
- [x] `pg_stat_statements_reset()` и когда он нужен

## Исправлено по ревью
- [x] SQL падал: `round(double precision, integer)` не существует → `::numeric`. Найдено
      прогоном на сервере, а не вычиткой
- [x] `pg_stat_statements.save` по умолчанию `on` — статистика **переживает** рестарт.
      Проверено: 9 записей до, 9 после. Формулировка «копится с рестарта» была неверна
- [x] Утверждение «рестартит только при смене этой строки» было уже кода — переписано
- [ ] Вариант запроса под PG 12 (`total_time`) — **отклонено**: роль пинит версию, такой код
      не исполнился бы ни на одном поддерживаемом хосте
