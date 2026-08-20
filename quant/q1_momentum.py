"""Deterministic direct log-momentum equation."""

from __future__ import annotations

from dataclasses import dataclass
import math

from .history import MidpointHistory
from .models import HORIZONS


QUANT_ID = "q1_momentum"
FORMULA_VERSION = "direct-log-momentum-v1"
HORIZON_SECONDS = (30, 60, 300, 900, 1800, 3600)


@dataclass(frozen=True, slots=True)
class MomentumResult:
    quant_id: str
    formula_version: str
    cutoff_epoch: float
    forecast_bps: tuple[float | None, ...]


def calculate_momentum(
    history: MidpointHistory, *, cutoff_epoch: float
) -> MomentumResult:
    """Return direct historical log returns for the exact-six horizons."""

    if not math.isfinite(cutoff_epoch):
        raise ValueError("cutoff_epoch must be finite")
    eligible = tuple(
        observation
        for observation in history.observations
        if observation.event_epoch <= cutoff_epoch
    )
    values: list[float | None] = []
    if not eligible:
        values = [None] * len(HORIZONS)
    else:
        current = eligible[-1]
        for seconds in HORIZON_SECONDS:
            target = current.event_epoch - seconds
            prior = next(
                (
                    observation
                    for observation in reversed(eligible)
                    if observation.event_epoch <= target
                ),
                None,
            )
            values.append(
                None
                if prior is None
                else 10_000.0 * math.log(current.midpoint / prior.midpoint)
            )
    return MomentumResult(
        QUANT_ID, FORMULA_VERSION, cutoff_epoch, tuple(values)
    )


__all__ = ["MomentumResult", "calculate_momentum"]
