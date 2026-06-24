"""Central configuration — loaded once, validated at startup."""
from pathlib import Path
from typing import Literal

from pydantic import field_validator
from pydantic_settings import BaseSettings

BASE_DIR = Path(__file__).parent


class Settings(BaseSettings):
    # Database
    DB_PATH: Path = BASE_DIR / "mail_agent.db"

    # Telegram
    TELEGRAM_BOT_TOKEN: str = ""
    TELEGRAM_CHAT_ID: str = ""

    # Polling
    POLL_INTERVAL_SECONDS: int = 60

    # Paths
    DOWNLOADS_DIR: Path = BASE_DIR / "downloads"
    LOGS_DIR: Path = BASE_DIR / "logs"
    SCREENSHOTS_DIR: Path = BASE_DIR / "screenshots"
    BROWSER_PROFILE_DIR: Path = BASE_DIR / "browser_profile"
    BROWSER_CHANNEL: Literal["chromium", "chrome"] = "chromium"
    BROWSER_PROXY_MODE: Literal["direct", "system"] = "direct"
    BROWSER_CONNECTIVITY_CHECK_URL: str = "https://example.com/"
    ZOHO_READY_TIMEOUT_SECONDS: int = 120

    # Zoho
    ZOHO_MAIL_URL: str = "https://workplace.mgovcloud.in/#mail_app/"

    model_config = {"env_file": str(BASE_DIR / ".env"), "extra": "ignore"}

    @field_validator("DOWNLOADS_DIR", "LOGS_DIR", "SCREENSHOTS_DIR", "BROWSER_PROFILE_DIR", mode="before")
    @classmethod
    def ensure_dir(cls, v):
        p = Path(v)
        p.mkdir(parents=True, exist_ok=True)
        return p


settings = Settings()
