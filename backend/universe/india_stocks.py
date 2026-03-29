"""
india_stocks.py — Fetches NSE index constituents from Wikipedia and stockanalysis.com.

NSE blocks direct API and archive requests from cloud-hosted servers (403).
- Wikipedia: used for indices that have constituent tables (Nifty 50, Bank, IT, etc.)
- stockanalysis.com: used for larger indices (Nifty 100, 200, 500) that lack Wikipedia pages
"""

import io
import time
import logging
import threading
import requests
import pandas as pd

log = logging.getLogger(__name__)

CACHE_TTL = 3600  # re-fetch at most once per hour

# ── Wikipedia URLs ─────────────────────────────────────────────────────────────
_WIKI_URLS: dict[str, str] = {
    "Nifty 50":        "https://en.wikipedia.org/wiki/NIFTY_50",
    "Nifty Next 50":   "https://en.wikipedia.org/wiki/Nifty_Next_50",
    "Nifty Midcap 50": "https://en.wikipedia.org/wiki/Nifty_Midcap_50",
    "Nifty Bank":      "https://en.wikipedia.org/wiki/NIFTY_Bank",
    "Nifty IT":        "https://en.wikipedia.org/wiki/NIFTY_IT",
    "Nifty Pharma":    "https://en.wikipedia.org/wiki/Nifty_Pharma",
    "Nifty FMCG":      "https://en.wikipedia.org/wiki/Nifty_FMCG",
}

# ── stockanalysis.com URLs ─────────────────────────────────────────────────────
# These return a JSON payload with a "data" array containing {s: "SYMBOL.NS", ...}
_SA_URLS: dict[str, str] = {
    "Nifty 100": "https://stockanalysis.com/indexes/nifty-100-index/",
    "Nifty 200": "https://stockanalysis.com/indexes/nifty-200-index/",
    "Nifty 500": "https://stockanalysis.com/indexes/nifty-500-index/",
}

INDEX_MAP = {**{k: k for k in _WIKI_URLS}, **{k: k for k in _SA_URLS}}

# ── In-memory cache ───────────────────────────────────────────────────────────
_cache: dict = {}
_cache_time: dict = {}
_cache_lock = threading.Lock()

_session = requests.Session()
_session.headers.update({
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                  "AppleWebKit/537.36 (KHTML, like Gecko) "
                  "Chrome/120.0.0.0 Safari/537.36",
    "Accept-Language": "en-US,en;q=0.9",
})


def _fetch_from_wikipedia(index_name: str) -> list[str]:
    url = _WIKI_URLS.get(index_name)
    if not url:
        return []

    try:
        resp = _session.get(url, timeout=20)
        log.info(f"{index_name}: Wikipedia HTTP {resp.status_code}")
        resp.raise_for_status()

        tables = pd.read_html(io.StringIO(resp.text))
        for df in tables:
            df.columns = [
                " ".join(str(c) for c in col).strip() if isinstance(col, tuple) else str(col).strip()
                for col in df.columns
            ]
            cols_lower = {c: c.lower() for c in df.columns}
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
                .str.replace(r"\.NS$", "", regex=True)
                .tolist()
            )
            symbols = [s for s in symbols if s and s.lower() not in ("symbol", "nse code", "ticker", "nan")]
            if symbols:
                log.info(f"{index_name}: got {len(symbols)} symbols from Wikipedia")
                return symbols

        log.error(f"{index_name}: no matching table found on Wikipedia page")
        return []

    except Exception as e:
        log.error(f"{index_name}: Wikipedia fetch error — {type(e).__name__}: {e}")
        return []


def _fetch_from_stockanalysis(index_name: str) -> list[str]:
    """
    Scrape the constituent table from stockanalysis.com index page.
    The page renders a table with a 'Symbol' column containing tickers like 'RELIANCE.NS'.
    """
    url = _SA_URLS.get(index_name)
    if not url:
        return []

    try:
        resp = _session.get(url, timeout=20)
        log.info(f"{index_name}: stockanalysis.com HTTP {resp.status_code}")
        resp.raise_for_status()

        tables = pd.read_html(io.StringIO(resp.text))
        for df in tables:
            df.columns = [
                " ".join(str(c) for c in col).strip() if isinstance(col, tuple) else str(col).strip()
                for col in df.columns
            ]
            cols_lower = {c: c.lower() for c in df.columns}
            match = next(
                (orig for orig, lower in cols_lower.items()
                 if any(kw in lower for kw in ("symbol", "ticker"))),
                None,
            )
            if match is None:
                continue

            symbols = (
                df[match]
                .dropna()
                .astype(str)
                .str.strip()
                .str.replace(r"\.NS$", "", regex=True)
                .tolist()
            )
            symbols = [s for s in symbols if s and s.lower() not in ("symbol", "ticker", "nan")]
            if symbols:
                log.info(f"{index_name}: got {len(symbols)} symbols from stockanalysis.com")
                return symbols

        log.error(f"{index_name}: no matching table found on stockanalysis.com page")
        return []

    except Exception as e:
        log.error(f"{index_name}: stockanalysis.com fetch error — {type(e).__name__}: {e}")
        return []


def get_universe(name: str) -> list[str]:
    if name not in INDEX_MAP:
        log.warning(f"Unknown universe: {name}")
        return []

    now = time.time()

    with _cache_lock:
        if name in _cache and (now - _cache_time.get(name, 0)) < CACHE_TTL:
            return _cache[name]

    if name in _SA_URLS:
        symbols = _fetch_from_stockanalysis(name)
    else:
        symbols = _fetch_from_wikipedia(name)

    if symbols:
        with _cache_lock:
            _cache[name] = symbols
            _cache_time[name] = now

    return symbols


def get_universe_names() -> list[str]:
    return list(INDEX_MAP.keys())
