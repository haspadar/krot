# Tasks: роль впервые встречает реальность на проде

## Замер (локально, 2026-08-15, Docker 29.7.2)
Пробный контейнер `krot-probe`, поднят и снят; образ
`geerlingguy/docker-ubuntu2404-ansible`, `--privileged --cgroupns=host`, `/sys/fs/cgroup:rw`.

- [x] ОС в контейнере — Ubuntu **24.04.4 LTS (Noble Numbat)**, целевая платформа krot
- [x] systemd поднялся: `systemctl is-system-running` -> **`running`**, версия **255**
      (`255.4-1ubuntu8.16`) — та же, на которой сделаны замеры в `wiki/operations/`
- [x] Роль `cron` прогнана через `connection: community.docker.docker` с одной задачей:
      **`ok=11 changed=3`**, установлены `.service` и `.timer`, отработал хендлер
      `Reload systemd`
- [x] **Второй прогон: `ok=10 changed=0`** — идемпотентность замерена в контейнере, без
      живой машины. Это и есть критерий приёмки всей затеи
- [x] Таймер существует по факту, а не в выводе Ansible: `systemctl is-enabled
      krot-probe-job.timer` -> `enabled`, строка в `list-timers` со следующим стартом
- [x] **ufw в контейнере работает** (проверено, потому что ожидалось обратное):
      `ufw enable` -> активен, `iptables -L INPUT -n` -> **`policy DROP`** и цепочки
      `ufw-before-input`. Правила ложатся в netfilter, а не имитируются
- [x] За собой убрано: `docker rm -f krot-probe`, контейнеров с этим именем не осталось

## Правка
- [ ] `molecule/` со сценарием `default`: драйвер docker, платформа noble, `privileged`,
      `cgroupns_mode: host`, монтирование cgroup
- [ ] Сценарий на роль `cron` — с неё начинаем, она уже дала тихий отказ
- [ ] Сценарии на `bootstrap`, `nginx`, `postgresql`
- [ ] `converge.yml` и прогон `idempotence` в каждом сценарии
- [ ] Шаг Molecule в `.github/workflows/` — отдельным job, чтобы падение линтера
      было отличимо от падения роли
- [ ] README: раздел про прогон тестов локально
- [ ] `CHANGELOG.md`
- [ ] Явный список покрытых и непокрытых ролей — иначе непокрытые тихо сойдут за проверенные

## Проверка
- [ ] `molecule test` зелёный локально на каждой заведённой роли
- [ ] Второй прогон даёт `changed=0` внутри сценария, а не только в ручной пробе
- [ ] Намеренно сломанная роль **роняет** сценарий — проверка проверки: без этого
      зелёный CI не значит ничего
- [ ] `yamllint`, `ansible-lint` чистые на самих файлах Molecule
- [ ] Замерено время прогона в CI и записано в change про расход Actions

## Не делать здесь
- [ ] `ansible-test` — нечего проверять, пока нет `plugins/` (обоснование в proposal)
- [ ] pytest на `scripts/*.py` — свой change
- [ ] Роли `deploy`, `deploy_keys`, `docker` — сценарии либо бессмысленны в контейнере,
      либо требуют отдельного решения
