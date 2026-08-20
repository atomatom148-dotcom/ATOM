"""Causal COIN-versus-QQQ relative-return reversion equation."""

from __future__ import annotations

from dataclasses import dataclass
import math

from .history import MidpointHistory, MidpointObservation


QUANT_ID = "q7_relative_value"
FORMULA_VERSION = "coin-qqq-relative-return-v1"
HORIZON_SECONDS = (30, 60, 300, 900, 1800, 3600)
LOOKBACK_SECONDS = 900
MAX_QQQ_AGE_SECONDS = 5
MIN_SYNCHRONIZED_OBSERVATIONS = 20
TAU_SECONDS = 900


@dataclass(frozen=True, slots=True)
class RelativeValueResult:
    quant_id: str
    formula_version: str
    cutoff_epoch: float
    forecast_bps: tuple[float, ...]
    relative_mean: float
    relative_displacement: float


def _synchronize(
    coin: tuple[MidpointObservation, ...], qqq: tuple[MidpointObservation, ...]
) -> tuple[tuple[MidpointObservation, MidpointObservation], ...]:
    pairs: list[tuple[MidpointObservation, MidpointObservation]] = []
    qqq_index = -1
    for coin_item in coin:
        while qqq_index + 1 < len(qqq) and qqq[qqq_index + 1].event_epoch <= coin_item.event_epoch:
            qqq_index += 1
        if qqq_index >= 0 and coin_item.event_epoch - qqq[qqq_index].event_epoch <= MAX_QQQ_AGE_SECONDS:
            pairs.append((coin_item, qqq[qqq_index]))
    return tuple(pairs)


def calculate_relative_value(
    coin_history: MidpointHistory, qqq_history: MidpointHistory, *, cutoff_epoch: float
) -> RelativeValueResult | None:
    """Estimate deterministic reversion of the 900-second relative displacement."""

    if not math.isfinite(cutoff_epoch):
        return None
    coin = coin_history.within(cutoff=cutoff_epoch, lookback=LOOKBACK_SECONDS)
    qqq = tuple(item for item in qqq_history.observations if item.event_epoch <= cutoff_epoch)
    pairs = _synchronize(coin, qqq)
    if len(pairs) < MIN_SYNCHRONIZED_OBSERVATIONS:
        return None
    relative_returns = tuple(
        math.log(current[0].midpoint / previous[0].midpoint)
        - math.log(current[1].midpoint / previous[1].midpoint)
        for previous, current in zip(pairs, pairs[1:])
    )
    if not relative_returns or not all(math.isfinite(value) for value in relative_returns):
        return None
    relative_mean = sum(relative_returns) / len(relative_returns)
    displacement = sum(value - relative_mean for value in relative_returns)
    forecasts = tuple(
        10_000.0 * -(1.0 - math.exp(-seconds / TAU_SECONDS)) * displacement
        for seconds in HORIZON_SECONDS
    )
    if not all(math.isfinite(value) for value in (relative_mean, displacement, *forecasts)):
        return None
    return RelativeValueResult(
        QUANT_ID, FORMULA_VERSION, cutoff_epoch, forecasts,
        relative_mean, displacement,
    )


__all__ = ["RelativeValueResult", "calculate_relative_value"]
