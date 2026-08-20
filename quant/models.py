"""Core types for ATOM V9 Thin. Keep small."""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Optional


HORIZONS = ("30S", "1M", "5M", "15M", "30M", "1H")


class SetupState(str, Enum):
    QUALIFIED = "QUALIFIED"
    BLOCKED = "BLOCKED"
    UNAVAILABLE = "UNAVAILABLE"
    NO_SETUP = "NO_SETUP"


@dataclass
class Snapshot:
    """Point-in-time market input. Invalid/missing fields => UNAVAILABLE downstream."""

    symbol: str
    asof_epoch: float
    last: Optional[float]
    bid: Optional[float] = None
    ask: Optional[float] = None
    bar_close: Optional[float] = None
    source: str = "unknown"
    fresh: bool = False
    reason_codes: list[str] = field(default_factory=list)

    def is_usable(self) -> bool:
        return bool(self.fresh and self.last is not None and self.last > 0)


@dataclass
class HorizonForecast:
    """Evidence for one horizon, including its expected midpoint log return.

    ``forecast_bps`` uses ``10^4 * ln(m(t+h) / m(t))`` for this exact horizon.
    """

    horizon: str
    setup_state: SetupState
    direction: Optional[str] = None  # "UP" | "DOWN" | None
    probability: Optional[float] = None
    reason_codes: list[str] = field(default_factory=list)
    cutoff_epoch: float = 0.0
    maturity_epoch: float = 0.0
    forecast_bps: float | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "horizon": self.horizon,
            "setup_state": self.setup_state.value,
            "direction": self.direction,
            "probability": self.probability,
            "reason_codes": list(self.reason_codes),
            "cutoff_epoch": self.cutoff_epoch,
            "maturity_epoch": self.maturity_epoch,
            "forecast_bps": self.forecast_bps,
        }


@dataclass
class ExactSixBundle:
    """One cycle = exactly six horizon rows with explicit quant evidence."""

    cycle_id: str
    symbol: str
    cutoff_epoch: float
    snapshot_hash: str
    policy_version: str
    rows: list[HorizonForecast]
    quant_id: str = "unified-quant"
    formula_version: str = "legacy"

    def __post_init__(self) -> None:
        if len(self.rows) != 6:
            raise ValueError("exact-six bundle requires exactly 6 rows")
        got = tuple(r.horizon for r in self.rows)
        if got != HORIZONS:
            raise ValueError(f"horizons must be {HORIZONS}, got {got}")

    def to_dict(self) -> dict[str, Any]:
        return {
            "cycle_id": self.cycle_id,
            "symbol": self.symbol,
            "cutoff_epoch": self.cutoff_epoch,
            "snapshot_hash": self.snapshot_hash,
            "policy_version": self.policy_version,
            "quant_id": self.quant_id,
            "formula_version": self.formula_version,
            "rows": [r.to_dict() for r in self.rows],
        }
