# Налаштування Home Assistant

## 1. Картка (custom card)

1. Скопіювати `ha/dtek-outage-card.js` у `config/www/` (на Pi: `/srv/homeassistant/config/www/dtek-outage-card.js`).
2. Lovelace → Edit dashboard → Resources (або Settings → Dashboards → Resources):
   - URL: `/local/dtek-outage-card.js`, type: **JavaScript module**.
3. Додати картку (Manual / raw):

```yaml
type: custom:dtek-outage-card
entity: sensor.dtek_outage
title: ДТЕК · відключення
```

## 2. Сенсор

### Варіант A — REST sensor (pull, без токенів) — рекомендовано

scraper пише `www/dtek_outage/state.json` (сервется HA як `/local/...`, без авторизації).
`configuration.yaml`:

```yaml
sensor:
  - platform: rest
    name: DTEK outage
    unique_id: dtek_outage
    resource: http://http://<HA_HOST>:8123lt;HA_HOSThttp://<HA_HOST>:8123gt;:8123/local/dtek_outage/state.json
    value_template: "{{ value_json.current.state }}"
    json_attributes:
      - current
      - next
      - today
      - tomorrow
      - news
      - emergency
      - address
      - updated
      - site_data_updated
      - time_type_legend
      - source
    scan_interval: 600
```

> URL має бути локальною адресою HA (не cloudflared-домен), інакше HA ходиме «в обхід» через інтернет.

### Варіант B — push з Mac (якщо scraper не на Pi)

Створити Long-Lived Access Token: HA → профіль → Long-lived access tokens, і в scraper:

```bash
python3 dtek_scraper.py --provider dnipro --push-url http://<HA_HOST>:8123 --push-token <TOKEN> --entity sensor.dtek_outage
```

Сенсор тоді створюється напряму (REST API `POST /api/states/sensor.dtek_outage`) і не потребує YAML —
лише додати `sensor.dtek_outage` у `recorder`/`history` за бажанням.

## 3. Automations (за бажанням)

Push-notify коли світло вимкнули:

```yaml
automation:
  - trigger:
      - platform: state
        entity_id: sensor.dtek_outage
        to: "off"
    action:
      - service: notify.mobile_app_your_phone
        data:
          title: "ДТЕК: відключення"
          message: >-
            {{ state_attr('sensor.dtek_outage','current').label }}
            (черга {{ state_attr('sensor.dtek_outage','address').group_name }})
```

## 5. Реєстрація resource без UI (файловий шлях)

Див. `.storage/lovelace_resources` + `lovelace_dashboards` + `lovelace.<id>`; після редагування — рестарт HA. Формати — як у наявних записів.
