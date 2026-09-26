# Устройство

## Грабли по каждому API

Перенесены из согласованного плана без сокращений: каждая строка — отказ, уже случившийся в
busel или gudok. Юнит-тест модуля покрывает свои строки.

| модуль | что делает | грабли |
|---|---|---|
| `dynadot_ns` | ставит NS у регистратора | Сначала публичный DNS. Нет ответа → стоп, NS не трогать. Домен неизвестен регистратору → сообщение «куплен не здесь», а не ошибка. |
| `cloudflare_zone` | get-or-create зоны, возвращает NS и status | В check-mode не создавать ничего (у busel dry-run чуть не создал зону). Аккаунт/токен задаётся на сайт: пара NS выдаётся на аккаунт. |
| `cloudflare_zone_settings` | ssl=strict, always_use_https=on, browser_cache_ttl=0 | Кеш 4 ч по умолчанию ЗАМЕНЯЕТ Cache-Control origin. strict_origin_pull не включать до установки серта. |
| `cloudflare_origin_cert` | выпуск Origin CA | Ключ выдаётся один раз. Если оба файла на машине непустые — не выпускать. |
| `umami_website` | сайт в Umami, возвращает id | Поиск по домену до создания. Способ доступа — один: API на машине (см. ниже). |
| `ga4_property` | свойство GA4 (Analytics Admin API) | Часовой пояс из страны сайта (stadtdame резал сутки по Europe/Minsk). Валюта — параметр (у busel зашит EUR). Поиск до создания. |
| `uptimerobot_monitor` | мониторы HTTP и keyword | Keyword регистрозависим, тревога на отсутствие; тип не меняется, только пересоздание; слово проверять на главной до создания. Нет активного alert contact → блок. |
| `gsc_site` | verify DNS_TXT, sites.add, owners, sitemap | verify: 6×20 с. 400 = ещё не видно, ретрай; 401/403 = не ретраить. Проверять ВЛАДЕНИЕ (siteOwner), а не присутствие; перечитывать 4×3 с. Owners — PUT всего списка вместе с самим SA (`SEARCH_CONSOLE_OWNER`). Sitemap — на каждом прогоне. Нужны три API: Search Console, Site Verification, Web Search Indexing. |
| `yandex_site` | POST /hosts, TXT, verify, sitemap | verification_uin появляется с задержкой. TXT — строка целиком «yandex-verification: <uin>». IN_PROGRESS опрашивать. Sitemap — в user-added-sitemaps. SITEMAP_ALREADY_ADDED = успех. HOST_NOT_LOADED неделями — норма. |
| `bing_site` | AddSite, CNAME, VerifySite, SubmitFeed | DnsVerificationCode пуст сразу после AddSite — ретрай. Код уже содержит домен: CNAME `<код>` → verify.bing.com, без дописывания домена. VerifySite: `{"d":true}`. SubmitFeed отклоняется (InvalidParameter) несколько минут после verify — ретрай. Опрос по одному URL даёт ThrottleUser на часы; для пачек — SubmitUrlBatch по 50. |

CNAME и TXT для поисковиков ставит `community.general.cloudflare_dns`, а не модуль поисковика:
модуль возвращает, какую запись нужно, роль её ставит, модуль проверяет.

Рабочая логика (ретраи, коды ответов) берётся из busel `src/Colony/{Launch,Search,Registrar,
Cloudflare}`; устройство запросов Origin CA — из роли asapdotid/ansible-role-cloudflare_oca.

## Грабли ролей

- **`site_dns_zone` → `site_domain` → `site_dns_records`**: зона создаётся до регистратора, потому
  что пара NS выдаётся на аккаунт и заранее неизвестна.
- **`site_dns_records`**: Cloudflare держит зону active и после ухода NS, а A-запись засвечивает origin в
  DNS-истории навсегда. Поэтому условие записи — оба факта: active **и** публичные резолверы
  видят NS Cloudflare.
