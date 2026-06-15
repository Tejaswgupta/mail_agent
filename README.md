launcher.py (entry point)
├── keep_awake — prevents OS sleep (no internal deps)
├── notifier — sends webhook/HTTP notifications → config
├── zoho_client — Playwright browser automation for Zoho Mail → config, session_monitor
│ └── session_monitor — detects login/session expiry → notifier
├── watcher — core polling loop → notifier, session_monitor, storage, zoho_client, attachment_processor, config
│ └── attachment_processor — downloads & parses files → storage, xlsx_parser, pdf_parser, config
│ ├── storage — SQLite persistence → config
│ ├── xlsx_parser — parses .xlsx files (no internal deps)
│ └── pdf_parser — parses .pdf files (no internal deps)
└── config — settings/env vars (base for everything)

Flow: launcher opens the browser → zoho_client navigates Zoho Mail → watcher polls for new emails → attachment_processor downloads
and parses files → storage persists results → notifier fires alerts if needed. session_monitor watches for login expiry and notifies
via notifier. keep_awake runs in a background thread throughout.
