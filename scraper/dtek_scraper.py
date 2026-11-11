#!/usr/bin/env python3
"""
Графіки відключень обленерго родини ДТЕК → Home Assistant state JSON.

Підтримувані провайдери (однакова платформа — DisconSchedule + /ua/ajax):
  dnipro     ДТЕК Дніпровські електромережі        (Дніпропетровська обл.)   --provider dnipro
  kyiv       ДТЕК Київські електромережі           (м. Київ)                 --provider kyiv
  kyiv-obl   ДТЕК Київські регіональні електромер. (Київська обл.)            --provider kyiv-obl
  donetsk    ДТЕК Донецькі електромережі           (Донецька обл.)           --provider donetsk
  odesa      ДТЕК Одеські електромережі            (Одеська обл.)            --provider odesa
Інші обленерго (Львів, Запоріжжя, Миколаїв, Вінниця, …) — інші рушії; не входить.

Повний цикл:
  1. GET /ua/shutdowns (через curl_cffi з імперсонацією Chrome + Incapsula-cookie)
     → вбудовані в HTML об'єкти DisconSchedule.preset / .fact (графіки + фактичні відключення)
  2. POST /ua/ajax method=getStreets   (прогрів сесії — інакше getHomeNum дає 500)
  3. POST /ua/ajax method=getHomeNum   → адреса → група ("черга"), поточний факт по будинку
  4. POST /ua/ajax method=getCekText   → офіційне повідомлення ЦЕК
  5. GET  /ua/news                     → останні новини
  6. Банер "екстрені відключення" (div.m-attention__text) прямо зі сторіки графіків

Допомога з адресою (назви населених пунктів специфічні для кожного провайдера):
  --list-providers            перелік провайдерів
  --list-cities               доступні населені пункти (після --provider)
  --streets-for "м. Х"        вулиці для пункту; --homes-for "м. Х" "вул. У" — будинки

Вихід — один JSON (stdout / --out файл / --push в HA REST /api/states/<entity>).
Код виходу: 0 ok, 2 Incapsula-куки протерміновані (потрібен refresh), 3 не вдалося розібрати дані.
"""
import argparse
import datetime as dt
import json
import re
import sys
from html import unescape
from pathlib import Path
from urllib.parse import quote, urlparse
from zoneinfo import ZoneInfo

# Реєстр провайдерів: одна платформа, різні домени. region — для заголовка картки.
PROVIDERS = {
    "dnipro":   {"base": "https://www.dtek-dnem.com.ua", "name": "ДТЕК Дніпровські електромережі",
                 "region": "Дніпропетровська обл.", "default_city": "м. Дніпро"},
    "kyiv":     {"base": "https://www.dtek-kem.com.ua",  "name": "ДТЕК Київські електромережі",
                 "region": "м. Київ", "default_city": "м. Київ"},
    "kyiv-obl": {"base": "https://www.dtek-krem.com.ua", "name": "ДТЕК Київські регіональні електромережі",
                 "region": "Київська обл.", "default_city": None},
    "donetsk":  {"base": "https://www.dtek-dem.com.ua",  "name": "ДТЕК Донецькі електромережі",
                 "region": "Донецька обл.", "default_city": None},
    "odesa":    {"base": "https://www.dtek-oem.com.ua",  "name": "ДТЕК Одеські електромережі",
                 "region": "Одеська обл.", "default_city": None},
}
DEFAULT_PROVIDER = "dnipro"
BASE = PROVIDERS[DEFAULT_PROVIDER]["base"]   # перевстановлюється у main() з --provider
TZ = ZoneInfo("Europe/Kyiv")

OFF_STATES = {"no", "first", "second"}
MAYBE_STATES = {"maybe", "mfirst", "msecond"}

BLOCKED_MARKERS = ("_Incapsula_Resource", "Incapsula incident")


class BlockedError(RuntimeError):
    pass


# ---------------------------------------------------------------- HTTP layer

