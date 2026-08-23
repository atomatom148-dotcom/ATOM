"""V4D orchestration for the frozen ATOM TRUE V9 components.

This module deliberately contains no forecasting or calibration mathematics.  The
live coordinator captures upstream values once, calls V3, durably records each
horizon independently, reads one compact immutable V4 state, and applies the
frozen V4C live transformation.  State building and outcome resolution are
separate entry points so neither can accidentally enter a request path.
"""

from __future__ import annotations

from collections import Counter, deque
from dataclasses import dataclass
from datetime import datetime, timezone
import math
import threading
import time
from typing import Callable, Mapping, Protocol

from quant.v9_v1_contract import HORIZONS, V1Input
from quant.v9_v2d_evidence_state import V2EvidenceState
from quant.v9_v3_synthesis import (
    CANONICAL_FAMILIES, V3Output, _eligible_v1_slot, synthesize_v3,
)
from quant.v9_v4a_evidence import (
    ForecastRecord, OutcomeRecord, V4AWriter, build_forecast, build_outcome,
)
from quant.v9_v4b_accuracy import AccuracyState, HorizonAccuracyState
from quant.v9_v4c_predictive import (
    CompactHorizonState, FinalNumbers, V4CState, final_numbers,
)


class CompactStateLookup(Protocol):
    def __call__(self, *, symbol: str, cohort_id: str,
                 requested_cutoff: datetime) -> tuple[V4CState | None, str]: ...


@dataclass(frozen=True, slots=True)
class PersistenceResult:
    horizon: str
    status: str
    forecast: ForecastRecord
    latency_ms: float
    error_type: str | None = None


@dataclass(frozen=True, slots=True)
class V4DCycleOutput:
    cycle_id: str
    symbol: str
    cutoff_at: datetime
    v1: V1Input
    v2: V2EvidenceState
    v3: V3Output
    final_numbers: tuple[FinalNumbers, ...]
    accuracy: tuple[HorizonAccuracyState | None, ...]
    persistence: tuple[PersistenceResult, ...]
    v4_state_status: str


@dataclass(frozen=True, slots=True)
class Distribution:
    count: int
    minimum: float | None
    p50: float | None
    p95: float | None
    p99: float | None
    maximum: float | None


@dataclass(frozen=True, slots=True)
class OperationalSnapshot:
    counters: tuple[tuple[str, int], ...]
    distributions: tuple[tuple[str, Distribution], ...]


class OperationalMetrics:
    """Small bounded in-process telemetry; observations never enter math values."""

    def __init__(self, *, retained_samples: int = 100_000):
        if retained_samples < 1:
            raise ValueError("retained_samples must be positive")
        self._limit = retained_samples
        self._counters: Counter[str] = Counter()
        self._samples: dict[str, deque[float]] = {}
        self._lock = threading.Lock()

    def increment(self, name: str, amount: int = 1) -> None:
        with self._lock:
            self._counters[name] += amount

    def observe(self, name: str, milliseconds: float) -> None:
        if not math.isfinite(milliseconds) or milliseconds < 0:
            return
        with self._lock:
            self._samples.setdefault(name, deque(maxlen=self._limit)).append(milliseconds)

    def snapshot(self) -> OperationalSnapshot:
        with self._lock:
            counters = tuple(sorted(self._counters.items()))
            copied = {key: tuple(value) for key, value in self._samples.items()}
        return OperationalSnapshot(counters, tuple(
            (name, _distribution(values)) for name, values in sorted(copied.items())
        ))


def _distribution(values: tuple[float, ...]) -> Distribution:
    if not values:
        return Distribution(0, None, None, None, None, None)
    ordered = sorted(values)
    def percentile(p: float) -> float:
        return ordered[max(0, math.ceil(p * len(ordered)) - 1)]
    return Distribution(len(ordered), ordered[0], percentile(.50), percentile(.95),
                        percentile(.99), ordered[-1])


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


