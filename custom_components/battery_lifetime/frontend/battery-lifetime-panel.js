class BatteryInfoPanel extends HTMLElement {
  constructor() {
    super();
    this._hass = null;
    this._data = null;
    this._loading = false;
    this._search = "";
    this._sort = "battery_asc";
    this._showIgnored = false;
    this._showBatteryType = false;
    this._timer = null;
  }

  set hass(hass) {
    const first = !this._hass;
    this._hass = hass;
    if (first) {
      this._load();
      this._timer = window.setInterval(() => this._load(), 30000);
    }
  }
  set narrow(value) {}
  set panel(value) {}

  disconnectedCallback() {
    if (this._timer) window.clearInterval(this._timer);
    this._timer = null;
  }

  _language() {
    const value = String(
      this._hass?.locale?.language || this._hass?.language || navigator.language || "en"
    ).toLowerCase();
    return value.startsWith("nb") || value.startsWith("nn") || value.startsWith("no")
      ? "nb" : "en";
  }

  _locale() { return this._language() === "nb" ? "nb-NO" : "en-GB"; }

  _t(key) {
    const text = {
      nb: {
        title: "Batteri info", loading: "Laster …", error: "Kunne ikke hente batteridata",
        summary: "batterienheter", low: "lavt batteri", ignored: "ignorert",
        show_ignored: "Ignorerte", back: "Tilbake", search: "Søk etter enhet eller batteritype …",
        battery_toggle: "Batteri",
        sort: "Sorter batterier", lowest: "Lavest nivå først", highest: "Høyest nivå først",
        name_asc: "Navn: A–Å", name_desc: "Navn: Å–A", unavailable_first: "Utilgjengelige først",
        device: "Enhet", type: "Batteritype", remaining: "Gjenværende", status: "Status",
        edit: "Endre type", ignore: "Ignorer", restore: "Fjern ignorering",
        not_set: "Ikke satt", automatic: "Automatisk fra Zigbee2MQTT", manual: "Manuelt satt",
        unavailable: "Utilgjengelig", unknown: "Ukjent", good: "Bra", medium: "Middels",
        low_status: "Lavt", critical: "Kritisk", empty: "Ingen batterier å vise.",
        prompt: "Batteritype, for eksempel AA, AAA eller CR2032. La feltet stå tomt for å fjerne typen.",
        save_error: "Kunne ikke lagre batteritype", ignore_error: "Kunne ikke endre ignorering",
        confirm: "Enheten skjules fra hovedoversikten, men kan hentes tilbake under Ignorerte."
      },
      en: {
        title: "Battery Info", loading: "Loading …", error: "Could not load battery data",
        summary: "battery devices", low: "low batteries", ignored: "ignored",
        show_ignored: "Ignored", back: "Back", search: "Search device or battery type …",
        battery_toggle: "Battery",
        sort: "Sort batteries", lowest: "Lowest level first", highest: "Highest level first",
        name_asc: "Name: A–Z", name_desc: "Name: Z–A", unavailable_first: "Unavailable first",
        device: "Device", type: "Battery type", remaining: "Remaining", status: "Status",
        edit: "Edit type", ignore: "Ignore", restore: "Stop ignoring",
        not_set: "Not set", automatic: "Automatic from Zigbee2MQTT", manual: "Manually set",
        unavailable: "Unavailable", unknown: "Unknown", good: "Good", medium: "Medium",
        low_status: "Low", critical: "Critical", empty: "No batteries to display.",
        prompt: "Battery type, for example AA, AAA or CR2032. Leave empty to remove the type.",
        save_error: "Could not save battery type", ignore_error: "Could not change ignore status",
        confirm: "The device will be hidden from the main overview and can be restored under Ignored."
      }
    };
    return text[this._language()][key] ?? key;
  }

  async _load() {
    if (!this._hass || this._loading) return;
    this._loading = true;
    try {
      this._data = await this._hass.callWS({ type: "battery_lifetime/get_data" });
    } catch (error) {
      this._data = { error: String(error), batteries: [], ignored_batteries: [] };
    } finally {
      this._loading = false;
      this._render();
    }
  }

  async _setBatteryType(row) {
    const value = window.prompt(this._t("prompt"), row.battery_type || "");
    if (value === null) return;
    try {
      await this._hass.callWS({
        type: "battery_lifetime/set_battery_type",
        source_id: row.source_id,
        battery_type: value.trim().slice(0, 50)
      });
      await this._load();
    } catch (error) {
      window.alert(`${this._t("save_error")}: ${String(error)}`);
    }
  }

  async _setIgnored(row, ignored) {
    if (ignored && !window.confirm(`${row.name || row.entity_id}\n\n${this._t("confirm")}`)) return;
    try {
      await this._hass.callWS({
        type: "battery_lifetime/set_ignored", source_id: row.source_id, ignored
      });
      await this._load();
    } catch (error) {
      window.alert(`${this._t("ignore_error")}: ${String(error)}`);
    }
  }

  _type(row) {
    if (!row.battery_type) return this._t("not_set");
    return String(row.battery_type).replace(/^\s*\d+\s*[x×]\s*/i, "");
  }
  _typeSource(row) {
    if (row.battery_type_source === "zigbee2mqtt") return "";
    return row.battery_type_source === "manual" ? this._t("manual") : "";
  }
  _unavailable(row) { return row.state === "unavailable" || row.state === "unknown"; }
  _level(row) {
    if (row.battery_level === null || row.battery_level === undefined) {
      return row.state === "unknown" ? this._t("unknown") : this._t("unavailable");
    }
    return `${Math.round(Number(row.battery_level))} %`;
  }
  _status(row) {
    if (this._unavailable(row)) return { key: "unavailable", css: "unavailable" };
    const level = Number(row.battery_level);
    if (level <= 10) return { key: "critical", css: "critical" };
    if (level <= 25) return { key: "low_status", css: "low" };
    if (level <= 50) return { key: "medium", css: "medium" };
    return { key: "good", css: "good" };
  }
  _escape(value) {
    return String(value ?? "").replaceAll("&", "&amp;").replaceAll("<", "&lt;")
      .replaceAll(">", "&gt;").replaceAll('"', "&quot;").replaceAll("'", "&#039;");
  }
  _open(entityId) {
    this.dispatchEvent(new CustomEvent("hass-more-info", {
      detail: { entityId }, bubbles: true, composed: true
    }));
  }
  _matches(row) {
    const q = this._search.trim().toLowerCase();
    return !q || `${row.name || ""} ${row.entity_id || ""} ${row.battery_type || ""}`
      .toLowerCase().includes(q);
  }
  _sortRows(rows) {
    const copy = [...rows];
    const name = (a, b) => (a.name || a.entity_id || "").localeCompare(
      b.name || b.entity_id || "", this._locale(), { sensitivity: "base" }
    );
    const level = row => Number.isFinite(Number(row.battery_level))
      ? Number(row.battery_level) : null;
    copy.sort((a, b) => {
      if (this._sort === "name_asc") return name(a, b);
      if (this._sort === "name_desc") return name(b, a);
      if (this._sort === "unavailable_first") {
        if (this._unavailable(a) !== this._unavailable(b)) return this._unavailable(a) ? -1 : 1;
        return name(a, b);
      }
      const av = level(a), bv = level(b);
      if (av === null && bv !== null) return 1;
      if (av !== null && bv === null) return -1;
      if (av === null && bv === null) return name(a, b);
      if (av === bv) return name(a, b);
      return this._sort === "battery_desc" ? bv - av : av - bv;
    });
    return copy;
  }

  _render() {
    if (!this._data) {
      this.innerHTML = `<div class="wrap">${this._t("loading")}</div>`;
      return;
    }
    if (this._data.error) {
      this.innerHTML = `<div class="wrap"><h1>${this._t("title")}</h1><p>${this._t("error")}: ${this._escape(this._data.error)}</p></div>`;
      return;
    }
    const active = this._data.batteries || [];
    const ignored = this._data.ignored_batteries || [];
    const source = this._showIgnored ? ignored : active;
    const rows = this._sortRows(source.filter(row => this._matches(row)));
    const lowCount = active.filter(row => Number(row.battery_level) <= 25).length;

    const rowHtml = rows.map(row => {
      const numeric = Number.isFinite(Number(row.battery_level))
        ? Math.max(0, Math.min(100, Number(row.battery_level))) : 0;
      return `
        <article class="battery-card ${this._showBatteryType ? "" : "types-hidden"}">
          <div class="card-main">
            <button class="device-name" data-entity="${this._escape(row.entity_id)}">${this._escape(row.name)}</button>
            <div class="entity-id">${this._escape(row.entity_id)}</div>
          </div>
          ${this._showBatteryType ? `<div class="type-block">
            <span class="label">${this._t("type")}</span>
            <strong>${this._escape(this._type(row))}</strong>
            <small>${this._escape(this._typeSource(row))}</small>
          </div>` : ""}
          <div class="level-block" data-source="${this._escape(row.source_id)}">
            <strong>${this._escape(this._level(row))}</strong>
            <div class="meter ${this._status(row).css}"><span style="width:${numeric}%"></span></div>
          </div>
          <div class="actions">
            ${this._showBatteryType ? `<button class="action edit" data-source="${this._escape(row.source_id)}">${this._t("edit")}</button>` : ""}
            <button class="action ${this._showIgnored ? "restore" : "ignore"}" data-source="${this._escape(row.source_id)}">${this._showIgnored ? this._t("restore") : this._t("ignore")}</button>
          </div>
        </article>`;
    }).join("");

    this.innerHTML = `
      <style>
        :host { display:block; color:var(--primary-text-color); }
        * { box-sizing:border-box; }
        .wrap { max-width:1200px; margin:0 auto; padding:20px; }
        .header { display:flex; justify-content:space-between; gap:16px; align-items:flex-start; flex-wrap:wrap; }
        .header-actions { display:flex; gap:8px; align-items:center; flex-wrap:wrap; }
        h1 { margin:0; font-size:30px; font-weight:600; }
        .summary { margin-top:5px; color:var(--secondary-text-color); }
        .summary .warn { color:var(--error-color); font-weight:600; }
        .ignored-toggle,.action { border:1px solid var(--divider-color); border-radius:10px; background:var(--card-background-color); color:var(--primary-color); padding:9px 13px; cursor:pointer; font:inherit; }
        .controls { display:grid; grid-template-columns:minmax(220px,1fr) minmax(190px,260px); gap:10px; margin:18px 0; }
        input,select { min-height:46px; width:100%; padding:10px 13px; border:1px solid var(--divider-color); border-radius:10px; background:var(--card-background-color); color:var(--primary-text-color); font:inherit; }
        .list { display:grid; gap:0; overflow:hidden; border:1px solid var(--ha-card-border-color,var(--divider-color)); border-radius:var(--ha-card-border-radius,12px); background:var(--card-background-color); box-shadow:var(--ha-card-box-shadow,none); }
        .battery-card { display:grid; grid-template-columns:minmax(220px,1fr) minmax(150px,220px) minmax(160px,220px) 160px; grid-template-areas:"main type level actions"; align-items:center; gap:14px; min-height:52px; padding:7px 12px; border:0; border-bottom:1px solid var(--divider-color); background:var(--card-background-color); }
        .battery-card.types-hidden { grid-template-columns:minmax(220px,1fr) minmax(150px,220px) minmax(160px,220px) 160px; grid-template-areas:"main main level actions"; }
        .battery-card:last-child { border-bottom:0; }
        .card-main { grid-area:main; min-width:0; }
        .type-block { grid-area:type; min-width:0; }
        .level-block { grid-area:level; min-width:0; }
        .actions { grid-area:actions; justify-content:flex-end; }
        .device-name { border:0; padding:0; background:none; color:var(--primary-color); font:inherit; font-weight:600; text-align:left; cursor:pointer; font-size:16px; }
        .device-name:hover { text-decoration:underline; }
        .entity-id,.label,small { color:var(--secondary-text-color); font-size:12px; overflow-wrap:anywhere; }
        .type-block { display:flex; flex-direction:column; gap:0; }
        .type-block .label,.type-block small { display:none; }
        .type-block small:empty { display:none; }
        .level-block strong { font-size:18px; white-space:nowrap; }
        .meter { width:100%; min-width:160px; height:6px; margin-top:4px; overflow:hidden; border-radius:999px; background:var(--divider-color); }
        .meter span { display:block; height:100%; background:var(--success-color,#43a047); border-radius:inherit; }
        .meter.medium span { background:#f9a825; }
        .meter.low span { background:#ef6c00; }
        .meter.critical span,.meter.unavailable span { background:var(--error-color,#db4437); }
        .actions { display:flex; gap:6px; flex-wrap:nowrap; justify-content:flex-end; }
        .actions .action { padding:7px 9px; white-space:nowrap; }
        .empty { padding:28px; text-align:center; color:var(--secondary-text-color); background:var(--card-background-color); border-radius:12px; }
        @media(max-width:800px) {
          .wrap { padding:8px; } h1 { font-size:23px; }
          .header { gap:8px; }
          .summary { font-size:13px; }
          .controls { grid-template-columns:1fr; gap:6px; margin:10px 0; }
          input,select { min-height:40px; padding:7px 10px; }
          .list { gap:4px; overflow:visible; border:0; border-radius:0; background:transparent; box-shadow:none; }
          .battery-card {
            grid-template-columns:minmax(0,1fr) auto;
            grid-template-areas:"main level" "type actions";
            gap:5px 10px;
            min-height:0;
            padding:8px 9px;
            border:1px solid var(--ha-card-border-color,var(--divider-color));
            border-radius:9px;
          }
          .battery-card.types-hidden {
            grid-template-columns:minmax(0,1fr) auto;
            grid-template-areas:"main level";
          }
          .battery-card:last-child { border-bottom:1px solid var(--ha-card-border-color,var(--divider-color)); }
          .actions { grid-area:actions; justify-content:flex-end; gap:4px; }
          .actions .ignore,.actions .restore { display:none; }
          .types-hidden .actions { display:none; }
          .level-block { cursor:pointer; touch-action:manipulation; }
          .entity-id,.type-block .label,.type-block small { display:none; }
          .device-name { display:block; max-width:100%; overflow:hidden; text-overflow:ellipsis; white-space:nowrap; font-size:14px; }
          .type-block strong { font-size:13px; }
          .level-block strong { font-size:16px; }
          .meter { min-width:116px; height:5px; margin-top:2px; }
          .action { min-height:30px; padding:4px 7px; border-radius:7px; font-size:12px; }
        }
      </style>
      <div class="wrap">
        <div class="header">
          <div><h1>${this._t("title")}</h1>
            <div class="summary">${active.length} ${this._t("summary")}
              ${lowCount ? ` · <span class="warn">${lowCount} ${this._t("low")}</span>` : ""}
              ${ignored.length ? ` · ${ignored.length} ${this._t("ignored")}` : ""}
            </div>
          </div>
          <div class="header-actions">
            <button class="ignored-toggle" id="battery-toggle" aria-pressed="${this._showBatteryType}">${this._t("battery_toggle")}</button>
            ${ignored.length || this._showIgnored ? `<button class="ignored-toggle" id="ignored-toggle">${this._showIgnored ? this._t("back") : `${this._t("show_ignored")} (${ignored.length})`}</button>` : ""}
          </div>
        </div>
        <div class="controls">
          <input id="search" type="search" placeholder="${this._t("search")}" value="${this._escape(this._search)}">
          <select id="sort" aria-label="${this._t("sort")}">
            <option value="battery_asc" ${this._sort === "battery_asc" ? "selected" : ""}>${this._t("lowest")}</option>
            <option value="battery_desc" ${this._sort === "battery_desc" ? "selected" : ""}>${this._t("highest")}</option>
            <option value="unavailable_first" ${this._sort === "unavailable_first" ? "selected" : ""}>${this._t("unavailable_first")}</option>
            <option value="name_asc" ${this._sort === "name_asc" ? "selected" : ""}>${this._t("name_asc")}</option>
            <option value="name_desc" ${this._sort === "name_desc" ? "selected" : ""}>${this._t("name_desc")}</option>
          </select>
        </div>
        <div class="list">${rowHtml || `<div class="empty">${this._t("empty")}</div>`}</div>
      </div>`;

    this.querySelector("#ignored-toggle")?.addEventListener("click", () => {
      this._showIgnored = !this._showIgnored; this._search = ""; this._render();
    });
    this.querySelector("#battery-toggle")?.addEventListener("click", () => {
      this._showBatteryType = !this._showBatteryType;
      this._render();
    });
    this.querySelector("#search")?.addEventListener("input", event => {
      this._search = event.target.value; this._render();
      const input = this.querySelector("#search");
      input?.focus(); input?.setSelectionRange(this._search.length, this._search.length);
    });
    this.querySelector("#sort")?.addEventListener("change", event => {
      this._sort = event.target.value; this._render();
    });
    this.querySelectorAll(".device-name").forEach(button =>
      button.addEventListener("click", () => this._open(button.dataset.entity)));
    this.querySelectorAll(".level-block").forEach(level =>
      level.addEventListener("click", () => {
        if (!window.matchMedia("(max-width: 800px)").matches) return;
        const collection = this._showIgnored ? ignored : active;
        const row = collection.find(item => item.source_id === level.dataset.source);
        if (row) this._setIgnored(row, !this._showIgnored);
      }));
    this.querySelectorAll(".edit").forEach(button =>
      button.addEventListener("click", () => this._setBatteryType(
        [...active, ...ignored].find(row => row.source_id === button.dataset.source))));
    this.querySelectorAll(".ignore").forEach(button =>
      button.addEventListener("click", () => this._setIgnored(
        active.find(row => row.source_id === button.dataset.source), true)));
    this.querySelectorAll(".restore").forEach(button =>
      button.addEventListener("click", () => this._setIgnored(
        ignored.find(row => row.source_id === button.dataset.source), false)));
  }
}

if (!customElements.get("battery-lifetime-panel")) {
  customElements.define("battery-lifetime-panel", BatteryInfoPanel);
}