def make_session(cookie_file: Path):
    """Сесія curl_cffi. Cookie-файл опціональний (тільки 'теплий' старт: visid_incap тощо);
    Incapsula-сесія самовідновлюється через challenge→retry у get_html().
    Куки беруться лише якщо їх домен збігається з поточним BASE (інакше — холодний старт)."""
    from curl_cffi import requests as cr

    s = cr.Session(impersonate="chrome")
    host = urlparse(BASE).netloc  # www.dtek-kem.com.ua
    cookie_host = "." + host[4:] if host.startswith("www.") else "." + host
    if cookie_file and Path(cookie_file).exists():
        try:
            raw = json.loads(Path(cookie_file).read_text())
            entries = raw if isinstance(raw, list) else [
                {"name": k, "value": v, "domain": cookie_host} for k, v in raw.items()]
            for c in entries:
                dom = c.get("domain") or cookie_host
                if c["name"].startswith(("visid_incap", "nlbi")) and (
                        dom == cookie_host or dom.endswith(cookie_host.lstrip("."))):
                    # тільки довговічні й тільки «свого» домену; incap_ses ротається сам
                    s.cookies.set(c["name"], c["value"], domain=dom)
        except (ValueError, OSError, KeyError):
            pass
    return s


def blocked(text: str) -> bool:
    return len(text) < 20_000 or any(m in text[:4000] for m in BLOCKED_MARKERS)


def get_html(s, path, retries=3):
    """GET з самовідновленням: Incapsula-челендж віддає свіжий incap_ses у Set-Cookie —
    достатньо повторити запит (JS виконувати не треба)."""
    last = ""
    for attempt in range(retries):
        r = s.get(BASE + path, timeout=45)
        last = r.text or ""
        if r.status_code == 200 and not blocked(last):
            return last
        import time

        time.sleep(2 * (attempt + 1))  # сесійна кука підхоплюється автоматично
    raise BlockedError(
        f"{path}: Incapsula не пропустила після {retries} спроб (остання сторінка {len(last)} B). "
        f"Спробуйте пізніше або оновіть cookies.dtek.json з браузера."
    )


def ajax(s, csrf, fields):
    """fields: list[(key, value)] — форма як у сайті: method=...&data[N][name]=...&data[N][value]=..."""
    body = "&".join(f"{quote(k, safe='')}" + "=" + f"{quote(str(v), safe='')}" for k, v in fields)
    r = s.post(
        BASE + "/ua/ajax",
        data=body.encode(),
        headers={
            "X-Requested-With": "XMLHttpRequest",
            "X-CSRF-Token": csrf,
            "Content-Type": "application/x-www-form-urlencoded; charset=UTF-8",
            "Referer": BASE + "/ua/shutdowns",
        },
        timeout=45,
    )
    try:
        return r.json()
    except Exception:
        return {"result": False, "_status": r.status_code, "_text": (r.text or "")[:200]}


# ---------------------------------------------------------------- HTML parsing

def extract_js_object(html: str, marker: str):
    """Знайти `marker = { ... }` і повернути розпарсений JSON-об'єкт."""
    i = html.find(marker)
    if i < 0:
        return None
    j = html.find("{", i)
    if j < 0:
        return None
    depth, instr, esc = 0, False, False
    for k in range(j, len(html)):
        c = html[k]
        if instr:
            if esc:
                esc = False
            elif c == "\\":
                esc = True
            elif c == '"':
                instr = False
        elif c == '"':
            instr = True
        elif c == "{":
            depth += 1
        elif c == "}":
            depth -= 1
            if depth == 0:
                return json.loads(html[j : k + 1])
    return None


def strip_tags(fragment: str) -> str:
    txt = re.sub(r"<br\s*/?>", "\n", fragment, flags=re.I)
    txt = re.sub(r"</p>", "\n", txt, flags=re.I)
    txt = re.sub(r"<[^>]+>", " ", txt)
    txt = unescape(txt)
    return re.sub(r"[ \t]+", " ", re.sub(r"\s*\n\s*", "\n", txt)).strip()


