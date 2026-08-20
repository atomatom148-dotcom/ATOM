"""Deterministic realized-volatility equation."""

from __future__ import annotations

from dataclasses import dataclass
import math

from .history import MidpointHistory
from .models import HORIZONS


QUANT_ID = "q3_volatility"
FORMULA_VERSION = "realized-volatility-v1"
LOOKBACK_SECONDS = 3600


@dataclass(frozen=True, slots=True)
class VolatilityResult:
    quant_id: str
    formula_version: str
    cutoff_epoch: float
    volatility_bps: tuple[float | None, ...]


def calculate_volatility(
    history: MidpointHistory, *, cutoff_epoch: float
) -> VolatilityResult:
    """Return realized log-return volatility as auxiliary exact-six evidence."""

    observations = history.within(
        cutoff=cutoff_epoch, lookback=LOOKBACK_SECONDS
    )
    if len(observations) < 2:
        values: tuple[float | None, ...] = (None,) * len(HORIZONS)
    else:
        realized_variance = sum(
            math.log(current.midpoint / previous.midpoint) ** 2
            for previous, current in zip(observations, observations[1:])
        )
        volatility_bps = 10_000.0 * math.sqrt(realized_variance)
        values = (volatility_bps,) * len(HORIZONS)
    return VolatilityResult(QUANT_ID, FORMULA_VERSION, cutoff_epoch, values)


__all__ = ["VolatilityResult", "calculate_volatility"]
