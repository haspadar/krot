# Задачи

- [x] Схема версии 2: `index_count`, версия в `schema.sql`, `vars/main.yml` и `store.py`
- [x] Store: `count` (upsert без затирания известного), `check` принимает версию 1 для ночей отправки
- [x] Bing: `GetCrawlStats` → дни и `InIndex`; Яндекс: история страниц в поиске и `summary`
- [x] `krot_index.counts`: обход сайтов по движкам, `HOST_NOT_LOADED` не красит юнит
- [x] Роль: юнит и таймер `-counts`, расписание, снятие вместе с проектом, проверка импорта
- [x] Юнит-тесты (с настоящим Postgres), molecule `indexing`, ansible-lint, yamllint
- [x] Вики: источник, частота, NULL/0, ограничения; CHANGELOG
- [ ] Живой читающий вызов API Яндекса: с машины разработки `api.webmaster.yandex.net` недоступен
      (тайм-аут и через тоннель, и напрямую); форма ответа взята из сохранённого снимка, формат
      `date_from`/`date_to` (`Y-m-d`) не подтверждён живым вызовом
- [ ] Двойное ревью до push
