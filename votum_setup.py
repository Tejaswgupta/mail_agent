"""First-run wizard: opens a local browser login page to collect Votum credentials."""

import json
import re
import threading
import webbrowser
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path
from urllib.parse import urlparse

import requests
from loguru import logger

from config import settings

_PORT = 9877
_DONE = threading.Event()
_ERROR: str | None = None

_HTML = """<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>Votum Setup</title>
<style>
  *{box-sizing:border-box;margin:0;padding:0}
  body{font-family:-apple-system,BlinkMacSystemFont,'Segoe UI',sans-serif;
       background:#0f1117;color:#e2e8f0;min-height:100vh;display:flex;
       align-items:center;justify-content:center}
  .card{background:#1a1f2e;border:1px solid #2d3548;border-radius:12px;
        padding:40px;width:100%;max-width:420px}
  h1{font-size:22px;font-weight:600;margin-bottom:6px}
  p{font-size:13px;color:#8892a4;margin-bottom:28px}
  label{display:block;font-size:12px;font-weight:500;color:#94a3b8;
        margin-bottom:6px;margin-top:18px}
  input{width:100%;background:#111827;border:1px solid #2d3548;border-radius:8px;
        padding:10px 14px;color:#e2e8f0;font-size:14px;outline:none}
  input:focus{border-color:#6366f1}
  button{margin-top:24px;width:100%;background:#6366f1;color:#fff;border:none;
         border-radius:8px;padding:11px;font-size:15px;font-weight:600;
         cursor:pointer;transition:background .15s}
  button:hover{background:#4f52d9}
  button:disabled{background:#3d3f6e;cursor:not-allowed}
  .err{margin-top:14px;font-size:13px;color:#f87171;text-align:center;
       min-height:20px}
  .ok{margin-top:14px;font-size:13px;color:#4ade80;text-align:center}
</style>
</head>
<body>
<div class="card">
  <h1>Votum Setup</h1>
  <p>Sign in once to link Mail Agent with your Votum workspace.</p>
  <label>Email</label>
  <input id="email" type="email" autocomplete="email" placeholder="you@example.com">
  <label>Password</label>
  <input id="password" type="password" autocomplete="current-password" placeholder="••••••••">
  <button id="btn" onclick="login()">Connect to Votum</button>
  <div class="err" id="err"></div>
</div>
<script>
async function login() {
  const btn = document.getElementById('btn');
  const errEl = document.getElementById('err');
  errEl.textContent = '';
  btn.disabled = true;
  btn.textContent = 'Signing in…';
  const email = document.getElementById('email').value.trim();
  const password = document.getElementById('password').value;
  if (!email || !password) {
    errEl.textContent = 'Email and password are required.';
    btn.disabled = false; btn.textContent = 'Connect to Votum'; return;
  }
  try {
    const res = await fetch('/api/setup', {
      method: 'POST',
      headers: {'Content-Type':'application/json'},
      body: JSON.stringify({email, password})
    });
    const data = await res.json();
    if (!res.ok) { errEl.textContent = data.error || 'Login failed.'; btn.disabled=false; btn.textContent='Connect to Votum'; return; }
    btn.textContent = '✓ Connected! You can close this window.';
    document.getElementById('err').className = 'ok';
    document.getElementById('err').textContent = 'Credentials saved. Mail Agent will continue automatically.';
  } catch(e) {
    errEl.textContent = 'Network error — is the agent running?';
    btn.disabled=false; btn.textContent='Connect to Votum';
  }
}
document.addEventListener('keydown', e => { if (e.key === 'Enter') login(); });
</script>
</body>
</html>"""


class _Handler(BaseHTTPRequestHandler):
    def log_message(self, fmt, *args):
        pass

    def do_GET(self):
        if urlparse(self.path).path == "/":
            self.send_response(200)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.end_headers()
            self.wfile.write(_HTML.encode())

    def do_POST(self):
        global _ERROR
        if urlparse(self.path).path != "/api/setup":
            self.send_response(404)
            self.end_headers()
            return

        length = int(self.headers.get("Content-Length", 0))
        body = json.loads(self.rfile.read(length))
        email = body.get("email", "").strip()
        password = body.get("password", "")

        try:
            user_id, access_token, workspace_id = _do_login(email, password)
            _write_env(user_id, access_token, workspace_id)
            self._json({"ok": True})
            _DONE.set()
        except Exception as exc:
            _ERROR = str(exc)
            self._json({"error": str(exc)}, 400)

    def _json(self, data, status=200):
        body = json.dumps(data).encode()
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)


def _do_login(email: str, password: str) -> tuple[str, str, str]:
    supabase_url = settings.VOTUM_SUPABASE_URL.rstrip("/")
    anon_key = settings.VOTUM_SUPABASE_KEY

    if not supabase_url or not anon_key:
        raise RuntimeError("VOTUM_SUPABASE_URL and VOTUM_SUPABASE_KEY must be set in .env before setup")

    # Supabase sign-in
    resp = requests.post(
        f"{supabase_url}/auth/v1/token?grant_type=password",
        json={"email": email, "password": password},
        headers={"apikey": anon_key, "Content-Type": "application/json"},
        timeout=15,
    )
    if not resp.ok:
        err = resp.json().get("error_description") or resp.json().get("msg") or "Invalid credentials"
        raise RuntimeError(err)

    data = resp.json()
    user_id = data["user"]["id"]
    access_token = data["access_token"]

    # Fetch workspace_id from votum_users
    row_resp = requests.get(
        f"{supabase_url}/rest/v1/votum_users",
        params={"select": "workspace_id", "id": f"eq.{user_id}", "limit": "1"},
        headers={
            "apikey": anon_key,
            "Authorization": f"Bearer {access_token}",
            "Accept": "application/json",
        },
        timeout=15,
    )
    rows = row_resp.json() if row_resp.ok else []
    workspace_id = (rows[0].get("workspace_id") or "") if rows else ""

    if not workspace_id:
        raise RuntimeError("Could not find a workspace for this account. Make sure you're using a Votum account that belongs to a workspace.")

    return user_id, access_token, workspace_id


def _env_path() -> Path:
    from config import BASE_DIR
    return BASE_DIR / ".env"


def _write_env(user_id: str, access_token: str, workspace_id: str) -> None:
    path = _env_path()
    text = path.read_text(encoding="utf-8") if path.exists() else ""

    def _set(key: str, value: str) -> str:
        nonlocal text
        pattern = rf"^{re.escape(key)}=.*$"
        replacement = f"{key}={value}"
        if re.search(pattern, text, flags=re.MULTILINE):
            return re.sub(pattern, replacement, text, flags=re.MULTILINE)
        return text.rstrip("\n") + f"\n{replacement}\n"

    text = _set("VOTUM_USER_ID", user_id)
    text = _set("VOTUM_WORKSPACE_ID", workspace_id)
    path.write_text(text, encoding="utf-8")
    logger.info(f"Votum credentials saved to {path}")


def run_wizard() -> bool:
    """Open the setup wizard in the browser. Block until complete. Returns True on success."""
    server = HTTPServer(("127.0.0.1", _PORT), _Handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()

    url = f"http://127.0.0.1:{_PORT}/"
    logger.info(f"Votum setup wizard started at {url}")
    webbrowser.open(url)

    _DONE.wait()
    server.shutdown()

    if _ERROR:
        logger.error(f"Votum setup failed: {_ERROR}")
        return False

    # Reload settings so the new values are picked up without restarting
    import importlib
    import config as _config_module
    _config_module.settings = type(_config_module.settings)()

    logger.info("Votum setup complete")
    return True
