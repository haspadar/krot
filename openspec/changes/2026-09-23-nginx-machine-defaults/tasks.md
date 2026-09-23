# Задачи

- [x] Флаги `nginx_cloudflare_real_ip` и `nginx_default_server`, оба `false`
- [x] Скрипт `krot-nginx-real-ip`: оба семейства, только CIDR, `nginx -t`, откат, коды 0/10
- [x] Суточный таймер обновления диапазонов
- [x] `krot-default-server.conf` на snakeoil-сертификате
- [x] Предпроверка: чужие `real_ip_*`, `set_real_ip_from`, `default_server` — отказ до записи
- [x] Флаг выключен — свой файл и таймер убраны
- [x] Molecule: сценарий с обоими флагами — 444 на неизвестное имя по 80 и 443, real-IP в `nginx -T`
- [x] Molecule: предпроверка отказывает на чужом файле
- [x] Вики: `cloudflare.md`, `logging.md`, `collection-layout.md` — кто теперь хозяин real-IP
- [ ] Двойное ревью до push
- [ ] Выкатка на busel вместе с PR busel — делается в busel
