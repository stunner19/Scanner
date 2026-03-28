"""
india_stocks.py — Fetches NSE index constituents from NSE's archive CSV files.

NSE publishes regularly-updated CSV files at archives.nseindia.com that list
index constituents. These are plain file downloads — no browser session or
cookies required — and work from cloud-hosted servers.

Archive CSV endpoint example:
  https://archives.nseindia.com/content/indices/ind_nifty50list.csv
"""

import io
import time
import logging
import threading
import requests

log = logging.getLogger(__name__)

NSE_ARCHIVE_BASE = "https://archives.nseindia.com/content/indices"
CACHE_TTL = 3600  # re-fetch at most once per hour

# ── NSE index name → archive CSV filename ─────────────────────────────────────
INDEX_MAP = {
    "Nifty 50":       "ind_nifty50list.csv",
    "Nifty Next 50":  "ind_niftynext50list.csv",
    "Nifty 100":      "ind_nifty100list.csv",
    "Nifty 200":      "ind_nifty200list.csv",
    "Nifty 500":      "ind_nifty500list.csv",
    "Nifty Midcap 50":"ind_niftymidcap50list.csv",
    "Nifty Bank":     "ind_niftybanklist.csv",
    "Nifty IT":       "ind_niftyitlist.csv",
    "Nifty Pharma":   "ind_niftypharmalist.csv",
    "Nifty FMCG":     "ind_niftyfmcglist.csv",
}

# ── In-memory cache ───────────────────────────────────────────────────────────
_cache: dict = {}       # { "Nifty 50": ["RELIANCE", "TCS", ...] }
_cache_time: dict = {}  # { "Nifty 50": timestamp }
_cache_lock = threading.Lock()

_session = requests.Session()
_session.headers.update({"User-Agent": "Mozilla/5.0"})


def _fetch_from_archive(index_name: str) -> list[str]:
    """
    Download the NSE archive CSV for one index and return a list of symbols.
    The CSV has a 'Symbol' column with plain NSE tickers.
    """
    import pandas as pd

    filename = INDEX_MAP[index_name]
    url = f"{NSE_ARCHIVE_BASE}/{filename}"

    try:
        resp = _session.get(url, timeout=15)
        resp.raise_for_status()

        df = pd.read_csv(io.StringIO(resp.text))
        # Column is typically "Symbol" — find it case-insensitively
        col = next((c for c in df.columns if c.strip().lower() == "symbol"), None)
        if col is None:
            log.error(f"{index_name}: no 'Symbol' column in CSV. Columns: {list(df.columns)}")
            return []

        symbols = df[col].dropna().str.strip().tolist()
        log.info(f"{index_name}: fetched {len(symbols)} stocks from NSE archive")
        return symbols

    except Exception as e:
        log.error(f"{index_name}: archive fetch error — {e}")
        return []


def get_universe(name: str) -> list[str]:
    """
    Return live constituents for a universe, with 1-hour cache.
    Falls back to empty list if NSE archive is unreachable.
    """
    if name not in INDEX_MAP:
        log.warning(f"Unknown universe: {name}")
        return []

    now = time.time()

    with _cache_lock:
        if name in _cache and (now - _cache_time.get(name, 0)) < CACHE_TTL:
            return _cache[name]

    # Fetch outside the lock so other universes aren't blocked
    symbols = _fetch_from_archive(name)

    if symbols:
        with _cache_lock:
            _cache[name] = symbols
            _cache_time[name] = now

    return symbols


def get_universe_names() -> list[str]:
    return list(INDEX_MAP.keys())
