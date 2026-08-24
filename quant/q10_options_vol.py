"""Causal directional forecast from the published COIN options surface."""

from __future__ import annotations

from dataclasses import dataclass
import math


QUANT_ID = "q10_options_vol"
FORMULA_VERSION = "coin-options-skew-delta-v2"
HORIZON_SECONDS = (30, 60, 300, 900, 1800, 3600)
MAX_SIGNAL_BPS = 25.0
MAX_SURFACE_AGE_SECONDS = 30.0


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
        if (isinstance(self.event_epoch, bool) or
                not isinstance(self.event_epoch, (int, float)) or
                not math.isfinite(self.event_epoch)):
            raise ValueError("surface event_epoch must be finite")
        if self.event_epoch != min(item.event_epoch for item in observations):
            raise ValueError("surface event_epoch must be the earliest provider timestamp")
        if any(item.expiration != self.expiration for item in observations):
            raise ValueError("all option observations must use the surface expiration")
        if tuple(sorted(self.calls, key=lambda item: (item.strike, item.contract_symbol))) != self.calls:
            raise ValueError("calls must be sorted by strike and symbol")
        if tuple(sorted(self.puts, key=lambda item: (item.strike, item.contract_symbol))) != self.puts:
            raise ValueError("puts must be sorted by strike and symbol")


@dataclass(frozen=True, slots=True)
class OptionsVolResult:
    quant_id: str
    formula_version: str
    source_as_of_epoch: float
    forecast_bps: tuple[float, float, float, float, float, float]


def calculate_options_vol(
    surface: OptionSurface | None = None, *, cutoff_epoch: float | None = None,
) -> OptionsVolResult | None:
    """Calculate Q10 from an already-published, causal, fresh options surface."""

    if surface is None or cutoff_epoch is None:
        return None
    if isinstance(cutoff_epoch, bool) or not isinstance(cutoff_epoch, (int, float)):
        return None
    cutoff_epoch = float(cutoff_epoch)
    if not math.isfinite(cutoff_epoch) or not math.isfinite(surface.event_epoch):
        return None
    observations = surface.calls + surface.puts
    if any(
        cutoff_epoch - item.event_epoch < 0 or
        cutoff_epoch - item.event_epoch > MAX_SURFACE_AGE_SECONDS
        for item in observations
    ):
        return None

    call_ivs = tuple(float(item.implied_volatility) for item in surface.calls
                     if item.implied_volatility is not None and
                     math.isfinite(item.implied_volatility) and item.implied_volatility > 0)
    put_ivs = tuple(float(item.implied_volatility) for item in surface.puts
                    if item.implied_volatility is not None and
                    math.isfinite(item.implied_volatility) and item.implied_volatility > 0)
    call_deltas = tuple(float(item.delta) for item in surface.calls
                        if item.delta is not None and math.isfinite(item.delta))
    put_deltas = tuple(float(item.delta) for item in surface.puts
                       if item.delta is not None and math.isfinite(item.delta))
    if min(map(len, (call_ivs, put_ivs, call_deltas, put_deltas))) < 2:
        return None

    call_iv = sum(call_ivs) / len(call_ivs)
    put_iv = sum(put_ivs) / len(put_ivs)
    iv_denominator = call_iv + put_iv
    call_abs_delta = sum(map(abs, call_deltas)) / len(call_deltas)
    put_abs_delta = sum(map(abs, put_deltas)) / len(put_deltas)
    delta_denominator = call_abs_delta + put_abs_delta
    if iv_denominator <= 0 or delta_denominator <= 0:
        return None

    iv_asymmetry = (call_iv - put_iv) / iv_denominator
    delta_asymmetry = (call_abs_delta - put_abs_delta) / delta_denominator
    options_signal = 0.5 * iv_asymmetry + 0.5 * delta_asymmetry
    one_hour_bps = MAX_SIGNAL_BPS * options_signal
    forecasts = tuple(one_hour_bps * seconds / 3600 for seconds in HORIZON_SECONDS)
    if len(forecasts) != 6 or not all(map(math.isfinite, forecasts)):
        return None
    return OptionsVolResult(QUANT_ID, FORMULA_VERSION, surface.event_epoch, forecasts)


__all__ = [
    "FORMULA_VERSION", "HORIZON_SECONDS", "MAX_SIGNAL_BPS",
    "MAX_SURFACE_AGE_SECONDS", "OptionObservation", "OptionSurface",
    "OptionsVolResult", "QUANT_ID", "calculate_options_vol",
]