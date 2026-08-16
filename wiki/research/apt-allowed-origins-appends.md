---
kind: research
title: Allowed-Origins в apt дополняется, а не заменяется
owner: haspadar
verified: 2026-08-15
roles: [common]
---

# Allowed-Origins в apt дополняется, а не заменяется

> **Реализовано** в `molecule-role-tests`, 2026-08-15 (роль `common`, версия 5.2.0). Замеры ниже —
> состояние на дату и переписыванию не подлежат.

Замер от 2026-08-15, Ubuntu 24.04 (noble), контейнер сценария `common`.

Файл в `/etc/apt/apt.conf.d/` с бо́льшим номером читается позже — и на этом основании легко
решить, что он перекрывает прежние значения. **Для списков это неверно.** `Allowed-Origins` —
список, и синтаксис блока

```
Unattended-Upgrade::Allowed-Origins {
    "${distro_id}:${distro_codename}-security";
};
```

разворачивается в `Allowed-Origins::` — оператор **добавления** в список, не присваивания.
Прежние элементы остаются.

## Замер

Роль `common` клала `52-krot-unattended` с тремя security-origin'ами, рассчитывая заменить ими
список из штатного `50unattended-upgrades`. Что apt считал на самом деле:

```console
# apt-config dump | grep Allowed-Origins
Unattended-Upgrade::Allowed-Origins "";
Unattended-Upgrade::Allowed-Origins:: "${distro_id}:${distro_codename}";
Unattended-Upgrade::Allowed-Origins:: "${distro_id}:${distro_codename}-security";
Unattended-Upgrade::Allowed-Origins:: "${distro_id}ESMApps:${distro_codename}-apps-security";
Unattended-Upgrade::Allowed-Origins:: "${distro_id}ESM:${distro_codename}-infra-security";
Unattended-Upgrade::Allowed-Origins:: "${distro_id}:${distro_codename}-security";
Unattended-Upgrade::Allowed-Origins:: "${distro_id}ESMApps:${distro_codename}-apps-security";
Unattended-Upgrade::Allowed-Origins:: "${distro_id}ESM:${distro_codename}-infra-security";
```

Восемь строк вместо трёх: свои добавились к чужим, а не вместо них. Среди уцелевших —
`${distro_id}:${distro_codename}`, и это **весь релизный pocket, а не security**. То есть
машина ставила без спроса обычные обновления релиза — ровно то, что файл был написан
запретить.

## Чем чинится

`#clear` перед блоком — директива apt, опустошающая список:

```
#clear Unattended-Upgrade::Allowed-Origins;

Unattended-Upgrade::Allowed-Origins {
    ...
};
```

После неё `apt-config dump` показывает ровно три security-origin'а, релизный pocket исчезает.

## Почему это не поймали раньше

Проверка «файл на месте, права 0644» проходила и до, и после. Разница видна только если
спросить **apt**, а не файловую систему — `apt-config dump` разбирает весь каталог по порядку и
печатает то, что будет использовано. Отсюда правило для проверок вокруг apt.conf.d: читать
`apt-config dump`, а содержимое собственного файла не считать ответом.

Нашёл сценарий `molecule/common`, при первом же прогоне — assert на origins упал сразу. Родня
этой находке — [отказы, которые не видно](../operations/silent-failures.md): там тот же сюжет,
когда система сообщает об успехе, а сделано не то.
