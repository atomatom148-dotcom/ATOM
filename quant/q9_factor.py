"""Causal one-factor COIN-on-QQQ OLS equation."""

from __future__ import annotations

from dataclasses import dataclass
import math

from .history import MidpointHistory, MidpointObservation


QUANT_ID = "q9_factor"
FORMULA_VERSION = "coin-qqq-factor-ols-v1"
HORIZON_SECONDS = (30, 60, 300, 900, 1800, 3600)
LOOKBACK_SECONDS = 3600
MAX_QQQ_AGE_SECONDS = 5
MIN_SYNCHRONIZED_RETURNS = 30


@dataclass(frozen=True, slots=True)
class FactorResult:
    quant_id: str
    formula_version: str
    cutoff_epoch: float
    forecast_bps: tuple[float, ...]
    alpha: float
    beta: float
    current_qqq_return: float
    factor_return: float


def _synchronize(coin: tuple[MidpointObservation, ...], qqq: tuple[MidpointObservation, ...]):
    pairs = []
    qqq_index = -1
    for coin_item in coin:
        while qqq_index + 1 < len(qqq) and qqq[qqq_index + 1].event_epoch <= coin_item.event_epoch:
            qqq_index += 1
        if qqq_index >= 0 and coin_item.event_epoch - qqq[qqq_index].event_epoch <= MAX_QQQ_AGE_SECONDS:
            pairs.append((coin_item, qqq[qqq_index]))
    return tuple(pairs)


def calculate_factor(
    coin_history: MidpointHistory, qqq_history: MidpointHistory, *, cutoff_epoch: float
) -> FactorResult | None:
    """Fit the frozen QQQ factor and apply its latest synchronized return."""

    if not math.isfinite(cutoff_epoch):
        return None
    coin = coin_history.within(cutoff=cutoff_epoch, lookback=LOOKBACK_SECONDS)
    qqq = tuple(item for item in qqq_history.observations if item.event_epoch <= cutoff_epoch)
    pairs = _synchronize(coin, qqq)
    returns = tuple(
        (math.log(current[1].midpoint / previous[1].midpoint),
         math.log(current[0].midpoint / previous[0].midpoint))
        for previous, current in zip(pairs, pairs[1:])
    )
    if len(returns) < MIN_SYNCHRONIZED_RETURNS or not all(
        math.isfinite(value) for pair in returns for value in pair
    ):
        return None
    x_bar = sum(x for x, _ in returns) / len(returns)
    y_bar = sum(y for _, y in returns) / len(returns)
    denominator = sum((x - x_bar) ** 2 for x, _ in returns)
    if denominator <= 0:
        return None
    beta = sum((x - x_bar) * (y - y_bar) for x, y in returns) / denominator
    alpha = y_bar - beta * x_bar
    current_signal = returns[-1][0]
    factor_return = alpha + beta * current_signal
    forecasts = tuple(10_000.0 * factor_return * min(seconds / 60.0, 1.0) for seconds in HORIZON_SECONDS)
    if not all(math.isfinite(value) for value in (alpha, beta, factor_return, *forecasts)):
        return None
    return FactorResult(
        QUANT_ID, FORMULA_VERSION, cutoff_epoch, forecasts,
        alpha, beta, current_signal, factor_return,
    )


__all__ = ["FactorResult", "calculate_factor"]
