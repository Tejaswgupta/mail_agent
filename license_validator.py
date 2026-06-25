"""License validation — validate license.key before the app starts."""

import base64
import hashlib
import hmac
import json
import sys
from datetime import date, datetime
from pathlib import Path

from loguru import logger

# ── Secret signing key (obfuscate this file with PyArmor before shipping) ────
# Generate your own with: python -c "import secrets; print(secrets.token_hex(32))"
_SIGNING_KEY = b"3551436b93a4bf1eaeaf334efd1ea75b903538170cb5a9cb8a0ca86d78814700"

_LICENSE_FILE = Path(__file__).parent / "license.key"


class LicenseError(Exception):
    pass


def _verify(payload_b64: str, sig_hex: str) -> dict:
    expected = hmac.new(_SIGNING_KEY, payload_b64.encode(), hashlib.sha256).hexdigest()
    if not hmac.compare_digest(expected, sig_hex):
        raise LicenseError("License signature is invalid.")
    try:
        return json.loads(base64.b64decode(payload_b64).decode())
    except Exception:
        raise LicenseError("License payload is corrupt.")


def validate() -> dict:
    """
    Read and validate license.key. Returns the license dict on success.
    Calls sys.exit(1) on any failure so the app never starts unlicensed.
    """
    if not _LICENSE_FILE.exists():
        logger.critical(
            "No license file found at %s — contact your vendor to obtain a license key.",
            _LICENSE_FILE,
        )
        sys.exit(1)

    raw = _LICENSE_FILE.read_text(encoding="utf-8").strip()
    parts = raw.split(".")
    if len(parts) != 2:
        logger.critical("License file is malformed.")
        sys.exit(1)

    payload_b64, sig_hex = parts
    try:
        lic = _verify(payload_b64, sig_hex)
    except LicenseError as exc:
        logger.critical("License validation failed: {}", exc)
        sys.exit(1)

    expiry = datetime.strptime(lic["expiry"], "%Y-%m-%d").date()
    if date.today() > expiry:
        logger.critical(
            "License expired on {} — contact your vendor to renew.",
            lic["expiry"],
        )
        sys.exit(1)

    days_left = (expiry - date.today()).days
    if days_left <= 14:
        logger.warning(
            "License for '{}' expires in {} day(s) on {}. Please renew soon.",
            lic.get("client_id", "unknown"),
            days_left,
            lic["expiry"],
        )

    logger.info(
        "License OK — client='{}' valid until {}",
        lic.get("client_id", "unknown"),
        lic["expiry"],
    )
    return lic
