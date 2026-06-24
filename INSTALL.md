# Installing & Running the Zoho Mail Agent on Windows
### For non-technical users — no coding experience needed

---

## Two ways to run

| | **Executable (recommended)** | **From source** |
|---|---|---|
| Needs Python installed | No | Yes |
| Needs Chrome installed | No | No |
| Setup time | ~2 minutes | ~15 minutes |
| Who should use this | End users | Developers |

---

## Option A — Run the Executable (recommended)

This is the simplest way. You receive a single file (`mail_agent.exe`) and a settings file. Nothing else needs to be installed.

### What you need
- A Windows 10 or Windows 11 computer
- Your Zoho Mail login credentials
- About 2 minutes

---

### Step 1 — Get the files

You should have received two files:
- `mail_agent.exe`
- `.env.example`

Copy both into a folder, for example: `C:\mail_agent\`

---

### Step 2 — Fill in your settings

1. Find the file called **`.env.example`** in your folder
2. Right-click it → **Open with** → **Notepad**
3. You will see:

```
DB_PATH=mail_agent.db

TELEGRAM_BOT_TOKEN=
TELEGRAM_CHAT_ID=

ZOHO_MAIL_URL=https://mail.zoho.com
POLL_INTERVAL_SECONDS=60
```

4. You do not need to change anything unless you want Telegram alerts:
   - `TELEGRAM_BOT_TOKEN` and `TELEGRAM_CHAT_ID` → fill these in to receive phone notifications. Leave blank to skip.
   - Leave everything else exactly as-is.

5. Click **File → Save As**
6. In the **"Save as type"** dropdown, select **"All Files"**
7. Change the filename to exactly: **`.env`**
8. Make sure **Save in** is still your `C:\mail_agent\` folder
9. Click **Save**

> If Windows warns you about changing the file extension, click **Yes**

---

### Step 3 — Run it

1. Double-click **`mail_agent.exe`**
2. A black window opens, then a **browser window** launches automatically
3. Log in to Zoho Mail — including any OTP or two-factor code
4. Once you are in your inbox, the agent takes over

The black window will show:
```
Using bundled Chromium: ...
Login detected — continuing
Watcher started — poll interval: 60s
```

**Leave both windows open.** The agent runs as long as those windows are open.

The database (`mail_agent.db`) is created automatically on first run — nothing to set up.

---

## Option B — Run from Source (developers)

Use this if you want to modify the code or if you were not given a pre-built exe.

### What you need
- A Windows 10 or Windows 11 computer
- About 15 minutes

---

### Step 1 — Install Python

1. Go to **python.org/downloads** and download **Python 3.12.x**
2. Run the installer
3. **Important:** tick **"Add python.exe to PATH"** on the first screen before clicking anything else
4. Click **"Install Now"**

Verify: press **Win + R**, type `cmd`, press Enter, then type `python --version`. You should see `Python 3.12.x`.

---

### Step 2 — Get the files

Copy the `mail_agent` folder to `C:\mail_agent\`.

> If it came as a zip: right-click → **Extract All** → choose `C:\` as destination.

---

### Step 3 — Install dependencies

Open `C:\mail_agent\` in File Explorer, click the address bar, type `cmd`, press Enter. Then run:

```
pip install -r requirements.txt
```

Wait for `Successfully installed …`, then run:

```
playwright install chromium
```

---

### Step 4 — Fill in your settings

Same as Option A Step 2 above.

---

### Step 5 — Run it

Double-click **`run.bat`**, or in the `cmd` window run:

```
python launcher.py
```

---

## Day-to-Day Use

| Situation | What to do |
|-----------|-----------|
| Start the agent | Double-click `mail_agent.exe` (or `run.bat` from source) |
| Stop the agent | Close the black window, or press **Ctrl+C** in it |
| Session expired | Log in again in the browser window |
| Computer restart | Just start it again — your login session is saved |

---

## What Gets Saved Where

| Location | Contents |
|----------|----------|
| `mail_agent.db` | All data — emails, attachment records, parsed spreadsheet rows, PDF tables |
| `downloads\` | Original attachment files, organised by date |
| `logs\application.log` | Full activity log — open with Notepad |
| `screenshots\` | Screenshots captured when errors occur |
| `browser_profile\` | Saved login session — **do not delete** |

> To browse the database, download the free **DB Browser for SQLite** from sqlitebrowser.org and open `mail_agent.db`.

---

## Troubleshooting

**The black window closes immediately**
→ The `.env` file is missing. Redo Step 2.

**"Windows protected your PC" warning when opening the exe**
→ Click **"More info"** then **"Run anyway"**. This appears because the exe is not code-signed.

**Chrome opens but goes to the login page every time**
→ The `browser_profile\` folder was deleted. Log in once and the session will be saved again.

**The browser opens but websites keep loading forever**
→ Open `.env` in Notepad and add:
```
BROWSER_PROXY_MODE=system
```
Save the file and restart the agent. By default the agent bypasses Windows proxy auto-detect because it can make Playwright Chromium hang on some machines. If your network requires the Windows system proxy, use `system`.

**"No module named …" (source only)**
→ Run `pip install -r requirements.txt` again in the `cmd` window.

**Attachments are saved but nothing appears in the database**
→ Only `.xlsx` and `.pdf` files are parsed into the database. Other file types are saved to `downloads\` but not written to `mail_agent.db`.
