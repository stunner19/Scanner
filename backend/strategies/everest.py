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
import numpy as np
from .base import BaseStrategy


def _supertrend(
    df: pd.DataFrame, period: int = 7, multiplier: float = 3.0
) -> pd.Series:
    """
    Returns a boolean Series — True where Supertrend is green (bullish).
    Standard Supertrend algorithm using Wilder's smoothed ATR.
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

    # Final bands with carry-forward logic
    upper = upper_basic.copy()
    lower = lower_basic.copy()

    for i in range(1, len(df)):
        upper.iloc[i] = (
            upper_basic.iloc[i]
            if upper_basic.iloc[i] < upper.iloc[i - 1]
            or close.iloc[i - 1] > upper.iloc[i - 1]
            else upper.iloc[i - 1]
        )
        lower.iloc[i] = (
            lower_basic.iloc[i]
            if lower_basic.iloc[i] > lower.iloc[i - 1]
            or close.iloc[i - 1] < lower.iloc[i - 1]
            else lower.iloc[i - 1]
        )

    # Direction: 1 = green (bullish), -1 = red (bearish)
    direction = pd.Series(index=df.index, dtype=int)
    direction.iloc[period] = 1  # seed

    for i in range(period + 1, len(df)):
        prev = direction.iloc[i - 1]
        c = close.iloc[i]
        if prev == -1 and c > upper.iloc[i]:
            direction.iloc[i] = 1
        elif prev == 1 and c < lower.iloc[i]:
            direction.iloc[i] = -1
        else:
            direction.iloc[i] = prev

    # Supertrend line value (for display)
    st_line = pd.Series(index=df.index, dtype=float)
    for i in range(len(df)):
        st_line.iloc[i] = lower.iloc[i] if direction.iloc[i] == 1 else upper.iloc[i]

    return direction == 1, st_line


class EverestStrategy(BaseStrategy):
    name = "Advanced Everest"
    description = (
        "Close breaks above the 13-week high AND "
        "Supertrend(7,3) is green — strong momentum breakout setup."
    )
    _period_days = 120  # ~91 days for 13W high + buffer for ATR warmup

    def scan(self, symbol: str, data: pd.DataFrame) -> dict | None:
        if len(data) < 100:
            return None

        close = data["Close"]
        high = data["High"]

        # ── Condition 1: close > 13-week high (91 calendar days) ──────────
        # We use the last 65 trading days ≈ 13 weeks
        # Exclude today (iloc[-1]) — we want price to BREAK above prior high
        lookback = 65
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
