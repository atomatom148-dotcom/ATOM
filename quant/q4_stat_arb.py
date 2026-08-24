"""Causal COIN-versus-QQQ residual-reversion equation."""

from __future__ import annotations

from dataclasses import dataclass
import math
from statistics import median

from .history import MidpointHistory, MidpointObservation
from .models import HORIZONS


QUANT_ID = "q4_stat_arb"
FORMULA_VERSION = "coin-market-residual-ar1-v2"
HORIZON_SECONDS = (30, 60, 300, 900, 1800, 3600)
LOOKBACK_SECONDS = 3600
MAX_QQQ_AGE_SECONDS = 5
MIN_SYNCHRONIZED_OBSERVATIONS = 20


@dataclass(frozen=True, slots=True)
class StatArbResult:
    quant_id: str
    formula_version: str
    cutoff_epoch: float
    source_as_of_epoch: float
    forecast_bps: tuple[float, ...]
    alpha: float
    beta: float
    phi: float
    current_residual: float
    median_spacing: float


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


def calculate_stat_arb(
    coin_history: MidpointHistory,
    qqq_history: MidpointHistory,
    *,
    cutoff_epoch: float,
) -> StatArbResult | None:
    """Estimate residual AR(1) reversion using only observations visible at cutoff."""

    coin = coin_history.within(cutoff=cutoff_epoch, lookback=LOOKBACK_SECONDS)
    qqq = tuple(item for item in qqq_history.observations if item.event_epoch <= cutoff_epoch)
    pairs = _synchronize(coin, qqq)
    if len(pairs) < MIN_SYNCHRONIZED_OBSERVATIONS:
        return None
    if cutoff_epoch - pairs[-1][1].event_epoch > MAX_QQQ_AGE_SECONDS:
        return None

    c = tuple(math.log(pair[0].midpoint) for pair in pairs)
    q = tuple(math.log(pair[1].midpoint) for pair in pairs)
    c_bar, q_bar = sum(c) / len(c), sum(q) / len(q)
    denominator = sum((value - q_bar) ** 2 for value in q)
    if denominator <= 0:
        return None
    beta = sum((q_value - q_bar) * (c_value - c_bar) for c_value, q_value in zip(c, q)) / denominator
    alpha = c_bar - beta * q_bar
    if not math.isfinite(alpha) or not math.isfinite(beta):
        return None

    residuals = tuple(c_value - alpha - beta * q_value for c_value, q_value in zip(c, q))
    ar_denominator = sum(previous**2 for previous in residuals[:-1])
    if ar_denominator <= 0:
        return None
    phi = sum(previous * current for previous, current in zip(residuals, residuals[1:])) / ar_denominator
    if not math.isfinite(phi):
        return None
    phi = min(1.0, max(0.0, phi))

    spacings = tuple(
        current[0].event_epoch - previous[0].event_epoch
        for previous, current in zip(pairs, pairs[1:])
        if current[0].event_epoch > previous[0].event_epoch
    )
    if not spacings:
        return None
    delta = median(spacings)
    if not math.isfinite(delta) or delta <= 0:
        return None
    current_residual = residuals[-1]
    forecasts = tuple(
        10_000.0 * (phi ** (seconds / delta) - 1.0) * current_residual
        for seconds in HORIZON_SECONDS
    )
    if not all(math.isfinite(value) for value in forecasts):
        return None
    return StatArbResult(
        QUANT_ID, FORMULA_VERSION, cutoff_epoch, pairs[-1][1].event_epoch, forecasts,
        alpha, beta, phi, current_residual, delta,
    )


__all__ = ["StatArbResult", "calculate_stat_arb"]