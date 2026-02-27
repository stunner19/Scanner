"""
india_stocks.py — Fetches live NSE index constituents from NSE's public API.

No API key needed. NSE's website uses the same endpoints internally.
Universes are fetched fresh each time (with in-memory caching per process
to avoid hammering NSE on every scan).

NSE index API endpoint:
  https://nseindia.com/api/equity-stockIndices?index=NIFTY%2050
"""

import time
import logging
import threading
import requests

log = logging.getLogger(__name__)

# ── NSE index name → API index param ─────────────────────────────────────────
INDEX_MAP = {
    "Nifty 100": "NIFTY 100",
    "Nifty 200": "NIFTY 200",
    "Nifty 500": "NIFTY 500",
    "Nifty 50": "NIFTY 50",
    "Nifty Next 50": "NIFTY NEXT 50",
    "Nifty Midcap 50": "NIFTY MIDCAP 50",
    "Nifty Bank": "NIFTY BANK",
    "Nifty IT": "NIFTY IT",
    "Nifty Pharma": "NIFTY PHARMA",
    "Nifty FMCG": "NIFTY FMCG",
}

NSE_BASE = "https://www.nseindia.com"
CACHE_TTL = 3600  # re-fetch from NSE at most once per hour

# ── In-memory cache ───────────────────────────────────────────────────────────
_cache: dict = {}  # { "Nifty 50": ["RELIANCE", "TCS", ...] }
_cache_time: dict = {}  # { "Nifty 50": timestamp }
_cache_lock = threading.Lock()

# ── Shared session (mimics browser visit NSE needs) ───────────────────────────
_session = requests.Session()
_session.headers.update(
    {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/120.0.0.0 Safari/537.36",
        "Accept": "application/json, text/plain, */*",
        "Accept-Language": "en-US,en;q=0.9",
        "Referer": "https://www.nseindia.com/",
    }
)
_session_initialised = False
_session_lock = threading.Lock()


def _init_nse_session():
    """
    Visit NSE homepage first to get cookies.
    NSE blocks API calls that don't have a prior homepage cookie.
    """
    global _session_initialised
    if _session_initialised:
        return
    with _session_lock:
        if _session_initialised:
            return
        try:
            log.info("Initialising NSE session...")
            _session.get(f"{NSE_BASE}/", timeout=10)
            time.sleep(0.5)
            _session_initialised = True
            log.info("NSE session ready")
        except Exception as e:
            log.warning(f"NSE session init warning: {e}")


def _fetch_from_nse(index_name: str) -> list[str]:
    """
    Fetch live constituents for one index from NSE API.
    Returns a list of plain NSE symbols e.g. ["RELIANCE", "TCS", ...]
    """
    _init_nse_session()

    nse_param = INDEX_MAP[index_name]
    url = f"{NSE_BASE}/api/equity-stockIndices"

    try:
        resp = _session.get(url, params={"index": nse_param}, timeout=15)
        resp.raise_for_status()
        data = resp.json()

        # Response: { "data": [ {"symbol": "RELIANCE", ...}, ... ] }
        # First item is the index itself — skip it
        stocks = data.get("data", [])[1:]
        symbols = [s["symbol"] for s in stocks if s.get("symbol")]

        log.info(f"{index_name}: fetched {len(symbols)} stocks from NSE")
        return symbols

    except Exception as e:
        log.error(f"{index_name}: NSE fetch error — {e}")
        return []


def get_universe(name: str) -> list[str]:
    """
    Return live constituents for a universe, with 1-hour cache.
    Falls back to empty list if NSE is unreachable.
    """
    if name not in INDEX_MAP:
        log.warning(f"Unknown universe: {name}")
        return []

    now = time.time()

    with _cache_lock:
        # Return cached value if fresh
        if name in _cache and (now - _cache_time.get(name, 0)) < CACHE_TTL:
            return _cache[name]

    # Fetch outside the lock so other universes aren't blocked
    symbols = _fetch_from_nse(name)

    if symbols:
        with _cache_lock:
            _cache[name] = symbols
            _cache_time[name] = now

    return symbols


def get_universe_names() -> list[str]:
    return list(INDEX_MAP.keys())
