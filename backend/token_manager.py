"""
token_manager.py — Manages Upstox OAuth2 token lifecycle.

Upstox access tokens do NOT expire daily like Kite.
They remain valid until manually revoked.

Token is stored in config.json with a timestamp.
The 24h check exists only as a safety net — in practice
Upstox tokens last much longer.

config.json structure:
{
  "access_token": "...",
  "token_saved_at": 1234567890.0   (UTC unix timestamp)
}
"""

import os
import json
import logging
from datetime import datetime, timezone

log = logging.getLogger(__name__)

CONFIG_PATH = os.path.join(os.path.dirname(__file__), "config.json")
TOKEN_MAX_AGE = 24 * 60 * 60  # treat as stale after 24h, re-verify


def _now() -> float:
    return datetime.now(timezone.utc).timestamp()


def _load_config() -> dict:
    try:
        if os.path.exists(CONFIG_PATH):
            with open(CONFIG_PATH, "r") as f:
                return json.load(f)
    except Exception as e:
        log.warning(f"config.json read error: {e}")
    return {}


def _save_config(updates: dict):
    data = _load_config()
    data.update(updates)
    with open(CONFIG_PATH, "w") as f:
        json.dump(data, f, indent=2)


def save_token(access_token: str):
    """Persist a new access token with current UTC timestamp."""
    now = _now()
    _save_config(
        {
            "access_token": access_token,
            "token_saved_at": now,
        }
    )
    os.environ["UPSTOX_ACCESS_TOKEN"] = access_token
    log.info(
        f"Token saved at "
        f"{datetime.fromtimestamp(now, tz=timezone.utc).strftime('%d %b %Y %H:%M UTC')}"
    )


def get_token_status() -> dict:
    """
    Returns:
    {
        "valid":        bool,
        "access_token": str,
        "age_hours":    float | None,
        "saved_at":     str   | None,
        "message":      str,
    }
    """
    config = _load_config()
    access_token = config.get("access_token") or os.environ.get(
        "UPSTOX_ACCESS_TOKEN", ""
    )
    saved_at = config.get("token_saved_at")

    if not access_token:
        return {
            "valid": False,
            "access_token": "",
            "age_hours": None,
            "saved_at": None,
            "message": "No token found. Complete one-time login to get started.",
        }

    if not saved_at:
        # Token exists but no timestamp — assume valid (legacy)
        os.environ["UPSTOX_ACCESS_TOKEN"] = access_token
        return {
            "valid": True,
            "access_token": access_token,
            "age_hours": 0,
            "saved_at": "Unknown",
            "message": "Token present (no timestamp). Assuming valid.",
        }

    age = _now() - saved_at
    hours = round(age / 3600, 2)
    saved_str = datetime.fromtimestamp(saved_at, tz=timezone.utc).strftime(
        "%d %b %Y %H:%M UTC"
    )

    # Always sync to environment
    os.environ["UPSTOX_ACCESS_TOKEN"] = access_token

    if age < TOKEN_MAX_AGE:
        remaining = TOKEN_MAX_AGE - age
        h, m = int(remaining // 3600), int((remaining % 3600) // 60)
        return {
            "valid": True,
            "access_token": access_token,
            "age_hours": hours,
            "saved_at": saved_str,
            "message": f"Token active — saved {hours:.1f}h ago",
        }
    else:
        # Token is older than 24h — verify it's still working
        # (Upstox tokens don't actually expire, this is just a health check)
        return {
            "valid": True,  # still return True for Upstox
            "access_token": access_token,
            "age_hours": hours,
            "saved_at": saved_str,
            "message": f"Token is {hours:.0f}h old — will verify on first request",
        }


def get_valid_token() -> str:
    """
    Returns the stored access token.
    Raises EnvironmentError if no token exists at all.
    """
    status = get_token_status()
    if status["valid"] and status["access_token"]:
        return status["access_token"]
    raise EnvironmentError(
        "No Upstox access token found. "
        "Complete the one-time login via the scanner UI."
    )