- **`site_tls`**: vhost, собранный без сертификата, остаётся без 443/www и сам не
  перегенерируется (521, www уходит чужому сайту машины) — отсюда «до первого деплоя». Файлы
  создаются сразу с 600 (`install -m 600 /dev/null`, не `tee` с umask 644), пишутся во
  временные имена и переезжают `mv` оба: половина пары роняет `nginx -t` для ВСЕХ сайтов машины.
  `no_log`.
- **`site_database`**: `createdb -O <роль сайта>`, не от postgres. Наличие — по `pg_database`, а
  не подключением. Роль включена, а имени нет → стоп: иначе сайт тихо делит базу с первым сайтом
  машины. psql — всегда `ON_ERROR_STOP=1`.
- **`site_serve_precheck`** (до деплоя): каталог сайта есть в `main` на машине. После деплоя
  эта проверка уже ничего не спасает.
- **`site_serve_check`** (после деплоя): vhost в `sites-enabled`. Код возврата деплоя не
  доказательство — деплой бывает зелёным и ничего не делающим.
- **`site_cloudflare_rules`**: необязательные правила зоны. У busel — кеширование фото
  (`Colony/Cloudflare/CacheRule`): без него каждое фото идёт на origin. Фазовый адрес
  отвечает 404 в конверте Cloudflare, пока набора нет, — это «ещё нет», а не сбой; только
  тогда набор создаётся одним PUT из наших правил. Существующий набор правится **по одному
  правилу** (POST/PATCH), свои узнаются по `ref`: запись целым списком откатила бы чужое
  правило, добавленное в дашборде между нашими чтением и записью.
- **`site_search`**: sitemap сперва запрашивается без авторизации и должен ответить 200. Путь —
  переменная (у gudok скрытый `/sitemap-<токен>.xml`).

## Повтор запросов

Повторяются только запросы, повтор которых ничего не удваивает: GET, PUT, PATCH, DELETE. POST
со сбоем — отказ «исход неизвестен», а не повтор: зона, сертификат или сайт в Bing могли уже
появиться, и следующий прогон найдёт их поиском до записи. 429 ждёт столько, сколько просит
`Retry-After`, но не дольше минуты.

Authenticated Origin Pulls — не зонная настройка (`origin_tls_client_auth`, а не
`tls_client_auth`), и `cloudflare_zone_settings` их не касается. Похожая по имени
`tls_client_auth` — другая функция, модуль её отвергает.

## Где исполняется модуль

- **Облачные API** (Dynadot, Cloudflare, GA4, UptimeRobot, GSC, Яндекс, Bing) — на
  control-машине, `delegate_to: localhost`, `run_once`. Токены не уезжают на сервер сайта.
- **Umami** — на самой машине (`delegate_to` на неё), запросом к API на
  `127.0.0.1:{{ umami_port }}{{ umami_base_path }}` (у busel base path — `/counter`). Тоннель не
  нужен, в базу Umami никто, кроме Umami, не пишет. Порт и путь — те же переменные, что у роли
  `umami`: одно число в одном месте; путь проверяется одним запросом до работы. Учётка — запись
  менеджера секретов. Согласовано с busel и gudok 2026-09-26.
- **Файлы и база** (`site_tls`, `site_database`, `site_serve_check`) — на машине.
- **Ключ Origin CA рождается на машине и её не покидает**: `site_tls` делает ключ и CSR через
  `openssl` во временный файл с 600, модулю `cloudflare_origin_cert` на контроллер уходит только
  CSR, обратно — сертификат. Модуль сам не решает «выпускать ли»: пара на машине уже есть и
  непуста — роль его не зовёт; без этого каждый прогон выпускал бы новый сертификат.

## Проверка делегирования

