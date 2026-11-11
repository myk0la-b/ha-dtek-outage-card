# Зворотній інжиніринг API dtek-dnem.com.ua

Перевірено на живому сайті: 11.11.2026.

## Захист

- **Incapsula/Imperva** (`visid_incap_2224656`, `incap_ses_553_2224656`, `incap_wrt_376`, `___utmvc`).
  - Статичні файли (`/src/js/...`) віддаються без куки; HTML-сторінки — ні (JS-challenge, сторінка
    з `/_Incapsula_Resource` і заголовком-🐴).
  - `curl`/`requests` — блок. `curl_cffi(impersonate="chrome")` **з валідною Incapsula-cookie** — проходить.
  - `incap_ses`/`incap_wrt` ротаються приблизно раз на 15–30 хв; `visid_incap` живе місяцями.
  - `___utmvc` обчислюється JS-ом челенджу → звичайний HTTP-клієнт сам його не отримає.
  - Практичний висновок: cookie треба періодично «підсвіжувати» з реального браузера.
- **CSRF (Yii2)**: `meta[name="csrf-token"]` + cookie `_csrf-dtek-dnem` (пара). Без заголовка
  `X-CSRF-Token` ajax дає `400 «Не вдалося перевірити передані дані»`.

## Ендпоінти

### GET /ua/shutdowns
HTML (≈815 KB) з вбудованими JS-об'єктами (валідний JSON у літералах):

| Об'єкт | Зміст |
|---|---|
| `DisconSchedule.streets = {...}` | `{ "м. Дніпро": ["вул. Прикладова", ...], ... }` (1177 населених пунктів) |
| `DisconSchedule.preset = {...}` | `days`, `days_mini`, `sch_names` (грupa→«Черга 5.1»), `time_zone` (слот→"00-01","00:00","01:00"), `time_type` (легенда), `data[грupa][день1-7][слот1-24]` = стан |
| `DisconSchedule.fact = {...}` | `data[unix_початок_дня][грupa][слот]` = фактичний стан, `update` (timestamp даних), `today` |

Стани: `yes` (світло є), `no` (немає), `maybe`, `first`/`second` (не буде перші/другі 30 хв),
`mfirst`/`msecond` (можливо). Слот N = `(N-1):00–N:00`.

Також у HTML: банер «екстрені відключення» — `div.m-attention__text`.

### POST /ua/ajax (form-urlencoded)
Обов'язкові заголовки: `X-Requested-With: XMLHttpRequest`, `X-CSRF-Token: <meta>`,
`Content-Type: application/x-www-form-urlencoded; charset=UTF-8`, cookie-сесія сайту.

| `method` | Тіло | Відповідь |
|---|---|---|
| `getStreets` | — | `{result, streets}` — **треба викликати перед getHomeNum** (інакше 500) |
| `getHomeNum` | `data[0][name]=city&data[0][value]=м. Дніпро&data[1][name]=street&data[1][value]=вул. Прикладова&data[2][name]=updateFact&data[2][value]=11.11.2026 15:35` | `{result, data: {"10": {sub_type, start_date, end_date, type, sub_type_reason:["GPV5.1"], ...}}, show*, updateTimestamp}` — адреси→черги + поточна подія по будинку |
| `checkDisconUpdate` | `update=<fact.update>` | оновлені `fact` + `preset` (ті самі об'єкти, що в HTML) |
| `getCekText` | — | `{result, cekText}` — повідомлення ЦЕК («ПЕЕМ Центральна енергетична компанія») з посиланням на cek.dp.ua |

Формат `data[N][name]/data[N][value]` — рядки з форм `serializeArray()` Yii-форми `#discon_form`
(поля `city`, `street`, `house_num`, `updateFact`).

### GET /ua/news
Сторінка новин: `news-top__date/title/text/link` + список `href="/ua/news/<slug>"` з `<h*>` і датою поруч.

## Підказки по адресі
- Ключі будинків у відповіді `getHomeNum` — у форматі вуличного довідника сайту (`10`, `10/к.1`, `10,кор.3/прим.1`, ...); шукайте точний ключ, а не «ваш» форматований рядок. Значення `sub_type_reason` — код черги (напр. `GPV5.1` = «Черга 5.1»).
- `sub_type` у `getHomeNum` — це **подія** (напр. «Стабілізаційне відключення … з 10:27 11.11 до 00:00 12.11»),
  а фактичний стан «зараз» треба брати з `fact.data` (може бути `yes` всередині вікна події).
- Офіційна першоджерельна інструкція сайту: номер черги (`sch_names`) використовується на
  cek.dp.ua для графіків погодинних відключень.

## Політика
Опитувати не частіше разу на 10 хв; не плодити сесій; берегти cookie-файл (це фактично сесійні дані браузера).
