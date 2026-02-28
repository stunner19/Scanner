"""Strategy registry — import and register all strategies here."""

from .rsi_oversold import RSIOversoldStrategy
from .macd_crossover import MACDCrossoverStrategy
from .golden_cross import GoldenCrossStrategy
from .breakout import BreakoutStrategy
from .volume_surge import VolumeSurgeStrategy
from .ema_pullback import EMAPullbackStrategy
from .everest import EverestStrategy

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
    ]
}


def get_strategy(name: str):
    return STRATEGIES.get(name)


def get_strategy_list() -> list[dict]:
    return [{"name": s.name, "description": s.description} for s in STRATEGIES.values()]
