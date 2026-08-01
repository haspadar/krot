# Tasks: деплой, ключи, замок на сайты

## Роль `deploy`
- [x] `delegate_to: localhost` — Deployer живёт на control-машине, не на сервере
- [x] Позиционный селектор хоста (у Deployer 8 нет `--hosts`)
- [x] Переменные `deploy_task` / `deploy_branch`

## Роль `deploy_keys`
- [x] Ключ на каждый репозиторий, `~/.ssh/config` с host-алиасами
- [x] Проверено на живой машине: клон busel по `git@busel.github.com:haspadar/busel.git`

## Basic auth
- [x] `htpasswd` из Bitwarden в рантайме, `assert` падает, если пароля нет (пустой не ставим)
- [x] Сниппет `krot-auth.conf`; включение — на стороне генератора vhost'ов
- [x] `files/htpasswd-sync.sh` вместо инлайн-shell: exit 0 без изменений, 10 при перезаписи
- [x] Идемпотентность: файл не переписывается на каждом прогоне

## Отдать `log_format` и real-IP проекту
- [x] Удалены `log-format.conf.j2`, `real-ip.conf.j2`, `real-ip.yml`, `vars/main.yml`
- [x] Роль убирает свои прежние файлы с машины
- [x] `access_log off` на уровне `http` с объяснением в шаблоне

## Проверка на живой машине
- [x] Полный плейбук `ok=66 changed=0`
- [x] Три сайта отдают 200 с настоящим контентом
- [x] `yamllint` и `ansible-lint` (profile production) чистые

## Попутно вскрылось и починено
- [x] hostname был `matilda` на машине busel
- [x] Origin светился: `Nginx Full ALLOW Anywhere` в ufw → CF-замок (44 правила), проверено
      снаружи: порт 80 не отвечает с не-CF адреса, SSH жив
- [x] `PermitRootLogin yes` → `no`, убран cloud-init drop-in, включавший его обратно
- [x] Права vhost'ов 0666 → 0644
- [x] Легаси-имя `felix` выпилено; `/var/www/felix` (206 МБ) удалён, vhost'ы уже указывали на
      `/var/www/busel`, которого не существовало — сайты были сломаны до вмешательства
- [x] `.env.local` 600 → 640 с группой `www-data` (php-fpm не мог прочитать)
- [x] ACL на `shared/var` для `www-data` — приложение не могло писать логи
- [x] Не было ни роли, ни базы в PostgreSQL: созданы, 9 миграций накатились
