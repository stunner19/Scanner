"""
BaseStrategy — concurrent scanning engine.

Upstox limits: 25 req/sec, 250 req/min, 1000 req/30min.

With the SQLite OHLCV cache in data_provider, most scans hit local disk and
complete in milliseconds — no Upstox calls needed after the first run each day.
On a cold cache, 20 workers naturally throttle to ~13 req/s (well under 25/s
limit), so no artificial stagger is needed.
"""

import logging
import pandas as pd
from abc import ABC, abstractmethod
from concurrent.futures import ThreadPoolExecutor, as_completed
from data_provider import fetch_ohlcv

log = logging.getLogger(__name__)

MAX_WORKERS = 20  # concurrent threads


class BaseStrategy(ABC):
    name: str = "Base"
    description: str = ""
    _period_days: int = 180

    @abstractmethod
    def scan(self, symbol: str, data: pd.DataFrame) -> dict | None:
        pass

    def _fetch_and_scan(self, symbol: str) -> tuple[str, dict | None]:
        try:
            df = fetch_ohlcv(symbol, period_days=self._period_days)
            if df.empty or len(df) < 30:
                return symbol, None
            return symbol, self.scan(symbol, df)
        except Exception as e:
            log.warning(f"{symbol}: {e}")
            return symbol, None

    def run(self, tickers: list) -> list:
        return list(self.run_stream(tickers))

    def run_stream(self, tickers: list):
        """
        Yields progress/match events as stocks complete.
        No stagger needed — OHLCV cache handles rate limiting naturally.
        """
        symbols = [t.replace(".NS", "").replace(".BO", "") for t in tickers]
        total = len(symbols)
        completed = 0

        log.info(f"Scanning {total} stocks — {MAX_WORKERS} workers")

        with ThreadPoolExecutor(max_workers=MAX_WORKERS) as executor:
            futures = {executor.submit(self._fetch_and_scan, sym): sym for sym in symbols}

            for future in as_completed(futures):
                sym = futures[future]
                completed += 1
                try:
                    _, result = future.result()
                    if result:
                        yield {
                            "type": "match",
                            "completed": completed,
                            "total": total,
                            **result,
                        }
                    else:
                        yield {
                            "type": "progress",
                            "completed": completed,
                            "total": total,
                            "symbol": sym,
                        }
                except Exception as e:
                    log.warning(f"{sym}: {e}")
                    yield {
                        "type": "progress",
                        "completed": completed,
                        "total": total,
                        "symbol": sym,
                    }

    @staticmethod
    def _price_change(close: pd.Series) -> float:
        p, pp = float(close.iloc[-1]), float(close.iloc[-2])
        return round(((p - pp) / pp) * 100, 2)

    @staticmethod
    def _clean(ticker: str) -> str:
        return ticker.replace(".NS", "").replace(".BO", "")
