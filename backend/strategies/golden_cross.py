"""Golden Cross — 50 SMA crossed above 200 SMA in last 5 bars."""

import pandas as pd
from .base import BaseStrategy


class GoldenCrossStrategy(BaseStrategy):
    name = "Golden Cross (50/200 SMA)"
    description = "Stocks where the 50-day SMA crossed above 200-day SMA — classic long-term bull signal."
    _period_days = 365  # need 1 year of data for 200-day SMA

    def scan(self, symbol: str, data: pd.DataFrame) -> dict | None:
        close = data["Close"].squeeze()
        if len(close) < 205:
            return None

        sma50 = close.rolling(50).mean()
        sma200 = close.rolling(200).mean()

        for i in range(-5, 0):
            p50, p200 = float(sma50.iloc[i - 1]), float(sma200.iloc[i - 1])
            c50, c200 = float(sma50.iloc[i]), float(sma200.iloc[i])
            if pd.isna(p50) or pd.isna(p200):
                continue
            if p50 < p200 and c50 > c200:
                gap = round(((c50 - c200) / c200) * 100, 2)
                return {
                    "ticker": symbol,
                    "price": round(float(close.iloc[-1]), 2),
                    "change_pct": self._price_change(close),
                    "sma_50": round(c50, 2),
                    "sma_200": round(c200, 2),
                    "signal": "Golden Cross",
                    "strength": "Strong",
                    "metric_label": "SMA50/200 Gap",
                    "metric_value": f"+{gap}%",
                }
        return None
