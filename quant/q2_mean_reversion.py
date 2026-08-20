"""Deterministic log-space mean-reversion equation."""

from __future__ import annotations

from dataclasses import dataclass
import math
import statistics

from .history import MidpointHistory
from .models import HORIZONS


QUANT_ID = "q2_mean_reversion"
FORMULA_VERSION = "log-mean-reversion-v1"
LOOKBACK_SECONDS = 3600
HORIZON_SECONDS = (30, 60, 300, 900, 1800, 3600)


@dataclass(frozen=True, slots=True)
class MeanReversionResult:
    quant_id: str
    formula_version: str
    cutoff_epoch: float
    forecast_bps: tuple[float | None, ...]


def calculate_mean_reversion(
    history: MidpointHistory, *, cutoff_epoch: float
) -> MeanReversionResult:
    """Estimate fixed-window AR(1) reversion for the exact-six horizons."""

    observations = history.within(
        cutoff=cutoff_epoch, lookback=LOOKBACK_SECONDS
    )
    unavailable = (None,) * len(HORIZONS)
    if len(observations) < 2:
        values = unavailable
    else:
        logs = tuple(math.log(item.midpoint) for item in observations)
        mean_log = statistics.fmean(logs)
        centered = tuple(value - mean_log for value in logs)
        denominator = sum(value * value for value in centered[:-1])
        if denominator <= 0:
            values = unavailable
        else:
            phi = sum(
                previous * current
                for previous, current in zip(centered, centered[1:])
            ) / denominator
            if not math.isfinite(phi):
                values = unavailable
            else:
                phi = min(max(phi, 0.0), 1.0)
                spacings = tuple(
                    current.event_epoch - previous.event_epoch
                    for previous, current in zip(
                        observations, observations[1:]
                    )
                    if current.event_epoch - previous.event_epoch > 0
                )
                if not spacings:
                    values = unavailable
                else:
                    spacing = statistics.median(spacings)
                    if not math.isfinite(spacing) or spacing <= 0:
                        values = unavailable
                    else:
                        current_deviation = centered[-1]
                        values = tuple(
                            10_000.0
                            * (phi ** (seconds / spacing) - 1.0)
                            * current_deviation
                            for seconds in HORIZON_SECONDS
                        )
    return MeanReversionResult(
        QUANT_ID, FORMULA_VERSION, cutoff_epoch, values
    )


__all__ = ["MeanReversionResult", "calculate_mean_reversion"]