def parse_emergency(html: str):
    out = []
    for m in re.finditer(r'<div[^>]*class="[^"]*m-attention__text[^"]*"[^>]*>(.*?)</div>', html, re.S):
        t = strip_tags(m.group(1))
        if t:
            out.append(t)
    return "\n\n".join(out)


def parse_news(html: str, limit: int = 5):
    items, seen = [], set()
    for m in re.finditer(r'href="(/ua/news/[a-z0-9\-]+)"', html):
        url = m.group(1)
        if url in seen or url.rstrip("/").endswith("/ua/news"):
            continue
        window = html[max(0, m.start() - 900) : m.start()]
        dm = re.findall(r"(\d{2}\.\d{2}\.\d{4})", window)
        tm = re.findall(r"<h\d[^>]*>([^<]{15,200})</h\d>", window)
        if not tm:
            continue
        seen.add(url)
        items.append(
            {
                "date": dm[-1] if dm else None,
                "title": unescape(tm[-1]).strip(),
                "url": BASE + url,
            }
        )
        if len(items) >= limit:
            break
    return items


# ---------------------------------------------------------------- schedule math

def slot_of(dt_local: dt.datetime) -> int:
    """Слот 1..24 (slot N = (N-1):00–N:00)."""
    return dt_local.hour + 1


def group_states(preset, fact, group, when: dt.datetime):
    """Стани 24 слотів на дату `when`: факт (якщо є) або план; повертає list[(slot, state, source)]."""
    day_slots = {}
    if fact and fact.get("data"):
        for ts_s, groups in fact.get("data", {}).items():
            try:
                ts_day = dt.datetime.fromtimestamp(int(ts_s), TZ).date()
            except (ValueError, OSError):
                continue
            if ts_day == when.date():
                day_slots = groups.get(group, {}) or {}
                break
    plan = (preset.get("data", {}).get(group, {}) or {}).get(str(when.isoweekday()), {}) or {}
    rows = []
    for sl in range(1, 25):
        s = str(sl)
        if day_slots.get(s):
            rows.append((sl, day_slots[s], "fact"))
        elif plan.get(s):
            rows.append((sl, plan[s], "plan"))
        else:
            rows.append((sl, None, "none"))
    return rows


def next_event(rows_today, rows_next_day, tz_map, now_local, current_state):
    """Найближча зміна стану 'живий' <-> 'мертвий' після поточного слоту."""
    def off(state):
        return state in OFF_STATES

    cur_off = current_state in OFF_STATES
    for sl, st, _ in rows_today:
        if sl <= slot_of(now_local) or st is None:
            continue
        if off(st) != cur_off:
            return {"at": tz_map[str(sl)][1], "state": "off" if off(st) else "on", "day": "today"}
    for sl, st, _ in rows_next_day:
        if st is None:
            continue
        if off(st) != cur_off:
            return {"at": tz_map[str(sl)][1], "state": "off" if off(st) else "on", "day": "tomorrow"}
    return None


# ---------------------------------------------------------------- main pipeline

