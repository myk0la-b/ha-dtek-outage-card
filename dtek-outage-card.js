/**
 * DTEK Outage Card — lovelace custom card (fetch-first: читає state.json,
 * який пише scraper/dtek_scraper.py з сайтів обленерго родини ДТЕК).
 *
 * No build step, no dependencies. Register as a module resource:
 *   /local/dtek-outage-card.js
 *
 * Card config:
 *   type: custom:dtek-outage-card
 *   fetch_url: /local/dtek_outage/state.json   # default; card fetches + refreshes itself
 *   refresh_minutes: 10                        # default
 *   entity: sensor.dtek_outage                 # optional alternative: read from HA sensor attributes instead
 *   title: ДТЕК
 */

const COLORS = {
  on: "#43a047",
  off: "#e53935",
  maybe: "#fb8c00",
  unknown: "#9e9e9e",
};

const STATE_COLORS = {
  yes: "#43a047",
  no: "#c62828",
  first: "#e53935",
  second: "#ef5350",
  maybe: "#fb8c00",
  mfirst: "#f57c00",
  msecond: "#ffa726",
};

function h(tag, attrs, ...kids) {
  const el = document.createElement(tag);
  for (const [k, v] of Object.entries(attrs || {})) {
    if (k === "style") el.style.cssText = v;
    else if (k.startsWith("on") && typeof v === "function") el.addEventListener(k.slice(2), v);
    else if (v !== null && v !== undefined) el.setAttribute(k, v);
  }
  for (const kid of kids.flat()) {
    if (kid === null || kid === undefined) continue;
    el.appendChild(typeof kid === "object" ? kid : document.createTextNode(String(kid)));
  }
  return el;
}

class DtekOutageCard extends HTMLElement {
  setConfig(config) {
    this._config = {
      fetch_url: "/local/dtek_outage/state.json",
      refresh_minutes: 10,
      title: null, // за замовчуванням — "ДТЕК · <регіон>" з даних скрапера
      ...(config || {}),
    };
  }

  set hass(hass) {
    this._hass = hass;
    if (!this._config.entity) this._ensureData();
    this.render();
  }

  connectedCallback() {
    if (this._config && !this._config.entity) this._ensureData();
  }

  disconnectedCallback() {
    if (this._timer) { clearInterval(this._timer); this._timer = null; }
  }

  _ensureData() {
    if (this._timer) return;
    this._fetch();
    const mins = Math.max(1, Number(this._config.refresh_minutes) || 10);
    this._timer = setInterval(() => this._fetch(), mins * 60000);
  }

  async _fetch() {
    try {
      const r = await fetch(this._config.fetch_url, { cache: "no-store" });
      if (!r.ok) throw new Error("HTTP " + r.status);
      this._data = await r.json();
      this._fetchError = null;
    } catch (e) {
      this._fetchError = String((e && e.message) || e);
    }
    if (this.isConnected) this.render();
  }

  getCardSize() {
    return 5;
  }

  _title() {
    if (this._config.title) return this._config.title;
    const region = this._data && this._data.provider && this._data.provider.region;
    return region ? `ДТЕК · ${region}` : "ДТЕК · відключення";
  }

