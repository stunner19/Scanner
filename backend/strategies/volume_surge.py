"""Volume Surge — 3x+ average volume with meaningful price move."""

import pandas as pd
from .base import BaseStrategy


class VolumeSurgeStrategy(BaseStrategy):
    name = "Volume Surge"
    description = "Stocks with 3× or more their 20-day average volume + 1.5%+ price move — institutional activity."

    def __init__(self, vol_mult: float = 3.0, min_change: float = 1.5):
        self.vol_mult = vol_mult
        self.min_change = min_change

    def scan(self, symbol: str, data: pd.DataFrame) -> dict | None:
        close = data["Close"].squeeze()
        volume = data["Volume"].squeeze()
        if len(close) < 25:
            return None

        avg_vol = float(volume.iloc[-21:-1].mean())
        cur_vol = float(volume.iloc[-1])
        price = float(close.iloc[-1])
        chg = self._price_change(close)
        vol_ratio = round(cur_vol / avg_vol, 2) if avg_vol > 0 else 0

        if vol_ratio >= self.vol_mult and abs(chg) >= self.min_change:
            direction = "Bullish" if chg > 0 else "Bearish"
            return {
                "ticker": symbol,
                "price": round(price, 2),
                "change_pct": chg,
                "volume_ratio": vol_ratio,
                "avg_volume": int(avg_vol),
                "current_volume": int(cur_vol),
                "signal": f"{direction} Volume Surge ({vol_ratio}× avg)",
                "strength": "Strong" if vol_ratio >= 5 else "Moderate",
                "metric_label": "Vol Ratio",
                "metric_value": f"{vol_ratio}×",
            }
        return None
