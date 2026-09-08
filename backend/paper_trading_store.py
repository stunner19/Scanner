"""
paper_trading_store.py — Holds the most recent paper-trading sync pushed by
the EC2 trader (see nifty500_momentum_trader.py in the options-swing repo).

Render's free tier has no persistent disk, so this also writes to a local
JSON file purely as a same-process fallback (e.g. surviving a request that
races a fresh deploy) — it is NOT relied on across deploys. The EC2 trader
re-syncs once a day, so a cold start just means an empty state until the
next sync lands.
"""

import json
import os
import threading

_PATH = os.path.join(os.path.dirname(__file__), "paper_trading_latest.json")
_lock = threading.Lock()
_latest: dict | None = None


def save_sync(payload: dict) -> None:
    global _latest
    with _lock:
        _latest = payload
        try:
            with open(_PATH, "w") as f:
                json.dump(payload, f)
        except Exception:
            pass  # best-effort disk cache only


def get_latest() -> dict | None:
    global _latest
    with _lock:
        if _latest is not None:
            return _latest
        if os.path.exists(_PATH):
            try:
                with open(_PATH) as f:
                    _latest = json.load(f)
            except Exception:
                _latest = None
        return _latest
