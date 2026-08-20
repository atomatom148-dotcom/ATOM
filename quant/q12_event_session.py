"""Causal COIN US-equity-session equation."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, time
import math
from zoneinfo import ZoneInfo

from .history import MidpointHistory, MidpointObservation


QUANT_ID = "q12_event_session"
FORMULA_VERSION = "us-equity-session-v1"
HORIZON_SECONDS = (30, 60, 300, 900, 1800, 3600)
EASTERN = ZoneInfo("America/New_York")


@dataclass(frozen=True, slots=True)
class EventSessionResult:
    quant_id: str
    formula_version: str
    cutoff_epoch: float
    forecast_bps: tuple[float, ...]
    five_minute_return: float
    session_multiplier: float
    session_return: float


def _at_or_before(observations: tuple[MidpointObservation, ...], target: float) -> MidpointObservation | None:
    return next((item for item in reversed(observations) if item.event_epoch <= target), None)


def calculate_event_session(history: MidpointHistory, *, cutoff_epoch: float) -> EventSessionResult | None:
    if not math.isfinite(cutoff_epoch):
        return None
    local_time = datetime.fromtimestamp(cutoff_epoch, EASTERN).time()
    if not time(9, 30) <= local_time < time(16):
        return None
    multiplier = 1.0 if local_time < time(10, 30) else 0.5 if local_time < time(14, 30) else 0.75
    causal = tuple(item for item in history.observations if item.event_epoch <= cutoff_epoch)
    current = _at_or_before(causal, cutoff_epoch)
    base = _at_or_before(causal, cutoff_epoch - 300)
    if current is None or base is None:
        return None
    five_minute_return = math.log(current.midpoint / base.midpoint)
    session_return = multiplier * five_minute_return
    forecasts = tuple(10_000 * session_return * min(horizon / 300, 1) for horizon in HORIZON_SECONDS)
    if not all(math.isfinite(value) for value in (five_minute_return, session_return, *forecasts)):
        return None
    return EventSessionResult(
        QUANT_ID, FORMULA_VERSION, cutoff_epoch, forecasts,
        five_minute_return, multiplier, session_return,
    )


__all__ = ["EventSessionResult", "calculate_event_session"]
