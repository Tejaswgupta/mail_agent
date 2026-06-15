"""Telegram notification helper. Silent-fails if credentials are missing."""
import requests
from loguru import logger
from config import settings


def send(message: str) -> bool:
    token = settings.TELEGRAM_BOT_TOKEN
    chat_id = settings.TELEGRAM_CHAT_ID
    if not token or not chat_id:
        logger.debug("Telegram not configured — skipping notification")
        return False
    url = f"https://api.telegram.org/bot{token}/sendMessage"
    try:
        resp = requests.post(url, json={"chat_id": chat_id, "text": message}, timeout=10)
        resp.raise_for_status()
        logger.debug("Telegram notification sent")
        return True
    except Exception as exc:
        logger.warning(f"Telegram notification failed: {exc}")
        return False


def send_photo(caption: str, photo_path: str) -> bool:
    token = settings.TELEGRAM_BOT_TOKEN
    chat_id = settings.TELEGRAM_CHAT_ID
    if not token or not chat_id:
        return False
    url = f"https://api.telegram.org/bot{token}/sendPhoto"
    try:
        with open(photo_path, "rb") as f:
            resp = requests.post(url, data={"chat_id": chat_id, "caption": caption}, files={"photo": f}, timeout=20)
        resp.raise_for_status()
        return True
    except Exception as exc:
        logger.warning(f"Telegram photo send failed: {exc}")
        return False
