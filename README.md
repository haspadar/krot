# Krot

Ansible-роли, которыми провижинятся серверы сети. Крот роет под сервисами и чинит «подземку»
незаметно — отсюда имя.

Роли переносимые: специфика проекта живёт в `inventory/group_vars`, а не в самой роли.
Проекты подключают их через `ansible-galaxy` + git-источник (см. «Подключение из проекта»).

## Требования

```bash
brew install ansible ansible-lint yamllint
ansible-galaxy collection install -r requirements.yml
```

Плейбук `bootstrap.yml` тянет SSH-ключ из Bitwarden — перед прогоном нужен разблокированный
`bw` (skill `/bw-unlock`).

## Быстрый старт

```bash
# Голая машина: юзер km, SSH-ключ, хардненинг sshd. Один раз, под root.
ansible-playbook playbooks/bootstrap.yml -l <host> -u root -k

# Дальше — обычные прогоны, уже под km.
ansible-playbook playbooks/busel.yml
ansible-playbook playbooks/matilda.yml

# Одна роль:
ansible-playbook playbooks/busel.yml --tags nginx

# Посмотреть, что изменится, ничего не трогая:
ansible-playbook playbooks/busel.yml --check --diff
```

## Роли

| Роль | Что делает | Кому |
|------|-----------|------|
| `bootstrap` | Юзер `km` + sudo, `authorized_keys` из Bitwarden, `PermitRootLogin no`, `PasswordAuthentication no` | все, один раз |
| `common` | hostname, timezone, базовые пакеты, unattended security-upgrades | все |
| `firewall` | ufw; при `firewall_cloudflare_only` пускает 80/443 **только** с диапазонов Cloudflare, обновляет их weekly-таймером | все |
| `fail2ban` | fail2ban с джейлом `sshd` | все |
| `php` | PHP 8.5 + FPM из ondrej PPA, slowlog и access-log под сбор логов | busel |
| `postgresql` | PostgreSQL 16 из pgdg, csvlog со slow-query логом. Только СЕРВЕР, без per-site баз | busel |
| `nginx` | nginx.conf, JSON-лог, real-IP по CF-заголовкам. Per-site vhost'ы **не трогает** | busel |
| `docker` | Docker + compose-плагин, лимит на рост логов контейнеров | matilda |

### Границы: что Krot НЕ делает

Ansible знает про **хост**, но не про сайты:

- **vhost'ы сайтов** генерит console-команда busel `recipient:nginx:generate`. Krot только
  владеет каталогами `sites-available`/`sites-enabled` и их правами.
- **БД и роли конкретного сайта** создаёт busel (`recipient:*`). Роль `postgresql` ставит
  только сервер.
- **Выкатка кода** — Deployer (`deploy.php`) в каждом проекте. Пересечение одно: Ansible создаёт
  юзера `km` и каталог `/var/www/<project>` с правами, куда Deployer кладёт релизы.
- **Облачные ресурсы** (CF-зоны, DNS, домены, R2) — не Ansible. Появятся отдельно в Terraform.

## Cloudflare-замок

`firewall_cloudflare_only: true` (включён для группы `recipients`) закрывает 80/443 для всего,
кроме опубликованных диапазонов Cloudflare — origin-IP перестаёт отвечать наружу. Обоснование:
`../busel/docs/deployment.md`, раздел «Скрытие origin».

Диапазоны берутся с `cloudflare.com/ips-v4`/`ips-v6`, складываются в
`/etc/krot/cloudflare-ranges.txt` и обновляются юнитом `krot-cf-ranges.timer` (еженедельно).
Тот же файл читает роль `nginx` для `set_real_ip_from` — два независимых списка неминуемо
разъехались бы.

Скрипт `/usr/local/sbin/krot-cf-ranges` отказывается менять правила, если ответ CF пустой или
подозрительно короткий: усечённый список молча отрезал бы сайты.

**Про SSH:** правило для 22 порта создаётся до включения ufw и до CF-замка, поэтому доступ к
машине не теряется.

## Логи

Настроены под будущий сбор (Loki/Alloy), но агент не ставится — это отдельная роль, когда дойдут руки.

- **nginx** — JSON-строки с `request_time`, `upstream_time`, `cf_ray`, `cf_country`.
  `$remote_addr` — уже настоящий посетитель, восстановленный из `CF-Connecting-IP`.
- **php-fpm** — `/var/log/php/`: access с таймингами, slowlog со стек-трейсом запросов
  дольше 5 с, отдельный error-log.
- **postgresql** — csvlog, запросы дольше 500 мс, `log_lock_waits`, `log_checkpoints`.

nginx и php ротируются через logrotate (14 дней), PostgreSQL ротирует себя сам.

## Качество

```bash
yamllint .        # форматирование YAML
ansible-lint      # профиль production — строжайший
```

CI (`.github/workflows/lint.yml`) гоняет оба плюс `--syntax-check` по всем плейбукам.

Все роли идемпотентны: повторный прогон даёт `changed=0`. Это не декларация — проверено
прогоном на живой машине.

## Подключение из проекта

В busel/matilda — свой `requirements.yml`:

```yaml
- src: git+https://github.com/haspadar/krot.git
  version: main   # или тег
```

`ansible-galaxy install -r requirements.yml` раскладывает роли локально, как `composer install`
в `vendor/`. Обновление роли = сменить `version`. Krot остаётся источником истины.

## Inventory

Хосты адресуются по алиасу из `~/.ssh/config` — IP в репозитории нет намеренно: origin-адрес
это единственное, что сети busel нельзя светить.

Группы названы по роли машины (`recipients`, `donors`), а не по проекту, чтобы имя группы
не совпадало с именем хоста.
