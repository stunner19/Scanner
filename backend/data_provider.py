"""
data_provider.py — Fetches OHLCV data from Upstox API v2.

Optimised for concurrent use:
  - Shared requests.Session with connection pooling (reuses TCP connections)
  - Thread-safe instrument cache loaded once at startup
  - No artificial delays — Upstox handles concurrent requests fine
"""

import os
import io
import logging
import threading
import requests
import pandas as pd
from datetime import datetime, timedelta
from dotenv import load_dotenv
from token_manager import get_valid_token, save_token

load_dotenv()

log = logging.getLogger(__name__)
BASE_URL = "https://api.upstox.com/v2"

# ── Shared HTTP session with connection pooling ───────────────────────────────
# Reuses TCP connections across threads — much faster than requests.get()
_http = requests.Session()
_http.mount(
    "https://",
    requests.adapters.HTTPAdapter(
        pool_connections=20,
        pool_maxsize=20,
        max_retries=requests.adapters.Retry(
            total=3, backoff_factor=0.3, status_forcelist=[500, 502, 503, 504]
        ),
    ),
)

# ── Thread-safe instrument cache ──────────────────────────────────────────────
_instrument_cache: dict = {}
_master_df: pd.DataFrame = None
_cache_lock = threading.Lock()


def _load_instrument_master():
    """
    Download Upstox NSE instrument master and cache it.
    Thread-safe double-checked locking — downloaded only once.
    """
    global _instrument_cache, _master_df

    if _instrument_cache:  # fast path
        return

    with _cache_lock:
        if _instrument_cache:  # re-check after acquiring lock
            return

        log.info("Loading Upstox instrument master...")
        url = "https://assets.upstox.com/market-quote/instruments/exchange/NSE.csv.gz"
        resp = _http.get(url, timeout=15)
        resp.raise_for_status()

        df = pd.read_csv(
            io.BytesIO(resp.content),
            compression="gzip",
            usecols=["tradingsymbol", "instrument_key", "instrument_type"],
        )
        df = df[df["instrument_type"] == "EQUITY"].copy()
        df["tradingsymbol_upper"] = df["tradingsymbol"].str.upper()

        _master_df = df
        _instrument_cache = dict(zip(df["tradingsymbol"], df["instrument_key"]))
        log.info(f"Loaded {len(_instrument_cache)} NSE EQUITY instruments")


def _get_instrument_key(symbol: str) -> str:
    """Return Upstox instrument key. Tries exact → uppercase → fuzzy."""
    _load_instrument_master()

    # 1. Exact
    if symbol in _instrument_cache:
        return _instrument_cache[symbol]

    # 2. Case-insensitive
    row = _master_df[_master_df["tradingsymbol_upper"] == symbol.upper()]
    if not row.empty:
        key = row.iloc[0]["instrument_key"]
        with _cache_lock:
            _instrument_cache[symbol] = key
        return key

    # 3. Fuzzy — strip punctuation and try prefix
    clean = symbol.upper().replace("&", "").replace("-", "").replace(" ", "")
    row = _master_df[
        _master_df["tradingsymbol_upper"]
        .str.replace(r"[&\-\s]", "", regex=True)
        .str.startswith(clean, na=False)
    ]
    if not row.empty:
        key = row.iloc[0]["instrument_key"]
        actual = row.iloc[0]["tradingsymbol"]
        with _cache_lock:
            _instrument_cache[symbol] = key
        log.info(f"{symbol}: fuzzy-matched to '{actual}'")
        return key

    raise ValueError(f"{symbol}: not found in Upstox instrument master")


def fetch_ohlcv(symbol: str, period_days: int = 180) -> pd.DataFrame:
    """
    Fetch daily OHLCV for one NSE symbol.
    Thread-safe — uses shared session with connection pooling.
    """
    try:
        access_token = get_valid_token()
        instrument_key = _get_instrument_key(symbol)

        to_date = datetime.today()
        from_date = to_date - timedelta(days=period_days)

        url = (
            f"{BASE_URL}/historical-candle"
            f"/{requests.utils.quote(instrument_key, safe='')}"
            f"/day/{to_date.strftime('%Y-%m-%d')}/{from_date.strftime('%Y-%m-%d')}"
        )

        resp = _http.get(
            url,
            headers={
                "Authorization": f"Bearer {access_token}",
                "Accept": "application/json",
            },
            timeout=5,
        )

        if resp.status_code == 401:
            raise EnvironmentError(
                "Upstox token rejected. Re-authenticate via the scanner UI."
            )

        resp.raise_for_status()
        candles = resp.json().get("data", {}).get("candles", [])

        if not candles:
            log.warning(f"{symbol}: no candles returned")
            return pd.DataFrame()

        df = pd.DataFrame(
            candles, columns=["Date", "Open", "High", "Low", "Close", "Volume", "OI"]
        )
        df["Date"] = pd.to_datetime(df["Date"])
        df = df.set_index("Date").sort_index()
        df = df[["Open", "High", "Low", "Close", "Volume"]]
        for col in df.columns:
            df[col] = pd.to_numeric(df[col], errors="coerce")
        df = df.dropna(how="all")

        log.info(f"{symbol}: {len(df)} rows")
        return df

    except EnvironmentError:
        raise
    except ValueError as e:
        log.warning(str(e))
        return pd.DataFrame()
    except Exception as e:
        log.error(f"{symbol}: fetch error — {e}")
        return pd.DataFrame()


def preload_instruments():
    """Pre-load instrument master at Flask startup so first scan is instant."""
    _load_instrument_master()


def exchange_code_for_token(code: str) -> str:
    """OAuth2: exchange authorization code for long-lived access token."""
    api_key = os.environ.get("UPSTOX_API_KEY", "").strip()
    api_secret = os.environ.get("UPSTOX_API_SECRET", "").strip()
    redirect = os.environ.get("UPSTOX_REDIRECT_URI", "").strip()

    if not all([api_key, api_secret, redirect]):
        raise EnvironmentError(
            "UPSTOX_API_KEY, UPSTOX_API_SECRET and UPSTOX_REDIRECT_URI "
            "must all be set in backend/.env"
        )

    resp = requests.post(
        f"{BASE_URL}/login/authorization/token",
        headers={"Content-Type": "application/x-www-form-urlencoded"},
        data={
            "code": code,
            "client_id": api_key,
            "client_secret": api_secret,
            "redirect_uri": redirect,
            "grant_type": "authorization_code",
        },
        timeout=5,
    )

    if not resp.ok:
        raise RuntimeError(f"Token exchange failed ({resp.status_code}): {resp.text}")

    access_token = resp.json().get("access_token")
    if not access_token:
        raise RuntimeError("No access_token in Upstox response")

    save_token(access_token)
    log.info("Upstox access token saved")
    return access_token
