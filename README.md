# Krot

Ansible-коллекция `haspadar.krot` — переносимые роли для провижининга Ubuntu-машин.
Крот роет под сервисами и чинит «подземку» незаметно — отсюда имя.

Роли знают про **хост**, но не про приложения на нём: специфика проекта живёт в его
`inventory`/`group_vars`, а не внутри роли.

## Установка

```yaml
# requirements.yml в проекте
collections:
  - name: git+https://github.com/haspadar/krot.git
    type: git
    version: main   # или тег, чтобы заморозить инфраструктуру
```

```bash
ansible-galaxy collection install -r requirements.yml
```

Зависимости (`ansible.posix`, `community.general`, `community.postgresql`) подтягиваются сами.

## Использование

```yaml
- name: Provision the machine
  hosts: web
  roles:
    - role: haspadar.krot.common
    - role: haspadar.krot.php
    - role: haspadar.krot.nginx
    - role: haspadar.krot.firewall
    - role: haspadar.krot.fail2ban
```

Голая машина — сперва один раз под root:

```yaml
- name: Bootstrap SSH access
  hosts: new
  roles:
    - role: haspadar.krot.bootstrap
      vars:
        bootstrap_authorized_keys: ["ssh-ed25519 AAAA..."]
```

```bash
ansible-playbook bootstrap.yml -u root -k
```

## Роли

| Роль | Что делает |
|------|-----------|
| `bootstrap` | Операторский юзер + sudo, `authorized_keys`, `PermitRootLogin no`, `PasswordAuthentication no` |
| `common` | hostname, timezone, базовые пакеты, unattended security-upgrades |
| `firewall` | ufw; при `firewall_cloudflare_only` пускает 80/443 только с диапазонов Cloudflare и обновляет их weekly-таймером |
| `fail2ban` | fail2ban с джейлом `sshd` |
| `php` | PHP-FPM из ondrej PPA; slowlog, access-log с таймингами |
| `postgresql` | PostgreSQL из pgdg, csvlog со slow-query логом, `pg_stat_statements`. Только сервер, без баз |
| `nginx` | nginx.conf, права, ротация, basic auth. Per-site vhost'ы, log_format и real-IP не трогает |
| `docker` | Docker + compose-плагин, лимит на рост логов контейнеров |
| `deploy_keys` | Отдельный SSH-ключ на каждый приватный репозиторий + host-алиасы, чтобы git предъявлял нужный |
| `deploy` | Запускает Deployer проекта с control-машины. Релизы и rollback остаются в `deploy.php` |

Каждая роль атомарна и применима отдельно. Все параметры — в `roles/<role>/defaults/main.yml`.

### Что роли намеренно НЕ делают

- **vhost'ы конкретных сайтов** — их генерит сам проект; роль `nginx` владеет только каталогами
  `sites-available`/`sites-enabled` и их правами.
- **Базы конкретных приложений** — роль `postgresql` ставит только сервер.
- **Выкатку кода** — это Deployer/CI проекта. Пересечение одно: роль создаёт юзера и каталог
  с правами, куда потом кладутся релизы.

## Деплой

Роль `deploy` — тонкая обёртка: Deployer запускается **на control-машине** и сам ходит на сервер
по SSH. CI для выкатки не нужен, это ручной путь.

```bash
ansible-playbook deploy.yml
ansible-playbook deploy.yml -e deploy_task=rollback
ansible-playbook deploy.yml -e deploy_branch=some-branch
```

Роль намеренно не переизобретает релизы, symlink и rollback — этим уже занимается `deploy.php`
проекта.

**Два подводных камня, оба реальные:**

- **Один deploy key нельзя использовать в двух репозиториях GitHub.** Машина, тянущая несколько
  приватных репо, получает по ключу на каждый (`deploy_keys`) плюс host-алиас: клонировать надо
  с `git@<name>.github.com:owner/repo.git`. Без алиаса ssh предъявляет первый подошедший ключ,
  и GitHub отвечает за чужой репозиторий.
- **`log_format` и real-IP роль не пишет** — их владелец генератор vhost'ов проекта: он знает,
  какое имя формата называют его же конфиги, и обновляет CF-диапазоны при каждой генерации, а не
  раз в прогон Ansible. Два писателя на одну настройку неизбежно разъезжаются, а устаревший
  `set_real_ip_from` молча пишет в логи адрес CDN вместо посетителя.

## Закрытие неопубликованных сайтов

Сайт не должен быть доступен, проиндексирован или обойдён краулером, пока его не посмотрели.
Поэтому **закрытое состояние — умолчание**, а публикация — явное действие.

Krot ставит только механизм: файл паролей `/etc/nginx/.htpasswd` (пароль берётся из секретницы
в рантайме) и сниппет:

```nginx
# /etc/nginx/snippets/krot-auth.conf
auth_basic "Preview";
auth_basic_user_file /etc/nginx/.htpasswd;
```

**Какие сайты закрыты — решает не Krot, а генератор vhost'ов проекта.** Он добавляет в шаблон
одну строку, пока сайт не помечен опубликованным:

