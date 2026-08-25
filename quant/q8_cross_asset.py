"""Causal fixed-lag QQQ-leads-COIN equation."""

from __future__ import annotations

from dataclasses import dataclass
import math

from .history import MidpointHistory, MidpointObservation


QUANT_ID = "q8_cross_asset"
FORMULA_VERSION = "qqq-lead-coin-v1"
HORIZON_SECONDS = (30, 60, 300, 900, 1800, 3600)
LOOKBACK_SECONDS = 3600
MAX_QQQ_AGE_SECONDS = 5
MIN_SYNCHRONIZED_RETURNS = 30
LEAD_LAGS_SECONDS = (30, 60)


@dataclass(frozen=True, slots=True)
class CrossAssetResult:
    quant_id: str
    formula_version: str
    cutoff_epoch: float
    forecast_bps: tuple[float, ...]
    beta_30: float
    beta_60: float
    current_qqq_return: float
    lead_signal: float
    source_as_of_epoch: float | None = None


def _synchronize(coin: tuple[MidpointObservation, ...], qqq: tuple[MidpointObservation, ...]):
    pairs = []
    qqq_index = -1
    for coin_item in coin:
        while qqq_index + 1 < len(qqq) and qqq[qqq_index + 1].event_epoch <= coin_item.event_epoch:
            qqq_index += 1
        if qqq_index >= 0 and coin_item.event_epoch - qqq[qqq_index].event_epoch <= MAX_QQQ_AGE_SECONDS:
            pairs.append((coin_item, qqq[qqq_index]))
    return tuple(pairs)


def calculate_cross_asset(
    coin_history: MidpointHistory, qqq_history: MidpointHistory, *, cutoff_epoch: float
) -> CrossAssetResult | None:
    """Fit both frozen lead coefficients and apply the latest causal QQQ return."""

    if not math.isfinite(cutoff_epoch):
        return None
    coin = coin_history.within(cutoff=cutoff_epoch, lookback=LOOKBACK_SECONDS)
    qqq = tuple(item for item in qqq_history.observations if item.event_epoch <= cutoff_epoch)
    pairs = _synchronize(coin, qqq)
    if not pairs or pairs[-1][0].event_epoch != cutoff_epoch:
        return None
    returns = tuple(
        (current[0].event_epoch,
         math.log(current[0].midpoint / previous[0].midpoint),
         math.log(current[1].midpoint / previous[1].midpoint))
        for previous, current in zip(pairs, pairs[1:])
    )
    if len(returns) < MIN_SYNCHRONIZED_RETURNS or not all(
        math.isfinite(value) for item in returns for value in item
    ):
        return None
    betas = []
    for lag in LEAD_LAGS_SECONDS:
        regression_pairs = []
        lagged_index = -1
        for ending, coin_return, _ in returns:
            while (lagged_index + 1 < len(returns) and
                   returns[lagged_index + 1][0] <= ending - lag):
                lagged_index += 1
            if lagged_index >= 0:
                regression_pairs.append((returns[lagged_index][2], coin_return))
        denominator = sum(x * x for x, _ in regression_pairs)
        if denominator <= 0:
            return None
        beta = sum(x * y for x, y in regression_pairs) / denominator
        if not math.isfinite(beta):
            return None
        betas.append(beta)
    current_signal = returns[-1][2]
    lead_signal = (sum(betas) / len(betas)) * current_signal
    forecasts = tuple(10_000.0 * lead_signal * min(seconds / 60.0, 1.0) for seconds in HORIZON_SECONDS)
    if not all(math.isfinite(value) for value in (current_signal, lead_signal, *forecasts)):
        return None
    return CrossAssetResult(
        QUANT_ID, FORMULA_VERSION, cutoff_epoch, forecasts,
        betas[0], betas[1], current_signal, lead_signal,
        source_as_of_epoch=pairs[-1][1].event_epoch,
    )


__all__ = ["CrossAssetResult", "calculate_cross_asset"]
