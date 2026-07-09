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
  @import url('https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600&display=swap');
  *{box-sizing:border-box;margin:0;padding:0}
  body{font-family:'Inter',system-ui,sans-serif;background:#f5f5f7;
       min-height:100vh;display:flex;align-items:center;justify-content:center}
  .wrap{width:100%;max-width:400px;padding:16px}
  .card{background:#fff;border-radius:16px;padding:40px 36px;
        box-shadow:0 1px 3px rgba(0,0,0,.08),0 8px 32px rgba(0,0,0,.06)}
  .logo{display:flex;align-items:center;gap:10px;margin-bottom:28px}
  .logo-icon{width:36px;height:36px;background:#18181b;border-radius:9px;
             display:flex;align-items:center;justify-content:center}
  .logo-icon svg{width:20px;height:20px}
  .logo-name{font-size:17px;font-weight:600;color:#18181b;letter-spacing:-.3px}
  h1{font-size:22px;font-weight:600;color:#18181b;letter-spacing:-.4px;margin-bottom:6px}
  .sub{font-size:14px;color:#71717a;margin-bottom:28px;line-height:1.5}
  label{display:block;font-size:12px;font-weight:500;color:#52525b;
        margin-bottom:5px;margin-top:16px;letter-spacing:.01em}
  .input-wrap{position:relative}
  input{width:100%;background:#fafafa;border:1.5px solid #e4e4e7;border-radius:9px;
        padding:10px 14px;color:#18181b;font-size:14px;font-family:inherit;
        outline:none;transition:border-color .15s,box-shadow .15s}
  input::placeholder{color:#a1a1aa}
  input:focus{border-color:#18181b;background:#fff;box-shadow:0 0 0 3px rgba(24,24,27,.07)}
  .eye{position:absolute;right:12px;top:50%;transform:translateY(-50%);
       background:none;border:none;cursor:pointer;color:#a1a1aa;padding:2px;line-height:0}
  .eye:hover{color:#52525b}
  button.primary{margin-top:24px;width:100%;background:#18181b;color:#fff;border:none;
         border-radius:9px;padding:11px;font-size:14px;font-weight:500;font-family:inherit;
         cursor:pointer;transition:background .15s,transform .1s;letter-spacing:.01em}
  button.primary:hover{background:#27272a}
  button.primary:active{transform:scale(.99)}
  button.primary:disabled{background:#d4d4d8;cursor:not-allowed;transform:none}
  .divider{display:flex;align-items:center;gap:10px;margin:20px 0 0}
  .divider span{flex:1;height:1px;background:#f0f0f0}
  .divider p{font-size:12px;color:#a1a1aa}
  .msg{margin-top:14px;font-size:13px;text-align:center;min-height:20px;line-height:1.5}
  .msg.err{color:#ef4444}
  .msg.ok{color:#16a34a}
  .spinner{display:inline-block;width:14px;height:14px;border:2px solid rgba(255,255,255,.3);
           border-top-color:#fff;border-radius:50%;animation:spin .6s linear infinite;
           vertical-align:middle;margin-right:6px}
  @keyframes spin{to{transform:rotate(360deg)}}
</style>
</head>
<body>
<div class="wrap">
<div class="card">
  <div class="logo">
    <div class="logo-icon">
      <svg viewBox="0 0 24 24" fill="none" stroke="#fff" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
        <path d="M13 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V9z"/><polyline points="13 2 13 9 20 9"/>
      </svg>
    </div>
    <span class="logo-name">Mail Agent</span>
  </div>
  <h1>Connect to Votum</h1>
  <p class="sub">Sign in once to link your inbox with your Votum workspace.</p>
  <label for="email">Email address</label>
  <input id="email" type="email" autocomplete="email" placeholder="you@example.com">
  <label for="password">Password</label>
  <div class="input-wrap">
    <input id="password" type="password" autocomplete="current-password" placeholder="Enter your password">
    <button class="eye" type="button" onclick="togglePw(this)" tabindex="-1" aria-label="Show password">
      <svg id="eye-icon" width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
        <path d="M1 12s4-8 11-8 11 8 11 8-4 8-11 8-11-8-11-8z"/><circle cx="12" cy="12" r="3"/>
      </svg>
    </button>
  </div>
  <button class="primary" id="btn" onclick="login()">Sign in</button>
  <div class="msg" id="msg"></div>
</div>
</div>
<script>
function togglePw(btn) {
  const inp = document.getElementById('password');
  const showing = inp.type === 'text';
  inp.type = showing ? 'password' : 'text';
  btn.querySelector('svg').innerHTML = showing
    ? '<path d="M1 12s4-8 11-8 11 8 11 8-4 8-11 8-11-8-11-8z"/><circle cx="12" cy="12" r="3"/>'
    : '<path d="M17.94 17.94A10.07 10.07 0 0 1 12 20c-7 0-11-8-11-8a18.45 18.45 0 0 1 5.06-5.94"/>'
      + '<path d="M9.9 4.24A9.12 9.12 0 0 1 12 4c7 0 11 8 11 8a18.5 18.5 0 0 1-2.16 3.19"/>'
      + '<line x1="1" y1="1" x2="23" y2="23"/>';
}
async function login() {
  const btn = document.getElementById('btn');
  const msg = document.getElementById('msg');
  msg.className = 'msg'; msg.textContent = '';
  btn.disabled = true;
  btn.innerHTML = '<span class="spinner"></span>Signing in…';
  const email = document.getElementById('email').value.trim();
  const password = document.getElementById('password').value;
  if (!email || !password) {
    msg.className = 'msg err'; msg.textContent = 'Email and password are required.';
    btn.disabled = false; btn.textContent = 'Sign in'; return;
  }
  try {
    const res = await fetch('/api/setup', {
      method: 'POST',
      headers: {'Content-Type':'application/json'},
      body: JSON.stringify({email, password})
    });
    const data = await res.json();
    if (!res.ok) {
      msg.className = 'msg err'; msg.textContent = data.error || 'Sign in failed.';
      btn.disabled = false; btn.textContent = 'Sign in'; return;
    }
    btn.textContent = '✓ Connected';
    msg.className = 'msg ok';
    msg.textContent = 'Workspace linked. Mail Agent will continue automatically.';
  } catch(e) {
    msg.className = 'msg err'; msg.textContent = 'Network error — is the agent running?';
    btn.disabled = false; btn.textContent = 'Sign in';
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