class V4DCoordinator:
    """Single-cycle live coordinator with horizon-local failure isolation."""

    def __init__(self, *, capture_v1: Callable[[], V1Input],
                 capture_v2: Callable[[V1Input], V2EvidenceState],
                 forecast_writer: V4AWriter,
                 compact_state_lookup: CompactStateLookup,
                 state_cohort_id: Callable[[V1Input, V2EvidenceState], str],
                 accuracy_state_lookup: Callable[..., tuple[AccuracyState | None, str]] | None = None,
                 metrics: OperationalMetrics | None = None,
                 wall_clock: Callable[[], datetime] = _utc_now,
                 monotonic_clock: Callable[[], float] = time.perf_counter):
        self._capture_v1 = capture_v1
        self._capture_v2 = capture_v2
        self._writer = forecast_writer
        self._lookup = compact_state_lookup
        self._state_cohort_id = state_cohort_id
        self._accuracy_lookup = accuracy_state_lookup
        self.metrics = metrics or OperationalMetrics()
        self._wall_clock = wall_clock
        self._monotonic = monotonic_clock

    def run_cycle(self) -> V4DCycleOutput:
        cycle_started = self._monotonic()
        v1 = self._capture_v1()
        v2 = self._capture_v2(v1)

        v3_started = self._monotonic()
        v3 = synthesize_v3(v1, v2)
        self.metrics.observe("v3_synthesis_latency_ms",
                             (self._monotonic() - v3_started) * 1000)
        if (v3.cycle_id != v1.cycle_id or v3.symbol != v1.symbol or
                tuple(item.horizon for item in v3.horizon_results) != HORIZONS):
            raise RuntimeError("V3_CYCLE_CONTRACT_VIOLATION")

        persistence = []
        for result in v3.horizon_results:
            forecast = build_forecast(v1=v1, v2=v2, result=result,
                                      evidence_origin="PRODUCTION")
            started = self._monotonic()
            try:
                stored = self._writer.persist_forecast(forecast, self._wall_clock())
                status = self._writer.last_write_status or "UNKNOWN"
                error_type = None
                self.metrics.increment("forecast_persistence.success")
            except Exception as error:  # persistence is an explicitly isolated boundary
                stored, status, error_type = forecast, "FAILED", type(error).__name__
                self.metrics.increment("forecast_persistence.failure")
            latency = (self._monotonic() - started) * 1000
            self.metrics.observe("forecast_persistence_latency_ms", latency)
            persistence.append(PersistenceResult(result.horizon, status, stored,
                                                 latency, error_type))

        state, state_status = self._lookup(
            symbol=v1.symbol, cohort_id=self._state_cohort_id(v1, v2),
            requested_cutoff=v1.cutoff_at,
        )
        if state_status != "AVAILABLE":
            state = None
        elif state is None:
            state_status = "UNAVAILABLE"
        self.metrics.increment("v4_state." + state_status)
        compact = {item.horizon: item for item in state.horizons} if state else {}
        accuracy_state, accuracy_status = (self._accuracy_lookup(
            symbol=v1.symbol, cohort_id=self._state_cohort_id(v1, v2),
            requested_cutoff=v1.cutoff_at) if self._accuracy_lookup else
            (None, "UNAVAILABLE"))
        if accuracy_status != "AVAILABLE" or accuracy_state is None:
            accuracy_state = None
        accuracy = {item.horizon: item for item in accuracy_state.horizon_states} if accuracy_state else {}

        v4_started = self._monotonic()
        finals = tuple(final_numbers(result, compact.get(result.horizon))
                       for result in v3.horizon_results)
        self.metrics.observe("v4_live_calculation_latency_ms",
                             (self._monotonic() - v4_started) * 1000)
        self._record_availability(v1, v2, v3, compact, accuracy)
        self.metrics.observe("complete_v9_cycle_latency_ms",
                             (self._monotonic() - cycle_started) * 1000)
        return V4DCycleOutput(v1.cycle_id, v1.symbol, v1.cutoff_at, v1, v2, v3,
                             finals, tuple(accuracy.get(h) for h in HORIZONS),
                             tuple(persistence), state_status)

    def _record_availability(self, v1: V1Input, v2: V2EvidenceState, v3: V3Output,
                             compact: Mapping[str, CompactHorizonState],
                             accuracy: Mapping[str, HorizonAccuracyState]) -> None:
        slots = {(slot.quant_id, slot.horizon): slot for slot in v1.slots}
        positive = {result.horizon: {family for family, weight in
                    zip(result.used_quant_ids, result.weights) if weight > 0}
                    for result in v3.horizon_results}
        v2_horizons = {item.horizon: item for item in v2.horizon_state_tuple}
        for horizon in HORIZONS:
            for family in CANONICAL_FAMILIES:
                prefix = f"family.{family}.{horizon}."
                self.metrics.increment(prefix + "cycles_observed")
                slot = slots.get((family, horizon))
                availability = slot.availability_state if slot else "MISSING"
                self.metrics.increment(prefix + availability)
                calibrations = {item.quant_id: item for item in
                                v2_horizons[horizon].directional_calibrations}
                calibration = calibrations.get(family)
                eligible = bool(slot and calibration and calibration.status != "UNAVAILABLE" and
                                _eligible_v1_slot(slot, calibration, v1, horizon))
                if eligible:
                    self.metrics.increment(prefix + "eligible")
                elif slot and slot.availability_state == "FRESH" and calibration and (
                        slot.formula_version != calibration.formula_version or
                        slot.data_schema_version != v1.data_schema_version or
                        slot.source_spec_version != v1.source_spec_version):
                    self.metrics.increment(prefix + "excluded_version_mismatch")
                if family in positive[horizon]:
                    self.metrics.increment(prefix + "used_positive_weight")
        for result in v3.horizon_results:
            prefix = f"horizon.{result.horizon}."
            operational_status = "AVAILABLE" if result.status == "MATURE" else result.status
            self.metrics.increment(prefix + operational_status)
            self.metrics.increment(prefix + "directional_input_count",
                                   result.directional_input_count)
            if 0 < result.directional_input_count < len(CANONICAL_FAMILIES):
                self.metrics.increment(prefix + "reduced_family")
            state = compact.get(result.horizon)
            self.metrics.increment(f"v4.{result.horizon}.accuracy." +
                                   (accuracy[result.horizon].status if result.horizon in accuracy
                                    else "UNAVAILABLE"))
            for component, status in (
                ("scale", state.scale_status if state else "UNAVAILABLE"),
                ("range", state.range_status if state else "UNAVAILABLE"),
            ):
                self.metrics.increment(f"v4.{result.horizon}.{component}.{status}")
            event_statuses = state.event_statuses if state else ("UNAVAILABLE",) * 6
            for index, status in enumerate(event_statuses):
                self.metrics.increment(f"v4.{result.horizon}.probability.{index}.{status}")
            self.metrics.increment(f"v4.{result.horizon}.gamma.INACTIVE")


