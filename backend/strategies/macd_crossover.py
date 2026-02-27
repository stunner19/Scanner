"""MACD Bullish Crossover — MACD line crossed above Signal in last 3 bars."""

import pandas as pd
from .base import BaseStrategy


class MACDCrossoverStrategy(BaseStrategy):
    name = "MACD Bullish Crossover"
    description = (
        "Stocks where MACD line crossed above its Signal line in the last 3 sessions."
    )

    def scan(self, symbol: str, data: pd.DataFrame) -> dict | None:
        close = data["Close"].squeeze()
        if len(close) < 40:
            return None

        ema12 = close.ewm(span=12, adjust=False).mean()
        ema26 = close.ewm(span=26, adjust=False).mean()
        macd = ema12 - ema26
        signal = macd.ewm(span=9, adjust=False).mean()
        hist = macd - signal

        for i in range(-3, 0):
            if macd.iloc[i - 1] < signal.iloc[i - 1] and macd.iloc[i] > signal.iloc[i]:
                h = round(float(hist.iloc[-1]), 4)
                return {
                    "ticker": symbol,
                    "price": round(float(close.iloc[-1]), 2),
                    "change_pct": self._price_change(close),
                    "macd": round(float(macd.iloc[-1]), 4),
                    "signal_line": round(float(signal.iloc[-1]), 4),
                    "histogram": h,
                    "signal": "MACD Bullish Crossover",
                    "strength": "Strong" if h > 0 else "Moderate",
                    "metric_label": "Histogram",
                    "metric_value": f"{h:+.3f}",
                }
        return None
