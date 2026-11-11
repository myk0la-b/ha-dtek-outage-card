# ДТЕК відключення — картка для Home Assistant

[English below](#english)

Картка Lovelace + скрапер офіційного сайту [ДТЕК Дніпрообленерго](https://www.dtek-dnem.com.ua/ua/shutdowns):
поточний статус світла по **вашій адресі**, графік погодинних відключень на день,
екстрені банери й новини. Без хмари, без сторонніх сервісів, без API-ключів —
все локально.

![Попередній перегляд](docs/screenshot.png)

## Як це працює

```
dtek-dnem.com.ua ──(скрапер, cron/systemd кожні 10 хв)──▶ /www/dtek_outage/state.json ──▶ картка
```

- `scraper/dtek_scraper.py` — чистий Python (`curl_cffi`), тягне статус по адресі з офіційного сайту.
- `dtek-outage-card.js` — картка без залежностей; сама завантажує `state.json` і оновлюється.
- Обхід Incapsula/Imperva — **без браузера**: challenge-відповідь віддає свіжу сесійну куку
  у `Set-Cookie`, другий запит проходить. Сесія самовідновлювана (деталі: [docs/API.md](docs/API.md)).

## Встановлення

### 1. Скрапер (можна на будь-якій машині, що бачить інтернет)

```bash
pip install curl_cffi
python3 scraper/dtek_scraper.py --city "м. Дніпро" --street "вул. Прикладова" --house "10" \
    --out /srv/homeassistant/config/www/dtek_outage/state.json
```

Адресу варто взяти з підказок самого сайту (сторінка «Графік відключень»): скрапер
свірить вуличний довідник і шукає точний ключ будинку. Для автозапуску кожні 10 хв —
`deploy/dtek-scraper.service` + `.timer` (systemd) або звичайний cron.

Альтернатива без файлу — push у `POST /api/states/sensor.dtek_outage` (токен довгого
життя з профілю HA): прапорець `--push-url` + `--push-token`, приклад у `docs/HA_SETUP.md`.

### 2. Картка

**Через HACS:** ⋮ → *Custom repositories* → додати URL цього репозиторію
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
# title: ДТЕК · відключення
```

Повний шлях налаштування (sensor, автоматизації «світло зникло → повідомлення»,
звернення до ІТ-підрозділу через `getCekText`) — [docs/HA_SETUP.md](docs/HA_SETUP.md).

## Обмеження

- Графік і статус доступні лише для клієнтів **ДТЕК Дніпрообленерго** (мережа Дніпра;
  для інших обленерго треба адаптувати скрапер — структура `state.json` навмисно проста).
- Сторінки сайту під Incapsula: якщо ДТЕК посилить захист, скрапер впаде з
  зрозумілою помилкою `[blocked]` — чекайте оновлення тут.
- Це неофіційний скрапер: не чиніть навантаження на сайт (таймер ≥ 10 хв).

## English

Lovelace card + scraper for the official DTEK Dniprooblenergo outage site. A small
Python script (only dependency: `curl_cffi`) fetches your address's live outage status,
the 24-slot day schedule, emergency banners and news into a static `state.json`; the
dependency-free card fetches and renders it. Incapsula is handled without a headless
browser: the challenge response issues a fresh session cookie via `Set-Cookie`, so a
plain retry passes — the session self-heals. Install via HACS (custom repository) or
manually as a `/local/` resource. MIT licensed.

## License

MIT — © 2026 Mykola Bashmakov
