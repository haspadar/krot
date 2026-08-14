---
kind: guide
title: Коллекция и её границы
owner: haspadar
verified: 2026-08-15
roles: []
---

# Коллекция и её границы

Krot — это **коллекция ролей, а не плейбук**. В репозитории нет inventory и нет `site.yml` для
конкретных машин: они живут в busel и matilda, каждый со своими хостами и переменными.

## Как проект подключает krot

```yaml
# requirements.yml проекта
collections:
  - name: git+https://github.com/haspadar/krot.git
    type: git
    version: main   # или тег, чтобы заморозить инфраструктуру
```

```bash
ansible-galaxy collection install -r requirements.yml
```

Зависимости (`ansible.posix`, `community.general`, `community.postgresql`) подтягиваются сами.

Это «composer-way»: `ansible-galaxy collection install` раскладывает коллекцию локально, как
`composer install` в `vendor/`. Не submodule и не symlink — обновление роли это смена `version`.

**Почему коллекция, а не набор ролей.** `ansible-galaxy` умеет ставить git-источник как **одну
роль**, а не как каталог ролей. Коллекция — единственная форма, в которой набор ролей ставится
одной командой и версионируется целиком.

Использование:

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

## Главный принцип: роль знает про хост, но не про приложения на нём

Это не стилистика, а то, что удерживает роли переносимыми. **Как только роль узнаёт имя сайта или
базы, она перестаёт быть общей и превращается в конфиг одной машины.**

| Слой | Что делает | Инструмент |
|------|-----------|-----------|
| Провижининг **машины** | юзер, пакеты, firewall, fail2ban, (docker \| php+pg+nginx) | **Krot (Ansible)** |
| Провижининг **сайта** | домен, CF-зона, vhost, БД сайта, Bearer к Matilda | **console-команды `recipient:*`** в busel |
| Выкатка **кода** | релизы, symlink, reload | **Deployer** (`deploy.php`) в каждом проекте |

Пересечение Ansible и Deployer ровно одно: Ansible создаёт юзера `km` и каталог
`/var/www/<project>` с правами, куда Deployer потом кладёт релизы.

## Что роли намеренно НЕ делают

Каждый пункт — не забытое, а отданное другому владельцу.

| Не делает | Кто владелец | Почему не роль |
|---|---|---|
| vhost'ы конкретных сайтов | генератор проекта | роль владеет только `sites-available`/`sites-enabled` и правами |
| `log_format` и real-IP | тот же генератор | он знает имя формата, которое называют его конфиги, и обновляет CF-диапазоны при каждой генерации |
| базы конкретных приложений | провижининг сайта | роль `postgresql` ставит только сервер |
| выкатку кода | Deployer проекта | роль `deploy` лишь запускает его; релизы и rollback в `deploy.php` |

Про `log_format` стоит отдельно: **два писателя на одну настройку неизбежно разъезжаются**, а
устаревший `set_real_ip_from` молча пишет в логи адрес CDN вместо посетителя. Отказ здесь не
падает — он портит данные, оставаясь незаметным.

## Два набора ролей

| Проект | Роли | Почему так |
|---|---|---|
| busel | `common + php + postgresql + nginx + firewall + fail2ban` | несколько сайтов на машине за Cloudflare, всё системное |
| matilda | `common + docker + firewall + fail2ban` | голый хост под Docker Compose |

Разница не в предпочтениях. У matilda тяжёлое специфичное окружение (playwright, flaresolverr,
minio, postgres, php, api), и его воспроизводимость **уже решена** compose'ом — машине остаётся
подготовить хост. У busel сайты простые и сервисы системные: Docker дал бы оверхед на слабых VPS
и вторую систему выкатки поверх Deployer.

Каждая роль атомарна и применима отдельно. Все параметры — в `roles/<role>/defaults/main.yml`.

## Terraform — это не про сервер

Частая путаница: Terraform в krot нет и не будет. Он для облака (CF-зоны и DNS, домены Dynadot,
R2), появится отдельно и позже. «Провижининг машины» (Ansible) и «облачные ресурсы» (Terraform) —
разные слои, и смешивать их в одном репозитории значит потерять границу, ради которой всё
разделено.

## Целевая платформа

Ubuntu 24.04 (noble). Все роли идемпотентны: повторный прогон даёт `changed=0`. Это не декларация
— проверено прогоном на живой машине, и каждое изменение роли проверяется тем же способом.

```bash
yamllint .        # форматирование YAML
ansible-lint      # профиль production — строжайший
```

CI (`.github/workflows/lint.yml`) гоняет оба на каждый PR плюс `ansible-galaxy collection build`.
