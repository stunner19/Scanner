"""
india_stocks.py — Fetches NSE index constituents from Wikipedia.

NSE blocks direct API and archive requests from cloud-hosted servers (403).
Wikipedia's index pages have up-to-date constituent tables, are publicly
accessible from any server, and don't require auth or cookies.

Nifty 100 = Nifty 50 + Nifty Next 50 (computed).
Nifty 200 / 500 are derived by combining available sub-indices.
"""

import io
import time
import logging
import threading
import requests
import pandas as pd

log = logging.getLogger(__name__)

CACHE_TTL = 3600  # re-fetch at most once per hour

# ── Wikipedia URLs for each index ─────────────────────────────────────────────
_WIKI_URLS: dict[str, str] = {
    "Nifty 50":       "https://en.wikipedia.org/wiki/NIFTY_50",
    "Nifty Next 50":  "https://en.wikipedia.org/wiki/Nifty_Next_50",
    "Nifty Bank":     "https://en.wikipedia.org/wiki/NIFTY_Bank",
    "Nifty IT":       "https://en.wikipedia.org/wiki/NIFTY_IT",
    "Nifty Pharma":   "https://en.wikipedia.org/wiki/Nifty_Pharma",
    "Nifty FMCG":     "https://en.wikipedia.org/wiki/Nifty_FMCG",
    "Nifty Midcap 50":"https://en.wikipedia.org/wiki/Nifty_Midcap_50",
}

# Derived indices — built from combining fetched ones
_DERIVED: dict[str, list[str]] = {
    "Nifty 100": ["Nifty 50", "Nifty Next 50"],
}

INDEX_MAP = {**{k: k for k in _WIKI_URLS}, **{k: k for k in _DERIVED}}

# ── In-memory cache ───────────────────────────────────────────────────────────
_cache: dict = {}
_cache_time: dict = {}
_cache_lock = threading.Lock()

_session = requests.Session()
_session.headers.update({
    "User-Agent": "Mozilla/5.0 (compatible; NSEScanner/1.0)",
    "Accept-Language": "en-US,en;q=0.9",
})


def _fetch_from_wikipedia(index_name: str) -> list[str]:
    """
    Parse the Wikipedia constituent table for an index.
    Looks for any table that has a 'symbol' or 'nse code' column.
    """
    url = _WIKI_URLS.get(index_name)
    if not url:
        return []

    try:
        resp = _session.get(url, timeout=20)
        log.info(f"{index_name}: Wikipedia HTTP {resp.status_code}")
        resp.raise_for_status()

        tables = pd.read_html(io.StringIO(resp.text))
        for df in tables:
            cols_lower = {c: c.strip().lower() for c in df.columns}
            # Match columns named "symbol", "nse symbol", "nse code", "ticker"
            match = next(
                (orig for orig, lower in cols_lower.items()
                 if any(kw in lower for kw in ("symbol", "nse code", "ticker"))),
                None,
            )
            if match is None:
                continue

            symbols = (
                df[match]
                .dropna()
                .astype(str)
                .str.strip()
                .str.replace(r"\.NS$", "", regex=True)  # strip Yahoo-style suffix
                .tolist()
            )
            # Filter out header-like rows (e.g. "Symbol", "NSE Code")
            symbols = [s for s in symbols if s and not s.lower() in ("symbol", "nse code", "ticker", "nan")]
            if symbols:
                log.info(f"{index_name}: got {len(symbols)} symbols from Wikipedia")
                return symbols

        log.error(f"{index_name}: no matching table found on Wikipedia page")
        return []

    except Exception as e:
        log.error(f"{index_name}: Wikipedia fetch error — {type(e).__name__}: {e}")
        return []


def get_universe(name: str) -> list[str]:
    """
    Return live constituents for a universe, with 1-hour cache.
    """
    if name not in INDEX_MAP:
        log.warning(f"Unknown universe: {name}")
        return []

    now = time.time()

    with _cache_lock:
        if name in _cache and (now - _cache_time.get(name, 0)) < CACHE_TTL:
            return _cache[name]

    # Derived index — combine component universes
    if name in _DERIVED:
        combined: list[str] = []
        for component in _DERIVED[name]:
            combined.extend(get_universe(component))
        symbols = list(dict.fromkeys(combined))  # deduplicate, preserve order
    else:
        symbols = _fetch_from_wikipedia(name)

    if symbols:
        with _cache_lock:
            _cache[name] = symbols
            _cache_time[name] = now

    return symbols


def get_universe_names() -> list[str]:
    return list(INDEX_MAP.keys())
