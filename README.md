# ДТЕК відключення — картка для Home Assistant

[English below](#english)

Картка Lovelace + скрапер офіційних сайтів **п'яти обленерго родини ДТЕК** (одна платформа):
поточний статус світла по **вашій адресі**, графік погодинних відключень на день,
екстрені банери й новини. Без хмари, без сторонніх сервісів, без API-ключів —
все локально.

| `--provider` | Обленерго | Регіон |
|---|---|---|
| `dnipro` (типово) | ДТЕК Дніпровські електромережі | Дніпропетровська обл. |
| `kyiv` | ДТЕК Київські електромережі | м. Київ |
| `kyiv-obl` | ДТЕК Київські регіональні електромережі | Київська обл. |
| `donetsk` | ДТЕК Донецькі електромережі | Донецька обл. |
| `odesa` | ДТЕК Одеські електромережі | Одеська обл. |

![Попередній перегляд](docs/screenshot.png)

## Як це працює

```
сайт обленерго ДТЕК ──(скрапер, cron/systemd кожні 10 хв)──▶ /www/dtek_outage/state.json ──▶ картка
```

- `scraper/dtek_scraper.py` — чистий Python (`curl_cffi`), тягне статус по адресі з офіційного сайту.
- `dtek-outage-card.js` — картка без залежностей; сама завантажує `state.json` і оновлюється.
- Обхід Incapsula/Imperva — **без браузера**: challenge-відповідь віддає свіжу сесійну куку
  у `Set-Cookie`, другий запит проходить. Сесія самовідновлювана (деталі: [docs/API.md](docs/API.md)).

## Встановлення

### 1. Скрапер (можна на будь-якій машині, що бачить інтернет)

```bash
pip install curl_cffi
# точні назви пункту/вулиці/будинку — з довідника самого сайту:
python3 scraper/dtek_scraper.py --provider kyiv --list-cities
python3 scraper/dtek_scraper.py --provider kyiv --streets-for "м. Бориспіль"
python3 scraper/dtek_scraper.py --provider kyiv --homes-for "м. Бориспіль" "вул. Головатого"
# запуск (для Дніпра --city можна не вказувати):
python3 scraper/dtek_scraper.py --provider dnipro --street "вул. Прикладова" --house "10" \
    --out /srv/homeassistant/config/www/dtek_outage/state.json
```

Назви населених пунктів специфічні для кожного провайдера — `--list-cities` показує саме той
довідник, з яким працює скрапер. Для автозапуску кожні 10 хв —
`deploy/dtek-scraper.service` + `.timer` (systemd) або звичайний cron.
Куки-файл опційний і тепер свій для кожного провайдера (`cookies.<provider>.json`);
без нього сесія самовідновлюється через challenge→retry.

Альтернатива без файлу — push у `POST /api/states/sensor.dtek_outage` (токен довгого
життя з профілю HA): прапорець `--push-url` + `--push-token`, приклад у `docs/HA_SETUP.md`.

### 2. Картка

**Через Marketplace** (HA 2026.11+, HACS тепер частина core):
*Settings → Marketplace* → **Add from link** → `myk0la-b/ha-dtek-outage-card`.
Потрібне підключення GitHub (device sign-in; читає лише публічну інформацію).

[![Відкрити репозиторій у Marketplace](https://my.home-assistant.io/badges/marketplace_repository.svg)](https://my.home-assistant.io/redirect/marketplace_repository/?owner=myk0la-b&repository=ha-dtek-outage-card&category=plugin)

**На старіших HA — через HACS:** ⋮ → *Custom repositories* → додати URL цього репозиторію
(тип *Frontend*) → встановити «DTEK Outage Card».

**Вручну:** покласти `dtek-outage-card.js` у `<config>/www/`, потім
*Settings → Dashboards → Resources → Add*: `/local/dtek-outage-card.js`, тип *JavaScript module*.

### 3. Картка на дашборді

```yaml
type: custom:dtek-outage-card
# опційно:
# fetch_url: /local/dtek_outage/state.json   # за замовчуванням
# refresh_minutes: 10
# entity: sensor.dtek_outage                 # читати з HA-сенсора замість fetch
# title: ...                                 # за замовчуванням — "ДТЕК · <регіон>" з даних
```

Повний шлях налаштування (sensor, автоматизації «світло зникло → повідомлення»,
звернення до ІТ-підрозділу через `getCekText`) — [docs/HA_SETUP.md](docs/HA_SETUP.md).

## Обмеження

- Підтримуються п'ять обленерго родини ДТЕК (таблиця на початку) — одна платформа, той самий
  API. Інші обленерго (Львів, Запоріжжя, Миколаїв, Вінниця, …) працюють на інших рушіях:
  адаптери для них у планах, структура `state.json` навмисно проста й від це не змінить.
- Сторінки сайту під Incapsula: якщо ДТЕК посилить захист, скрапер впаде з
  зрозумілою помилкою `[blocked]` — чекайте оновлення тут.
- Це неофіційний скрапер: не чиніть навантаження на сайт (таймер ≥ 10 хв).

## English

Lovelace card + scraper for the official outage sites of the **five DTEK-family oblenergos**
(one shared platform — see the provider table above): current power status for **your
address**, the hourly shutdown schedule for the day, emergency banners and news. No cloud,
no third-party services, no API keys — everything stays local.

### How it works

```
DTEK oblenergo site ──(scraper, cron/systemd every 10 min)──▶ /www/dtek_outage/state.json ──▶ card
```

- `scraper/dtek_scraper.py` — plain Python (single dependency: `curl_cffi`), pulls the
  outage status for your address from the official site.
- `dtek-outage-card.js` — dependency-free card; fetches `state.json` itself and
  auto-refreshes (no sensor or YAML required).
- Incapsula/Imperva is handled **without a browser**: the challenge response issues a
  fresh session cookie via `Set-Cookie`, so a plain retry passes. The session self-heals
  even from a cold start with zero cookies (details: [docs/API.md](docs/API.md) — the
  full API reverse-engineering).

### Installation

**1. Scraper** (any internet-connected machine):

```bash
pip install curl_cffi
# exact settlement/street/house spellings come from the site's own directory:
python3 scraper/dtek_scraper.py --provider kyiv --list-cities
python3 scraper/dtek_scraper.py --provider kyiv --streets-for "м. Бориспіль"
python3 scraper/dtek_scraper.py --provider kyiv --homes-for "м. Бориспіль" "вул. Головатого"
# run (for dnipro, --city can be omitted):
python3 scraper/dtek_scraper.py --provider dnipro --street "вул. Прикладова" --house "10" \
    --out /srv/homeassistant/config/www/dtek_outage/state.json
```

Settlement names are provider-specific — `--list-cities` prints exactly the directory the
scraper matches against. For unattended runs every 10 minutes:
`deploy/dtek-scraper.service` + `.timer` (systemd) or plain cron.
The cookie file is optional and now per-provider (`cookies.<provider>.json`); without it the
session self-heals via challenge→retry.

File-free alternative — push straight into HA via `POST /api/states/sensor.dtek_outage`
(long-lived access token from your HA profile): `--push-url` + `--push-token`, example in
`docs/HA_SETUP.md`.

**2. Card.** Via **Marketplace** (HA 2026.11+, HACS is now part of core):
*Settings → Marketplace* → **Add from link** → `myk0la-b/ha-dtek-outage-card`.
Requires a GitHub connection (device sign-in; reads public information only).

[![Open this repository in the Marketplace](https://my.home-assistant.io/badges/marketplace_repository.svg)](https://my.home-assistant.io/redirect/marketplace_repository/?owner=myk0la-b&repository=ha-dtek-outage-card&category=plugin)

On older HA — via **HACS**: ⋮ → *Custom repositories* → add this repository URL (type
*Frontend*) → install «DTEK Outage Card». Manually: copy `dtek-outage-card.js` to
`<config>/www/`, then *Settings → Dashboards → Resources → Add* →
`/local/dtek-outage-card.js`, type *JavaScript module*.

**3. Dashboard card:**

```yaml
type: custom:dtek-outage-card
# optional:
# fetch_url: /local/dtek_outage/state.json   # default
# refresh_minutes: 10
# entity: sensor.dtek_outage                 # read from an HA sensor instead of fetching
# title: ...                                 # default: "ДТЕК · <region>" from the data
```

Full setup path (REST sensor, "power went out → push notification" automations, filing
a request to the utility's IT unit via `getCekText`) — [docs/HA_SETUP.md](docs/HA_SETUP.md).

### Limitations

- Supported: the five DTEK-family oblenergos (table at the top) — one platform, same API.
  Other oblenergos (Lviv, Zaporizhzhia, Mykolaiv, Vinnytsia, …) run different engines;
  adapters are on the roadmap and the deliberately simple `state.json` schema won't change.
- The site sits behind Incapsula: if DTEK hardens protection, the scraper will fail with
  a clear `[blocked]` error — an update will appear here.
- Unofficial scraper: be polite to the site (interval ≥ 10 minutes).

## License

MIT — © 2026 Mykola Bashmakov
