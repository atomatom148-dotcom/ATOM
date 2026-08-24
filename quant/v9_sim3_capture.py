"""Isolated asynchronous capture of persisted V4D simulation intents."""

from __future__ import annotations

from collections import deque
from dataclasses import dataclass
from datetime import datetime, timezone
import math
from queue import Empty, Full, Queue
import threading
import time
from typing import Callable

from .v9_sim1_contract import build_simulation_trade_intent
from .v9_sim2_store import IDEMPOTENT, INSERTED, SimulationIntentStore
from .v9_v1_contract import HORIZONS
from .v9_v4a_evidence import ForecastRecord
from .v9_v4d_integration import V4DCycleOutput

SIM3_QUEUE_CAPACITY = 64
ACCEPTED = "ACCEPTED"
DROPPED_QUEUE_FULL = "DROPPED_QUEUE_FULL"
CAPTURE_UNAVAILABLE = "CAPTURE_UNAVAILABLE"
_STATUSES = {"NOT_STARTED", "READY", "STOPPED", "FAILED"}
_V3_STATUS = {"MATURE": "AVAILABLE", "PROVISIONAL": "PROVISIONAL",
              "UNAVAILABLE": "UNAVAILABLE"}


@dataclass(frozen=True, slots=True)
class FinalizedV4PersistenceResult:
    horizon: str
    status: str
    forecast: ForecastRecord


@dataclass(frozen=True, slots=True)
class SimulationCaptureWorkItem:
    cycle_output: V4DCycleOutput
    persistence_results: tuple[FinalizedV4PersistenceResult, ...]
    eligible_at: datetime


@dataclass(frozen=True, slots=True)
class Sim3TelemetrySnapshot:
    sim3_submit_status: str
    sim3_queue_depth: int
    sim3_cycles_accepted_total: int
    sim3_cycles_dropped_total: int
    sim3_cycles_processed_total: int
    sim3_intents_inserted_total: int
    sim3_intents_idempotent_total: int
    sim3_horizon_failures_total: int
    sim3_worker_failures_total: int
    sim3_capture_latency_ms: tuple[float, ...]
    sim3_worker_latency_ms: tuple[float, ...]


class Sim3Telemetry:
    """Fixed-cardinality, bounded operational telemetry."""

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._status = "NOT_STARTED"
        self._queue_depth = 0
        self._counters = [0] * 7
        self._capture = deque(maxlen=256)
        self._worker = deque(maxlen=256)

    def status(self, value: str) -> None:
        if value not in _STATUSES:
            raise ValueError("invalid SIM-3 status")
        with self._lock:
            self._status = value

    def depth(self, value: int) -> None:
        with self._lock:
            self._queue_depth = max(0, min(SIM3_QUEUE_CAPACITY, int(value)))

    def increment(self, index: int) -> None:
        with self._lock:
            self._counters[index] += 1

    def observe_capture(self, value: float) -> None:
        with self._lock:
            self._capture.append(float(value))

    def observe_worker(self, value: float) -> None:
        with self._lock:
            self._worker.append(float(value))

    def snapshot(self) -> Sim3TelemetrySnapshot:
        with self._lock:
            return Sim3TelemetrySnapshot(self._status, self._queue_depth,
                *self._counters, tuple(self._capture), tuple(self._worker))


