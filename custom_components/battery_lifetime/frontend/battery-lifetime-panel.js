class BatteryLifetimePanel extends HTMLElement {
  constructor() {
    super();
    this._hass = null;
    this._data = null;
    this._loading = false;
    this._search = "";
    this._sort = "battery_asc";
    this._showIgnored = false;
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
    if (this._timer) {
      window.clearInterval(this._timer);
      this._timer = null;
    }
  }

  _language() {
    const language =
      this._hass?.locale?.language ||
      this._hass?.language ||
      window.navigator.language ||
      "en";
    const normalized = String(language).toLowerCase();
    return normalized.startsWith("nb") ||
      normalized.startsWith("nn") ||
      normalized.startsWith("no")
      ? "nb"
      : "en";
  }

  _locale() {
    return this._language() === "nb" ? "nb-NO" : "en-GB";
  }

  _t(key) {
    const translations = {
      nb: {
        loading: "Laster …",
        title: "Batterilevetid",
        load_error: "Kunne ikke hente data",
        monitored_count: "batterientiteter overvåkes",
        ignored_count: "ignorert",
        show_ignored: "Ignorerte",
        back: "Tilbake",
        search_placeholder: "Søk etter batteri …",
        sort_label: "Sorter batterier",
        sort_battery_asc: "Batteri: lavest først",
        sort_battery_desc: "Batteri: høyest først",
        sort_unavailable_first: "Utilgjengelige først",
        sort_name_asc: "Navn: A–Å",
        sort_name_desc: "Navn: Å–A",
        battery: "Batteri",
        battery_type: "Batteritype",
        set_battery_type: "Sett type",
        battery_type_prompt: "Batteritype, for eksempel AA, AAA eller CR2032. La feltet stå tomt for å fjerne typen.",
        battery_type_error: "Kunne ikke lagre batteritype",
        not_set: "Ikke satt",
        battery_type_auto: "Automatisk fra Zigbee2MQTT",
        battery_type_manual: "Manuelt satt",
        level: "Nivå",
        started: "Startet",
        current: "Nåværende",
        previous: "Forrige",
        average: "Gjennomsnitt",
        cycles: "Sykluser",
        expected_empty: "Forventet tom",
        last_end_reason: "Siste sluttårsak",
        ignore: "Ignorer",
        restore: "Fjern ignorering",
        ignored_batteries: "Ignorerte batterier",
        no_monitored_match: "Ingen overvåkede batterier matcher søket.",
        no_ignored_match: "Ingen ignorerte batterier matcher søket.",
        unavailable: "Utilgjengelig",
        unknown: "Ukjent",
        reason_empty: "Batteri 0 %",
        reason_unavailable: "Enhet utilgjengelig",
        ignore_confirm_prefix: "Ignorere",
        ignore_confirm_text: "Den skjules fra hovedlisten. Batterimåling og historikk fortsetter i bakgrunnen.",
        ignore_error: "Kunne ikke endre ignorering",
        day_short: "d",
        hour_short: "t",
      },
      en: {
        loading: "Loading …",
        title: "Battery Lifetime",
        load_error: "Could not load data",
        monitored_count: "battery entities monitored",
        ignored_count: "ignored",
        show_ignored: "Ignored",
        back: "Back",
        search_placeholder: "Search batteries …",
        sort_label: "Sort batteries",
        sort_battery_asc: "Battery: lowest first",
        sort_battery_desc: "Battery: highest first",
        sort_unavailable_first: "Unavailable first",
        sort_name_asc: "Name: A–Z",
        sort_name_desc: "Name: Z–A",
        battery: "Battery",
        battery_type: "Battery type",
        set_battery_type: "Set type",
        battery_type_prompt: "Battery type, for example AA, AAA or CR2032. Leave empty to remove the type.",
        battery_type_error: "Could not save battery type",
        not_set: "Not set",
        battery_type_auto: "Automatic from Zigbee2MQTT",
        battery_type_manual: "Manually set",
        level: "Level",
        started: "Started",
        current: "Current",
        previous: "Previous",
        average: "Average",
        cycles: "Cycles",
        expected_empty: "Expected empty",
        last_end_reason: "Last end reason",
        ignore: "Ignore",
        restore: "Stop ignoring",
        ignored_batteries: "Ignored batteries",
        no_monitored_match: "No monitored batteries match the search.",
        no_ignored_match: "No ignored batteries match the search.",
        unavailable: "Unavailable",
        unknown: "Unknown",
        reason_empty: "Battery 0%",
        reason_unavailable: "Device unavailable",
        ignore_confirm_prefix: "Ignore",
        ignore_confirm_text: "It will be hidden from the main list. Battery tracking and history continue in the background.",
        ignore_error: "Could not change ignore status",
        day_short: "d",
        hour_short: "h",
      },
    };
    return translations[this._language()][key] ?? key;
  }

  async _load() {
    if (!this._hass || this._loading) return;
    this._loading = true;
    try {
      this._data = await this._hass.callWS({ type: "battery_lifetime/get_data" });
      this._render();
    } catch (err) {
      this._data = { error: String(err), batteries: [], ignored_batteries: [] };
      this._render();
    } finally {
      this._loading = false;
    }
  }

  async _setIgnored(row, ignored) {
    if (!this._hass) return;

    if (ignored) {
      const ok = window.confirm(
        `${this._t("ignore_confirm_prefix")} ${row.name || row.entity_id}?\n\n${this._t("ignore_confirm_text")}`
      );
      if (!ok) return;
    }

    try {
      await this._hass.callWS({
        type: "battery_lifetime/set_ignored",
        source_id: row.source_id,
        ignored,
      });
      await this._load();
    } catch (err) {
      window.alert(`${this._t("ignore_error")}: ${String(err)}`);
    }
  }

  async _setBatteryType(row) {
    if (!this._hass) return;
    const value = window.prompt(
      this._t("battery_type_prompt"),
      row.battery_type || ""
    );
    if (value === null) return;

    try {
      await this._hass.callWS({
        type: "battery_lifetime/set_battery_type",
        source_id: row.source_id,
        battery_type: value.trim().slice(0, 50),
      });
      await this._load();
    } catch (err) {
      window.alert(`${this._t("battery_type_error")}: ${String(err)}`);
    }
  }

  _batteryType(row) {
    return row.battery_type || this._t("not_set");
  }

  _batteryTypeSource(row) {
    if (row.battery_type_source === "zigbee2mqtt") {
      return row.battery_type_model
        ? `${this._t("battery_type_auto")} (${row.battery_type_model})`
        : this._t("battery_type_auto");
    }
    if (row.battery_type_source === "manual") return this._t("battery_type_manual");
    return "";
  }

  _duration(seconds) {
    if (seconds === null || seconds === undefined) return "–";
    const totalHours = Math.max(0, Math.floor(Number(seconds) / 3600));
    const days = Math.floor(totalHours / 24);
    const hours = totalHours % 24;
    if (days > 0) return `${days} ${this._t("day_short")} ${hours} ${this._t("hour_short")}`;
    return `${hours} ${this._t("hour_short")}`;
  }

  _date(value) {
    if (!value) return "–";
    const d = new Date(value);
    if (Number.isNaN(d.getTime())) return value;
    return new Intl.DateTimeFormat(this._locale(), {
      dateStyle: "short",
      timeStyle: "short",
    }).format(d);
  }

  _reason(value) {
    if (value === "battery_empty") return this._t("reason_empty");
    if (value === "device_unavailable") return this._t("reason_unavailable");
    return value || "–";
  }

  _isUnavailable(row) {
    return row.state === "unavailable" || row.state === "unknown";
  }

  _level(row) {
    if (row.battery_level === null || row.battery_level === undefined) {
      if (row.state === "unavailable") return this._t("unavailable");
      if (row.state === "unknown") return this._t("unknown");
      return "–";
    }
    return `${Math.round(row.battery_level)} %`;
  }

  _escape(value) {
    return String(value ?? "")
      .replaceAll("&", "&amp;")
      .replaceAll("<", "&lt;")
      .replaceAll(">", "&gt;")
      .replaceAll('"', "&quot;")
      .replaceAll("'", "&#039;");
  }

  _openMoreInfo(entityId) {
    if (!entityId) return;
    this.dispatchEvent(
      new CustomEvent("hass-more-info", {
        detail: { entityId },
        bubbles: true,
        composed: true,
      })
    );
  }

  _sortRows(rows) {
    const copy = [...rows];
    const hasLevel = (row) =>
      row.battery_level !== null &&
      row.battery_level !== undefined &&
      Number.isFinite(Number(row.battery_level));
    const nameCompare = (a, b) =>
      (a.name || a.entity_id || "").localeCompare(
        b.name || b.entity_id || "",
        this._locale(),
        { sensitivity: "base" }
      );

    copy.sort((a, b) => {
      if (this._sort === "name_asc") return nameCompare(a, b);
      if (this._sort === "name_desc") return nameCompare(b, a);

      if (this._sort === "unavailable_first") {
        const au = this._isUnavailable(a);
        const bu = this._isUnavailable(b);
        if (au && !bu) return -1;
        if (!au && bu) return 1;
        if (au && bu) return nameCompare(a, b);

        const aHas = hasLevel(a);
        const bHas = hasLevel(b);
        if (aHas && !bHas) return -1;
        if (!aHas && bHas) return 1;
        if (aHas && bHas && Number(a.battery_level) !== Number(b.battery_level)) {
          return Number(a.battery_level) - Number(b.battery_level);
        }
        return nameCompare(a, b);
      }

      const aHas = hasLevel(a);
      const bHas = hasLevel(b);
      if (aHas && !bHas) return -1;
      if (!aHas && bHas) return 1;
      if (!aHas && !bHas) return nameCompare(a, b);

      const av = Number(a.battery_level);
      const bv = Number(b.battery_level);
      if (av === bv) return nameCompare(a, b);
      return this._sort === "battery_desc" ? bv - av : av - bv;
    });

    return copy;
  }

  _matchesSearch(row) {
    const q = this._search.trim().toLowerCase();
    if (!q) return true;
    return `${row.name || ""} ${row.entity_id || ""}`.toLowerCase().includes(q);
  }

  _render() {
    if (!this._data) {
      this.innerHTML = `<div class="wrap"><p>${this._t("loading")}</p></div>`;
      return;
    }

    if (this._data.error) {
      this.innerHTML = `<div class="wrap"><h1>${this._t("title")}</h1><p>${this._t("load_error")}: ${this._escape(this._data.error)}</p></div>`;
      return;
    }

    const activeAll = this._data.batteries || [];
    const ignoredAll = this._data.ignored_batteries || [];
    const rows = this._sortRows(activeAll.filter((row) => this._matchesSearch(row)));
    const ignoredRows = [...ignoredAll]
      .filter((row) => this._matchesSearch(row))
      .sort((a, b) =>
        (a.name || a.entity_id || "").localeCompare(
          b.name || b.entity_id || "",
          this._locale(),
          { sensitivity: "base" }
        )
      );

    const tableBody = rows
      .map(
        (row) => `
      <tr class="${this._isUnavailable(row) ? "unavailable" : ""}">
        <td><button type="button" class="entity-name-button" data-entity="${this._escape(row.entity_id)}">${this._escape(row.name)}</button><div class="entity">${this._escape(row.entity_id)}</div></td>
        <td><div>${this._escape(this._batteryType(row))}</div><div class="entity">${this._escape(this._batteryTypeSource(row))}</div><button class="action type-edit" data-source="${this._escape(row.source_id)}">${this._t("set_battery_type")}</button></td>
        <td class="level">${this._escape(this._level(row))}</td>
        <td>${this._date(row.cycle_started)}</td>
        <td>${this._duration(row.current_duration_seconds)}</td>
        <td>${this._duration(row.last_duration_seconds)}</td>
        <td>${this._duration(row.average_duration_seconds)}</td>
        <td>${this._escape(row.completed_cycles)}</td>
        <td>${this._date(row.expected_empty)}</td>
        <td>${this._escape(this._reason(row.last_end_reason))}</td>
        <td><button class="action ignore" data-source="${this._escape(row.source_id)}">${this._t("ignore")}</button></td>
      </tr>`
      )
      .join("");

    const mobileCards = rows
      .map(
        (row) => `
      <div class="battery-card ${this._isUnavailable(row) ? "unavailable" : ""}">
        <div class="battery-card-head">
          <div>
            <button type="button" class="entity-name-button" data-entity="${this._escape(row.entity_id)}">${this._escape(row.name)}</button>
            <div class="entity">${this._escape(row.entity_id)}</div>
          </div>
          <div class="battery-level">${this._escape(this._level(row))}</div>
        </div>
        <div class="details">
          <div><span>${this._t("battery_type")}</span><strong>${this._escape(this._batteryType(row))}</strong><span>${this._escape(this._batteryTypeSource(row))}</span></div>
          <div><span>${this._t("started")}</span><strong>${this._date(row.cycle_started)}</strong></div>
          <div><span>${this._t("current")}</span><strong>${this._duration(row.current_duration_seconds)}</strong></div>
          <div><span>${this._t("previous")}</span><strong>${this._duration(row.last_duration_seconds)}</strong></div>
          <div><span>${this._t("average")}</span><strong>${this._duration(row.average_duration_seconds)}</strong></div>
          <div><span>${this._t("cycles")}</span><strong>${this._escape(row.completed_cycles)}</strong></div>
          <div><span>${this._t("expected_empty")}</span><strong>${this._date(row.expected_empty)}</strong></div>
          <div class="full"><span>${this._t("last_end_reason")}</span><strong>${this._escape(this._reason(row.last_end_reason))}</strong></div>
        </div>
        <button class="action type-edit wide" data-source="${this._escape(row.source_id)}">${this._t("set_battery_type")}</button>
        <button class="action ignore wide" data-source="${this._escape(row.source_id)}">${this._t("ignore")}</button>
      </div>`
      )
      .join("");

    const ignoredCards = ignoredRows
      .map(
        (row) => `
      <div class="ignored-row">
        <div>
          <div class="name">${this._escape(row.name)}</div>
          <div class="entity">${this._escape(row.entity_id)}</div>
          <div class="entity">${this._t("battery_type")}: ${this._escape(this._batteryType(row))}</div>
          <div class="entity">${this._escape(this._batteryTypeSource(row))}</div>
        </div>
        <div class="ignored-actions"><button class="action type-edit" data-source="${this._escape(row.source_id)}">${this._t("set_battery_type")}</button><button class="action restore" data-source="${this._escape(row.source_id)}">${this._t("restore")}</button></div>
      </div>`
      )
      .join("");

    this.innerHTML = `
      <style>
        :host { display: block; width: 100%; max-width: 100%; min-width: 0; overflow-x: hidden; }
        *, *::before, *::after { box-sizing: border-box; }
        .wrap { width: 100%; max-width: 1600px; min-width: 0; padding: 16px; margin: 0 auto; overflow-x: hidden; }
        .top { display: flex; width: 100%; min-width: 0; gap: 12px; align-items: flex-end; justify-content: space-between; flex-wrap: wrap; margin-bottom: 16px; }
        .top > div { min-width: 0; max-width: 100%; }
        .title-row { display: flex; width: 100%; min-width: 0; align-items: flex-start; justify-content: space-between; gap: 12px; }
        .title-text { min-width: 0; }
        .ignored-toggle { flex: 0 0 auto; min-height: 44px; border: 1px solid var(--divider-color); border-radius: 10px; padding: 8px 14px; background: var(--card-background-color); color: var(--primary-color); font: inherit; cursor: pointer; white-space: nowrap; }
        h1 { margin: 0; font-size: 28px; font-weight: 500; }
        h2 { margin: 24px 0 10px; font-size: 20px; font-weight: 500; }
        .count { color: var(--secondary-text-color); margin-top: 4px; }
        .controls { display: flex; min-width: 0; max-width: 100%; gap: 10px; align-items: center; flex-wrap: wrap; }
        input, select { box-sizing: border-box; padding: 11px 12px; border-radius: 10px; border: 1px solid var(--divider-color); background: var(--card-background-color); color: var(--primary-text-color); font-size: 16px; min-height: 44px; }
        input { min-width: 260px; max-width: 480px; width: 32vw; }
        select { min-width: 215px; }
        .card { background: var(--card-background-color); border-radius: var(--ha-card-border-radius, 12px); box-shadow: var(--ha-card-box-shadow, none); border: var(--ha-card-border-width, 1px) solid var(--ha-card-border-color, var(--divider-color)); overflow: auto; }
        table { width: 100%; border-collapse: collapse; min-width: 1180px; }
        th, td { text-align: left; padding: 12px 14px; border-bottom: 1px solid var(--divider-color); white-space: nowrap; }
        th { position: sticky; top: 0; background: var(--card-background-color); font-weight: 500; z-index: 1; }
        tr:last-child td { border-bottom: none; }
        .name { font-weight: 500; }
        .entity-name-button { display: inline; max-width: 100%; margin: 0; padding: 0; border: 0; background: transparent; color: var(--primary-color); font: inherit; font-weight: 500; text-align: left; cursor: pointer; overflow-wrap: anywhere; }
        .entity-name-button:hover { text-decoration: underline; }
        .entity-name-button:focus-visible { outline: 2px solid var(--primary-color); outline-offset: 3px; border-radius: 3px; }
        .entity { color: var(--secondary-text-color); font-size: 12px; margin-top: 3px; overflow-wrap: anywhere; }
        .level, .battery-level { font-weight: 600; }
        .unavailable .level, .unavailable .battery-level { color: var(--error-color); }
        .mobile-list { display: none; width: 100%; min-width: 0; }
        .battery-card { width: 100%; max-width: 100%; min-width: 0; background: var(--card-background-color); border-radius: var(--ha-card-border-radius, 12px); box-shadow: var(--ha-card-box-shadow, none); border: var(--ha-card-border-width, 1px) solid var(--ha-card-border-color, var(--divider-color)); padding: 14px; }
        .battery-card-head { display: flex; width: 100%; min-width: 0; justify-content: space-between; gap: 12px; align-items: flex-start; }
        .battery-card-head > div:first-child { min-width: 0; flex: 1 1 auto; }
        .battery-level { flex: 0 0 auto; white-space: nowrap; font-size: 18px; }
        .details { display: grid; grid-template-columns: repeat(2, minmax(0, 1fr)); gap: 12px 18px; margin-top: 16px; }
        .details div { display: flex; flex-direction: column; gap: 3px; min-width: 0; }
        .details span { color: var(--secondary-text-color); font-size: 12px; }
        .details strong { font-size: 14px; font-weight: 500; overflow-wrap: anywhere; }
        .details .full { grid-column: 1 / -1; }
        .action { min-height: 36px; border: 1px solid var(--divider-color); border-radius: 9px; padding: 7px 12px; background: var(--card-background-color); color: var(--primary-color); font: inherit; cursor: pointer; }
        .action.wide { width: 100%; margin-top: 14px; }
        .action.wide + .action.wide { margin-top: 8px; }
        .ignored-actions { display: flex; gap: 8px; flex-wrap: wrap; justify-content: flex-end; }
        .ignored-list { display: grid; width: 100%; min-width: 0; gap: 1px; overflow: hidden; }
        .ignored-row { display: flex; gap: 12px; align-items: center; justify-content: space-between; padding: 12px 14px; background: var(--card-background-color); border-bottom: 1px solid var(--divider-color); }
        .ignored-row:last-child { border-bottom: none; }
        .empty { padding: 24px; color: var(--secondary-text-color); }
        @media (max-width: 700px) {
          :host { width: 100%; max-width: 100%; overflow-x: clip; }
          .wrap { width: 100%; max-width: 100%; min-width: 0; padding: 10px; margin: 0; overflow-x: clip; }
          h1 { font-size: 24px; }
          .title-row { align-items: flex-start; }
          .ignored-toggle { min-height: 40px; padding: 6px 10px; font-size: 14px; }
          .top { align-items: stretch; }
          .controls { width: 100%; max-width: 100%; min-width: 0; flex-direction: column; align-items: stretch; }
          input, select { display: block; width: 100%; max-width: 100%; min-width: 0; }
          .desktop-table { display: none; }
          .mobile-list { display: grid; width: 100%; max-width: 100%; min-width: 0; grid-template-columns: minmax(0, 1fr); gap: 10px; }
          .battery-card { width: 100%; max-width: 100%; min-width: 0; padding: 12px; overflow: hidden; }
          .entity { max-width: 100%; overflow-wrap: anywhere; word-break: break-word; }
          h1, h2, .count { max-width: 100%; overflow-wrap: anywhere; }
          .ignored-row { align-items: flex-start; flex-direction: column; }
          .ignored-row .action { width: 100%; }
          .ignored-actions { width: 100%; flex-direction: column; }
        }
      </style>
      <div class="wrap">
        <div class="top">
          <div class="title-row">
            <div class="title-text">
              <h1>${this._t("title")}</h1>
              <div class="count">${activeAll.length} ${this._t("monitored_count")}${ignoredAll.length ? ` · ${ignoredAll.length} ${this._t("ignored_count")}` : ""}</div>
            </div>
            ${ignoredAll.length || this._showIgnored ? `<button type="button" id="ignored-toggle" class="ignored-toggle">${this._showIgnored ? this._t("back") : `${this._t("show_ignored")} (${ignoredAll.length})`}</button>` : ""}
          </div>
          <div class="controls" style="${this._showIgnored ? "display:none" : ""}">
            <input id="search" type="search" placeholder="${this._t("search_placeholder")}" value="${this._escape(this._search)}">
            <select id="sort" aria-label="${this._t("sort_label")}">
              <option value="battery_asc" ${this._sort === "battery_asc" ? "selected" : ""}>${this._t("sort_battery_asc")}</option>
              <option value="battery_desc" ${this._sort === "battery_desc" ? "selected" : ""}>${this._t("sort_battery_desc")}</option>
              <option value="unavailable_first" ${this._sort === "unavailable_first" ? "selected" : ""}>${this._t("sort_unavailable_first")}</option>
              <option value="name_asc" ${this._sort === "name_asc" ? "selected" : ""}>${this._t("sort_name_asc")}</option>
              <option value="name_desc" ${this._sort === "name_desc" ? "selected" : ""}>${this._t("sort_name_desc")}</option>
            </select>
          </div>
        </div>
        ${this._showIgnored ? `
          <h2>${this._t("ignored_batteries")} (${ignoredAll.length})</h2>
          <div class="card ignored-list">
            ${ignoredRows.length ? ignoredCards : `<div class="empty">${this._t("no_ignored_match")}</div>`}
          </div>
        ` : (rows.length ? `
          <div class="card desktop-table">
            <table>
              <thead><tr>
                <th>${this._t("battery")}</th><th>${this._t("battery_type")}</th><th>${this._t("level")}</th><th>${this._t("started")}</th><th>${this._t("current")}</th><th>${this._t("previous")}</th><th>${this._t("average")}</th><th>${this._t("cycles")}</th><th>${this._t("expected_empty")}</th><th>${this._t("last_end_reason")}</th><th></th>
              </tr></thead>
              <tbody>${tableBody}</tbody>
            </table>
          </div>
          <div class="mobile-list">${mobileCards}</div>
        ` : `<div class="card"><div class="empty">${this._t("no_monitored_match")}</div></div>`)}
      </div>`;

    const ignoredToggle = this.querySelector("#ignored-toggle");
    if (ignoredToggle) {
      ignoredToggle.addEventListener("click", () => {
        this._showIgnored = !this._showIgnored;
        this._search = "";
        this._render();
      });
    }

    const search = this.querySelector("#search");
    if (search) {
      search.addEventListener("input", (event) => {
        this._search = event.target.value;
        this._render();
        const next = this.querySelector("#search");
        if (next) {
          next.focus();
          next.setSelectionRange(this._search.length, this._search.length);
        }
      });
    }

    const sort = this.querySelector("#sort");
    if (sort) {
      sort.addEventListener("change", (event) => {
        this._sort = event.target.value;
        this._render();
      });
    }

    this.querySelectorAll("button.entity-name-button").forEach((button) => {
      button.addEventListener("click", () => {
        this._openMoreInfo(button.dataset.entity);
      });
    });

    this.querySelectorAll("button.ignore").forEach((button) => {
      button.addEventListener("click", () => {
        const row = activeAll.find((item) => item.source_id === button.dataset.source);
        if (row) this._setIgnored(row, true);
      });
    });

    this.querySelectorAll("button.type-edit").forEach((button) => {
      button.addEventListener("click", () => {
        const allRows = [...activeAll, ...ignoredAll];
        const row = allRows.find((item) => item.source_id === button.dataset.source);
        if (row) this._setBatteryType(row);
      });
    });

    this.querySelectorAll("button.restore").forEach((button) => {
      button.addEventListener("click", () => {
        const row = ignoredAll.find((item) => item.source_id === button.dataset.source);
        if (row) this._setIgnored(row, false);
      });
    });
  }
}

if (!customElements.get("battery-lifetime-panel")) {
  customElements.define("battery-lifetime-panel", BatteryLifetimePanel);
}
