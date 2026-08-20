"""Causal COIN volatility-attenuated trend-persistence equation."""

from __future__ import annotations

from dataclasses import dataclass
import math

from .history import MidpointHistory, MidpointObservation


QUANT_ID = "q11_regime"
FORMULA_VERSION = "coin-vol-trend-regime-v1"
HORIZON_SECONDS = (30, 60, 300, 900, 1800, 3600)
LOOKBACK_SECONDS = 900
MIN_OBSERVATIONS = 20


@dataclass(frozen=True, slots=True)
class RegimeResult:
    quant_id: str
    formula_version: str
    cutoff_epoch: float
    forecast_bps: tuple[float, ...]
    short_return: float
    long_return: float
    sigma: float
    trend_alignment: int
    volatility_attenuation: float
    regime_return: float


def _at_or_before(observations: tuple[MidpointObservation, ...], target: float) -> MidpointObservation | None:
    return next((item for item in reversed(observations) if item.event_epoch <= target), None)


def calculate_regime(history: MidpointHistory, *, cutoff_epoch: float) -> RegimeResult | None:
    if not math.isfinite(cutoff_epoch):
        return None
    causal = tuple(item for item in history.observations if item.event_epoch <= cutoff_epoch)
    current = _at_or_before(causal, cutoff_epoch)
    short_base = _at_or_before(causal, cutoff_epoch - 60)
    long_base = _at_or_before(causal, cutoff_epoch - LOOKBACK_SECONDS)
    window = tuple(item for item in causal if item.event_epoch >= cutoff_epoch - LOOKBACK_SECONDS)
    if current is None or short_base is None or long_base is None or len(window) < MIN_OBSERVATIONS:
        return None
    short_return = math.log(current.midpoint / short_base.midpoint)
    long_return = math.log(current.midpoint / long_base.midpoint)
    returns = tuple(math.log(item.midpoint / prior.midpoint) for prior, item in zip(window, window[1:]))
    if not returns:
        return None
    sigma = math.sqrt(sum(value * value for value in returns) / len(returns))
    product = short_return * long_return
    alignment = 1 if product > 0 else -1 if product < 0 else 0
    attenuation = 1 / (1 + 100 * sigma)
    regime_return = 0.5 * (short_return + long_return) * alignment * attenuation
    forecasts = tuple(10_000 * regime_return * min(horizon / 900, 1) for horizon in HORIZON_SECONDS)
    values = (short_return, long_return, sigma, attenuation, regime_return, *forecasts)
    if not all(math.isfinite(value) for value in values):
        return None
    return RegimeResult(
        QUANT_ID, FORMULA_VERSION, cutoff_epoch, forecasts, short_return,
        long_return, sigma, alignment, attenuation, regime_return,
    )


__all__ = ["RegimeResult", "calculate_regime"]
