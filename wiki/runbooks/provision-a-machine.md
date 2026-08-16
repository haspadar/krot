---
kind: runbook
title: Поднять машину с нуля
owner: haspadar
verified: 2026-08-15
roles: [bootstrap, common, firewall, fail2ban]
---

# Поднять машину с нуля

Порядок для голого VPS. Шаги 1-2 выполняются **один раз** и под root; дальше машина обслуживается
обычным прогоном от оператора.

## 1. Bootstrap под root

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

Роль заводит операторского юзера с sudo, кладёт `authorized_keys`, ставит `PermitRootLogin no` и
`PasswordAuthentication no`.

**Она отказывается выключать парольный вход, пока не убедится, что валидный ключ на месте.** Это
единственная защита от того, чтобы запереть себя снаружи: после выключения пароля вернуться будет
нечем, кроме консоли провайдера.

Оболочка операторского аккаунта — bash (дефолт роли, krot ≥ 5.0.0). Машины водят агенты по SSH, а
не человек за приглашением.

## 2. Проверить, что вход по ключу работает

Прежде чем прогонять что-то ещё:

```bash
ssh <host> 'id; sudo -n true && echo sudo-ok'
```

Если эта команда не отвечает — чинить сейчас, пока root-доступ ещё возможен.

## 3. Основной прогон

busel:

```yaml
- name: Provision the machine
  hosts: web
  roles:
    - role: haspadar.krot.common
    - role: haspadar.krot.php
    - role: haspadar.krot.postgresql
    - role: haspadar.krot.nginx
    - role: haspadar.krot.firewall
    - role: haspadar.krot.fail2ban
```

matilda:

```yaml
    - role: haspadar.krot.common
    - role: haspadar.krot.docker
    - role: haspadar.krot.firewall
    - role: haspadar.krot.fail2ban
```

Если какая-то роль тянет пароль из секретницы, токен передаётся через окружение — см.
[секреты](../operations/secrets.md):

```bash
BW_SESSION="$(cat /tmp/bw-$USER/session)" ansible-playbook site.yml
```

## 4. Firewall: порядок важен

Правило для SSH создаётся **до** включения ufw и до Cloudflare-замка. Роль делает это сама, но
знать стоит: обратный порядок отрезает прогон от машины на середине.

`firewall_cloudflare_only: true` включается там, где origin прячется за CF —
см. [Cloudflare-замок](../operations/cloudflare.md).

## 5. Проверить, что прогон идемпотентен

```bash
ansible-playbook site.yml     # второй прогон подряд
```

Ожидание — `changed=0`. Это не формальность: `changed` на втором прогоне означает роль, которая
переписывает файл каждый раз, а такая роль рано или поздно перезапустит сервис в неподходящий
момент.

## 6. Сверить, что машина не молчит о поломках

```bash
systemctl --failed                  # должно быть пусто
systemctl list-timers 'krot-*'      # если задачи объявлены
```

Ради этой команды сделан выбор транспорта в роли `cron` — разбор в
[отказах, которые не видно](../operations/silent-failures.md).

## Мелочь, которая сбивает

**`fd` на машине называется `fdfind`.** Пакет `fd-find` не может занять имя `fd` — оно принадлежит
другому пакету Debian. Алиас роль не заводит: содержимое login-шелла — дело оператора, а не
машины.