def resolve_outcome(*, writer: V4AWriter, forecast: ForecastRecord,
                    target_identity: str, endpoint_observation_at: datetime,
                    target_resolved_at: datetime, actual_return_bps: float | None,
                    created_at: datetime | None = None,
                    metrics: OperationalMetrics | None = None) -> OutcomeRecord:
    """Append a canonical outcome without modifying its immutable forecast."""
    started = time.perf_counter()
    outcome = build_outcome(forecast=forecast, target_identity=target_identity,
        endpoint_observation_at=endpoint_observation_at,
        target_resolved_at=target_resolved_at, actual_return_bps=actual_return_bps)
    stored = writer.persist_outcome(outcome, created_at or _utc_now())
    if metrics:
        metrics.increment("outcome_resolution." + (writer.last_write_status or "UNKNOWN"))
        metrics.observe("outcome_resolution_latency_ms", (time.perf_counter()-started)*1000)
    return stored


class OfflineStateBuildScheduler:
    """Rate-limited trigger for an injected frozen offline state builder."""

    def __init__(self, build_and_publish: Callable[[], str], *,
                 metrics: OperationalMetrics | None = None,
                 monotonic_clock: Callable[[], float] = time.monotonic,
                 minimum_interval_seconds: float = 60.0):
        self._build = build_and_publish
        self._metrics = metrics or OperationalMetrics()
        self._clock = monotonic_clock
        self._interval = max(60.0, minimum_interval_seconds)
        self._last_build: float | None = None
        self._latest_outcome_generation = 0
        self._built_generation = 0
        self._lock = threading.Lock()

    def note_new_outcome(self) -> None:
        with self._lock:
            self._latest_outcome_generation += 1

    def run_if_due(self) -> str:
        with self._lock:
            now = self._clock()
            if self._latest_outcome_generation == self._built_generation:
                return "SKIPPED_NO_NEW_OUTCOME"
            if self._last_build is not None and now - self._last_build < self._interval:
                return "SKIPPED_RATE_LIMIT"
            generation = self._latest_outcome_generation
            self._last_build = now
        started = self._clock()
        status = self._build()
        elapsed = (self._clock() - started) * 1000
        self._metrics.observe("state_build_latency_ms", elapsed)
        self._metrics.increment("state_publication." + status)
        if status in ("INSERT", "IDEMPOTENT"):
            with self._lock:
                self._built_generation = max(self._built_generation, generation)
        return status


__all__ = [
    "Distribution", "OfflineStateBuildScheduler", "OperationalMetrics",
    "OperationalSnapshot", "PersistenceResult", "V4DCoordinator",
    "V4DCycleOutput", "resolve_outcome",
]
