"""
Sleeve 2 — Momentum Ignition

Weekly rotation strategy, rebalanced only after Friday close. Same universe
and eligibility rules as Sleeve 1 (liquid, trend-confirmed Nifty 500 names),
but no breadth/regime gate, and a different score:

  ret_63d         = close ÷ close.shift(63) − 1
  momentum_accel  = ret_63d − ret_63d.shift(63)
  score           = z(ret_63d) + 1.5 × z(momentum_accel)

Cross-sectionally scored, so this overrides run()/run_stream() instead of
scan(), same as Sleeve 1.

Pipeline:
  1. Fetch OHLCV for every ticker in the universe.
  2. Per stock, compute liquid_ok (trailing-60d avg traded value >= 1cr,
     <=2 zero-volume days in that window, close >= 20, >=260d of history)
     and above_sma200 (close > 200-day SMA).
  3. Friday gate: the latest trading day across all fetched data must be a
     Friday — fetch_ohlcv already rolls back to the prior close before
     15:30 IST, so this also enforces "after Friday close" for free.
  4. Eligible set = liquid_ok AND above_sma200. Cross-sectional z-scores of
     ret_63d and momentum_accel are computed over this set; score is their
     weighted sum. Only score > 0 stocks are ranked and returned.
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
SMA_TREND = 200
RET_LOOKBACK = 63
ACCEL_WEIGHT = 1.5


class Sleeve2Strategy(BaseStrategy):
    name = "Sleeve 2 — Momentum Ignition"
    description = (
        "Weekly (Friday close) rotation across liquid Nifty 500 names in a "
        "confirmed uptrend, ranked by 63-day return blended with its "
        "acceleration versus the prior 63-day period."
    )
    _period_days = 420  # ~285 trading days — covers the 260d history + 2x63d lookbacks with margin

    def scan(self, symbol: str, data: pd.DataFrame) -> dict | None:
        # Scored cross-sectionally, not per-symbol — see run_stream().
        raise NotImplementedError("Sleeve2Strategy scores the whole universe at once; use run_stream().")

    def run(self, tickers: list) -> list:
        return list(self.run_stream(tickers))

    def run_stream(self, tickers: list):
        symbols = [self._clean(t) for t in tickers]
        total = len(symbols)

        log.info(f"Sleeve 2: fetching {total} stocks")

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
                f"Sleeve 2 only rebalances after Friday close. Latest available "
                f"trading day is {as_of:%Y-%m-%d} ({as_of:%A})."
            )

        liquid = {s: f for s, f in features.items() if f["liquid_ok"]}
        if not liquid:
            return

        eligible = {s: f for s, f in liquid.items() if f["above_sma200"]}
        if len(eligible) < 2:
            return

        ret_z = self._zscore(pd.Series({s: f["ret_63d"] for s, f in eligible.items()}))
        accel_z = self._zscore(pd.Series({s: f["momentum_accel"] for s, f in eligible.items()}))
        score = (ret_z + ACCEL_WEIGHT * accel_z).dropna()

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
                    f"Rank #{rank} · 63d return {f['ret_63d'] * 100:+.1f}% · "
                    f"accel {f['momentum_accel'] * 100:+.1f}pp"
                ),
                "strength": "Strong" if sc > 1 else "Moderate",
                "metric_label": "Score",
                "metric_value": f"{sc:+.2f}",
                "ret_63d": round(f["ret_63d"] * 100, 2),
                "momentum_accel": round(f["momentum_accel"] * 100, 2),
                "rank": rank,
            }

    def _compute_features(self, data: pd.DataFrame) -> dict | None:
        if data.empty or len(data) < MIN_HISTORY_DAYS:
            return None

        close = data["Close"]
        volume = data["Volume"]

        last_close = float(close.iloc[-1])

        sma200 = close.rolling(SMA_TREND).mean().iloc[-1]
        if pd.isna(sma200):
            return None

        ret_63d_series = close / close.shift(RET_LOOKBACK) - 1
        ret_63d = ret_63d_series.iloc[-1]
        ret_63d_prior = ret_63d_series.iloc[-1 - RET_LOOKBACK]
        if pd.isna(ret_63d) or pd.isna(ret_63d_prior):
            return None

        traded_value = (close * volume).tail(LIQUIDITY_LOOKBACK)
        zero_vol_days = int((volume.tail(LIQUIDITY_LOOKBACK) == 0).sum())
        liquid_ok = (
            traded_value.mean() >= MIN_AVG_TRADED_VALUE
            and zero_vol_days <= MAX_ZERO_VOLUME_DAYS
            and last_close >= PRICE_FLOOR
        )

        return {
            "as_of": data.index[-1].date(),
            "close": last_close,
            "change_pct": self._price_change(close),
            "liquid_ok": bool(liquid_ok),
            "above_sma200": bool(last_close > sma200),
            "ret_63d": ret_63d,
            "momentum_accel": ret_63d - ret_63d_prior,
        }

    @staticmethod
    def _zscore(s: pd.Series) -> pd.Series:
        std = s.std(ddof=0)
        if not std or pd.isna(std):
            return pd.Series(0.0, index=s.index)
        return (s - s.mean()) / std
