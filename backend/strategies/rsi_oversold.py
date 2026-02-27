"""RSI Oversold — RSI(14) < 35, potential mean-reversion bounce."""

import pandas as pd
from .base import BaseStrategy


def _rsi(close: pd.Series, period: int = 14) -> pd.Series:
    delta = close.diff()
    gain = delta.clip(lower=0).ewm(com=period - 1, min_periods=period).mean()
    loss = (-delta.clip(upper=0)).ewm(com=period - 1, min_periods=period).mean()
    rs = gain / loss
    return 100 - (100 / (1 + rs))


class RSIOversoldStrategy(BaseStrategy):
    name = "RSI Oversold"
    description = "Stocks where RSI(14) has dropped below 35 — oversold, potential bounce candidates."

    def __init__(self, threshold: float = 35):
        self.threshold = threshold

    def scan(self, symbol: str, data: pd.DataFrame) -> dict | None:
        close = data["Close"].squeeze()
        if len(close) < 20:
            return None

        rsi_val = float(_rsi(close).iloc[-1])
        if rsi_val < self.threshold:
            return {
                "ticker": symbol,
                "price": round(float(close.iloc[-1]), 2),
                "change_pct": self._price_change(close),
                "rsi": round(rsi_val, 1),
                "signal": f"RSI Oversold @ {rsi_val:.1f}",
                "strength": "Strong" if rsi_val < 25 else "Moderate",
                "metric_label": "RSI(14)",
                "metric_value": f"{rsi_val:.1f}",
            }
        return None
