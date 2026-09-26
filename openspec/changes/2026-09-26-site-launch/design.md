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
| `umami_website` | сайт в Umami, возвращает id | Поиск по домену до создания. Способ доступа — один (см. ниже). |
| `ga4_property` | свойство GA4 (Analytics Admin API) | Часовой пояс из страны сайта (stadtdame резал сутки по Europe/Minsk). Поиск до создания. |
| `uptimerobot_monitor` | мониторы HTTP и keyword | Keyword регистрозависим, тревога на отсутствие; тип не меняется, только пересоздание; слово проверять на главной до создания. Нет активного alert contact → блок. |
| `gsc_site` | verify DNS_TXT, sites.add, owners, sitemap | verify: 6×20 с. 400 = ещё не видно, ретрай; 401/403 = не ретраить. Проверять ВЛАДЕНИЕ (siteOwner), а не присутствие; перечитывать 4×3 с. Owners — PUT всего списка вместе с самим SA (`SEARCH_CONSOLE_OWNER`). Sitemap — на каждом прогоне. Нужны три API: Search Console, Site Verification, Web Search Indexing. |
| `yandex_site` | POST /hosts, TXT, verify, sitemap | verification_uin появляется с задержкой. TXT — строка целиком «yandex-verification: <uin>». IN_PROGRESS опрашивать. Sitemap — в user-added-sitemaps. SITEMAP_ALREADY_ADDED = успех. HOST_NOT_LOADED неделями — норма. |
| `bing_site` | AddSite, CNAME, VerifySite, SubmitFeed | DnsVerificationCode пуст сразу после AddSite — ретрай. Код уже содержит домен: CNAME `<код>` → verify.bing.com, без дописывания домена. VerifySite: `{"d":true}`. SubmitFeed отклоняется (InvalidParameter) несколько минут после verify — ретрай. Опрос по одному URL даёт ThrottleUser на часы; для пачек — SubmitUrlBatch по 50. |

CNAME и TXT для поисковиков ставит `community.general.cloudflare_dns`, а не модуль поисковика:
модуль возвращает, какую запись нужно, роль её ставит, модуль проверяет.

Рабочая логика (ретраи, коды ответов) берётся из busel `src/Colony/{Launch,Search,Registrar,
Cloudflare}`; устройство запросов Origin CA — из роли asapdotid/ansible-role-cloudflare_oca.

## Грабли ролей

- **`site_dns`**: Cloudflare держит зону active и после ухода NS, а A-запись засвечивает origin в
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
- **`site_serve_check`**: код возврата деплоя не доказательство — деплой бывает зелёным и
  ничего не делающим. Проверяется vhost в `sites-enabled` и каталог сайта в текущем релизе.
- **`site_search`**: sitemap сперва запрашивается без авторизации и должен ответить 200. Путь —
  переменная (у gudok скрытый `/sitemap-<токен>.xml`).

## Где исполняется модуль

- **Облачные API** (Dynadot, Cloudflare, GA4, UptimeRobot, GSC, Яндекс, Bing) — на
  control-машине, `delegate_to: localhost`, `run_once`. Токены не уезжают на сервер сайта.
- **Umami** — на самой машине, запросом к API на `127.0.0.1:<umami_port>`. Тоннель не нужен, в
  базу Umami никто, кроме Umami, не пишет. Порт — из той же переменной, что у роли `umami`:
  одно число в одном месте.
- **Файлы и база** (`site_tls`, `site_database`, `site_serve_check`) — на машине.

## Проверка делегирования

Публичные резолверы спрашиваются по DNS-over-HTTPS (JSON API), двумя независимыми: ответ
обязан прийти от обоих и совпасть. Это HTTP — значит, подделка в молекуле отвечает и за него,
а модули не тянут `dnspython`. Пустой ответ или сбой — «не смог спросить», а не «NS не наши».

## Секреты

По соглашению krot (`wiki/operations/secrets.md`): lookup `community.general.bitwarden` в
рантайме, поле notes, `no_log`. Роль получает **имя записи** (`site_cloudflare_account` и т. п.),
а не значение; preflight проверяет, что все записи находятся, до первой записи.

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
site_cloudflare_account: gudok-b        # имя записи с токеном
site_origin_ip: 1.2.3.4
site_database_name: null                 # не создавать
site_analytics: {umami: true, ga4: false, country: de}
site_monitor: {enabled: false, keyword: null}
site_search_engines: [google, yandex, bing]
site_sitemap_path: /sitemap-<token>.xml
site_env_required: [TELEGRAM_BOT_TOKEN, UMAMI_...]
site_project_fill: tasks/fill.yml        # task-файлы проекта, необязательны
site_project_deploy: tasks/deploy.yml
site_project_open: tasks/open.yml
site_results_writer: tasks/write-results.yml
```

Рантайм-ключи приложения в эти переменные не переносятся.
