"""
Strategy registry — import and register all strategies here.

REMINDER: after adding a strategy here, also add it to STATIC_STRATEGIES in
frontend/index.html. That list is a hardcoded snapshot so the scanner UI
loads instantly without waiting on a backend round trip — it's not derived
from this file, so it goes stale silently if you forget.
"""

from .rsi_oversold import RSIOversoldStrategy
from .macd_crossover import MACDCrossoverStrategy
from .golden_cross import GoldenCrossStrategy
from .breakout import BreakoutStrategy
from .volume_surge import VolumeSurgeStrategy
from .ema_pullback import EMAPullbackStrategy
from .everest import EverestStrategy
from .sma34_pullback import SMA34PullbackStrategy
from .sleeve1_52w_volume import Sleeve1Strategy
from .sleeve2_momentum_ignition import Sleeve2Strategy

STRATEGIES: dict = {
    s.name: s
    for s in [
        RSIOversoldStrategy(),
        MACDCrossoverStrategy(),
        GoldenCrossStrategy(),
        BreakoutStrategy(),
        VolumeSurgeStrategy(),
        EMAPullbackStrategy(),
        EverestStrategy(),
        SMA34PullbackStrategy(),
        Sleeve1Strategy(),
        Sleeve2Strategy(),
    ]
}


def get_strategy(name: str):
    return STRATEGIES.get(name)


def get_strategy_list() -> list[dict]:
    return [{"name": s.name, "description": s.description} for s in STRATEGIES.values()]
