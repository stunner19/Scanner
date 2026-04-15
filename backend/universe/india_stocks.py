"""
india_stocks.py — Fetch NSE index constituents from official NSE CSV files.

Why this approach:
  - Avoids brittle HTML scraping from Wikipedia / third-party sites
  - Uses official NSE-published constituent lists
  - Works with simple CSV parsing and a small in-memory cache

Notes for deployment:
  - We try multiple NSE hosts because old and new archive URLs coexist
  - Static CSV endpoints generally work more reliably than dynamic NSE APIs
  - A browser-like User-Agent helps when running from cloud hosts such as Render
"""

from __future__ import annotations

import csv
import io
import time
import logging
import threading
import requests

log = logging.getLogger(__name__)

CACHE_TTL = 3600  # 1 hour
REQUEST_TIMEOUT = 20

_CSV_FILES: dict[str, str] = {
    "Nifty 50": "ind_nifty50list.csv",
    "Nifty Next 50": "ind_niftynext50list.csv",
    "Nifty Midcap 50": "ind_niftymidcap50list.csv",
    "Nifty Bank": "ind_niftybanklist.csv",
    "Nifty IT": "ind_niftyitlist.csv",
    "Nifty Pharma": "ind_niftypharmalist.csv",
    "Nifty FMCG": "ind_niftyfmcglist.csv",
    "Nifty 100": "ind_nifty100list.csv",
    "Nifty 200": "ind_nifty200list.csv",
    "Nifty 500": "ind_nifty500list.csv",
}

_BASE_URLS = [
    "https://nsearchives.nseindia.com/content/indices",
    "https://www.nseindia.com/content/indices",
    "https://www1.nseindia.com/content/indices",
]

_cache: dict[str, list[str]] = {}
_cache_time: dict[str, float] = {}
_cache_lock = threading.Lock()

_session = requests.Session()
_session.headers.update(
    {
        "User-Agent": (
            "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
            "AppleWebKit/537.36 (KHTML, like Gecko) "
            "Chrome/123.0.0.0 Safari/537.36"
        ),
        "Accept": "text/csv,text/plain,application/octet-stream,*/*",
        "Accept-Language": "en-US,en;q=0.9",
        "Referer": "https://www.nseindia.com/",
        "Connection": "keep-alive",
    }
)


def _normalize_symbol(value: str) -> str:
    symbol = str(value).strip().upper()
    if not symbol:
        return ""
    return symbol.replace(".NS", "")


def _parse_constituents(csv_text: str, index_name: str) -> list[str]:
    reader = csv.DictReader(io.StringIO(csv_text))
    rows = list(reader)
    if not rows:
        log.warning("%s: NSE CSV returned no rows", index_name)
        return []

    if not reader.fieldnames:
        log.warning("%s: NSE CSV has no header row", index_name)
        return []

    normalized = {name.strip().lower(): name for name in reader.fieldnames}
    symbol_col = None
    for candidate in ("symbol", "ticker", "nse symbol", "company symbol"):
        if candidate in normalized:
            symbol_col = normalized[candidate]
            break

    if not symbol_col:
        log.warning("%s: no symbol column found in NSE CSV headers %s", index_name, reader.fieldnames)
        return []

    symbols: list[str] = []
    seen: set[str] = set()
    for row in rows:
        symbol = _normalize_symbol(row.get(symbol_col, ""))
        if symbol and symbol not in seen:
            seen.add(symbol)
            symbols.append(symbol)

    log.info("%s: parsed %s symbols from NSE CSV", index_name, len(symbols))
    return symbols


def _fetch_csv(index_name: str) -> list[str]:
    filename = _CSV_FILES.get(index_name)
    if not filename:
        return []

    errors: list[str] = []
    for base_url in _BASE_URLS:
        url = f"{base_url}/{filename}"
        try:
            resp = _session.get(url, timeout=REQUEST_TIMEOUT)
            log.info("%s: NSE CSV %s -> HTTP %s", index_name, url, resp.status_code)
            resp.raise_for_status()

            symbols = _parse_constituents(resp.text, index_name)
            if symbols:
                return symbols

            errors.append(f"{url} returned no symbols")
        except Exception as exc:
            errors.append(f"{url}: {type(exc).__name__}: {exc}")

    log.error("%s: failed to fetch NSE constituents. %s", index_name, " | ".join(errors))
    return []


def get_universe(name: str) -> list[str]:
    if name not in _CSV_FILES:
        log.warning("Unknown universe: %s", name)
        return []

    now = time.time()
    with _cache_lock:
        if name in _cache and (now - _cache_time.get(name, 0)) < CACHE_TTL:
            return list(_cache[name])

    symbols = _fetch_csv(name)
    if symbols:
        with _cache_lock:
            _cache[name] = symbols
            _cache_time[name] = now

    return symbols


def get_universe_names() -> list[str]:
    return list(_CSV_FILES.keys())