Публичные резолверы спрашиваются по DNS-over-HTTPS (JSON API), двумя независимыми: ответ
обязан прийти от обоих и совпасть. Это HTTP — значит, подделка в молекуле отвечает и за него,
а модули не тянут `dnspython`. Пустой ответ или сбой — «не смог спросить», а не «NS не наши».
Согласовано с busel 2026-09-26.

## Секреты

**Отступление от плана, принято 2026-09-26 (PR 3).** План предлагал передавать ролям имя записи
в хранилище (`site_cloudflare_account`). В krot действует обратное правило
(`wiki/operations/secrets.md`): ни одна роль в хранилище не ходит, она получает **значение**
(`site_cloudflare_token`, `site_dynadot_key`, `site_bing_key` …), а lookup стоит в инвентаре
проекта. Так роли гоняются в molecule без хранилища и не привязаны к одному менеджеру паролей.

Цель плана — «нет секрета → стоп до первой записи» — сохраняется: `site_preflight` проверяет
непустоту каждого нужного секрета, и ленивые lookup'ы инвентаря вычисляются именно там.

## Записи DNS — свой модуль

**Отступление от плана, PR 3.** `community.general.cloudflare_dns` не принимает адрес API, и его
нельзя направить в подделку — публикация адреса, самый опасный шаг запуска, осталась бы вне
тестов. Записи ставит `haspadar.krot.cloudflare_record`: адрес ищется по типу И имени (иначе
AAAA перезапишет живую A), TXT сравнивается без кавычек и ставится рядом с чужими.

## Роль `site` и плейбук

Общие умолчания всех ролей сайта — в роли `site` без задач, от которой зависят остальные. Имя
выбрано ради правила ansible-lint: переменные роли начинаются с её имени, и `site_` — префикс,
который у них и так есть. Порядок шагов живёт в `playbooks/site_launch.yml`, который входит в
коллекцию: проект запускает `haspadar.krot.site_launch`, а свои шаги передаёт абсолютными
путями к task-файлам. Полученные ID роль отдаёт фактом `site_analytics_results` (не
`site_launch_results`, как в плане, — то же правило префиксов).

## Тесты

- **Модули — pytest против поддельного HTTP-сервера** (`http.server` в потоке, отвечает как
  оригинал и запоминает запросы). Не моки `open_url`: подделка проверяет и то, что модуль
  действительно отправил. Покрытие: ретраи, 400 против 401/403, «не смог спросить»,
  второй вызов → `changed=false`, check-mode без единого пишущего запроса.
- **Юниты гоняются в job'е `lint`** — он уже обязателен для мержа; отдельный job пришлось бы
  отдельно вносить в защиту `main`, и пока его там нет, красные юниты мержу не мешали бы.
- **Роли — molecule, сценарий `site_launch`**: второй контейнер — подделка всех API
  (Cloudflare, Dynadot, Bing, GSC, Яндекс, Umami, DoH), `verify.yml` спрашивает у неё, что было
  заведено. Прецедент — MinIO в `molecule/backup`. Шаг `idempotence` обязателен.

## Переменные сайта (форма)

```yaml
site_domain: tbl-telefon.de
site_registrar: dynadot
site_cloudflare_token: "{{ lookup(...) }}"  # значение; lookup — в инвентаре проекта
site_origin_ip: 1.2.3.4
site_database_name: null                 # не создавать
site_analytics: {umami: true, ga4: false, country: de}
site_monitor: {enabled: false, keyword: null}
site_search_engines: [google, yandex, bing]
site_sitemap_path: /sitemap-<token>.xml
site_env_required: [TELEGRAM_BOT_TOKEN, UMAMI_...]
site_cloudflare_rules: []                # доп. правила зоны, у busel кеш фото
site_analytics_currency: EUR
site_project_fill: tasks/fill.yml        # task-файлы проекта, необязательны
site_project_deploy: tasks/deploy.yml
site_project_verify: tasks/verify.yml
site_project_open: tasks/open.yml
site_results_writer: tasks/write-results.yml
```

Рантайм-ключи приложения в эти переменные не переносятся.