  render() {
    if (!this._hass || !this._config) return;
    if (!this.shadowRoot) this.attachShadow({ mode: "open" });
    const root = this.shadowRoot;
    root.textContent = "";

    const style = document.createElement("style");
    style.textContent = `
      :host { display: block; }
      .card { background: var(--ha-card-background, var(--card-background-color, #fff));
              border-radius: var(--ha-card-border-radius, 12px);
              box-shadow: var(--ha-card-box-shadow, 0 1px 3px rgba(0,0,0,.12));
              padding: 14px 16px; color: var(--primary-text-color, #212121);
              font-family: var(--paper-font-body1_-_font-family, Roboto, sans-serif); }
      .head { display:flex; align-items:center; justify-content:space-between; margin-bottom:10px; }
      .title { font-size:1.05em; font-weight:600; }
      .queue { font-size:.8em; opacity:.7; }
      .chip { display:inline-flex; align-items:center; gap:8px; padding:8px 14px; border-radius:24px;
              color:#fff; font-weight:700; font-size:1.15em; }
      .dot { width:10px; height:10px; border-radius:50%; background:rgba(255,255,255,.9); }
      .sub { margin-top:6px; font-size:.82em; opacity:.85; line-height:1.35; }
      .bar { display:flex; gap:1px; margin:12px 0 4px; height:26px; }
      .slot { flex:1; border-radius:2px; position:relative; }
      .slot.plan { opacity:.45; }
      .slot.now { outline:2px solid var(--accent-color, #03a9f4); outline-offset:-1px; z-index:1; }
      .ticks { display:flex; justify-content:space-between; font-size:.65em; opacity:.55; }
      .news { margin-top:12px; border-top:1px solid var(--divider-color, rgba(0,0,0,.12)); padding-top:8px; }
      .news a { display:block; color:var(--primary-text-color,#212121); text-decoration:none;
                font-size:.82em; padding:4px 0; line-height:1.3; }
      .news a .d { opacity:.55; margin-right:6px; }
      .news a:hover { color: var(--accent-color,#03a9f4); }
      .emerg { margin-top:10px; background:rgba(229,57,53,.12); border-left:4px solid #e53935;
               padding:8px 10px; border-radius:6px; font-size:.8em; white-space:pre-line; line-height:1.35; }
      .foot { margin-top:10px; font-size:.7em; opacity:.6; display:flex; justify-content:space-between; }
      .foot a { color:inherit; }
      .next { margin-top:8px; font-size:.9em; }
      .next b { font-weight:600; }
    `;
    root.appendChild(style);

    const card = h("div", { class: "ha-card card" });
    root.appendChild(card);

    let a;
    if (this._config.entity) {
      const st = this._hass.states[this._config.entity];
      if (!st) {
        card.appendChild(h("div", { class: "title" }, this._title()));
        card.appendChild(h("div", { class: "sub" }, `Сенсор ${this._config.entity} не знайдений`));
        return;
      }
      a = st.attributes || {};
    } else if (this._data) {
      a = this._data;
    } else {
      card.appendChild(h("div", { class: "title" }, this._title()));
      card.appendChild(h("div", { class: "sub" },
        this._fetchError ? `Помилка завантаження: ${this._fetchError}` : "Завантаження даних…"));
      return;
    }
    const addr = a.address || {};
    const cur = a.current || {};
    const stateKey = ["on", "off", "maybe"].includes(cur.state) ? cur.state : "unknown";

    card.appendChild(h("div", { class: "head" },
      h("div", { class: "title" }, this._title()),
      h("div", { class: "queue" }, [addr.group_name || "", addr.house ? " · " + addr.house : ""].join(""))));

    const label = { on: "Світло є", off: "Відключено", maybe: "Можливе відключення", unknown: "Немає даних" }[stateKey];
    card.appendChild(h("div", { class: "chip", style: `background:${COLORS[stateKey]}` },
      h("span", { class: "dot" }), label));

    if (cur.detail || cur.since) {
      card.appendChild(h("div", { class: "sub" }, [
        cur.detail,
        cur.since ? `з ${cur.since}` : "", cur.until ? `до ${cur.until}` : "",
      ].filter(Boolean).join(" · ")));
    }

    const nx = a.next;
    if (nx && nx.at) {
      const when = nx.day === "tomorrow" ? "завтра" : "сьогодні";
      card.appendChild(h("div", { class: "next" },
        "Наступне: ", h("b", {}, nx.state === "off" ? `відключення о ${nx.at}` : `світло о ${nx.at}`), ` (${when})`));
    }

    const today = a.today || [];
    if (today.length) {
      const nowSlot = new Date().getHours() + 1;
      const bar = h("div", { class: "bar" });
      for (const row of today) {
        const cls = ["slot", row.source === "plan" ? "plan" : "", row.slot === nowSlot ? "now" : ""].join(" ");
        bar.appendChild(h("div", {
          class: cls,
          title: `${row.from}–${row.to}: ${(a.time_type_legend || {})[row.state] || row.state || "—"}${row.source === "plan" ? " (план)" : ""}`,
          style: `background:${STATE_COLORS[row.state] || "#bdbdbd"}`,
        }));
      }
      card.appendChild(bar);
      card.appendChild(h("div", { class: "ticks" },
        ...["00", "06", "12", "18", "24"].map((t) => h("span", {}, t))));
    }

    if (a.emergency) card.appendChild(h("div", { class: "emerg" }, a.emergency));

    const news = a.news || [];
    if (news.length) {
      card.appendChild(h("div", { class: "news" },
        ...news.map((n) =>
          h("a", { href: n.url, target: "_blank", rel: "noopener" },
            h("span", { class: "d" }, n.date || ""), n.title))));
    }

    card.appendChild(h("div", { class: "foot" },
      h("span", {}, "дані сайту: " + (a.site_data_updated || "?")),
      h("a", { href: a.source || "https://www.dtek-dnem.com.ua/ua/shutdowns", target: "_blank", rel: "noopener" },
        "dtek-dnem.com.ua")));
  }
}

customElements.define("dtek-outage-card", DtekOutageCard);
window.customCards = window.customCards || [];
window.customCards.push({
  type: "dtek-outage-card",
  name: "DTEK Outage Card",
  description: "Графік відключень обленерго родини ДТЕК (Дніпро/Київ/Київщина/Донеччина/Одещина) + новини",
});
