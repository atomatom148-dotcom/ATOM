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


@dataclass(frozen=True, slots=True)
class OptionSurface:
    """One atomically publishable, real-contract COIN options surface."""

    event_epoch: float
    expiration: str
    calls: tuple[OptionObservation, ...]
    puts: tuple[OptionObservation, ...]

    def __post_init__(self) -> None:
        if len(self.calls) > 5 or len(self.puts) > 5:
            raise ValueError("an option surface contains at most five contracts per side")
        if not self.calls and not self.puts:
            raise ValueError("an option surface must contain a real snapshot")
        observations = self.calls + self.puts
        if any(item.expiration != self.expiration for item in observations):
            raise ValueError("all option observations must use the surface expiration")
        if tuple(sorted(self.calls, key=lambda item: (item.strike, item.contract_symbol))) != self.calls:
            raise ValueError("calls must be sorted by strike and symbol")
        if tuple(sorted(self.puts, key=lambda item: (item.strike, item.contract_symbol))) != self.puts:
            raise ValueError("puts must be sorted by strike and symbol")


def calculate_options_vol(
    observations: Iterable[OptionObservation] | None = None,
) -> None:
    """Return no forecast until a real options equation and live dataset exist."""

    # Deliberately do not substitute stock volatility or synthesize option fields.
    return None


__all__ = ["OptionObservation", "OptionSurface", "calculate_options_vol"]