def build_state(provider, city, street, house, cookie_file, news_max=5):
    s = make_session(cookie_file)
    html = get_html(s, "/ua/shutdowns")
    csrf_m = re.search(r'name="csrf-token" content="([^"]+)"', html)
    if not csrf_m:
        raise BlockedError("csrf-token не знайдено в HTML — структура сторінки змінилась.")
    csrf = csrf_m.group(1)

    preset = extract_js_object(html, "DisconSchedule.preset")
    fact = extract_js_object(html, "DisconSchedule.fact")
    if preset is None or fact is None:
        raise BlockedError("Не знайдено вбудовані об'єкти preset/fact — сайт змінив розмітку.")

    # прогрів сесії (обов'язково перед getHomeNum) + адреса → група
    ajax(s, csrf, [("method", "getStreets")])
    fields = [("method", "getHomeNum"),
              ("data[0][name]", "city"), ("data[0][value]", city),
              ("data[1][name]", "street"), ("data[1][value]", street),
              ("data[2][name]", "updateFact"), ("data[2][value]", fact.get("update", ""))]
    home = ajax(s, csrf, fields)
    if not home.get("result") or house not in home.get("data", {}):
        raise BlockedError(
            f"Будинок '{house}' не знайдено для '{city}' / '{street}'. "
            f"Доступні приклади: {sorted(home.get('data', {}).keys())[:12]}"
        )
    house_info = home["data"][house]
    groups = house_info.get("sub_type_reason") or []
    group = groups[0] if groups else None

    cek = ajax(s, csrf, [("method", "getCekText")]).get("cekText")
    now_local = dt.datetime.now(TZ)
    tz_map = preset.get("time_zone", {})

    current = {"state": "unknown", "label": "Немає даних", "detail": house_info.get("sub_type"),
               "since": house_info.get("start_date"), "until": house_info.get("end_date")}
    today_rows, tomorrow_rows, next_ev = [], [], None
    if group:
        today_rows = group_states(preset, fact, group, now_local)
        tomorrow_rows = group_states(preset, fact, group, now_local + dt.timedelta(days=1))
        cur_slot = today_rows[slot_of(now_local) - 1]
        st = cur_slot[1] or (tomorrow_rows[0][1] if tomorrow_rows else None)
        if st:
            if st in OFF_STATES:
                current.update(state="off", label=preset["time_type"].get(st, "Відключено"))
            elif st in MAYBE_STATES:
                current.update(state="maybe", label=preset["time_type"].get(st, "Можливе відключення"))
            else:
                current.update(state="on", label=preset["time_type"].get(st, "Світло є"))
        next_ev = next_event(today_rows, tomorrow_rows, tz_map, now_local, current["state"])

    news_html = get_html(s, "/ua/news")
    prov = PROVIDERS[provider]
    out = {
        "updated": now_local.isoformat(timespec="seconds"),
        "source": BASE + "/ua/shutdowns",
        "provider": {"key": provider, "name": prov["name"], "region": prov["region"]},
        "address": {"city": city, "street": street, "house": house,
                    "group": group, "group_name": (preset.get("sch_names", {}) or {}).get(group),
                    "multi_group": groups if len(groups) > 1 else None},
        "current": current,
        "next": next_ev,
        "today": [{"slot": sl, "from": tz_map.get(str(sl), [None, f"{sl-1:02d}:00"])[1],
                   "to": tz_map.get(str(sl), [None, None, f"{sl:02d}:00"])[2] if len(tz_map.get(str(sl), [])) > 2 else f"{sl:02d}:00",
                   "state": st, "source": src} for sl, st, src in today_rows],
        "tomorrow": [{"slot": sl, "state": st, "source": src} for sl, st, src in tomorrow_rows],
        "news": parse_news(news_html, news_max),
        "emergency": parse_emergency(html) or None,
        "cek_text": strip_tags(cek) if cek else None,
        "site_data_updated": fact.get("update"),
        "time_type_legend": preset.get("time_type"),
    }
    return out


def push_ha(url, token, entity, state):
    from curl_cffi import requests as cr

    payload = {"state": state["current"]["state"], "attributes": state}
    r = cr.post(
        f"{url.rstrip('/')}/api/states/{entity}",
        json=payload,
        headers={"Authorization": f"Bearer {token}", "Content-Type": "application/json"},
        timeout=30,
        impersonate="chrome",
    )
    r.raise_for_status()
    return r.status_code


def open_session(provider, cookie_file):
    """Сесія + csrf для довільного провайдера (спільна логіка для discovery-режимів)."""
    global BASE
    BASE = PROVIDERS[provider]["base"]
    s = make_session(cookie_file)
    html = get_html(s, "/ua/shutdowns")
    m = re.search(r'name="csrf-token" content="([^"]+)"', html)
    if not m:
        raise BlockedError("csrf-token не знайдено — структура сторінки змінилась.")
    fact = extract_js_object(html, "DisconSchedule.fact") or {}
    return s, m.group(1), fact


