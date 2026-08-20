"""Minimal in-process telemetry for successful V9 observations."""

from dataclasses import dataclass
import threading

from .v9_math_core import V9MathInput, V9MathState


@dataclass(frozen=True, slots=True)
class V9ObservationTelemetry:
    status: str
    family_count: int
    non_null_variable_count: int
    as_of_epoch: float


_telemetry_lock = threading.Lock()
_latest_telemetry: V9ObservationTelemetry | None = None


def record_v9_observation(value: V9MathInput, state: V9MathState) -> None:
    """Atomically replace telemetry after a successful V9 evaluation."""

    telemetry = V9ObservationTelemetry(
        status=state.status,
        family_count=len(value.families),
        non_null_variable_count=sum(
            item is not None
            for family in value.families
            for item in family.horizon_values
        ),
        as_of_epoch=value.as_of_epoch,
    )
    global _latest_telemetry
    with _telemetry_lock:
        _latest_telemetry = telemetry


def latest_v9_observation() -> V9ObservationTelemetry | None:
    """Return the immutable latest successful observation, if one exists."""

    with _telemetry_lock:
        return _latest_telemetry


__all__ = ["V9ObservationTelemetry", "latest_v9_observation", "record_v9_observation"]