```nginx
server {
    server_name {{ domain }};
{% raw %}{% if not published %}{% endraw %}
    include /etc/nginx/snippets/krot-auth.conf;
{% raw %}{% endif %}{% endraw %}
    ...
```

Так сайты открываются по одному, а не все разом. Включается через `nginx_auth_enabled: true`
плюс `nginx_auth_password` из секретницы.

## Cloudflare-замок

`firewall_cloudflare_only: true` закрывает 80/443 для всего, кроме опубликованных диапазонов
Cloudflare, — origin-адрес перестаёт отвечать напрямую.

Диапазоны берутся с `cloudflare.com/ips-v4`/`ips-v6`, складываются в
`/etc/krot/cloudflare-ranges.txt` и обновляются юнитом `krot-cf-ranges.timer` (еженедельно).
Роль `nginx` этот список не читает: real-IP настраивает генератор vhost'ов проекта, обновляя
диапазоны при каждой генерации.

Скрипт `/usr/local/sbin/krot-cf-ranges` отказывается менять правила, если ответ CF пустой или
подозрительно короткий: усечённый список молча отрезал бы сайты от мира.

**Про SSH:** правило для 22 порта создаётся до включения ufw и до CF-замка, поэтому доступ
к машине не теряется. Роль `bootstrap` по той же причине отказывается выключать парольный вход,
пока не убедится, что валидный ключ на месте.

## Логи

Настроены под сбор (Loki/Alloy и аналоги), но агент не ставится — это отдельная роль.

- **nginx** — формат задаёт генератор vhost'ов проекта; роль отвечает за ротацию и за то, что
  `conf.d` подключается раньше vhost'ов, которые на него опираются.
- **php-fpm** — `/var/log/php/`: access с таймингами, slowlog со стек-трейсом медленных
  запросов, отдельный error-log.
- **postgresql** — csvlog, медленные запросы, `log_lock_waits`, `log_checkpoints`, плюс
  `pg_stat_statements` (см. ниже).

nginx и php ротируются через logrotate, PostgreSQL ротирует себя сам.

## Статистика запросов PostgreSQL

Медленный лог (`log_min_duration_statement = 500`) ловит запрос, который тормозит **однажды**.
Но запрос на 20 мс, вызываемый 100 000 раз в сутки, в него не попадёт никогда — а по суммарному
времени он может быть первым в базе, и индекс просит именно он. Это видно только через
`pg_stat_statements`, который агрегирует по нормализованному тексту запроса.

Включено по умолчанию (`postgresql_stat_statements: true`). Расширение ставится в служебную базу
`postgres`: представление показывает статистику **всего кластера** независимо от того, из какой
базы смотреть, поэтому роль по-прежнему не знает про базы конкретных сайтов.

Топ по суммарному времени:

```sql
SELECT calls,
       round(total_exec_time::numeric)     AS total_ms,
       round(mean_exec_time::numeric, 2)   AS mean_ms,
       rows,
       left(query, 120)                    AS query
FROM pg_stat_statements
ORDER BY total_exec_time DESC
LIMIT 20;
```

С сервера — одной командой:

```bash
sudo -u postgres psql -d postgres -c "SELECT calls, round(total_exec_time::numeric) AS total_ms, \
round(mean_exec_time::numeric, 2) AS mean_ms, rows, left(query, 120) AS query \
FROM pg_stat_statements ORDER BY total_exec_time DESC LIMIT 20;"
```

Два подвоха, оба стоили бы минуты на сервере:

- колонки в PG 13+ называются `total_exec_time`/`mean_exec_time`, а не `total_time`, как в старых
  рецептах из интернета;
- `::numeric` обязателен: времена хранятся как `double precision`, а двухаргументного
  `round(double precision, integer)` в PostgreSQL нет — без приведения запрос падает.

Статистика копится с момента рестарта, поэтому после добавления индекса старые цифры продолжат
тянуть картину назад. Сбросить перед замером:

```sql
SELECT pg_stat_statements_reset();
```

**`shared_preload_libraries` — списочный параметр, и PostgreSQL берёт последнее присваивание
целиком**, синтаксиса «дописать» у него нет. Поэтому роль пишет весь список разом, а не
отдельной строкой на библиотеку. Второй потребитель (`auto_explain`, `pg_cron`) добавляется
в `postgresql_shared_preload_libraries`, а не вторым конфигом — иначе он молча вытеснит
`pg_stat_statements`. Смена этого параметра требует **рестарта** базы, то есть простоя всех
сайтов на машине; роль рестартит только когда строка действительно изменилась.

## Разработка

```bash
yamllint .        # форматирование YAML
ansible-lint      # профиль production — строжайший
```

CI (`.github/workflows/lint.yml`) гоняет оба на каждый PR.

Все роли идемпотентны: повторный прогон даёт `changed=0`. Это не декларация — проверено
прогоном на живой машине.

Целевая платформа — Ubuntu 24.04 (noble).
