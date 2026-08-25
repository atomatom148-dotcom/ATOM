"""Deterministic top-book queue-imbalance equation."""

from __future__ import annotations

from dataclasses import dataclass

from .models import HORIZONS
from .quote_history import QuoteHistory


QUANT_ID = "q5_microstructure"
FORMULA_VERSION = "top-book-imbalance-v1"
LOOKBACK_SECONDS = 60
HORIZON_MULTIPLIERS = (5.0, 7.5, 10.0, 12.5, 15.0, 17.5)


@dataclass(frozen=True, slots=True)
class MicrostructureResult:
    quant_id: str
    formula_version: str
    cutoff_epoch: float
    forecast_bps: tuple[float, ...]
    mean_imbalance: float
    source_as_of_epoch: float | None = None


def calculate_queue_imbalance(*, bid_size: float, ask_size: float) -> float | None:
    depth = bid_size + ask_size
    return None if depth <= 0 else (bid_size - ask_size) / depth


def calculate_microstructure(history: QuoteHistory, *, cutoff_epoch: float) -> MicrostructureResult | None:
    """Map the causal 60-second mean queue imbalance to exact-six BPS forecasts."""

    observations = history.within(cutoff=cutoff_epoch, lookback=LOOKBACK_SECONDS)
    if len(observations) < 2 or observations[-1].event_epoch != cutoff_epoch:
        return None
    imbalances = tuple(calculate_queue_imbalance(bid_size=item.bid_size, ask_size=item.ask_size) for item in observations)
    if any(value is None for value in imbalances):
        return None
    mean_imbalance = sum(imbalances) / len(imbalances)  # type: ignore[arg-type]
    forecasts = tuple(multiplier * mean_imbalance for multiplier in HORIZON_MULTIPLIERS)
    return MicrostructureResult(
        QUANT_ID, FORMULA_VERSION, cutoff_epoch, forecasts, mean_imbalance,
        source_as_of_epoch=observations[-1].event_epoch,
    )


__all__ = ["MicrostructureResult", "calculate_microstructure", "calculate_queue_imbalance"]
