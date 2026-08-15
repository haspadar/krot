---
kind: research
title: status у systemd_service — снимок до действия
owner: haspadar
verified: 2026-08-15
roles: []
---

# status у systemd_service — снимок до действия

Замер от 2026-08-15, ansible-core **2.21.3**, контейнер сценария `cron`
(`geerlingguy/docker-ubuntu2404-ansible`, systemd 255).

Модуль `ansible.builtin.systemd_service` возвращает `status` — словарь пар из `systemctl show`,
как и обещает документация. **Но снимок берётся до действия и после не обновляется.** Модуль
может в одном ответе сообщить `changed: true` и `ActiveState=inactive` про юнит, который сам же
только что запустил.

## Замер

```yaml
- name: Make sure it is stopped before we start
  ansible.builtin.systemd_service: {name: probe-sleep.service, state: stopped}

- name: Start it — the module both acts and reports
  ansible.builtin.systemd_service: {name: probe-sleep.service, state: started}
  register: started

- name: What the module says versus what the machine says
  ansible.builtin.command: systemctl show probe-sleep.service -p ActiveState
  register: truth
  changed_when: false
```

```
"module_changed": true,
"module_reports_activestate": "inactive",
"machine_says": "ActiveState=active"
```

Юнит взят долгоживущий (`ExecStart=/bin/sleep 3600`) намеренно: на `Type=oneshot` состояние
`inactive` после успешной отработки законно, и расхождение было бы неотличимо от нормы.

## Почему так — в коде

`ansible/modules/systemd_service.py`:

| Строка | Что происходит |
|---|---|
| 390 | `result = dict(name=unit, changed=False, status=dict())` |
| 425 | `result['status'] = parse_systemctl_show(...)` — снимок машины |
| 571 | `module.run_command("%s %s '%s'" % (systemctl, action, unit))` — start/stop |

Между 425 и 571 состояние меняется, а `result['status']` — нет. Повторного `systemctl show`
после действия в модуле нет.

## Следствие

Для роли это несущественно: она **выставляет** состояние, и снимок «как было» ей не мешает.
Для проверки — существенно, потому что проверка спрашивает, **что осталось после прогона**.
Отсюда разделение: состояние выставляют модулем, факт читают командой.

Вторая, более узкая причина: модуль падает, если юнит не пришёл в `active` —
`Unable to start service krot-failing-job.service: Job for ... failed`. В сценарии `cron` есть
задача, которая обязана падать (`/bin/false`), и проверить её видимость модулем, считающим этот
отказ своей ошибкой, невозможно.

## Как перепроверить

Проба целиком — [assets/systemd-service-status-probe.yml](../assets/systemd-service-status-probe.yml),
готовый плейбук. Кладётся на место `verify.yml`, чтобы работать в том же контейнере:

```bash
cp molecule/cron/verify.yml /tmp/verify.yml.bak
cp wiki/assets/systemd-service-status-probe.yml molecule/cron/verify.yml
molecule converge -s cron   # юниты должны существовать
molecule verify -s cron
cp /tmp/verify.yml.bak molecule/cron/verify.yml
```

## Как этот замер сперва получился неверным

Первая версия страницы утверждала, что `status` **отсутствует вовсе**: проба печатала пять
ключей, среди которых его не было. Вывод был ложный, и способ ошибиться стоит записать — он
воспроизводится легко.

Проба гонялась на `krot-failing-job.service` (это `/bin/false`) и была написана с
`failed_when: false`. Модуль на таком юните **падает** — и `failed_when: false` красил падение
зелёным. До строки 425 выполнение не доходило, поэтому в ответе оставались лишь `msg` и служебные
ключи. Улика была на виду и осталась незамеченной: ключ `failed_when_suppressed_exception`
появляется только тогда, когда у задачи было подавленное исключение.

Три «разных состояния» — `started`, `restarted`, `stopped`→`started` — были тремя прогонами по
одному и тому же сломанному пути и подтверждали не поведение модуля, а одну и ту же собственную
ошибку.

Отсюда правило, стоящее дороже самого замера: **`failed_when: false` в пробе обесценивает её**.
Проба, изучающая поведение инструмента, должна падать громко; глушитель ошибок превращает отказ
инструмента в наблюдение о нём. Опровергнуто ревью и перепроверено прогоном на юните, который
завершается успешно (`krot-journal-job.service`): там `status` присутствует, а в нём
`Result=success` и `ExecMainStatus=0`.

## Что осталось непроверенным

- Мерили одну версию, 2.21.3. Было ли иначе раньше и починят ли позже — отсюда не следует.
- Не проверяли, обновляется ли `status` при `daemon_reload` без смены состояния.
