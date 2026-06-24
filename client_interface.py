"""Local client dashboard for blacklist review, alerts, and passenger history."""
from __future__ import annotations

import argparse
import json
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import parse_qs, unquote, urlparse

from loguru import logger

import storage

HTML = r"""<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>Manifest Watch</title>
  <style>
    :root {
      --bg: #f6f7f2;
      --panel: #ffffff;
      --ink: #1f2523;
      --muted: #66706b;
      --line: #d9ded7;
      --accent: #0f766e;
      --accent-2: #9f1239;
      --gold: #b7791f;
      --blue: #1d4e89;
      --soft: #e8f3f1;
      --danger-soft: #f8e7ed;
      --shadow: 0 10px 30px rgba(31, 37, 35, .08);
    }

    * { box-sizing: border-box; }
    body {
      margin: 0;
      background: var(--bg);
      color: var(--ink);
      font-family: Inter, ui-sans-serif, system-ui, -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif;
      letter-spacing: 0;
    }

    header {
      display: flex;
      align-items: center;
      justify-content: space-between;
      gap: 18px;
      min-height: 72px;
      padding: 14px 24px;
      border-bottom: 1px solid var(--line);
      background: #fbfcf9;
      position: sticky;
      top: 0;
      z-index: 5;
    }

    h1 {
      margin: 0;
      font-size: 22px;
      line-height: 1.1;
      font-weight: 760;
    }

    .subtle { color: var(--muted); font-size: 13px; }

    nav {
      display: flex;
      gap: 6px;
      padding: 4px;
      background: #edf1ec;
      border: 1px solid var(--line);
      border-radius: 8px;
    }

    button, input, textarea, select {
      font: inherit;
      letter-spacing: 0;
    }

    button {
      border: 1px solid var(--line);
      background: var(--panel);
      color: var(--ink);
      border-radius: 7px;
      min-height: 36px;
      padding: 0 12px;
      cursor: pointer;
      white-space: nowrap;
    }

    button:hover { border-color: #aab5ae; }
    button.primary { background: var(--accent); color: white; border-color: var(--accent); }
    button.danger { color: var(--accent-2); border-color: #e9b9c8; background: #fff8fa; }
    button.tab { border: 0; background: transparent; }
    button.tab.active { background: white; box-shadow: var(--shadow); }

    main {
      display: grid;
      grid-template-columns: minmax(0, 1fr);
      gap: 18px;
      padding: 22px 24px 36px;
    }

    .view { display: none; }
    .view.active { display: grid; gap: 16px; }

    .toolbar {
      display: flex;
      align-items: end;
      justify-content: space-between;
      gap: 12px;
      flex-wrap: wrap;
    }

    .filters {
      display: flex;
      gap: 10px;
      flex-wrap: wrap;
      align-items: end;
    }

    label {
      display: grid;
      gap: 5px;
      color: var(--muted);
      font-size: 12px;
      font-weight: 680;
      text-transform: uppercase;
    }

    input, textarea, select {
      width: 100%;
      min-height: 36px;
      border: 1px solid var(--line);
      border-radius: 7px;
      background: white;
      color: var(--ink);
      padding: 8px 10px;
      outline: none;
    }

    textarea {
      min-height: 72px;
      resize: vertical;
    }

    input:focus, textarea:focus, select:focus {
      border-color: var(--accent);
      box-shadow: 0 0 0 3px rgba(15, 118, 110, .14);
    }

    .form-grid {
      display: grid;
      grid-template-columns: repeat(4, minmax(150px, 1fr));
      gap: 10px;
      align-items: end;
      padding: 14px;
      background: var(--panel);
      border: 1px solid var(--line);
      border-radius: 8px;
      box-shadow: var(--shadow);
    }

    .form-grid .wide { grid-column: span 2; }
    .form-actions { display: flex; gap: 8px; justify-content: flex-end; }

    .table-wrap {
      overflow: auto;
      border: 1px solid var(--line);
      border-radius: 8px;
      background: var(--panel);
      box-shadow: var(--shadow);
    }

    table {
      width: 100%;
      min-width: 980px;
      border-collapse: collapse;
    }

    th, td {
      border-bottom: 1px solid var(--line);
      padding: 10px 12px;
      text-align: left;
      vertical-align: top;
      font-size: 13px;
    }

    th {
      position: sticky;
      top: 0;
      background: #f8faf6;
      color: #4d5853;
      font-size: 12px;
      text-transform: uppercase;
      z-index: 1;
    }

    tr:last-child td { border-bottom: 0; }
    tr.clickable { cursor: pointer; }
    tr.clickable:hover { background: #f5fbfa; }

    .day-group {
      border: 1px solid var(--line);
      border-radius: 8px;
      background: var(--panel);
      box-shadow: var(--shadow);
      overflow: hidden;
    }

    .day-head {
      display: flex;
      justify-content: space-between;
      gap: 12px;
      padding: 12px 14px;
      background: #f8faf6;
      border-bottom: 1px solid var(--line);
      font-weight: 760;
    }

    .alert-row {
      display: grid;
      grid-template-columns: minmax(180px, 1.1fr) minmax(260px, 1.6fr) minmax(220px, 1.3fr);
      gap: 14px;
      padding: 14px;
      border-bottom: 1px solid var(--line);
    }

    .alert-row:last-child { border-bottom: 0; }
    .alert-title { font-weight: 760; }
    .chips { display: flex; gap: 6px; flex-wrap: wrap; margin-top: 7px; }
    .chip {
      display: inline-flex;
      align-items: center;
      min-height: 24px;
      padding: 2px 8px;
      border-radius: 999px;
      background: var(--soft);
      color: #075e59;
      font-size: 12px;
      font-weight: 700;
    }
    .chip.danger { background: var(--danger-soft); color: var(--accent-2); }
    .chip.gold { background: #fbf0d3; color: #7c4a03; }
    .mono { font-family: ui-monospace, SFMono-Regular, Menlo, Consolas, monospace; }

    .drawer {
      position: fixed;
      right: 0;
      top: 0;
      bottom: 0;
      width: min(620px, 100vw);
      background: white;
      border-left: 1px solid var(--line);
      box-shadow: -18px 0 42px rgba(31, 37, 35, .16);
      transform: translateX(105%);
      transition: transform .18s ease;
      z-index: 10;
      display: grid;
      grid-template-rows: auto 1fr;
    }
    .drawer.open { transform: translateX(0); }
    .drawer-head {
      display: flex;
      justify-content: space-between;
      align-items: start;
      gap: 14px;
      padding: 18px;
      border-bottom: 1px solid var(--line);
      background: #fbfcf9;
    }
    .drawer-body {
      overflow: auto;
      padding: 16px 18px 24px;
      display: grid;
      gap: 12px;
      align-content: start;
    }
    .history-item {
      border: 1px solid var(--line);
      border-radius: 8px;
      padding: 12px;
      display: grid;
      gap: 8px;
      background: #fff;
    }
    .kv {
      display: grid;
      grid-template-columns: repeat(2, minmax(0, 1fr));
      gap: 8px 14px;
      font-size: 13px;
    }
    .kv div span {
      display: block;
      color: var(--muted);
      font-size: 11px;
      text-transform: uppercase;
      font-weight: 700;
      margin-bottom: 2px;
    }
    .empty {
      border: 1px dashed #b9c1bc;
      border-radius: 8px;
      padding: 24px;
      color: var(--muted);
      background: rgba(255,255,255,.55);
      text-align: center;
    }
    .status {
      color: var(--blue);
      font-size: 13px;
      min-height: 18px;
    }

    @media (max-width: 860px) {
      header { align-items: stretch; flex-direction: column; padding: 14px; }
      nav { overflow: auto; }
      main { padding: 14px; }
      .form-grid { grid-template-columns: 1fr; }
      .form-grid .wide { grid-column: auto; }
      .alert-row { grid-template-columns: 1fr; }
      .kv { grid-template-columns: 1fr; }
    }
  </style>
</head>
<body>
  <header>
    <div>
      <h1>Manifest Watch</h1>
    </div>
    <nav aria-label="Views">
      <button class="tab active" data-view="blacklist">Blacklist DB</button>
      <button class="tab" data-view="alerts">Active Alerts</button>
      <button class="tab" data-view="passengers">Manifest + History</button>
    </nav>
  </header>

  <main>
    <section class="view active" id="view-blacklist">
      <form id="blacklistForm" class="form-grid">
        <input type="hidden" id="blacklistId">
        <label>Passport <input id="passport" autocomplete="off"></label>
        <label>Mobile No <input id="mobile_no" autocomplete="off"></label>
        <label>Email ID <input id="email_id" type="email" autocomplete="off"></label>
        <label>Name <input id="name" autocomplete="off"></label>
        <label class="wide">Notes <textarea id="notes"></textarea></label>
        <div class="form-actions">
          <button type="button" id="resetBlacklist">Clear</button>
          <button type="submit" class="primary">Save</button>
        </div>
      </form>
      <div class="toolbar">
        <div class="status" id="blacklistStatus"></div>
        <button type="button" id="refreshBlacklist">Refresh</button>
      </div>
      <div class="table-wrap">
        <table>
          <thead><tr><th>Passport</th><th>Mobile No</th><th>Email ID</th><th>Name</th><th>Notes</th><th>Updated</th><th>Actions</th></tr></thead>
          <tbody id="blacklistRows"></tbody>
        </table>
      </div>
    </section>

    <section class="view" id="view-alerts">
      <div class="toolbar">
        <div class="filters">
          <label>Days
            <select id="alertDays">
              <option value="">All</option>
              <option value="1">Last 1 day</option>
              <option value="7" selected>Last 7 days</option>
              <option value="30">Last 30 days</option>
              <option value="90">Last 90 days</option>
            </select>
          </label>
          <button type="button" id="refreshAlerts">Refresh</button>
        </div>
        <div class="status" id="alertStatus"></div>
      </div>
      <div id="alertGroups"></div>
    </section>

    <section class="view" id="view-passengers">
      <div class="toolbar">
        <div class="filters">
          <label>Search <input id="passengerQuery" placeholder="Passport, name, PNR, flight, email"></label>
          <label>Flight Date <input id="flightDate" type="date"></label>
          <button type="button" id="refreshPassengers">Search</button>
        </div>
        <div class="status" id="passengerStatus"></div>
      </div>
      <div class="table-wrap">
        <table>
          <thead><tr><th>Passenger</th><th>Passport</th><th>Contact</th><th>Flight</th><th>PNR</th><th>Route</th><th>Manifest</th><th>Source</th></tr></thead>
          <tbody id="passengerRows"></tbody>
        </table>
      </div>
    </section>
  </main>

  <aside class="drawer" id="historyDrawer" aria-label="Passenger history">
    <div class="drawer-head">
      <div>
        <h2 id="historyTitle" style="margin:0;font-size:18px;">Passenger History</h2>
        <div class="subtle" id="historySubtitle"></div>
      </div>
      <button id="closeHistory" type="button">Close</button>
    </div>
    <div class="drawer-body" id="historyBody"></div>
  </aside>

  <script>
    const state = { blacklist: [], passengers: [], alerts: [] };
    const $ = (id) => document.getElementById(id);
    const esc = (value) => String(value ?? '').replace(/[&<>"']/g, (ch) => ({
      '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;'
    }[ch]));
    const valueOrDash = (value) => value ? esc(value) : '<span class="subtle">-</span>';

    async function api(path, options = {}) {
      const response = await fetch(path, {
        headers: { 'Content-Type': 'application/json' },
        ...options,
      });
      const data = await response.json().catch(() => ({}));
      if (!response.ok) throw new Error(data.error || response.statusText);
      return data;
    }

    function showView(view) {
      document.querySelectorAll('.tab').forEach((tab) => tab.classList.toggle('active', tab.dataset.view === view));
      document.querySelectorAll('.view').forEach((el) => el.classList.toggle('active', el.id === `view-${view}`));
      if (view === 'blacklist') loadBlacklist();
      if (view === 'alerts') loadAlerts();
      if (view === 'passengers') loadPassengers();
    }

    function resetBlacklistForm() {
      ['blacklistId', 'passport', 'mobile_no', 'email_id', 'name', 'notes'].forEach((id) => $(id).value = '');
    }

    async function loadBlacklist() {
      $('blacklistStatus').textContent = 'Loading...';
      const data = await api('/api/blacklist');
      state.blacklist = data.items;
      $('blacklistRows').innerHTML = state.blacklist.map((row) => `
        <tr>
          <td class="mono">${valueOrDash(row.passport)}</td>
          <td>${valueOrDash(row.mobile_no)}</td>
          <td>${valueOrDash(row.email_id)}</td>
          <td>${valueOrDash(row.name)}</td>
          <td>${valueOrDash(row.notes)}</td>
          <td>${valueOrDash(row.updated_at)}</td>
          <td>
            <button type="button" data-edit="${esc(row.id)}">Edit</button>
            <button type="button" class="danger" data-delete="${esc(row.id)}">Delete</button>
          </td>
        </tr>
      `).join('') || '<tr><td colspan="7"><div class="empty">No blacklist records.</div></td></tr>';
      $('blacklistStatus').textContent = `${state.blacklist.length} blacklist record(s)`;
    }

    async function saveBlacklist(event) {
      event.preventDefault();
      const id = $('blacklistId').value;
      const body = JSON.stringify({
        passport: $('passport').value,
        mobile_no: $('mobile_no').value,
        email_id: $('email_id').value,
        name: $('name').value,
        notes: $('notes').value,
      });
      $('blacklistStatus').textContent = 'Saving...';
      await api(id ? `/api/blacklist/${encodeURIComponent(id)}` : '/api/blacklist', {
        method: id ? 'PUT' : 'POST',
        body,
      });
      resetBlacklistForm();
      await loadBlacklist();
    }

    function editBlacklist(id) {
      const row = state.blacklist.find((item) => item.id === id);
      if (!row) return;
      $('blacklistId').value = row.id;
      $('passport').value = row.passport || '';
      $('mobile_no').value = row.mobile_no || '';
      $('email_id').value = row.email_id || '';
      $('name').value = row.name || '';
      $('notes').value = row.notes || '';
      $('passport').focus();
    }

    async function deleteBlacklist(id) {
      if (!confirm('Delete this blacklist record?')) return;
      await api(`/api/blacklist/${encodeURIComponent(id)}`, { method: 'DELETE' });
      await loadBlacklist();
    }

    async function loadAlerts() {
      $('alertStatus').textContent = 'Loading...';
      const days = $('alertDays').value;
      const data = await api(`/api/alerts${days ? `?days=${encodeURIComponent(days)}` : ''}`);
      state.alerts = data.items;
      const groups = data.groups;
      $('alertStatus').textContent = `${state.alerts.length} active match(es)`;
      $('alertGroups').innerHTML = Object.keys(groups).map((day) => `
        <div class="day-group">
          <div class="day-head"><span>${esc(day)}</span><span class="subtle">${groups[day].length} match(es)</span></div>
          ${groups[day].map(renderAlert).join('')}
        </div>
      `).join('') || '<div class="empty">No active alerts for this range.</div>';
    }

    function renderAlert(alert) {
      const p = alert.passenger;
      const b = alert.blacklist;
      return `
        <div class="alert-row">
          <div>
            <div class="alert-title">${valueOrDash(p.display_name)}</div>
            <div class="subtle mono">${valueOrDash(p.passport_number)}</div>
            <div class="chips">${alert.matched_fields.map((field) => `<span class="chip danger">${esc(field)}</span>`).join('')}</div>
          </div>
          <div>
            <div><b>${valueOrDash(p.flight_number)}</b> <span class="subtle">${valueOrDash(p.manifest_type)}</span></div>
            <div class="subtle">${valueOrDash(p.origin)} to ${valueOrDash(p.destination)} | PNR ${valueOrDash(p.pnr)}</div>
            <div class="subtle">${valueOrDash(p.email)} | ${valueOrDash(p.phone)}</div>
          </div>
          <div>
            <div class="alert-title">Blacklist Record</div>
            <div class="subtle">${valueOrDash(b.name)} | ${valueOrDash(b.email_id)}</div>
            <div class="subtle">${valueOrDash(b.passport)} | ${valueOrDash(b.mobile_no)}</div>
            <div class="chips"><button type="button" data-passport="${esc(p.passport_number || '')}">History</button></div>
          </div>
        </div>
      `;
    }

    async function loadPassengers() {
      $('passengerStatus').textContent = 'Loading...';
      const params = new URLSearchParams();
      if ($('passengerQuery').value.trim()) params.set('q', $('passengerQuery').value.trim());
      if ($('flightDate').value) params.set('flight_date', $('flightDate').value);
      const data = await api(`/api/passengers?${params.toString()}`);
      state.passengers = data.items;
      $('passengerRows').innerHTML = state.passengers.map((row) => `
        <tr class="clickable" data-passport="${esc(row.passport_number || '')}">
          <td>${valueOrDash(row.display_name)}<div class="subtle">${valueOrDash(row.nationality)}</div></td>
          <td class="mono">${valueOrDash(row.passport_number)}</td>
          <td>${valueOrDash(row.phone)}<div class="subtle">${valueOrDash(row.email)}</div></td>
          <td><b>${valueOrDash(row.flight_number)}</b><div class="subtle">${valueOrDash(row.flight_date)}</div></td>
          <td class="mono">${valueOrDash(row.pnr)}</td>
          <td>${valueOrDash(row.origin)} to ${valueOrDash(row.destination)}</td>
          <td><span class="chip gold">${valueOrDash(row.airline_code)}</span> ${valueOrDash(row.manifest_type)}</td>
          <td>${valueOrDash(row.attachment_file_name)}<div class="subtle">${valueOrDash(row.email_subject)}</div></td>
        </tr>
      `).join('') || '<tr><td colspan="8"><div class="empty">No manifest passengers found.</div></td></tr>';
      $('passengerStatus').textContent = `${state.passengers.length} passenger row(s)`;
    }

    async function openHistory(passport) {
      if (!passport) return;
      $('historyDrawer').classList.add('open');
      $('historyTitle').textContent = 'Passenger History';
      $('historySubtitle').textContent = passport;
      $('historyBody').innerHTML = '<div class="empty">Loading...</div>';
      const data = await api(`/api/passengers/history/${encodeURIComponent(passport)}`);
      $('historyTitle').textContent = data.passenger_name || 'Passenger History';
      $('historySubtitle').textContent = `${passport} | ${data.items.length} manifest row(s)`;
      $('historyBody').innerHTML = data.items.map((row) => `
        <div class="history-item">
          <div><b>${valueOrDash(row.flight_number)}</b> <span class="subtle">${valueOrDash(row.flight_date)} | ${valueOrDash(row.manifest_type)}</span></div>
          <div class="kv">
            <div><span>Route</span>${valueOrDash(row.origin)} to ${valueOrDash(row.destination)}</div>
            <div><span>PNR</span><span class="mono">${valueOrDash(row.pnr)}</span></div>
            <div><span>Seat</span>${valueOrDash(row.seat_number)}</div>
            <div><span>Cabin</span>${valueOrDash(row.cabin_class)}</div>
            <div><span>Bags</span>${valueOrDash(row.no_of_bags)} | ${valueOrDash(row.baggage_weight)}</div>
            <div><span>Contact</span>${valueOrDash(row.phone)} | ${valueOrDash(row.email)}</div>
            <div><span>Ticket</span>${valueOrDash(row.ticket_number)}</div>
            <div><span>Source</span>${valueOrDash(row.attachment_file_name)}</div>
          </div>
        </div>
      `).join('') || '<div class="empty">No history found for this passport.</div>';
    }

    document.querySelectorAll('.tab').forEach((tab) => tab.addEventListener('click', () => showView(tab.dataset.view)));
    $('blacklistForm').addEventListener('submit', saveBlacklist);
    $('resetBlacklist').addEventListener('click', resetBlacklistForm);
    $('refreshBlacklist').addEventListener('click', loadBlacklist);
    $('refreshAlerts').addEventListener('click', loadAlerts);
    $('alertDays').addEventListener('change', loadAlerts);
    $('refreshPassengers').addEventListener('click', loadPassengers);
    $('passengerQuery').addEventListener('keydown', (event) => { if (event.key === 'Enter') loadPassengers(); });
    $('closeHistory').addEventListener('click', () => $('historyDrawer').classList.remove('open'));
    document.body.addEventListener('click', (event) => {
      const editId = event.target.dataset?.edit;
      const deleteId = event.target.dataset?.delete;
      const passport = event.target.dataset?.passport || event.target.closest('tr[data-passport]')?.dataset.passport;
      if (editId) editBlacklist(editId);
      if (deleteId) deleteBlacklist(deleteId);
      if (passport) openHistory(passport);
    });

    loadBlacklist().catch((error) => $('blacklistStatus').textContent = error.message);
  </script>
</body>
</html>"""


