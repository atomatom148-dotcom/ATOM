"""Options observation contract for the intentionally inactive Q10 family."""

from __future__ import annotations

from dataclasses import dataclass
import math
from typing import Iterable


QUANT_ID = "q10_options_vol"
FORMULA_VERSION = "options-volatility-v1"


@dataclass(frozen=True, slots=True)
class OptionObservation:
    event_epoch: float
    strike: float
    expiration_epoch: float
    premium: float
    implied_volatility: float
    delta: float
    gamma: float
    theta: float
    vega: float
    bid: float
    ask: float

    def __post_init__(self) -> None:
        values = tuple(getattr(self, field) for field in self.__dataclass_fields__)
        if any(isinstance(value, bool) or not isinstance(value, (int, float)) for value in values):
            raise ValueError("all option fields must be numerical")
        if not all(math.isfinite(value) for value in values):
            raise ValueError("all option fields must be finite")
        if self.strike <= 0:
            raise ValueError("strike must be greater than zero")
        if self.expiration_epoch <= self.event_epoch:
            raise ValueError("expiration must be after the event")
        if self.premium < 0 or self.implied_volatility < 0:
            raise ValueError("premium and implied volatility must be nonnegative")
        if self.bid < 0 or self.ask < 0 or self.ask < self.bid:
            raise ValueError("bid/ask must be nonnegative and uncrossed")


def calculate_options_vol(
    observations: Iterable[OptionObservation] | None = None,
) -> None:
    """Return no forecast until a real options equation and live dataset exist."""

    # Deliberately do not substitute stock volatility or synthesize option fields.
    return None


__all__ = ["OptionObservation", "calculate_options_vol"]
