"""Local client dashboard for blacklist review, alerts, and passenger history."""

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
      --bg: #0f1117;
      --surface: #161b22;
      --surface-2: #1c2230;
      --surface-3: #222b3a;
      --border: #2a3347;
      --border-light: #1e2a3a;
      --ink: #e2e8f0;
      --muted: #7a8ba0;
      --muted-2: #4a5568;
      --accent: #3b82f6;
      --accent-dark: #2563eb;
      --accent-glow: rgba(59,130,246,.18);
      --green: #10b981;
      --green-soft: rgba(16,185,129,.14);
      --red: #ef4444;
      --red-soft: rgba(239,68,68,.13);
      --amber: #f59e0b;
      --amber-soft: rgba(245,158,11,.14);
      --purple: #8b5cf6;
      --purple-soft: rgba(139,92,246,.14);
      --shadow: 0 4px 24px rgba(0,0,0,.45);
      --radius: 10px;
      --radius-sm: 7px;
    }

    *, *::before, *::after { box-sizing: border-box; }

    body {
      margin: 0;
      background: var(--bg);
      color: var(--ink);
      font-family: Inter, ui-sans-serif, system-ui, -apple-system, sans-serif;
      font-size: 13.5px;
      line-height: 1.55;
      min-height: 100vh;
    }

    /* ── Scrollbars ─────────────────────────────────────── */
    ::-webkit-scrollbar { width: 6px; height: 6px; }
    ::-webkit-scrollbar-track { background: transparent; }
    ::-webkit-scrollbar-thumb { background: var(--border); border-radius: 3px; }

    /* ── Header ─────────────────────────────────────────── */
    header {
      position: sticky; top: 0; z-index: 20;
      background: rgba(22,27,34,.92);
      backdrop-filter: blur(12px);
      border-bottom: 1px solid var(--border);
      display: flex; align-items: center; justify-content: space-between;
      gap: 16px; padding: 0 24px; min-height: 60px;
    }

    .logo { display: flex; align-items: center; gap: 10px; }
    .logo-icon {
      width: 32px; height: 32px; border-radius: 8px;
      background: linear-gradient(135deg, #3b82f6 0%, #8b5cf6 100%);
      display: flex; align-items: center; justify-content: center;
      font-size: 16px; flex-shrink: 0;
    }
    .logo-text { font-size: 16px; font-weight: 720; color: var(--ink); }
    .logo-sub { font-size: 11px; color: var(--muted); }

    .header-stats {
      display: flex; gap: 18px; align-items: center;
    }
    .stat-pill {
      display: flex; align-items: center; gap: 6px;
      font-size: 12px; color: var(--muted);
    }
    .stat-pill strong { color: var(--ink); font-weight: 700; }
    .stat-dot {
      width: 6px; height: 6px; border-radius: 50%;
    }

    nav {
      display: flex; gap: 2px;
      padding: 3px; background: var(--surface-2);
      border: 1px solid var(--border); border-radius: var(--radius-sm);
    }
    .tab {
      border: 0; background: transparent; color: var(--muted);
      border-radius: 5px; padding: 6px 14px; cursor: pointer;
      font-size: 13px; font-weight: 600; transition: all .15s;
      white-space: nowrap;
    }
    .tab:hover { color: var(--ink); background: var(--surface-3); }
    .tab.active { background: var(--accent); color: #fff; }

    /* ── Layout ─────────────────────────────────────────── */
    main { padding: 20px 24px 48px; display: grid; gap: 16px; }
    .view { display: none; }
    .view.active { display: grid; gap: 14px; }

    /* ── Filter panel ───────────────────────────────────── */
    .filter-panel {
      background: var(--surface);
      border: 1px solid var(--border);
      border-radius: var(--radius);
      padding: 14px 16px;
      display: grid; gap: 10px;
    }
    .filter-panel-head {
      display: flex; align-items: center; justify-content: space-between; gap: 12px;
    }
    .filter-panel-head h3 {
      margin: 0; font-size: 12px; font-weight: 700;
      text-transform: uppercase; letter-spacing: .06em; color: var(--muted);
    }
    .filter-actions { display: flex; gap: 8px; align-items: center; }
    .active-badge {
      display: inline-flex; align-items: center; gap: 4px;
      padding: 2px 8px; border-radius: 999px;
      background: var(--accent-glow); color: var(--accent);
      font-size: 11px; font-weight: 700;
    }

    .filter-grid {
      display: grid;
      grid-template-columns: repeat(auto-fill, minmax(160px, 1fr));
      gap: 8px;
    }
    .filter-grid .span2 { grid-column: span 2; }
    .filter-grid .span3 { grid-column: span 3; }

    .fg { display: grid; gap: 4px; }
    .fg label {
      font-size: 11px; font-weight: 700; color: var(--muted);
      text-transform: uppercase; letter-spacing: .05em;
    }
    .fg input, .fg select {
      width: 100%; height: 34px;
      background: var(--surface-2); color: var(--ink);
      border: 1px solid var(--border); border-radius: var(--radius-sm);
      padding: 0 10px; font: inherit; font-size: 13px; outline: none;
      transition: border-color .15s, box-shadow .15s;
      -webkit-appearance: none; appearance: none;
    }
    .fg input:focus, .fg select:focus {
      border-color: var(--accent);
      box-shadow: 0 0 0 3px var(--accent-glow);
    }
    .fg input::placeholder { color: var(--muted-2); }
    .fg select option { background: var(--surface-2); color: var(--ink); }

    .date-range { display: flex; gap: 6px; align-items: center; }
    .date-range input { flex: 1; min-width: 0; }
    .date-sep { color: var(--muted); font-size: 11px; flex-shrink: 0; }

    /* ── Buttons ────────────────────────────────────────── */
    button { font: inherit; cursor: pointer; transition: all .15s; }

    .btn {
      display: inline-flex; align-items: center; gap: 6px;
      border-radius: var(--radius-sm);
      padding: 7px 14px; font-size: 13px; font-weight: 600;
      border: 1px solid var(--border); background: var(--surface-2); color: var(--ink);
      white-space: nowrap;
    }
    .btn:hover { background: var(--surface-3); border-color: #3a4a60; }
    .btn.primary { background: var(--accent); color: #fff; border-color: var(--accent); }
    .btn.primary:hover { background: var(--accent-dark); border-color: var(--accent-dark); }
    .btn.danger { color: var(--red); border-color: rgba(239,68,68,.3); background: var(--red-soft); }
    .btn.danger:hover { background: rgba(239,68,68,.22); }
    .btn.ghost { background: transparent; border-color: transparent; color: var(--muted); }
    .btn.ghost:hover { color: var(--ink); background: var(--surface-2); }
    .btn.sm { padding: 4px 10px; font-size: 12px; }
    .btn-icon { width: 32px; height: 32px; padding: 0; display: inline-flex; align-items: center; justify-content: center; }

    /* ── Toolbar ────────────────────────────────────────── */
    .toolbar {
      display: flex; align-items: center; justify-content: space-between;
      gap: 12px; flex-wrap: wrap;
    }
    .toolbar-left { display: flex; gap: 8px; align-items: center; flex-wrap: wrap; }
    .status { font-size: 12px; color: var(--muted); }
    .status strong { color: var(--ink); }

    /* ── Table ──────────────────────────────────────────── */
    .table-wrap {
      overflow: auto;
      border: 1px solid var(--border);
      border-radius: var(--radius);
      background: var(--surface);
      box-shadow: var(--shadow);
    }
    table {
      width: 100%; min-width: 980px;
      border-collapse: collapse;
    }
    thead th {
      position: sticky; top: 0; z-index: 2;
      background: var(--surface-2);
      border-bottom: 1px solid var(--border);
      padding: 9px 12px;
      font-size: 11px; font-weight: 700;
      text-transform: uppercase; letter-spacing: .05em;
      color: var(--muted); white-space: nowrap;
      cursor: default; user-select: none;
    }
    thead th.sortable { cursor: pointer; }
    thead th.sortable:hover { color: var(--ink); }
    thead th .sort-icon { margin-left: 4px; opacity: .4; font-size: 9px; }
    thead th.asc .sort-icon::after { content: '▲'; opacity: 1; }
    thead th.desc .sort-icon::after { content: '▼'; opacity: 1; }
    thead th .sort-icon::after { content: '⬍'; }

    tbody tr {
      border-bottom: 1px solid var(--border-light);
      transition: background .1s;
    }
    tbody tr:last-child { border-bottom: 0; }
    tbody tr:hover { background: var(--surface-2); }
    tbody tr.clickable { cursor: pointer; }
    td {
      padding: 9px 12px; font-size: 13px;
      vertical-align: middle; color: var(--ink);
    }

    /* ── Chips / badges ─────────────────────────────────── */
    .chip {
      display: inline-flex; align-items: center;
      padding: 2px 8px; border-radius: 999px;
      font-size: 11px; font-weight: 700; white-space: nowrap;
    }
    .chip.green { background: var(--green-soft); color: var(--green); }
    .chip.red { background: var(--red-soft); color: var(--red); }
    .chip.amber { background: var(--amber-soft); color: var(--amber); }
    .chip.blue { background: var(--accent-glow); color: var(--accent); }
    .chip.purple { background: var(--purple-soft); color: var(--purple); }
    .chip.neutral { background: var(--surface-3); color: var(--muted); }

    .chips { display: flex; gap: 5px; flex-wrap: wrap; margin-top: 4px; }

    /* ── Blacklist form ─────────────────────────────────── */
    .bl-form {
      background: var(--surface);
      border: 1px solid var(--border);
      border-radius: var(--radius);
      padding: 16px;
      display: grid;
      grid-template-columns: repeat(auto-fill, minmax(180px, 1fr));
      gap: 10px;
    }
    .bl-form .full { grid-column: 1/-1; }
    .bl-form .actions { grid-column: 1/-1; display: flex; gap: 8px; justify-content: flex-end; }
    .bl-form textarea {
      width: 100%; min-height: 64px; resize: vertical;
      background: var(--surface-2); color: var(--ink);
      border: 1px solid var(--border); border-radius: var(--radius-sm);
      padding: 8px 10px; font: inherit; font-size: 13px; outline: none;
    }
    .bl-form textarea:focus {
      border-color: var(--accent); box-shadow: 0 0 0 3px var(--accent-glow);
    }

    /* ── Alerts ─────────────────────────────────────────── */
    .alert-day {
      border: 1px solid var(--border);
      border-radius: var(--radius);
      background: var(--surface);
      box-shadow: var(--shadow);
      overflow: hidden;
    }
    .alert-day-head {
      display: flex; justify-content: space-between; align-items: center;
      gap: 12px; padding: 12px 16px;
      background: var(--surface-2);
      border-bottom: 1px solid var(--border);
      font-weight: 700; font-size: 13.5px;
      cursor: pointer; user-select: none;
    }
    .alert-day-head:hover { background: var(--surface-3); }
    .alert-day-head .toggle-icon { color: var(--muted); font-size: 11px; }
    .alert-day-body.collapsed { display: none; }

    .alert-card {
      display: grid;
      grid-template-columns: 1fr 1.5fr 1.1fr auto;
      gap: 16px; padding: 14px 16px;
      border-bottom: 1px solid var(--border-light);
      align-items: start;
    }
    .alert-card:last-child { border-bottom: 0; }
    .alert-card:hover { background: var(--surface-2); }

    .alert-name { font-weight: 700; font-size: 14px; }
    .alert-sub { color: var(--muted); font-size: 12px; margin-top: 2px; }
    .alert-field { font-size: 12.5px; color: var(--ink); }
    .alert-field span { color: var(--muted); }

    /* ── Drawer ─────────────────────────────────────────── */
    .overlay {
      position: fixed; inset: 0; background: rgba(0,0,0,.55);
      z-index: 25; opacity: 0; pointer-events: none;
      transition: opacity .2s;
    }
    .overlay.open { opacity: 1; pointer-events: auto; }
    .drawer {
      position: fixed; right: 0; top: 0; bottom: 0;
      width: min(660px, 100vw);
      background: var(--surface);
      border-left: 1px solid var(--border);
      box-shadow: -24px 0 60px rgba(0,0,0,.6);
      transform: translateX(105%);
      transition: transform .2s cubic-bezier(.4,0,.2,1);
      z-index: 30;
      display: grid; grid-template-rows: auto 1fr;
    }
    .drawer.open { transform: translateX(0); }
    .drawer-head {
      display: flex; justify-content: space-between; align-items: start;
      gap: 14px; padding: 18px 20px;
      border-bottom: 1px solid var(--border);
      background: var(--surface-2);
    }
    .drawer-head h2 { margin: 0; font-size: 17px; font-weight: 720; }
    .drawer-head .sub { font-size: 12px; color: var(--muted); margin-top: 3px; }
    .drawer-body {
      overflow-y: auto; padding: 16px 20px 28px;
      display: grid; gap: 10px; align-content: start;
    }
    .history-card {
      border: 1px solid var(--border);
      border-radius: var(--radius);
      background: var(--surface-2);
      overflow: hidden;
    }
    .history-card-head {
      display: flex; justify-content: space-between; align-items: center;
      gap: 10px; padding: 10px 14px;
      background: var(--surface-3);
      border-bottom: 1px solid var(--border);
    }
    .history-card-body {
      display: grid;
      grid-template-columns: repeat(2, 1fr);
      gap: 0;
    }
    .kv-cell {
      padding: 8px 14px;
      border-bottom: 1px solid var(--border-light);
      border-right: 1px solid var(--border-light);
      font-size: 12.5px;
    }
    .kv-cell:nth-child(2n) { border-right: 0; }
    .kv-cell:nth-last-child(-n+2) { border-bottom: 0; }
    .kv-label { font-size: 10.5px; text-transform: uppercase; font-weight: 700; color: var(--muted); margin-bottom: 2px; }

    /* ── Empty state ────────────────────────────────────── */
    .empty {
      padding: 40px 24px; text-align: center;
      color: var(--muted); font-size: 13.5px;
    }
    .empty-icon { font-size: 32px; margin-bottom: 10px; opacity: .5; }

    /* ── Misc helpers ───────────────────────────────────── */
    .mono { font-family: ui-monospace, SFMono-Regular, Menlo, Consolas, monospace; font-size: 12.5px; }
    .text-muted { color: var(--muted); }
    .text-sm { font-size: 12px; }
    .text-xs { font-size: 11px; }
    .fw-bold { font-weight: 700; }
    .flex { display: flex; }
    .items-center { align-items: center; }
    .gap-8 { gap: 8px; }
    .mt-2 { margin-top: 2px; }
    .mt-4 { margin-top: 4px; }
    a { color: var(--accent); text-decoration: none; }
    a:hover { text-decoration: underline; }

    /* ── Pagination ─────────────────────────────────────── */
    .pagination {
      display: flex; align-items: center; gap: 8px;
      padding: 10px 0; justify-content: center;
    }
    .page-info { font-size: 12px; color: var(--muted); }

    /* ── Toast ──────────────────────────────────────────── */
    .toast {
      position: fixed; bottom: 24px; right: 24px; z-index: 50;
      background: var(--surface-3); color: var(--ink);
      border: 1px solid var(--border);
      border-radius: var(--radius); padding: 10px 16px;
      font-size: 13px; box-shadow: var(--shadow);
      transform: translateY(16px); opacity: 0;
      transition: all .2s; pointer-events: none;
    }
    .toast.show { transform: translateY(0); opacity: 1; }
    .toast.ok { border-color: var(--green); color: var(--green); }
    .toast.err { border-color: var(--red); color: var(--red); }

    @media (max-width: 860px) {
      header { flex-direction: column; align-items: stretch; padding: 12px 16px; gap: 10px; }
      .header-stats { display: none; }
      main { padding: 12px 16px; }
      .filter-grid { grid-template-columns: 1fr 1fr; }
      .filter-grid .span2, .filter-grid .span3 { grid-column: span 2; }
      .alert-card { grid-template-columns: 1fr; gap: 10px; }
    }
    @media (max-width: 560px) {
      .filter-grid { grid-template-columns: 1fr; }
      .filter-grid .span2, .filter-grid .span3 { grid-column: 1; }
    }
  </style>
</head>
<body>

<header>
  <div class="logo">
    <div class="logo-icon">✈</div>
    <div>
      <div class="logo-text">Manifest Watch</div>
      <div class="logo-sub">DRI Surveillance Platform</div>
    </div>
  </div>
  <div class="header-stats" id="headerStats"></div>
  <nav>
    <button class="tab active" data-view="blacklist">Blacklist DB</button>
    <button class="tab" data-view="alerts">Active Alerts</button>
    <button class="tab" data-view="passengers">Passengers</button>
  </nav>
</header>

<main>

  <!-- ═══════════════ BLACKLIST ═══════════════ -->
  <section class="view active" id="view-blacklist">
    <form id="blacklistForm" class="bl-form">
      <input type="hidden" id="blacklistId">
      <div class="fg">
        <label>Passport No</label>
        <input id="passport" autocomplete="off" placeholder="AB1234567">
      </div>
      <div class="fg">
        <label>Mobile No</label>
        <input id="mobile_no" autocomplete="off" placeholder="+91 9999999999">
      </div>
      <div class="fg">
        <label>Email ID</label>
        <input id="email_id" type="email" autocomplete="off" placeholder="name@domain.com">
      </div>
      <div class="fg">
        <label>Full Name</label>
        <input id="name" autocomplete="off" placeholder="Last, First">
      </div>
      <div class="fg full">
        <label>Notes</label>
        <textarea id="notes" placeholder="Reason for blacklisting, case reference..."></textarea>
      </div>
      <div class="actions">
        <button type="button" id="resetBlacklist" class="btn ghost">Clear</button>
        <button type="submit" class="btn primary" id="saveBlacklistBtn">
          <span id="saveBlacklistLabel">Save Entry</span>
        </button>
      </div>
    </form>

    <div class="toolbar">
      <div class="toolbar-left">
        <div class="fg" style="width:240px">
          <input id="blSearch" placeholder="Search by name, passport, email, mobile…">
        </div>
        <button type="button" id="refreshBlacklist" class="btn sm">Refresh</button>
      </div>
      <div class="status" id="blacklistStatus"></div>
    </div>

    <div class="table-wrap">
      <table id="blacklistTable">
        <thead><tr>
          <th class="sortable" data-col="passport">Passport <span class="sort-icon"></span></th>
          <th class="sortable" data-col="mobile_no">Mobile <span class="sort-icon"></span></th>
          <th class="sortable" data-col="email_id">Email <span class="sort-icon"></span></th>
          <th class="sortable" data-col="name">Name <span class="sort-icon"></span></th>
          <th>Notes</th>
          <th class="sortable" data-col="updated_at">Updated <span class="sort-icon"></span></th>
          <th>Actions</th>
        </tr></thead>
        <tbody id="blacklistRows"></tbody>
      </table>
    </div>
  </section>

  <!-- ═══════════════ ALERTS ═══════════════ -->
  <section class="view" id="view-alerts">
    <div class="filter-panel">
      <div class="filter-panel-head">
        <h3>Filters</h3>
        <div class="filter-actions">
          <span class="active-badge" id="alertFilterBadge" style="display:none"></span>
          <button type="button" id="resetAlertFilters" class="btn ghost sm">Reset</button>
          <button type="button" id="refreshAlerts" class="btn sm primary">Apply</button>
        </div>
      </div>
      <div class="filter-grid">
        <div class="fg">
          <label>Time Range</label>
          <select id="alertDays">
            <option value="">All time</option>
            <option value="1">Last 24 h</option>
            <option value="7" selected>Last 7 days</option>
            <option value="30">Last 30 days</option>
            <option value="90">Last 90 days</option>
          </select>
        </div>
        <div class="fg">
          <label>Match Field</label>
          <select id="alertMatchField">
            <option value="">Any field</option>
            <option value="passport">Passport</option>
            <option value="mobile_no">Mobile</option>
            <option value="email_id">Email</option>
            <option value="name">Name</option>
          </select>
        </div>
        <div class="fg span2">
          <label>Search Passenger</label>
          <input id="alertSearch" placeholder="Name, passport, flight, PNR…">
        </div>
      </div>
    </div>

    <div class="toolbar">
      <div class="status" id="alertStatus"></div>
      <div class="flex items-center gap-8">
        <button type="button" id="alertExpandAll" class="btn ghost sm">Expand All</button>
        <button type="button" id="alertCollapseAll" class="btn ghost sm">Collapse All</button>
      </div>
    </div>
    <div id="alertGroups"></div>
  </section>

  <!-- ═══════════════ PASSENGERS ═══════════════ -->
  <section class="view" id="view-passengers">
    <div class="filter-panel">
      <div class="filter-panel-head">
        <h3>Filters</h3>
        <div class="filter-actions">
          <span class="active-badge" id="paxFilterBadge" style="display:none"></span>
          <button type="button" id="resetPaxFilters" class="btn ghost sm">Reset</button>
          <button type="button" id="searchPassengers" class="btn sm primary">Search</button>
        </div>
      </div>
      <div class="filter-grid">
        <div class="fg span3">
          <label>Full-text Search</label>
          <input id="passengerQuery" placeholder="Passport, name, PNR, flight, email, phone…">
        </div>
        <div class="fg">
          <label>Flight Date</label>
          <input id="flightDate" type="date">
        </div>
        <div class="fg span2">
          <label>Date Range</label>
          <div class="date-range">
            <input id="flightDateFrom" type="date" placeholder="From">
            <span class="date-sep">to</span>
            <input id="flightDateTo" type="date" placeholder="To">
          </div>
        </div>
        <div class="fg">
          <label>Flight No</label>
          <input id="filterFlightNo" placeholder="e.g. 6E-123">
        </div>
        <div class="fg">
          <label>Airline</label>
          <select id="filterAirline">
            <option value="">All airlines</option>
          </select>
        </div>
        <div class="fg">
          <label>Manifest Type</label>
          <select id="filterManifestType">
            <option value="">All types</option>
          </select>
        </div>
        <div class="fg">
          <label>Origin</label>
          <select id="filterOrigin">
            <option value="">All origins</option>
          </select>
        </div>
        <div class="fg">
          <label>Destination</label>
          <select id="filterDestination">
            <option value="">All destinations</option>
          </select>
        </div>
        <div class="fg">
          <label>Cabin Class</label>
          <select id="filterCabin">
            <option value="">All cabins</option>
          </select>
        </div>
        <div class="fg">
          <label>Nationality</label>
          <select id="filterNationality">
            <option value="">All nationalities</option>
          </select>
        </div>
        <div class="fg">
          <label>Pax Type</label>
          <select id="filterPaxType">
            <option value="">All types</option>
          </select>
        </div>
        <div class="fg">
          <label>Bags (min–max)</label>
          <div class="date-range">
            <input id="filterMinBags" type="number" min="0" placeholder="Min">
            <span class="date-sep">–</span>
            <input id="filterMaxBags" type="number" min="0" placeholder="Max">
          </div>
        </div>
        <div class="fg">
          <label>Weight kg (min–max)</label>
          <div class="date-range">
            <input id="filterMinWeight" type="number" min="0" step="0.1" placeholder="Min">
            <span class="date-sep">–</span>
            <input id="filterMaxWeight" type="number" min="0" step="0.1" placeholder="Max">
          </div>
        </div>
        <div class="fg">
          <label>Max results</label>
          <select id="filterLimit">
            <option value="100">100</option>
            <option value="250">250</option>
            <option value="500" selected>500</option>
            <option value="1000">1000</option>
            <option value="2000">2000</option>
          </select>
        </div>
      </div>
    </div>

    <div class="toolbar">
      <div class="toolbar-left">
        <div class="status" id="passengerStatus"></div>
      </div>
      <div class="flex items-center gap-8">
        <button type="button" id="exportCsv" class="btn sm">Export CSV</button>
      </div>
    </div>

    <div class="table-wrap">
      <table id="passengerTable">
        <thead><tr>
          <th class="sortable" data-col="display_name">Passenger <span class="sort-icon"></span></th>
          <th class="sortable" data-col="passport_number">Passport <span class="sort-icon"></span></th>
          <th>Contact</th>
          <th class="sortable" data-col="flight_number">Flight <span class="sort-icon"></span></th>
          <th class="sortable" data-col="flight_date">Date <span class="sort-icon"></span></th>
          <th class="sortable" data-col="pnr">PNR <span class="sort-icon"></span></th>
          <th>Route</th>
          <th class="sortable" data-col="cabin_class">Cabin <span class="sort-icon"></span></th>
          <th class="sortable" data-col="airline_code">Airline <span class="sort-icon"></span></th>
          <th>Source</th>
        </tr></thead>
        <tbody id="passengerRows"></tbody>
      </table>
    </div>
    <div id="paxPagination" class="pagination"></div>
  </section>

</main>

<!-- History Drawer -->
<div class="overlay" id="drawerOverlay"></div>
<aside class="drawer" id="historyDrawer">
  <div class="drawer-head">
    <div>
      <h2 id="historyTitle">Passenger History</h2>
      <div class="sub" id="historySubtitle"></div>
    </div>
    <button class="btn ghost btn-icon" id="closeHistory">✕</button>
  </div>
  <div class="drawer-body" id="historyBody"></div>
</aside>

<div class="toast" id="toast"></div>

<script>
  /* ── State ────────────────────────────────── */
  const state = {
    blacklist: [],
    passengers: [],
    alerts: [],
    meta: {},
    paxSort: { col: 'flight_date', dir: 'desc' },
    blSort: { col: 'updated_at', dir: 'desc' },
    paxPage: 1,
    paxPageSize: 100,
  };

  /* ── Helpers ──────────────────────────────── */
  const $ = id => document.getElementById(id);
  const esc = v => String(v ?? '').replace(/[&<>"']/g, c => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
  const dash = v => v ? esc(v) : '<span class="text-muted">—</span>';

  function toast(msg, type = '') {
    const el = $('toast');
    el.textContent = msg;
    el.className = 'toast show' + (type ? ' ' + type : '');
    clearTimeout(el._t);
    el._t = setTimeout(() => el.classList.remove('show'), 3000);
  }

  async function api(path, opts = {}) {
    const r = await fetch(path, { headers: { 'Content-Type': 'application/json' }, ...opts });
    const data = await r.json().catch(() => ({}));
    if (!r.ok) throw new Error(data.error || r.statusText);
    return data;
  }

  /* ── View routing ─────────────────────────── */
  function showView(view) {
    document.querySelectorAll('.tab').forEach(t => t.classList.toggle('active', t.dataset.view === view));
    document.querySelectorAll('.view').forEach(el => el.classList.toggle('active', el.id === `view-${view}`));
    if (view === 'blacklist') loadBlacklist();
    if (view === 'alerts') loadAlerts();
    if (view === 'passengers') { loadMeta(); loadPassengers(); }
  }

  /* ── Header stats ─────────────────────────── */
  async function loadStats() {
    try {
      const d = await api('/api/stats');
      $('headerStats').innerHTML = `
        <div class="stat-pill"><div class="stat-dot" style="background:var(--accent)"></div>
          <span>Passengers: <strong>${d.passenger_count.toLocaleString()}</strong></span></div>
        <div class="stat-pill"><div class="stat-dot" style="background:var(--red)"></div>
          <span>Blacklist: <strong>${d.blacklist_count.toLocaleString()}</strong></span></div>
      `;
    } catch(e) {}
  }

  /* ── Meta (dropdown values) ───────────────── */
  async function loadMeta() {
    if (Object.keys(state.meta).length) return;
    try {
      const d = await api('/api/meta');
      state.meta = d;
      const fill = (selId, arr) => {
        const sel = $(selId);
        const first = sel.options[0].outerHTML;
        sel.innerHTML = first + arr.map(v => `<option value="${esc(v)}">${esc(v)}</option>`).join('');
      };
      fill('filterAirline', d.airline_codes || []);
      fill('filterManifestType', d.manifest_types || []);
      fill('filterOrigin', d.origins || []);
      fill('filterDestination', d.destinations || []);
      fill('filterCabin', d.cabin_classes || []);
      fill('filterNationality', d.nationalities || []);
      fill('filterPaxType', d.passenger_types || []);
    } catch(e) {}
  }

  /* ══════════════════ BLACKLIST ══════════════════ */

  function resetBlacklistForm() {
    ['blacklistId','passport','mobile_no','email_id','name','notes'].forEach(id => $(id).value = '');
    $('saveBlacklistLabel').textContent = 'Save Entry';
  }

  function renderBlacklist() {
    const q = ($('blSearch').value || '').toLowerCase();
    let rows = state.blacklist;
    if (q) {
      rows = rows.filter(r =>
        [r.passport, r.mobile_no, r.email_id, r.name, r.notes]
          .some(v => (v || '').toLowerCase().includes(q))
      );
    }
    // sort
    const { col, dir } = state.blSort;
    rows = [...rows].sort((a, b) => {
      const av = (a[col] || ''), bv = (b[col] || '');
      return dir === 'asc' ? av.localeCompare(bv) : bv.localeCompare(av);
    });

    $('blacklistRows').innerHTML = rows.length ? rows.map(row => `
      <tr>
        <td class="mono">${dash(row.passport)}</td>
        <td>${dash(row.mobile_no)}</td>
        <td>${dash(row.email_id)}</td>
        <td class="fw-bold">${dash(row.name)}</td>
        <td class="text-sm text-muted">${dash(row.notes)}</td>
        <td class="text-sm text-muted">${dash((row.updated_at || '').slice(0,16).replace('T',' '))}</td>
        <td>
          <div class="flex gap-8">
            <button class="btn sm" data-edit="${esc(row.id)}">Edit</button>
            <button class="btn sm danger" data-delete="${esc(row.id)}">Delete</button>
          </div>
        </td>
      </tr>
    `).join('') : '<tr><td colspan="7"><div class="empty"><div class="empty-icon">🚫</div>No blacklist records.</div></td></tr>';

    $('blacklistStatus').innerHTML = `<strong>${rows.length}</strong> of <strong>${state.blacklist.length}</strong> record(s)`;
    updateSortHeaders('blacklistTable', state.blSort);
  }

  async function loadBlacklist() {
    $('blacklistStatus').textContent = 'Loading…';
    const data = await api('/api/blacklist');
    state.blacklist = data.items;
    renderBlacklist();
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
    $('saveBlacklistLabel').textContent = 'Saving…';
    try {
      await api(id ? `/api/blacklist/${encodeURIComponent(id)}` : '/api/blacklist', {
        method: id ? 'PUT' : 'POST', body,
      });
      toast(id ? 'Entry updated.' : 'Entry added.', 'ok');
      resetBlacklistForm();
      await loadBlacklist();
      await loadStats();
    } catch(e) {
      toast(e.message, 'err');
      $('saveBlacklistLabel').textContent = 'Save Entry';
    }
  }

  function editBlacklist(id) {
    const row = state.blacklist.find(r => r.id === id);
    if (!row) return;
    ['id','passport','mobile_no','email_id','name','notes'].forEach(f => {
      $(f === 'id' ? 'blacklistId' : f).value = row[f] || '';
    });
    $('saveBlacklistLabel').textContent = 'Update Entry';
    $('passport').focus();
    window.scrollTo({ top: 0, behavior: 'smooth' });
  }

  async function deleteBlacklist(id) {
    if (!confirm('Delete this blacklist entry?')) return;
    try {
      await api(`/api/blacklist/${encodeURIComponent(id)}`, { method: 'DELETE' });
      toast('Entry deleted.', 'ok');
      await loadBlacklist();
      await loadStats();
    } catch(e) { toast(e.message, 'err'); }
  }

  /* ══════════════════ ALERTS ══════════════════ */

  async function loadAlerts() {
    $('alertStatus').textContent = 'Loading…';
    const days = $('alertDays').value;
    try {
      const data = await api(`/api/alerts${days ? `?days=${encodeURIComponent(days)}` : ''}`);
      state.alerts = data.items;
      renderAlerts();
    } catch(e) {
      $('alertStatus').textContent = e.message;
    }
  }

  function renderAlerts() {
    const matchFilter = $('alertMatchField').value;
    const q = ($('alertSearch').value || '').toLowerCase();

    let alerts = state.alerts;
    if (matchFilter) alerts = alerts.filter(a => a.matched_fields.includes(matchFilter));
    if (q) alerts = alerts.filter(a => {
      const p = a.passenger;
      return [p.display_name, p.passport_number, p.flight_number, p.pnr, p.email, p.phone]
        .some(v => (v || '').toLowerCase().includes(q));
    });

    const activeFilters = [matchFilter, q].filter(Boolean).length;
    const badge = $('alertFilterBadge');
    badge.style.display = activeFilters ? '' : 'none';
    badge.textContent = `${activeFilters} active`;

    $('alertStatus').innerHTML = `<strong>${alerts.length}</strong> alert(s)${activeFilters ? ' (filtered)' : ''}`;

    const groups = {};
    alerts.forEach(a => groups[a.day] = [...(groups[a.day] || []), a]);

    $('alertGroups').innerHTML = Object.keys(groups).length
      ? Object.keys(groups).sort((a,b) => b.localeCompare(a)).map(day => `
        <div class="alert-day">
          <div class="alert-day-head" data-day="${esc(day)}">
            <div class="flex items-center gap-8">
              <span>${esc(day)}</span>
              <span class="chip red">${groups[day].length} match${groups[day].length !== 1 ? 'es' : ''}</span>
            </div>
            <span class="toggle-icon">▼</span>
          </div>
          <div class="alert-day-body">
            ${groups[day].map(renderAlertCard).join('')}
          </div>
        </div>
      `).join('')
      : '<div class="empty"><div class="empty-icon">✅</div>No alerts for this range.</div>';
  }

  function renderAlertCard(alert) {
    const p = alert.passenger;
    const b = alert.blacklist;
    const fieldChips = alert.matched_fields.map(f => `<span class="chip red">${esc(f)}</span>`).join('');
    return `
      <div class="alert-card">
        <div>
          <div class="alert-name">${dash(p.display_name)}</div>
          <div class="mono text-sm text-muted mt-2">${dash(p.passport_number)}</div>
          <div class="chips">${fieldChips}</div>
        </div>
        <div>
          <div class="fw-bold">${dash(p.flight_number)}</div>
          <div class="alert-sub">${dash(p.origin)} → ${dash(p.destination)}</div>
          <div class="alert-sub">PNR <span class="mono">${dash(p.pnr)}</span></div>
          <div class="alert-sub mt-2">${dash(p.email)} | ${dash(p.phone)}</div>
          <div class="chips mt-2">
            <span class="chip ${p.manifest_type === 'pre_departure' ? 'amber' : 'blue'}">${esc(p.manifest_type || '-')}</span>
            ${p.airline_code ? `<span class="chip neutral">${esc(p.airline_code)}</span>` : ''}
          </div>
        </div>
        <div>
          <div class="text-muted text-xs" style="text-transform:uppercase;letter-spacing:.05em;margin-bottom:4px">Blacklist Record</div>
          <div class="fw-bold">${dash(b.name)}</div>
          <div class="alert-sub">${dash(b.email_id)}</div>
          <div class="mono text-sm alert-sub">${dash(b.passport)}</div>
          <div class="alert-sub">${dash(b.mobile_no)}</div>
          ${b.notes ? `<div class="text-sm text-muted mt-2">${esc(b.notes)}</div>` : ''}
        </div>
        <div>
          <button type="button" class="btn sm" data-passport="${esc(p.passport_number || '')}">History</button>
        </div>
      </div>
    `;
  }

  /* ══════════════════ PASSENGERS ══════════════════ */

  function getPaxParams() {
    const p = new URLSearchParams();
    const add = (key, id) => { const v = $(id).value; if (v) p.set(key, v); };
    add('q', 'passengerQuery');
    add('flight_date', 'flightDate');
    add('flight_date_from', 'flightDateFrom');
    add('flight_date_to', 'flightDateTo');
    add('flight_number', 'filterFlightNo');
    add('airline_code', 'filterAirline');
    add('manifest_type', 'filterManifestType');
    add('origin', 'filterOrigin');
    add('destination', 'filterDestination');
    add('cabin_class', 'filterCabin');
    add('nationality', 'filterNationality');
    add('passenger_type', 'filterPaxType');
    add('min_bags', 'filterMinBags');
    add('max_bags', 'filterMaxBags');
    add('min_weight', 'filterMinWeight');
    add('max_weight', 'filterMaxWeight');
    add('limit', 'filterLimit');
    return p;
  }

  function countActiveFilters() {
    const ids = ['passengerQuery','flightDateFrom','flightDateTo',
      'filterFlightNo','filterAirline','filterManifestType','filterOrigin',
      'filterDestination','filterCabin','filterNationality','filterPaxType',
      'filterMinBags','filterMaxBags','filterMinWeight','filterMaxWeight'];
    return ids.filter(id => $(id).value).length;
  }

  function resetPaxFilters() {
    ['passengerQuery','flightDateFrom','flightDateTo',
     'filterFlightNo','filterAirline','filterManifestType','filterOrigin',
     'filterDestination','filterCabin','filterNationality','filterPaxType',
     'filterMinBags','filterMaxBags','filterMinWeight','filterMaxWeight'].forEach(id => $(id).value = '');
    $('filterLimit').value = '500';
    $('paxFilterBadge').style.display = 'none';
    state.passengers = [];
    renderPassengers();
  }

  function resetAlertFilters() {
    $('alertDays').value = '7';
    $('alertMatchField').value = '';
    $('alertSearch').value = '';
    loadAlerts();
  }

  async function loadPassengers() {
    $('passengerStatus').textContent = 'Searching…';
    state.paxPage = 1;
    try {
      const data = await api(`/api/passengers?${getPaxParams()}`);
      state.passengers = data.items;
      const active = countActiveFilters();
      const badge = $('paxFilterBadge');
      badge.style.display = active ? '' : 'none';
      badge.textContent = `${active} filter${active !== 1 ? 's' : ''} active`;
      renderPassengers();
    } catch(e) {
      $('passengerStatus').textContent = e.message;
    }
  }

  function renderPassengers() {
    let rows = [...state.passengers];

    // client-side sort
    const { col, dir } = state.paxSort;
    rows.sort((a, b) => {
      const av = (a[col] || ''), bv = (b[col] || '');
      return dir === 'asc' ? av.localeCompare(bv) : bv.localeCompare(av);
    });

    // pagination
    const total = rows.length;
    const pages = Math.max(1, Math.ceil(total / state.paxPageSize));
    state.paxPage = Math.min(state.paxPage, pages);
    const start = (state.paxPage - 1) * state.paxPageSize;
    const pageRows = rows.slice(start, start + state.paxPageSize);

    $('passengerStatus').innerHTML =
      `<strong>${total}</strong> passenger(s)` +
      (total > state.paxPageSize ? `, showing ${start+1}–${Math.min(start+state.paxPageSize, total)}` : '');

    $('passengerRows').innerHTML = pageRows.length ? pageRows.map(row => `
      <tr class="clickable" data-passport="${esc(row.passport_number || '')}">
        <td>
          <div class="fw-bold">${dash(row.display_name)}</div>
          <div class="text-xs text-muted mt-2">${dash(row.nationality)}${row.gender ? ' · ' + esc(row.gender) : ''}</div>
        </td>
        <td class="mono">${dash(row.passport_number)}</td>
        <td>
          <div>${dash(row.phone)}</div>
          <div class="text-xs text-muted mt-2">${dash(row.email)}</div>
        </td>
        <td class="fw-bold">${dash(row.flight_number)}</td>
        <td>${dash(row.flight_date)}</td>
        <td class="mono">${dash(row.pnr)}</td>
        <td><span title="${esc(row.origin || '')} to ${esc(row.destination || '')}">${dash(row.origin)} → ${dash(row.destination)}</span></td>
        <td>
          ${row.cabin_class ? `<span class="chip ${cabinChipClass(row.cabin_class)}">${esc(row.cabin_class)}</span>` : dash(null)}
          ${row.seat_number ? `<div class="text-xs text-muted mt-2">Seat ${esc(row.seat_number)}</div>` : ''}
        </td>
        <td>
          ${row.airline_code ? `<span class="chip neutral">${esc(row.airline_code)}</span>` : dash(null)}
          <div class="text-xs text-muted mt-2">${row.manifest_type ? `<span class="chip ${row.manifest_type === 'pre_departure' ? 'amber' : 'blue'}" style="font-size:10px">${esc(row.manifest_type)}</span>` : ''}</div>
        </td>
        <td class="text-xs text-muted">${dash(row.attachment_file_name)}</td>
      </tr>
    `).join('') : '<tr><td colspan="10"><div class="empty"><div class="empty-icon">🔍</div>No passengers found. Adjust filters and search.</div></td></tr>';

    // pagination controls
    if (pages > 1) {
      let paginationHtml = '';
      if (state.paxPage > 1) paginationHtml += `<button class="btn sm" data-page="${state.paxPage - 1}">← Prev</button>`;
      paginationHtml += `<span class="page-info">Page ${state.paxPage} of ${pages}</span>`;
      if (state.paxPage < pages) paginationHtml += `<button class="btn sm" data-page="${state.paxPage + 1}">Next →</button>`;
      $('paxPagination').innerHTML = paginationHtml;
    } else {
      $('paxPagination').innerHTML = '';
    }

    updateSortHeaders('passengerTable', state.paxSort);
  }

  function cabinChipClass(cabin) {
    const c = (cabin || '').toLowerCase();
    if (c.includes('first') || c.includes('f')) return 'purple';
    if (c.includes('business') || c.includes('c')) return 'amber';
    return 'neutral';
  }

  /* ══════════════════ SORT ══════════════════ */

  function updateSortHeaders(tableId, sortState) {
    const table = $(tableId);
    if (!table) return;
    table.querySelectorAll('thead th.sortable').forEach(th => {
      th.classList.remove('asc', 'desc');
      if (th.dataset.col === sortState.col) th.classList.add(sortState.dir);
    });
  }

  function handleSortClick(event, sortState, renderFn) {
    const th = event.target.closest('th.sortable');
    if (!th) return;
    const col = th.dataset.col;
    if (sortState.col === col) {
      sortState.dir = sortState.dir === 'asc' ? 'desc' : 'asc';
    } else {
      sortState.col = col;
      sortState.dir = 'asc';
    }
    renderFn();
  }

  /* ══════════════════ HISTORY DRAWER ══════════════════ */

  async function openHistory(passport) {
    if (!passport) return;
    $('drawerOverlay').classList.add('open');
    $('historyDrawer').classList.add('open');
    $('historyTitle').textContent = 'Passenger History';
    $('historySubtitle').textContent = passport;
    $('historyBody').innerHTML = '<div class="empty">Loading…</div>';
    try {
      const data = await api(`/api/passengers/history/${encodeURIComponent(passport)}`);
      $('historyTitle').textContent = data.passenger_name || 'Passenger History';
      $('historySubtitle').textContent = `${passport} · ${data.items.length} flight(s)`;
      $('historyBody').innerHTML = data.items.length ? data.items.map(row => `
        <div class="history-card">
          <div class="history-card-head">
            <div class="flex items-center gap-8">
              <span class="fw-bold">${esc(row.flight_number || '—')}</span>
              <span class="text-muted text-sm">${esc(row.flight_date || '')}</span>
              ${row.manifest_type ? `<span class="chip ${row.manifest_type === 'pre_departure' ? 'amber' : 'blue'}" style="font-size:10px">${esc(row.manifest_type)}</span>` : ''}
            </div>
            <span class="text-sm text-muted">${esc(row.origin || '')} → ${esc(row.destination || '')}</span>
          </div>
          <div class="history-card-body">
            <div class="kv-cell"><div class="kv-label">PNR</div><span class="mono">${esc(row.pnr || '—')}</span></div>
            <div class="kv-cell"><div class="kv-label">Seat</div>${esc(row.seat_number || '—')}</div>
            <div class="kv-cell"><div class="kv-label">Cabin</div>${esc(row.cabin_class || '—')}</div>
            <div class="kv-cell"><div class="kv-label">Ticket</div><span class="mono text-sm">${esc(row.ticket_number || '—')}</span></div>
            <div class="kv-cell"><div class="kv-label">Bags</div>${esc(row.no_of_bags != null ? row.no_of_bags : '—')} ${row.baggage_weight ? '· '+esc(row.baggage_weight) : ''}</div>
            <div class="kv-cell"><div class="kv-label">Pax Type</div>${esc(row.passenger_type || '—')}</div>
            <div class="kv-cell"><div class="kv-label">Phone</div>${esc(row.phone || '—')}</div>
            <div class="kv-cell"><div class="kv-label">Email</div>${esc(row.email || '—')}</div>
            <div class="kv-cell"><div class="kv-label">Payment</div>${esc(row.payment_mode || '—')}</div>
            <div class="kv-cell"><div class="kv-label">Source</div><span class="text-sm text-muted">${esc(row.attachment_file_name || '—')}</span></div>
          </div>
        </div>
      `).join('') : '<div class="empty"><div class="empty-icon">📭</div>No history found.</div>';
    } catch(e) {
      $('historyBody').innerHTML = `<div class="empty" style="color:var(--red)">${esc(e.message)}</div>`;
    }
  }

  function closeHistory() {
    $('drawerOverlay').classList.remove('open');
    $('historyDrawer').classList.remove('open');
  }

  /* ══════════════════ CSV EXPORT ══════════════════ */

  function exportCsv() {
    if (!state.passengers.length) { toast('No data to export.', 'err'); return; }
    const cols = ['display_name','passport_number','nationality','gender','phone','email',
      'flight_number','flight_date','pnr','origin','destination','cabin_class','seat_number',
      'airline_code','manifest_type','no_of_bags','baggage_weight','ticket_number','attachment_file_name'];
    const header = cols.join(',');
    const csvEsc = v => `"${String(v ?? '').replace(/"/g, '""')}"`;
    const rows = state.passengers.map(r => cols.map(c => csvEsc(r[c])).join(','));
    const blob = new Blob([header + '\n' + rows.join('\n')], { type: 'text/csv' });
    const a = document.createElement('a');
    a.href = URL.createObjectURL(blob);
    a.download = `manifest-export-${new Date().toISOString().slice(0,10)}.csv`;
    a.click();
    toast('CSV exported.', 'ok');
  }

  /* ══════════════════ EVENT WIRING ══════════════════ */

  document.querySelectorAll('.tab').forEach(t => t.addEventListener('click', () => showView(t.dataset.view)));

  $('blacklistForm').addEventListener('submit', saveBlacklist);
  $('resetBlacklist').addEventListener('click', resetBlacklistForm);
  $('refreshBlacklist').addEventListener('click', loadBlacklist);
  $('blSearch').addEventListener('input', renderBlacklist);

  $('refreshAlerts').addEventListener('click', loadAlerts);
  $('alertDays').addEventListener('change', loadAlerts);
  $('alertMatchField').addEventListener('change', renderAlerts);
  $('alertSearch').addEventListener('input', renderAlerts);
  $('resetAlertFilters').addEventListener('click', resetAlertFilters);
  $('alertExpandAll').addEventListener('click', () => {
    document.querySelectorAll('.alert-day-body').forEach(b => b.classList.remove('collapsed'));
  });
  $('alertCollapseAll').addEventListener('click', () => {
    document.querySelectorAll('.alert-day-body').forEach(b => b.classList.add('collapsed'));
  });

  $('searchPassengers').addEventListener('click', loadPassengers);
  $('resetPaxFilters').addEventListener('click', resetPaxFilters);
  $('exportCsv').addEventListener('click', exportCsv);
  $('passengerQuery').addEventListener('keydown', e => { if (e.key === 'Enter') loadPassengers(); });

  $('closeHistory').addEventListener('click', closeHistory);
  $('drawerOverlay').addEventListener('click', closeHistory);

  // delegated: edit/delete blacklist, open history, alert day toggle, table sort, pagination
  document.body.addEventListener('click', event => {
    const t = event.target;
    const editId = t.dataset?.edit;
    const deleteId = t.dataset?.delete;
    const passport = t.dataset?.passport || t.closest('tr[data-passport]')?.dataset.passport;
    const day = t.closest('.alert-day-head')?.dataset.day;
    const page = t.dataset?.page;

    if (editId) { editBlacklist(editId); return; }
    if (deleteId) { deleteBlacklist(deleteId); return; }
    if (passport) { openHistory(passport); return; }
    if (page) { state.paxPage = parseInt(page); renderPassengers(); return; }
    if (day != null) {
      const body = t.closest('.alert-day').querySelector('.alert-day-body');
      body.classList.toggle('collapsed');
      t.closest('.alert-day-head').querySelector('.toggle-icon').textContent =
        body.classList.contains('collapsed') ? '▶' : '▼';
      return;
    }
  });

  // table header sort
  $('blacklistTable').querySelector('thead').addEventListener('click', e =>
    handleSortClick(e, state.blSort, renderBlacklist));
  $('passengerTable').querySelector('thead').addEventListener('click', e =>
    handleSortClick(e, state.paxSort, renderPassengers));

  /* ── Boot ──────────────────────────── */
  loadStats();
  loadBlacklist().catch(e => $('blacklistStatus').textContent = e.message);
</script>
</body>
</html>"""


class ClientInterfaceHandler(BaseHTTPRequestHandler):
    server_version = "ManifestWatch/2.0"

    def log_message(self, fmt: str, *args) -> None:
        logger.info("{} - {}", self.address_string(), fmt % args)

    def do_GET(self) -> None:
        parsed = urlparse(self.path)
        try:
            if parsed.path == "/":
                self._send_html(HTML)
            elif parsed.path == "/api/stats":
                self._send_json(storage.get_stats())
            elif parsed.path == "/api/meta":
                self._send_json(storage.list_meta_values())
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

                def _p(key: str) -> str | None:
                    return params.get(key, [""])[0] or None

                def _int(key: str) -> int | None:
                    v = _p(key)
                    return int(v) if v else None

                def _float(key: str) -> float | None:
                    v = _p(key)
                    return float(v) if v else None

                items = storage.list_manifest_passengers(
                    query=_p("q"),
                    flight_date_from=_p("flight_date_from"),
                    flight_date_to=_p("flight_date_to"),
                    airline_code=_p("airline_code"),
                    manifest_type=_p("manifest_type"),
                    origin=_p("origin"),
                    destination=_p("destination"),
                    flight_number=_p("flight_number"),
                    cabin_class=_p("cabin_class"),
                    nationality=_p("nationality"),
                    passenger_type=_p("passenger_type"),
                    min_bags=_int("min_bags"),
                    max_bags=_int("max_bags"),
                    min_weight=_float("min_weight"),
                    max_weight=_float("max_weight"),
                    limit=int(_p("limit") or 500),
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
