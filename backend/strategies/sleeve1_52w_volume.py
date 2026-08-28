"""
Sleeve 1 — 52-Week-High + Volume

Weekly rotation strategy, rebalanced only after Friday close. Unlike the other
strategies (which score each stock independently), this one ranks the whole
Nifty 500 cross-sectionally, so it overrides run()/run_stream() instead of
scan().

Pipeline:
  1. Fetch OHLCV for every ticker in the universe.
  2. Per stock, compute liquid_ok (trailing-60d avg traded value >= 1cr,
     <=2 zero-volume days in that window, close >= 20, >=260d of history)
     and above_sma200 (close > 200-day SMA).
  3. Friday gate: the latest trading day across all fetched data must be a
     Friday — fetch_ohlcv already rolls back to the prior close before
     15:30 IST, so this also enforces "after Friday close" for free.
  4. Regime gate: breadth = fraction of liquid_ok stocks with
     above_sma200 == True. If breadth < 0.54, no new entries this week.
  5. Eligible set = liquid_ok AND above_sma200. Cross-sectional z-scores of
     pct_of_52w_high and volume_trend are computed over this set; score is
     their sum. Only score > 0 stocks are ranked and returned.
"""

import logging
import pandas as pd
from concurrent.futures import ThreadPoolExecutor, as_completed

from .base import BaseStrategy
from data_provider import fetch_ohlcv

log = logging.getLogger(__name__)

MAX_WORKERS = 20

MIN_HISTORY_DAYS = 260
LIQUIDITY_LOOKBACK = 60
MIN_AVG_TRADED_VALUE = 1_00_00_000  # ₹1cr
MAX_ZERO_VOLUME_DAYS = 2
PRICE_FLOOR = 20.0
HIGH_LOOKBACK = 252
SMA_TREND = 200
VOL_SHORT = 20
VOL_LONG = 60
BREADTH_MIN = 0.54


class Sleeve1Strategy(BaseStrategy):
    name = "Sleeve 1 — 52-Week-High + Volume"
    description = (
        "Weekly (Friday close) rotation across liquid Nifty 500 names in a "
        "confirmed uptrend, ranked by proximity to the 52-week high blended "
        "with rising volume — gated by market-wide breadth."
    )
    _period_days = 420  # ~285 trading days — covers the 260d/252d lookbacks with margin

    def scan(self, symbol: str, data: pd.DataFrame) -> dict | None:
        # Scored cross-sectionally, not per-symbol — see run_stream().
        raise NotImplementedError("Sleeve1Strategy scores the whole universe at once; use run_stream().")

    def run(self, tickers: list) -> list:
        return list(self.run_stream(tickers))

    def run_stream(self, tickers: list):
        symbols = [self._clean(t) for t in tickers]
        total = len(symbols)

        log.info(f"Sleeve 1: fetching {total} stocks")

        features = {}
        completed = 0
        with ThreadPoolExecutor(max_workers=MAX_WORKERS) as executor:
            futures = {
                executor.submit(fetch_ohlcv, sym, self._period_days): sym
                for sym in symbols
            }
            for future in as_completed(futures):
                sym = futures[future]
                completed += 1
                yield {"type": "progress", "completed": completed, "total": total, "symbol": sym}
                try:
                    df = future.result()
                except Exception as e:
                    log.warning(f"{sym}: {e}")
                    continue
                feat = self._compute_features(df)
                if feat is not None:
                    features[sym] = feat

        if not features:
            return

        as_of = max(f["as_of"] for f in features.values())
        if as_of.weekday() != 4:  # Monday=0 ... Friday=4
            raise ValueError(
                f"Sleeve 1 only rebalances after Friday close. Latest available "
                f"trading day is {as_of:%Y-%m-%d} ({as_of:%A})."
            )

        liquid = {s: f for s, f in features.items() if f["liquid_ok"]}
        if not liquid:
            return

        breadth = sum(f["above_sma200"] for f in liquid.values()) / len(liquid)
        log.info(f"Sleeve 1: breadth={breadth:.3f} across {len(liquid)} liquid names")

        if breadth < BREADTH_MIN:
            log.info(
                f"Sleeve 1: regime gate closed (breadth {breadth:.3f} < {BREADTH_MIN}) "
                "— no new entries this week"
            )
            return

        eligible = {s: f for s, f in liquid.items() if f["above_sma200"]}
        if len(eligible) < 2:
            return

        pct_z = self._zscore(pd.Series({s: f["pct_of_52w_high"] for s, f in eligible.items()}))
        vol_z = self._zscore(pd.Series({s: f["volume_trend"] for s, f in eligible.items()}))
        score = (pct_z + vol_z).dropna()

        picks = score[score > 0].sort_values(ascending=False)

        for rank, (sym, sc) in enumerate(picks.items(), start=1):
            f = eligible[sym]
            yield {
                "type": "match",
                "completed": total,
                "total": total,
                "ticker": sym,
                "price": round(f["close"], 2),
                "change_pct": f["change_pct"],
                "signal": (
                    f"Rank #{rank} · {f['pct_of_52w_high'] * 100:.1f}% of 52W high · "
                    f"vol trend {f['volume_trend'] * 100:+.1f}%"
                ),
                "strength": "Strong" if sc > 1 else "Moderate",
                "metric_label": "Score",
                "metric_value": f"{sc:+.2f}",
                "pct_of_52w_high": round(f["pct_of_52w_high"] * 100, 2),
                "volume_trend": round(f["volume_trend"] * 100, 2),
                "rank": rank,
            }

    def _compute_features(self, data: pd.DataFrame) -> dict | None:
        if data.empty or len(data) < MIN_HISTORY_DAYS:
            return None

        close = data["Close"]
        high = data["High"]
        volume = data["Volume"]

        last_close = float(close.iloc[-1])

        rolling_high = high.rolling(HIGH_LOOKBACK).max().iloc[-1]
        sma200 = close.rolling(SMA_TREND).mean().iloc[-1]
        if pd.isna(rolling_high) or pd.isna(sma200) or rolling_high <= 0:
            return None

        traded_value = (close * volume).tail(LIQUIDITY_LOOKBACK)
        zero_vol_days = int((volume.tail(LIQUIDITY_LOOKBACK) == 0).sum())
        liquid_ok = (
            traded_value.mean() >= MIN_AVG_TRADED_VALUE
            and zero_vol_days <= MAX_ZERO_VOLUME_DAYS
            and last_close >= PRICE_FLOOR
        )

        vol_short = volume.tail(VOL_SHORT).mean()
        vol_long = volume.tail(VOL_LONG).mean()
        if not vol_long:
            return None

        return {
            "as_of": data.index[-1].date(),
            "close": last_close,
            "change_pct": self._price_change(close),
            "liquid_ok": bool(liquid_ok),
            "above_sma200": bool(last_close > sma200),
            "pct_of_52w_high": last_close / rolling_high,
            "volume_trend": (vol_short / vol_long) - 1,
        }

    @staticmethod
    def _zscore(s: pd.Series) -> pd.Series:
        std = s.std(ddof=0)
        if not std or pd.isna(std):
            return pd.Series(0.0, index=s.index)
        return (s - s.mean()) / std
