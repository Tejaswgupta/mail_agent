from playwright.sync_api import sync_playwright
import time
from pathlib import Path

PROFILE_DIR = Path("c:/Users/Administrator/Downloads/mail_agent (1)/mail_agent/browser_profile")

with sync_playwright() as p:
    context = p.chromium.launch_persistent_context(
        user_data_dir=str(PROFILE_DIR),
        headless=False,
        channel="chrome"
    )
    page = context.pages[0] if context.pages else context.new_page()
    page.goto("https://mail.zoho.in/zm/#mail/folder/inbox")
    time.sleep(5) # wait for load
    
    # Try to find the email list container
    html = page.evaluate("() => document.body.innerHTML")
    
    # Save HTML to a file so we can inspect it
    with open("zoho_dump.html", "w", encoding="utf-8") as f:
        f.write(html)
        
    print("HTML dumped to zoho_dump.html. Page title:", page.title())
    context.close()