class ClientInterfaceHandler(BaseHTTPRequestHandler):
    server_version = "ManifestWatch/1.0"

    def log_message(self, fmt: str, *args) -> None:
        logger.info("{} - {}", self.address_string(), fmt % args)

    def do_GET(self) -> None:
        parsed = urlparse(self.path)
        try:
            if parsed.path == "/":
                self._send_html(HTML)
            elif parsed.path == "/api/blacklist":
                self._send_json({"items": storage.list_blacklist_entries()})
            elif parsed.path == "/api/alerts":
                params = parse_qs(parsed.query)
                days = int(params["days"][0]) if params.get("days") and params["days"][0] else None
                items = storage.active_blacklist_alerts(days=days)
                groups: dict[str, list[dict]] = {}
                for item in items:
                    groups.setdefault(item["day"], []).append(item)
                self._send_json({"items": items, "groups": groups})
            elif parsed.path == "/api/passengers":
                params = parse_qs(parsed.query)
                items = storage.list_manifest_passengers(
                    query=params.get("q", [""])[0] or None,
                    flight_date=params.get("flight_date", [""])[0] or None,
                )
                self._send_json({"items": items})
            elif parsed.path.startswith("/api/passengers/history/"):
                passport = unquote(parsed.path.rsplit("/", 1)[-1])
                items = storage.passenger_history_by_passport(passport)
                passenger_name = items[0]["display_name"] if items else ""
                self._send_json({"passport": passport, "passenger_name": passenger_name, "items": items})
            else:
                self._send_json({"error": "Not found"}, HTTPStatus.NOT_FOUND)
        except Exception as exc:
            logger.exception("GET %s failed", self.path)
            self._send_json({"error": str(exc)}, HTTPStatus.INTERNAL_SERVER_ERROR)

    def do_POST(self) -> None:
        parsed = urlparse(self.path)
        try:
            if parsed.path == "/api/blacklist":
                payload = self._read_json()
                item = storage.upsert_blacklist_entry(**payload)
                self._send_json({"item": item}, HTTPStatus.CREATED)
            else:
                self._send_json({"error": "Not found"}, HTTPStatus.NOT_FOUND)
        except ValueError as exc:
            self._send_json({"error": str(exc)}, HTTPStatus.BAD_REQUEST)
        except Exception as exc:
            logger.exception("POST %s failed", self.path)
            self._send_json({"error": str(exc)}, HTTPStatus.INTERNAL_SERVER_ERROR)

    def do_PUT(self) -> None:
        parsed = urlparse(self.path)
        try:
            if parsed.path.startswith("/api/blacklist/"):
                entry_id = unquote(parsed.path.rsplit("/", 1)[-1])
                payload = self._read_json()
                item = storage.upsert_blacklist_entry(entry_id=entry_id, **payload)
                self._send_json({"item": item})
            else:
                self._send_json({"error": "Not found"}, HTTPStatus.NOT_FOUND)
        except KeyError as exc:
            self._send_json({"error": str(exc)}, HTTPStatus.NOT_FOUND)
        except ValueError as exc:
            self._send_json({"error": str(exc)}, HTTPStatus.BAD_REQUEST)
        except Exception as exc:
            logger.exception("PUT %s failed", self.path)
            self._send_json({"error": str(exc)}, HTTPStatus.INTERNAL_SERVER_ERROR)

    def do_DELETE(self) -> None:
        parsed = urlparse(self.path)
        try:
            if parsed.path.startswith("/api/blacklist/"):
                entry_id = unquote(parsed.path.rsplit("/", 1)[-1])
                deleted = storage.delete_blacklist_entry(entry_id)
                self._send_json({"deleted": deleted}, HTTPStatus.OK if deleted else HTTPStatus.NOT_FOUND)
            else:
                self._send_json({"error": "Not found"}, HTTPStatus.NOT_FOUND)
        except Exception as exc:
            logger.exception("DELETE %s failed", self.path)
            self._send_json({"error": str(exc)}, HTTPStatus.INTERNAL_SERVER_ERROR)

    def _read_json(self) -> dict:
        length = int(self.headers.get("Content-Length", "0"))
        if length <= 0:
            return {}
        return json.loads(self.rfile.read(length).decode("utf-8"))

    def _send_html(self, body: str, status: HTTPStatus = HTTPStatus.OK) -> None:
        encoded = body.encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.send_header("Content-Length", str(len(encoded)))
        self.end_headers()
        self.wfile.write(encoded)

    def _send_json(self, payload: dict, status: HTTPStatus = HTTPStatus.OK) -> None:
        encoded = json.dumps(payload, default=str).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(encoded)))
        self.end_headers()
        self.wfile.write(encoded)


def run(host: str = "127.0.0.1", port: int = 8080) -> None:
    storage.init_db()
    server = ThreadingHTTPServer((host, port), ClientInterfaceHandler)
    logger.info("Client interface running at http://{}:{}", host, port)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        logger.info("Client interface stopped")
    finally:
        server.server_close()


def main() -> None:
    parser = argparse.ArgumentParser(description="Run the local client manifest dashboard.")
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=8080)
    args = parser.parse_args()
    run(args.host, args.port)


if __name__ == "__main__":
    main()
