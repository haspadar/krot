# Tasks: провалившийся assert пропускал задачу молча

## Замер (busel, systemd 255, 2026-08-13)
Пробные юниты, поставленные и снятые вручную; `krot-traffic` и `krot-cf-ranges` не тронуты.

- [x] `AssertPathIsDirectory=/nonexistent` + `systemctl start`: **`Result=success`**,
      `ExecMainStatus=0`, `ActiveState=inactive`, `AssertResult=no`, `systemctl --failed` пуст.
      Команда `start` при этом вернула 1 и напечатала `Assertion failed on job for …` — то есть
      **отказ виден только тому, кто запускает вручную**, а таймеру такого канала нет
- [x] `WorkingDirectory=/nonexistent` без assert: `Result=exit-code`, `ExecMainStatus=200`
      (CHDIR), `ActiveState=failed`, одна строка в `systemctl --failed`
- [x] То же **по таймеру**, а не руками: `OnCalendar=*-*-* *:*:00`, после первого срабатывания
      юнит в `--failed`. Это и есть критерий приёмки — ручной запуск ничего не доказывает,
      задача запускается таймером
- [x] За собой убрано: пробные `.service`/`.timer` удалены, `daemon-reload`, `reset-failed`;
      на машине остались только `krot-cf-ranges.*` и `krot-traffic.*`, `--failed` пуст

## Правка
- [x] `AssertPathIsDirectory=` убран из `job.service.j2` вместе с секцией `[Unit]`-условия
- [x] Объяснение и замер перенесены к `WorkingDirectory=` — к строке, которая теперь и
      обеспечивает падение
- [x] `defaults/main.yml`: описание `working_directory` говорит, что симлинк в никуда валит
      задачу, а не запускает её из `/`
- [x] README: то же в разделе про периодические задачи
- [x] CHANGELOG: 5.1.1, с указанием, что юниты на развёрнутых машинах перезапишутся

## Проверка
- [x] Шаблон рендерится обоими путями: с `working_directory` и без него — во втором случае
      `WorkingDirectory=` не появляется вовсе, и юнит по-прежнему валиден
- [x] **Приёмка на отрендеренном ролью юните.** Тот самый файл, что даёт исправленный шаблон,
      положен на busel с `working_directory`, указывающим в никуда, и заведён таймером. После
      срабатывания: `status=200/CHDIR`, `ActiveState=failed`, строка в `systemctl --failed`.
      Проверялось не «assert убран», а видимость отказа
- [x] Проба снята, `krot-traffic` и `krot-cf-ranges` на месте, `--failed` пуст
- [x] `yamllint`, `ansible-lint` (profile production) чистые
- [ ] На busel не применять: роль там стоит и работает, сайты открыты. Прогон — отдельным
      решением после мержа