def discovery(provider, cookie_file, list_cities, streets_for, homes_for):
    s, csrf, fact = open_session(provider, cookie_file)
    streets = ajax(s, csrf, [("method", "getStreets")]).get("streets") or {}
    if list_cities:
        for c in sorted(streets):
            print(c)
        return
    if streets_for:
        if streets_for not in streets:
            raise BlockedError(f"Пункт '{streets_for}' не знайдено. Приклади: {sorted(streets)[:10]}")
        for st in streets[streets_for]:
            print(st)
        return
    if homes_for:
        city, street = homes_for
        home = ajax(s, csrf, [("method", "getHomeNum"),
                              ("data[0][name]", "city"), ("data[0][value]", city),
                              ("data[1][name]", "street"), ("data[1][value]", street),
                              ("data[2][name]", "updateFact"), ("data[2][value]", fact.get("update", ""))])
        if not home.get("result"):
            raise BlockedError(f"getHomeNum не вдався: {str(home)[:200]}")
        for h in sorted(home.get("data", {})):
            print(h)


def main():
    global BASE
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    here = Path(__file__).resolve().parent
    ap.add_argument("--provider", default=DEFAULT_PROVIDER, choices=sorted(PROVIDERS),
                    help="обленерго (за замовчуванням dnipro)")
    ap.add_argument("--cookies", default=None,
                    help="куки-файл (типово cookies.<provider>.json поруч зі скриптом, опційно)")
    ap.add_argument("--city", default=None, help="населений пункт (точна назва; див. --list-cities)")
    ap.add_argument("--street", help="вулиця (див. --streets-for)")
    ap.add_argument("--house", help="№ будинку (див. --homes-for)")
    ap.add_argument("--news-max", type=int, default=5)
    ap.add_argument("--out", help="записати JSON у файл")
    ap.add_argument("--push-url", help="базова URL Home Assistant, напр. http://<HA_HOST>:8123")
    ap.add_argument("--push-token", help="HA long-lived access token")
    ap.add_argument("--entity", default="sensor.dtek_outage")
    ap.add_argument("--list-providers", action="store_true", help="перелік провайдерів і вийти")
    ap.add_argument("--list-cities", action="store_true", help="показати населені пункти провайдера")
    ap.add_argument("--streets-for", metavar="МІСТО", help="показати вулиці населеного пункту")
    ap.add_argument("--homes-for", nargs=2, metavar=("МІСТО", "ВУЛИЦЯ"), help="показати будинки вулиці")
    a = ap.parse_args()

    if a.list_providers:
        for k, p in PROVIDERS.items():
            star = "*" if k == DEFAULT_PROVIDER else " "
            print(f"{star} {k:9s} {p['region']:22s} {p['name']}")
        return

    BASE = PROVIDERS[a.provider]["base"]
    cookies = Path(a.cookies) if a.cookies else here / f"cookies.{a.provider}.json"
    try:
        if a.list_cities or a.streets_for or a.homes_for:
            discovery(a.provider, cookies, a.list_cities, a.streets_for, a.homes_for)
            return
        if not (a.street and a.house):
            ap.error("--street і --house обов'язкові (або скористайтесь --list-cities/--streets-for/--homes-for)")
        city = a.city or PROVIDERS[a.provider]["default_city"]
        if not city:
            ap.error("у провайдера багато населених пунктів — вкажіть --city (див. --list-cities)")
        state = build_state(a.provider, city, a.street, a.house, cookies, a.news_max)
    except BlockedError as e:
        print(f"[blocked] {e}", file=sys.stderr)
        sys.exit(2)

    text = json.dumps(state, ensure_ascii=False, indent=1)
    if a.out:
        Path(a.out).parent.mkdir(parents=True, exist_ok=True)
        Path(a.out).write_text(text, encoding="utf-8")
    if a.push_url and a.push_token:
        push_ha(a.push_url, a.push_token, a.entity, state)
    if not a.out and not (a.push_url and a.push_token):
        print(text)
    cur = state["current"]
    print(f"[ok] {cur['state']}: {cur['label']} | група {state['address']['group_name']} | "
          f"дані сайту: {state['site_data_updated']} | новин: {len(state['news'])}", file=sys.stderr)


if __name__ == "__main__":
    main()
