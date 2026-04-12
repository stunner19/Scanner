"""
Advanced Everest Strategy
Daily timeframe:
  1. Today's close > highest high of the previous 13 weeks (91 calendar days)
     — excludes today so we're breaking OUT above prior resistance
  2. Supertrend(7, 3) is currently green (price above supertrend line)

Supertrend calculation:
  - ATR period  : 7
  - Multiplier  : 3
  - Green means : close > supertrend line (bullish)
"""

import pandas as pd
from .base import BaseStrategy


def _supertrend(
    df: pd.DataFrame, period: int = 7, multiplier: float = 3.0
) -> tuple[pd.Series, pd.Series]:
    """
    Returns:
      - bullish: True where close is above the active Supertrend line
      - st_line: active Supertrend line

    Uses Wilder-style ATR and starts only once ATR values are available.
    """
    high = df["High"]
    low = df["Low"]
    close = df["Close"]

    # Wilder's smoothed ATR
    tr = pd.concat(
        [
            high - low,
            (high - close.shift(1)).abs(),
            (low - close.shift(1)).abs(),
        ],
        axis=1,
    ).max(axis=1)
    atr = tr.ewm(alpha=1 / period, min_periods=period, adjust=False).mean()

    hl2 = (high + low) / 2
    upper_basic = hl2 + multiplier * atr
    lower_basic = hl2 - multiplier * atr

    upper = pd.Series(index=df.index, dtype=float)
    lower = pd.Series(index=df.index, dtype=float)
    st_line = pd.Series(index=df.index, dtype=float)
    bullish = pd.Series(False, index=df.index, dtype=bool)

    first_valid = atr.first_valid_index()
    if first_valid is None:
        return bullish, st_line

    start = df.index.get_loc(first_valid)
    upper.iloc[start] = upper_basic.iloc[start]
    lower.iloc[start] = lower_basic.iloc[start]

    # Seed the initial state from price vs the lower band at the first valid bar.
    bullish.iloc[start] = close.iloc[start] >= lower.iloc[start]
    st_line.iloc[start] = lower.iloc[start] if bullish.iloc[start] else upper.iloc[start]

    for i in range(start + 1, len(df)):
        prev_upper = upper.iloc[i - 1]
        prev_lower = lower.iloc[i - 1]
        prev_close = close.iloc[i - 1]

        upper.iloc[i] = (
            upper_basic.iloc[i]
            if upper_basic.iloc[i] < prev_upper or prev_close > prev_upper
            else prev_upper
        )
        lower.iloc[i] = (
            lower_basic.iloc[i]
            if lower_basic.iloc[i] > prev_lower or prev_close < prev_lower
            else prev_lower
        )

        prev_bullish = bullish.iloc[i - 1]
        if prev_bullish:
            bullish.iloc[i] = close.iloc[i] >= lower.iloc[i]
        else:
            bullish.iloc[i] = close.iloc[i] > upper.iloc[i]

        st_line.iloc[i] = lower.iloc[i] if bullish.iloc[i] else upper.iloc[i]

    return bullish, st_line


class EverestStrategy(BaseStrategy):
    name = "Advanced Everest"
    description = (
        "Close breaks above the 13-week high AND "
        "Supertrend(7,3) is green — strong momentum breakout setup."
    )
    _period_days = 180  # enough trading bars for 13W breakout + indicator warmup

    def scan(self, symbol: str, data: pd.DataFrame) -> dict | None:
        lookback = 65  # ~13 trading weeks
        min_bars = lookback + 10  # breakout window + ATR warmup margin
        if len(data) < min_bars:
            return None

        close = data["Close"]
        high = data["High"]

        # ── Condition 1: close > 13-week high (91 calendar days) ──────────
        # We use the last 65 trading days ≈ 13 weeks
        # Exclude today (iloc[-1]) — we want price to BREAK above prior high
        prior_high = high.iloc[-(lookback + 1) : -1].max()
        today_close = float(close.iloc[-1])

        broke_out = today_close > float(prior_high)
        if not broke_out:
            return None

        # ── Condition 2: Supertrend(7, 3) is green ────────────────────────
        is_green, st_line = _supertrend(data, period=7, multiplier=3.0)

        if not bool(is_green.iloc[-1]):
            return None

        # ── Build result ──────────────────────────────────────────────────
        st_val = round(float(st_line.iloc[-1]), 2)
        pct_above_st = round(((today_close - st_val) / st_val) * 100, 2)
        pct_breakout = round(
            ((today_close - float(prior_high)) / float(prior_high)) * 100, 2
        )

        # Check if supertrend flipped green today (fresh signal = stronger)
        flipped_today = bool(is_green.iloc[-1]) and not bool(is_green.iloc[-2])
        strength = "Strong" if flipped_today or pct_breakout > 1.0 else "Moderate"

        return {
            "ticker": symbol,
            "price": round(today_close, 2),
            "change_pct": self._price_change(close),
            "signal": f"Everest Breakout +{pct_breakout}% above 13W high",
            "strength": strength,
            "metric_label": "Above ST(7,3)",
            "metric_value": f"+{pct_above_st}%",
            "week13_high": round(float(prior_high), 2),
            "supertrend": st_val,
            "st_flipped": flipped_today,
            "pct_breakout": pct_breakout,
        }
