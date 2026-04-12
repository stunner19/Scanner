"""34 SMA Pullback — uptrend, daily candle touches 34 SMA, closes above it."""

import pandas as pd
from .base import BaseStrategy


class SMA34PullbackStrategy(BaseStrategy):
    name = "34 SMA Pullback"
    description = (
        "Stocks in an uptrend whose daily candle touches the 34 SMA and closes "
        "back above it — trend pullback continuation setup."
    )

    def scan(self, symbol: str, data: pd.DataFrame) -> dict | None:
        if len(data) < 55:
            return None

        open_ = data["Open"].squeeze()
        close = data["Close"].squeeze()
        high = data["High"].squeeze()
        low = data["Low"].squeeze()

        sma34 = close.rolling(34).mean()
        sma50 = close.rolling(50).mean()
        sma_now = float(sma34.iloc[-1])
        sma_prev = float(sma34.iloc[-6])
        sma50_now = float(sma50.iloc[-1])
        day_open = float(open_.iloc[-1])
        price = float(close.iloc[-1])
        day_high = float(high.iloc[-1])
        day_low = float(low.iloc[-1])

        if pd.isna(sma_now) or pd.isna(sma_prev) or pd.isna(sma50_now):
            return None

        # Define uptrend as price above the 34 SMA, 34 SMA rising,
        # and 34 SMA above the 50 SMA.
        in_uptrend = price > sma_now and sma_now > sma_prev and sma_now > sma50_now

        # Only the lower wick should touch the 34 SMA.
        lower_wick_touch = (
            day_low <= sma_now
            and day_open > sma_now
            and price > sma_now
            and day_high > sma_now
        )

        if not (in_uptrend and lower_wick_touch):
            return None

        dist_pct = round(((price - sma_now) / sma_now) * 100, 2)
        slope_pct = round(((sma_now - sma_prev) / sma_prev) * 100, 2)

        return {
            "ticker": symbol,
            "price": round(price, 2),
            "change_pct": self._price_change(close),
            "sma_34": round(sma_now, 2),
            "sma_50": round(sma50_now, 2),
            "dist_from_sma": dist_pct,
            "signal": f"Touched 34 SMA, closed above ({dist_pct:+.1f}%)",
            "strength": "Strong" if dist_pct <= 1.0 and slope_pct > 1.0 else "Moderate",
            "metric_label": "Δ 34 SMA",
            "metric_value": f"{dist_pct:+.1f}%",
        }