class SimulationCaptureAdapter:
    """One-worker, whole-cycle FIFO adapter; submission never waits."""

    _SENTINEL = object()

    def __init__(self, store: SimulationIntentStore,
                 utc_clock: Callable[[], datetime], *,
                 telemetry: Sim3Telemetry | None = None) -> None:
        if not callable(utc_clock):
            raise TypeError("utc_clock must be callable")
        self._store = store
        self._utc_clock = utc_clock
        self.telemetry = telemetry or Sim3Telemetry()
        self._queue: Queue[object] = Queue(SIM3_QUEUE_CAPACITY)
        self._lock = threading.Lock()
        self._thread: threading.Thread | None = None
        self._start_attempted = False
        self._start_succeeded = False
        self._stopping = False

    def _metric(self, method: str, *args: object) -> None:
        try:
            getattr(self.telemetry, method)(*args)
        except Exception:
            pass

    def start(self) -> None:
        with self._lock:
            if self._start_attempted:
                return
            self._start_attempted = True
            thread = threading.Thread(target=self._run, name="v9-sim3-capture",
                                      daemon=True)
            self._thread = thread
            try:
                thread.start()
            except Exception:
                self._metric("status", "FAILED")
                self._thread = None
                raise
            self._start_succeeded = True
            self._metric("status", "READY")

    @staticmethod
    def _valid_utc(value: object) -> bool:
        if not isinstance(value, datetime) or value.tzinfo is None:
            return False
        try:
            return (value.utcoffset() == timezone.utc.utcoffset(value) and
                    math.isfinite(value.timestamp()))
        except (OverflowError, OSError, ValueError):
            return False

    def submit(self, cycle_output: V4DCycleOutput,
               persistence_results: tuple[FinalizedV4PersistenceResult, ...]) -> str:
        started = time.perf_counter()
        result = CAPTURE_UNAVAILABLE
        try:
            eligible_at = self._utc_clock()
            if not self._valid_utc(eligible_at):
                return result
            item = SimulationCaptureWorkItem(
                cycle_output, persistence_results, eligible_at)
            with self._lock:
                thread = self._thread
                if (self._start_succeeded and not self._stopping and
                        (thread is None or not thread.is_alive())):
                    self._metric("status", "FAILED")
                    return result
                if (not self._start_succeeded or self._stopping or
                        thread is None):
                    return result
                try:
                    self._queue.put_nowait(item)
                except Full:
                    self._metric("increment", 1)
                    result = DROPPED_QUEUE_FULL
                except Exception:
                    result = CAPTURE_UNAVAILABLE
                else:
                    self._metric("increment", 0)
                    self._metric("depth", self._queue.qsize())
                    result = ACCEPTED
            return result
        except Exception:
            return CAPTURE_UNAVAILABLE
        finally:
            try:
                self.telemetry.observe_capture((time.perf_counter() - started) * 1000)
            except Exception:
                pass

    @staticmethod
    def _validate_structure(item: SimulationCaptureWorkItem) -> None:
        output = item.cycle_output
        if not isinstance(output, V4DCycleOutput):
            raise ValueError("invalid V4D output")
        results = item.persistence_results
        if (not isinstance(results, tuple) or
                tuple(row.horizon for row in results) != HORIZONS or
                tuple(row.horizon for row in output.v3.horizon_results) != HORIZONS or
                tuple(row.horizon for row in output.final_numbers) != HORIZONS):
            raise ValueError("malformed horizon structure")
        for horizon, finalized, v3, final in zip(
                HORIZONS, results, output.v3.horizon_results, output.final_numbers):
            if (not isinstance(finalized, FinalizedV4PersistenceResult) or
                    finalized.horizon != horizon or v3.horizon != horizon or
                    final.horizon != horizon or finalized.forecast.horizon != horizon):
                raise ValueError("mismatched horizon structure")

    def _process(self, item: SimulationCaptureWorkItem) -> None:
        self._validate_structure(item)
        output = item.cycle_output
        for finalized, v3, final in zip(
                item.persistence_results, output.v3.horizon_results,
                output.final_numbers):
            if finalized.status not in {INSERTED, IDEMPOTENT}:
                self._metric("increment", 5)
                continue
            try:
                forecast = finalized.forecast
                if (forecast.cycle_id != output.cycle_id or
                        forecast.cutoff_at != output.cutoff_at or
                        forecast.v2_state_id != output.v2.state_id or
                        forecast.v2_state_hash != output.v2.state_hash or
                        forecast.v3_model_version != output.v3.model_version):
                    raise ValueError("source identity mismatch")
                source_status = _V3_STATUS[v3.status]
                intent = build_simulation_trade_intent(
                    source_cycle_id=output.cycle_id,
                    source_forecast_record_id=forecast.forecast_record_id,
                    source_forecast_record_hash=forecast.forecast_record_hash,
                    source_v2_state_id=output.v2.state_id,
                    source_v2_state_hash=output.v2.state_hash,
                    source_v3_contract_version=forecast.v3_contract_version,
                    source_v3_model_version=output.v3.model_version,
                    cutoff_at=output.cutoff_at, eligible_at=item.eligible_at,
                    horizon=v3.horizon, horizon_seconds=v3.horizon_seconds,
                    final_bps=final.final_bps, source_v3_status=source_status,
                )
                stored = self._store.insert(intent)
                if stored == INSERTED:
                    self._metric("increment", 3)
                elif stored == IDEMPOTENT:
                    self._metric("increment", 4)
                else:
                    raise ValueError("unexpected store result")
            except Exception:
                self._metric("increment", 5)

    def _run(self) -> None:
        expected_exit = False
        try:
            while True:
                try:
                    value = self._queue.get(timeout=.1)
                except Empty:
                    if self._stopping:
                        expected_exit = True
                        return
                    continue
                if value is self._SENTINEL:
                    self._queue.task_done()
                    expected_exit = True
                    return
                started = time.perf_counter()
                try:
                    self._process(value)  # type: ignore[arg-type]
                except Exception:
                    self._metric("increment", 6)
                finally:
                    self._metric("increment", 2)
                    self._queue.task_done()
                    self._metric("depth", self._queue.qsize())
                    try:
                        self.telemetry.observe_worker(
                            (time.perf_counter() - started) * 1000)
                    except Exception:
                        pass
        finally:
            if not expected_exit:
                self._metric("status", "FAILED")

    def stop(self) -> None:
        with self._lock:
            if self._stopping:
                return
            self._stopping = True
            thread = self._thread
            self._metric("status", "STOPPED")
        if thread is None:
            return
        try:
            self._queue.put_nowait(self._SENTINEL)
        except (Full, Exception):
            pass
        thread.join(timeout=1.0)
        if thread.is_alive():
            try:
                self._metric("depth", self._queue.qsize())
            except Exception:
                pass
