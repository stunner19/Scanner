"""52-Week High Breakout — price within 2% of 52-week high."""

import pandas as pd
from .base import BaseStrategy


class BreakoutStrategy(BaseStrategy):
    name = "52-Week High Breakout"
    description = (
        "Stocks trading within 2% of their 52-week high — momentum breakout candidates."
    )
    _period_days = 365

    def __init__(self, threshold_pct: float = 2.0):
        self.threshold_pct = threshold_pct

    def scan(self, symbol: str, data: pd.DataFrame) -> dict | None:
        close = data["Close"].squeeze()
        high = data["High"].squeeze()
        volume = data["Volume"].squeeze()
        if len(close) < 50:
            return None

        w52_high = float(high.iloc[:-1].max())
        price = float(close.iloc[-1])
        dist_pct = round(((w52_high - price) / w52_high) * 100, 2)
        avg_vol = float(volume.iloc[-21:-1].mean())
        cur_vol = float(volume.iloc[-1])
        vol_ratio = round(cur_vol / avg_vol, 2) if avg_vol > 0 else 0

        if dist_pct <= self.threshold_pct:
            return {
                "ticker": symbol,
                "price": round(price, 2),
                "change_pct": self._price_change(close),
                "week52_high": round(w52_high, 2),
                "week52_low": round(float(close.min()), 2),
                "distance_pct": dist_pct,
                "volume_ratio": vol_ratio,
                "signal": f"Near 52W High ({dist_pct}% away)",
                "strength": "Strong" if dist_pct < 0.5 else "Moderate",
                "metric_label": "Dist. from High",
                "metric_value": f"{dist_pct}%",
            }
        return None
