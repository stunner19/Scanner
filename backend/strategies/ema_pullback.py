"""EMA Pullback — uptrending stock pulling back to touch 20 EMA."""

import pandas as pd
from .base import BaseStrategy


class EMAPullbackStrategy(BaseStrategy):
    name = "EMA Pullback (Trend Dip)"
    description = "Stocks in an uptrend (above 50 EMA) pulling back to the 20 EMA — buy-the-dip setup."

    def __init__(self, tolerance_pct: float = 1.5):
        self.tolerance_pct = tolerance_pct

    def scan(self, symbol: str, data: pd.DataFrame) -> dict | None:
        close = data["Close"].squeeze()
        if len(close) < 55:
            return None

        ema20 = close.ewm(span=20, adjust=False).mean()
        ema50 = close.ewm(span=50, adjust=False).mean()

        price = float(close.iloc[-1])
        e20 = float(ema20.iloc[-1])
        e50 = float(ema50.iloc[-1])

        in_uptrend = price > e50 and e20 > e50
        dist_from_e20 = round(((price - e20) / e20) * 100, 2)
        touching = -self.tolerance_pct <= dist_from_e20 <= self.tolerance_pct * 2

        if in_uptrend and touching:
            return {
                "ticker": symbol,
                "price": round(price, 2),
                "change_pct": self._price_change(close),
                "ema_20": round(e20, 2),
                "ema_50": round(e50, 2),
                "dist_from_ema": dist_from_e20,
                "signal": f"EMA20 Pullback ({dist_from_e20:+.1f}%)",
                "strength": "Strong" if abs(dist_from_e20) < 0.5 else "Moderate",
                "metric_label": "Δ EMA20",
                "metric_value": f"{dist_from_e20:+.1f}%",
            }
        return None
