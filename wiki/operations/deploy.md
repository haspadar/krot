---
kind: guide
title: Выкатка и ключи репозиториев
owner: haspadar
verified: 2026-08-15
roles: [deploy, deploy_keys]
---

# Выкатка и ключи репозиториев

Роль `deploy` — **тонкая обёртка**: Deployer запускается на control-машине и сам ходит на сервер
по SSH. CI для выкатки не нужен, это ручной путь.

```bash
ansible-playbook deploy.yml
ansible-playbook deploy.yml -e deploy_task=rollback
ansible-playbook deploy.yml -e deploy_branch=some-branch
```

Роль намеренно не переизобретает релизы, symlink и rollback — этим уже занимается `deploy.php`
проекта. Пересечение Ansible и Deployer ровно одно: Ansible создаёт юзера `km` и каталог
`/var/www/<project>` с правами, куда Deployer кладёт релизы.

## Один deploy key нельзя использовать в двух репозиториях GitHub

Это ограничение GitHub, а не Ansible: ключ привязывается к одному репозиторию.

Машина, тянущая несколько приватных репо, получает **по ключу на каждый** (`deploy_keys`) плюс
host-алиас. Клонировать тогда надо с

```
git@<name>.github.com:owner/repo.git
```

Без алиаса ssh предъявляет **первый подошедший ключ**, и GitHub отвечает за чужой репозиторий —
ошибка при этом выглядит как отсутствие доступа, а не как перепутанный ключ.

## `working_directory` после неудачного деплоя

Релизный симлинк указывает в никуда, и периодические задачи начинают падать с `status=200/CHDIR`.
Это правильное поведение — оно видно в `systemctl --failed`; почему именно так,
в [периодических задачах](cron-jobs.md).
