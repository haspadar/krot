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
| `postgresql` | PostgreSQL из pgdg, csvlog со slow-query логом. Только сервер, без баз |
| `nginx` | nginx.conf, JSON-лог, real-IP по CF-заголовкам. Per-site vhost'ы не трогает |
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
- **`nginx_log_format_name` обязан совпадать** с именем формата, на которое ссылаются
  сгенерированные vhost'ы. nginx не стартует на неизвестном `log_format`, так что расхождение
  роняет все сайты разом.

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
Тот же файл читает роль `nginx` для `set_real_ip_from` — два независимых списка неминуемо
разъехались бы.

Скрипт `/usr/local/sbin/krot-cf-ranges` отказывается менять правила, если ответ CF пустой или
подозрительно короткий: усечённый список молча отрезал бы сайты от мира.

**Про SSH:** правило для 22 порта создаётся до включения ufw и до CF-замка, поэтому доступ
к машине не теряется. Роль `bootstrap` по той же причине отказывается выключать парольный вход,
пока не убедится, что валидный ключ на месте.

## Логи

Настроены под сбор (Loki/Alloy и аналоги), но агент не ставится — это отдельная роль.

- **nginx** — JSON-строки с `request_time`, `upstream_time`, `cf_ray`, `cf_country`.
  `$remote_addr` — уже настоящий посетитель, восстановленный из `CF-Connecting-IP`.
- **php-fpm** — `/var/log/php/`: access с таймингами, slowlog со стек-трейсом медленных
  запросов, отдельный error-log.
- **postgresql** — csvlog, медленные запросы, `log_lock_waits`, `log_checkpoints`.

nginx и php ротируются через logrotate, PostgreSQL ротирует себя сам.

## Разработка

```bash
yamllint .        # форматирование YAML
ansible-lint      # профиль production — строжайший
```

CI (`.github/workflows/lint.yml`) гоняет оба на каждый PR.

Все роли идемпотентны: повторный прогон даёт `changed=0`. Это не декларация — проверено
прогоном на живой машине.

Целевая платформа — Ubuntu 24.04 (noble).
