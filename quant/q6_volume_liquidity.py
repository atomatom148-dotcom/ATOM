"""Deterministic quote spread-depth liquidity equation."""

from __future__ import annotations

from dataclasses import dataclass

from .quote_history import QuoteHistory, QuoteObservation


QUANT_ID = "q6_volume_liquidity"
FORMULA_VERSION = "spread-depth-liquidity-v1"
LOOKBACK_SECONDS = 300
HORIZON_MULTIPLIERS = (5.0, 7.5, 10.0, 12.5, 15.0, 17.5)


@dataclass(frozen=True, slots=True)
class VolumeLiquidityResult:
    quant_id: str
    formula_version: str
    cutoff_epoch: float
    forecast_bps: tuple[float, ...]
    liquidity_factor: float
    mean_relative_spread_bps: float
    mean_depth: float


def quote_liquidity(quote: QuoteObservation) -> tuple[float, float, float] | None:
    """Return relative spread BPS, depth, and depth imbalance for one quote."""

    midpoint = (quote.bid + quote.ask) / 2.0
    depth = quote.bid_size + quote.ask_size
    if depth <= 0:
        return None
    return 10_000.0 * (quote.ask - quote.bid) / midpoint, depth, (quote.bid_size - quote.ask_size) / depth


def calculate_volume_liquidity(history: QuoteHistory, *, cutoff_epoch: float) -> VolumeLiquidityResult | None:
    """Map causal five-minute quote liquidity to exact-six BPS forecasts."""

    observations = history.within(cutoff=cutoff_epoch, lookback=LOOKBACK_SECONDS)
    if len(observations) < 2:
        return None
    values = tuple(quote_liquidity(item) for item in observations)
    if any(value is None for value in values):
        return None
    valid = tuple(value for value in values if value is not None)
    mean_spread = sum(value[0] for value in valid) / len(valid)
    mean_depth = sum(value[1] for value in valid) / len(valid)
    mean_imbalance = sum(value[2] for value in valid) / len(valid)
    liquidity_factor = mean_imbalance / (1.0 + mean_spread)
    forecasts = tuple(multiplier * liquidity_factor for multiplier in HORIZON_MULTIPLIERS)
    return VolumeLiquidityResult(
        QUANT_ID, FORMULA_VERSION, cutoff_epoch, forecasts,
        liquidity_factor, mean_spread, mean_depth,
    )


__all__ = ["VolumeLiquidityResult", "calculate_volume_liquidity", "quote_liquidity"]
