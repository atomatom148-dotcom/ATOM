"""Immutable numerical midpoint history for deterministic quant equations."""

from __future__ import annotations

from dataclasses import dataclass
import math
from typing import Iterable


@dataclass(frozen=True, slots=True)
class MidpointObservation:
    """One already-calculated midpoint at its market event time."""

    event_epoch: float
    midpoint: float

    def __post_init__(self) -> None:
        if not math.isfinite(self.event_epoch):
            raise ValueError("event_epoch must be finite")
        if not math.isfinite(self.midpoint) or self.midpoint <= 0:
            raise ValueError("midpoint must be finite and greater than zero")


@dataclass(frozen=True, slots=True, init=False)
class MidpointHistory:
    """Strictly chronological, immutable midpoint observations."""

    _observations: tuple[MidpointObservation, ...]

    def __init__(self, observations: Iterable[MidpointObservation] = ()) -> None:
        copied = tuple(observations)
        if any(not isinstance(item, MidpointObservation) for item in copied):
            raise TypeError("observations must be MidpointObservation instances")
        if any(
            current.event_epoch >= following.event_epoch
            for current, following in zip(copied, copied[1:])
        ):
            raise ValueError("observations must be strictly chronological")
        object.__setattr__(self, "_observations", copied)

    @property
    def count(self) -> int:
        return len(self._observations)

    @property
    def latest(self) -> MidpointObservation | None:
        return self._observations[-1] if self._observations else None

    @property
    def observations(self) -> tuple[MidpointObservation, ...]:
        return self._observations

    def within(self, *, cutoff: float, lookback: float) -> tuple[MidpointObservation, ...]:
        """Return actual observations in the inclusive ``[cutoff-lookback, cutoff]`` window."""

        if not math.isfinite(cutoff):
            raise ValueError("cutoff must be finite")
        if not math.isfinite(lookback) or lookback < 0:
            raise ValueError("lookback must be finite and nonnegative")
        start = cutoff - lookback
        return tuple(
            observation
            for observation in self._observations
            if start <= observation.event_epoch <= cutoff
        )
