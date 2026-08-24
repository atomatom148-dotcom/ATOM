"""Bounded, non-blocking handoff from the COIN quote path to its ledger.

The envelope is deliberately made entirely from frozen values.  In particular the
worker is never allowed to go looking for a quote with which to resolve a target.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
import math
from queue import Empty, Full, Queue
import threading
import time
from typing import Callable

from .evidence import ForecastRecord as RawForecastRecord, VolatilityForecastRecord
from .history import MidpointObservation
from .v9_v4a_evidence import ForecastRecord as V4ForecastRecord, V4AWriter, canonical_target_identity
from .v9_v4a_evidence import deserialize_forecast_record
from .v9_v4d_integration import (
    ImmutableStateCache, OperationalMetrics, V4DCycleOutput, resolve_outcome,
)
from .v9_sim3_capture import FinalizedV4PersistenceResult


EVIDENCE_OUTBOX_CAPACITY = 256


class TerminalDeliveryError(RuntimeError):
    """An immutable envelope cannot succeed if retried."""


def _transient_database_error(error: Exception) -> bool:
    """Recognize DB-API connection/operational failures without importing on path."""
    return type(error).__name__ in {
        "OperationalError", "InterfaceError", "ConnectionError", "TimeoutError",
    }


class V4StateCacheRefresher:
    """Background-only reader which atomically publishes exact cohort entries."""

    def __init__(self, *, compact_store, accuracy_store,
                 compact_cache: ImmutableStateCache,
                 accuracy_cache: ImmutableStateCache):
        self._compact_store, self._accuracy_store = compact_store, accuracy_store
        self._compact_cache, self._accuracy_cache = compact_cache, accuracy_cache

    def refresh(self, *, symbol: str, cohort_id: str, cutoff: datetime) -> None:
        compact, compact_status = self._compact_store.latest_json(
            symbol=symbol, cohort_id=cohort_id, requested_cutoff=cutoff)
        if compact_status == "AVAILABLE" and compact is not None:
            self._compact_cache.publish(compact)
        accuracy, accuracy_status = self._accuracy_store.latest_json(
            symbol=symbol, cohort_id=cohort_id, requested_cutoff=cutoff)
        if accuracy_status == "AVAILABLE" and accuracy is not None:
            self._accuracy_cache.publish(accuracy)


@dataclass(frozen=True, slots=True)
class QuoteEvidenceWork:
    """One complete, immutable COIN event envelope."""

    sequence: int
    cycle_id: str
    previous_observation: MidpointObservation | None
    current_observation: MidpointObservation
    received_at: datetime
    directional: tuple[RawForecastRecord, ...]
    q3: tuple[VolatilityForecastRecord, ...]
    v4: tuple[V4ForecastRecord, ...]
    state_cohort_id: str | None = None
    v4d_output: V4DCycleOutput | None = None


class EvidenceOutbox:
    """A fixed-size outbox whose producer operation can never wait."""

    def __init__(self, *, metrics: OperationalMetrics | None = None):
        self._queue: Queue[QuoteEvidenceWork] = Queue(EVIDENCE_OUTBOX_CAPACITY)
        self.metrics = metrics or OperationalMetrics()
        self._available = True

    def put_nowait(self, item: QuoteEvidenceWork) -> bool:
        started = time.perf_counter()
        try:
            if not self._available:
                self.metrics.increment("EVIDENCE_OUTBOX_UNAVAILABLE")
                return False
            self._queue.put_nowait(item)
            return True
        except Full:
            self.metrics.increment("EVIDENCE_OUTBOX_FULL")
            return False
        finally:
            self.metrics.observe("hot_path_evidence_enqueue_latency_ms",
                                 (time.perf_counter() - started) * 1000)

    def get(self, timeout: float | None = None) -> QuoteEvidenceWork:
        return self._queue.get(timeout=timeout)

    def task_done(self) -> None:
        self._queue.task_done()

    def unavailable(self) -> None:
        self._available = False


class EvidenceLedgerWorker:
    """The one serial FIFO owner of COIN evidence persistence and resolution."""

    def __init__(self, outbox: EvidenceOutbox, *, evidence_store,
                 connection=None, connect: Callable | None = None,
                 database_url: str | None = None,
                 metrics: OperationalMetrics | None = None,
                 cache_refresher: V4StateCacheRefresher | None = None,
                 simulation_submit: Callable | None = None,
                 wall_clock: Callable[[], datetime] = lambda: datetime.now(timezone.utc)):
        if connection is None:
            if connect is None:
                import psycopg
                connect = psycopg.connect
            connection = connect(database_url)
        self.outbox, self._store, self._connection = outbox, evidence_store, connection
        self._writer = V4AWriter(connection)
        self.metrics = metrics or outbox.metrics
        self._clock = wall_clock
        self._cache_refresher = cache_refresher
        self._simulation_submit = simulation_submit
        self._pending: list[V4ForecastRecord] = self._load_pending()
        self._last_sequence: int | None = None
        self._resolution_contiguous = True
        self._stop = threading.Event()

    def _load_pending(self) -> list[V4ForecastRecord]:
        """Recover only durable, unresolved forecasts in the conservative window."""
        cursor = self._connection.cursor()
        try:
            cursor.execute(
                """SELECT f.forecast_record_hash, f.record_json
                   FROM public.atom_v9_v4_forecasts AS f
                   WHERE f.target_endpoint >= now() - interval '1 hour'
                     AND NOT EXISTS (
                         SELECT 1 FROM public.atom_v9_v4_outcomes AS o
                         WHERE o.forecast_record_id=f.forecast_record_id)
                   ORDER BY f.target_endpoint, f.forecast_record_id""", ())
            rows = tuple(cursor.fetchall())
            commit = getattr(self._connection, "commit", None)
            if callable(commit):
                commit()
        except Exception:
            rollback = getattr(self._connection, "rollback", None)
            if callable(rollback):
                rollback()
            raise
        finally:
            close = getattr(cursor, "close", None)
            if callable(close):
                close()
        recovered = []
        for expected_hash, payload in rows:
            try:
                record = deserialize_forecast_record(payload, expected_hash=str(expected_hash))
            except ValueError:
                self.metrics.increment("evidence_recovery.invalid_record")
                continue
            if record.persistence_proof_eligible is True:
                recovered.append(record)
        return recovered

    def process(self, item: QuoteEvidenceWork) -> None:
        """Process exactly one bracket; callers may retry this same item."""
        started = time.perf_counter()
        if not isinstance(item, QuoteEvidenceWork) or item.sequence < 1:
            raise TerminalDeliveryError("MALFORMED_EVIDENCE_ENVELOPE")
        if self._last_sequence is not None and item.sequence <= self._last_sequence:
            raise TerminalDeliveryError("EVIDENCE_EVENT_ORDER_VIOLATION")
        gap = (not self._resolution_contiguous or
               (self._last_sequence is not None and
                item.sequence != self._last_sequence + 1))
        if gap:
            self.metrics.increment("EVIDENCE_SEQUENCE_GAP")
        previous, current = item.previous_observation, item.current_observation
        remaining = []
        if previous is not None:
            for forecast in self._pending:
                endpoint = forecast.target_endpoint.timestamp()
                if endpoint > current.event_epoch:
                    remaining.append(forecast)
                elif endpoint <= previous.event_epoch or forecast.cutoff_midpoint is None:
                    # A missing exact bracket is intentionally never reconstructed.
                    continue
                elif not gap:
                    resolve_outcome(
                        writer=self._writer, forecast=forecast,
                        target_identity=canonical_target_identity(forecast),
                        previous_observation_at=datetime.fromtimestamp(previous.event_epoch, timezone.utc),
                        endpoint_observation_at=datetime.fromtimestamp(current.event_epoch, timezone.utc),
                        target_resolved_at=item.received_at,
                        actual_return_bps=10_000.0 * math.log(
                            current.midpoint / forecast.cutoff_midpoint),
                        metrics=self.metrics,
                    )
                    if self._writer.last_write_status == "OUTCOME_CONFLICT":
                        raise TerminalDeliveryError("OUTCOME_CONFLICT")
        else:
            remaining.extend(self._pending)
        # The legacy raw ledger operation is wholly worker-owned.  Its capture
        # timestamp remains capture time; no availability timestamp is invented.
        self._store.record_cycle_and_resolve(
            item.directional, observation_epoch=current.event_epoch,
            observation_midpoint=current.midpoint, volatility_forecasts=item.q3,
            previous_observation_epoch=(previous.event_epoch if previous else None),
            resolution_enabled=not gap and previous is not None,
        )
        pending_ids = {record.forecast_record_id for record in remaining}
        finalized = []
        for forecast in item.v4:
            stored = self._writer.persist_forecast(forecast, self._clock())
            if self._writer.last_write_status in {
                    "FORECAST_DUPLICATE_CONFLICT", "OUTCOME_CONFLICT"}:
                raise TerminalDeliveryError(self._writer.last_write_status)
            status = ("INSERTED" if self._writer.last_write_status == "INSERT"
                      else self._writer.last_write_status)
            finalized.append(FinalizedV4PersistenceResult(
                forecast.horizon, status, stored))
            if (stored.persistence_proof_eligible is True and
                    stored.forecast_record_id not in pending_ids):
                remaining.append(stored)
                pending_ids.add(stored.forecast_record_id)
        remaining.sort(key=lambda row: (row.target_endpoint, row.forecast_record_id))
        self._pending = remaining
        self._last_sequence = item.sequence
        self._resolution_contiguous = True
        if (self._simulation_submit is not None and item.v4d_output is not None
                and len(finalized) == 6):
            try:
                self._simulation_submit(item.v4d_output, tuple(finalized))
            except Exception:
                pass
        if self._cache_refresher is not None and item.state_cohort_id is not None:
            try:
                self._cache_refresher.refresh(
                    symbol="COIN", cohort_id=item.state_cohort_id,
                    cutoff=datetime.fromtimestamp(current.event_epoch, timezone.utc))
            except Exception:
                self.metrics.increment("v4_state_cache.refresh_failure")
        self.metrics.observe("evidence_ledger_worker_latency_ms",
                             (time.perf_counter() - started) * 1000)

    def run(self) -> None:
        while not self._stop.is_set():
            try:
                item = self.outbox.get(timeout=.1)
            except Empty:
                continue
            while not self._stop.is_set():
                try:
                    self.process(item)
                    self.outbox.task_done()
                    break
                except TerminalDeliveryError:
                    self.metrics.increment("evidence_ledger_worker.terminal_failure")
                    sequence = getattr(item, "sequence", None)
                    if isinstance(sequence, int):
                        self._last_sequence = sequence
                    self._resolution_contiguous = False
                    self.outbox.task_done()
                    break
                except Exception as error:
                    self.metrics.increment("evidence_ledger_worker.failure")
                    if not _transient_database_error(error):
                        self.metrics.increment("evidence_ledger_worker.terminal_failure")
                        sequence = getattr(item, "sequence", None)
                        if isinstance(sequence, int):
                            self._last_sequence = sequence
                        self._resolution_contiguous = False
                        self.outbox.task_done()
                        break
                    time.sleep(.1)  # transient off-path retry of the same FIFO head

    def start(self) -> threading.Thread:
        thread = threading.Thread(target=self.run, name="coin-evidence-ledger", daemon=True)
        thread.start()
        return thread

    def close(self) -> None:
        self._stop.set()
        close = getattr(self._connection, "close", None)
        if callable(close):
            close()
