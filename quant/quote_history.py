"""Immutable top-of-book quote observations for depth-based quant equations."""

from __future__ import annotations

from dataclasses import dataclass
import math
from typing import Iterable


@dataclass(frozen=True, slots=True)
class QuoteObservation:
    """One actual top-of-book quote at its market event time."""

    event_epoch: float
    bid: float
    ask: float
    bid_size: float
    ask_size: float

    def __post_init__(self) -> None:
        values = (self.event_epoch, self.bid, self.ask, self.bid_size, self.ask_size)
        if any(isinstance(value, bool) or not isinstance(value, (int, float)) for value in values):
            raise ValueError("quote fields must be numerical")
        if not all(math.isfinite(float(value)) for value in values):
            raise ValueError("quote fields must be finite")
        if self.bid <= 0 or self.ask <= 0:
            raise ValueError("bid and ask must be positive")
        if self.ask < self.bid:
            raise ValueError("ask must be greater than or equal to bid")
        if self.bid_size < 0 or self.ask_size < 0:
            raise ValueError("quote sizes must be nonnegative")


@dataclass(frozen=True, slots=True, init=False)
class QuoteHistory:
    """Strictly chronological, immutable actual quote observations."""

    _observations: tuple[QuoteObservation, ...]

    def __init__(self, observations: Iterable[QuoteObservation] = ()) -> None:
        copied = tuple(observations)
        if any(not isinstance(item, QuoteObservation) for item in copied):
            raise TypeError("observations must be QuoteObservation instances")
        if any(a.event_epoch >= b.event_epoch for a, b in zip(copied, copied[1:])):
            raise ValueError("observations must be strictly chronological")
        object.__setattr__(self, "_observations", copied)

    @property
    def observations(self) -> tuple[QuoteObservation, ...]:
        return self._observations

    def within(self, *, cutoff: float, lookback: float) -> tuple[QuoteObservation, ...]:
        if not math.isfinite(cutoff):
            raise ValueError("cutoff must be finite")
        if not math.isfinite(lookback) or lookback < 0:
            raise ValueError("lookback must be finite and nonnegative")
        start = cutoff - lookback
        return tuple(item for item in self._observations if start <= item.event_epoch <= cutoff)


__all__ = ["QuoteHistory", "QuoteObservation"]
