"""Read-only synchronized numerical inputs for G2 Phase A."""

from __future__ import annotations

from dataclasses import dataclass
import math

from .history import MidpointHistory, MidpointObservation
from .models import HORIZONS


HORIZON_SECONDS = (30, 60, 300, 900, 1800, 3600)
MAX_HISTORY_SECONDS = 3600.0
_EMPTY_SIX = (None,) * 6


@dataclass(frozen=True, slots=True)
class CrossAssetState:
    """One immutable view of the four assets knowable at a common cutoff."""

    as_of_epoch: float
    btc_price: float | None
    coin_price: float | None
    qqq_price: float | None
    ndx_price: float | None
    btc_return_bps: tuple[float | None, ...]
    coin_return_bps: tuple[float | None, ...]
    qqq_return_bps: tuple[float | None, ...]
    ndx_return_bps: tuple[float | None, ...]
    btc_usd_move: tuple[float | None, ...]

    def __post_init__(self) -> None:
        if not math.isfinite(self.as_of_epoch):
            raise ValueError("as_of_epoch must be finite")
        vectors = (
            self.btc_return_bps, self.coin_return_bps, self.qqq_return_bps,
            self.ndx_return_bps, self.btc_usd_move,
        )
        if any(len(vector) != len(HORIZONS) for vector in vectors):
            raise ValueError("every horizon vector must use the exact six horizons")


def _asset_values(
    history: MidpointHistory, cutoff_epoch: float,
) -> tuple[float | None, tuple[float | None, ...], tuple[float | None, ...]]:
    eligible = tuple(
        item for item in history.observations if item.event_epoch <= cutoff_epoch
    )
    if not eligible:
        return None, _EMPTY_SIX, _EMPTY_SIX
    current = eligible[-1]
    returns: list[float | None] = []
    moves: list[float | None] = []
    for seconds in HORIZON_SECONDS:
        target = current.event_epoch - seconds
        prior = next(
            (item for item in reversed(eligible) if item.event_epoch <= target), None,
        )
        returns.append(
            None if prior is None
            else 10_000.0 * math.log(current.midpoint / prior.midpoint)
        )
        moves.append(None if prior is None else current.midpoint - prior.midpoint)
    return current.midpoint, tuple(returns), tuple(moves)


def synchronize(
    *, as_of_epoch: float, btc: MidpointHistory, coin: MidpointHistory,
    qqq: MidpointHistory, ndx: MidpointHistory,
) -> CrossAssetState:
    """Build a state using only observations at or before ``as_of_epoch``."""

    if not math.isfinite(as_of_epoch):
        raise ValueError("as_of_epoch must be finite")
    btc_price, btc_returns, btc_moves = _asset_values(btc, as_of_epoch)
    coin_price, coin_returns, _ = _asset_values(coin, as_of_epoch)
    qqq_price, qqq_returns, _ = _asset_values(qqq, as_of_epoch)
    ndx_price, ndx_returns, _ = _asset_values(ndx, as_of_epoch)
    return CrossAssetState(
        as_of_epoch, btc_price, coin_price, qqq_price, ndx_price,
        btc_returns, coin_returns, qqq_returns, ndx_returns, btc_moves,
    )


def append_bounded(
    history: MidpointHistory, observation: MidpointObservation,
) -> MidpointHistory:
    """Append a chronological price and retain at most the required hour."""

    old = history.observations
    if old and observation.event_epoch <= old[-1].event_epoch:
        raise ValueError("observation must be newer than history")
    boundary = observation.event_epoch - MAX_HISTORY_SECONDS
    return MidpointHistory(
        item for item in old + (observation,) if item.event_epoch >= boundary
    )


assert len(HORIZONS) == len(HORIZON_SECONDS) == 6

__all__ = ["CrossAssetState", "HORIZON_SECONDS", "MAX_HISTORY_SECONDS",
           "append_bounded", "synchronize"]
