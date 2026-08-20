"""Options observation contract for the intentionally inactive Q10 family."""

from __future__ import annotations

from dataclasses import dataclass
import math
from typing import Iterable


QUANT_ID = "q10_options_vol"
FORMULA_VERSION = "options-volatility-v1"


@dataclass(frozen=True, slots=True)
class OptionObservation:
    contract_symbol: str
    event_epoch: float
    strike: float
    expiration_epoch: float
    expiration: str
    premium: float | None
    implied_volatility: float | None
    delta: float | None
    gamma: float | None
    theta: float | None
    vega: float | None
    bid: float | None
    ask: float | None

    def __post_init__(self) -> None:
        required = (self.event_epoch, self.strike, self.expiration_epoch)
        optional = (self.premium, self.implied_volatility, self.delta, self.gamma,
                    self.theta, self.vega, self.bid, self.ask)
        if not self.contract_symbol or not isinstance(self.contract_symbol, str):
            raise ValueError("contract_symbol is required")
        if not self.expiration or not isinstance(self.expiration, str):
            raise ValueError("expiration is required")
        if any(isinstance(value, bool) or not isinstance(value, (int, float)) for value in required):
            raise ValueError("required option fields must be numerical")
        if any(value is not None and (isinstance(value, bool) or not isinstance(value, (int, float))) for value in optional):
            raise ValueError("available option values must be numerical")
        if not all(math.isfinite(value) for value in required + tuple(value for value in optional if value is not None)):
            raise ValueError("available option fields must be finite")
        if self.strike <= 0:
            raise ValueError("strike must be greater than zero")
        if self.expiration_epoch <= self.event_epoch:
            raise ValueError("expiration must be after the event")
        if self.premium is not None and self.premium < 0:
            raise ValueError("premium must be nonnegative")
        if self.implied_volatility is not None and self.implied_volatility < 0:
            raise ValueError("premium and implied volatility must be nonnegative")
        if self.bid is not None and self.bid < 0:
            raise ValueError("bid must be nonnegative")
        if self.ask is not None and self.ask < 0:
            raise ValueError("ask must be nonnegative")

    @property
    def spread(self) -> float | None:
        if self.bid is None or self.ask is None or self.ask < self.bid:
            return None
        return self.ask - self.bid


def calculate_options_vol(
    observations: Iterable[OptionObservation] | None = None,
) -> None:
    """Return no forecast until a real options equation and live dataset exist."""

    # Deliberately do not substitute stock volatility or synthesize option fields.
    return None


__all__ = ["OptionObservation", "calculate_options_vol"]
