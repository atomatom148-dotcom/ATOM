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
from .v9_v4d_integration import OperationalMetrics, resolve_outcome


EVIDENCE_OUTBOX_CAPACITY = 256


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
        self._pending: list[V4ForecastRecord] = []
        self._last_sequence: int | None = None
        self._stop = threading.Event()

    def process(self, item: QuoteEvidenceWork) -> None:
        """Process exactly one bracket; callers may retry this same item."""
        started = time.perf_counter()
        if self._last_sequence is not None and item.sequence <= self._last_sequence:
            raise RuntimeError("EVIDENCE_EVENT_ORDER_VIOLATION")
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
                else:
                    resolve_outcome(
                        writer=self._writer, forecast=forecast,
                        target_identity=canonical_target_identity(forecast),
                        previous_observation_at=datetime.fromtimestamp(previous.event_epoch, timezone.utc),
                        endpoint_observation_at=datetime.fromtimestamp(current.event_epoch, timezone.utc),
                        target_resolved_at=self._clock(),
                        actual_return_bps=10_000.0 * math.log(
                            current.midpoint / forecast.cutoff_midpoint),
                        metrics=self.metrics,
                    )
        else:
            remaining.extend(self._pending)
        self._pending = remaining

        # The legacy raw ledger operation is wholly worker-owned.  Its capture
        # timestamp remains capture time; no availability timestamp is invented.
        self._store.record_cycle_and_resolve(
            item.directional, observation_epoch=current.event_epoch,
            observation_midpoint=current.midpoint, volatility_forecasts=item.q3,
        )
        pending_ids = {record.forecast_record_id for record in self._pending}
        for forecast in item.v4:
            stored = self._writer.persist_forecast(forecast, self._clock())
            if (stored.persistence_proof_eligible is True and
                    stored.forecast_record_id not in pending_ids):
                self._pending.append(stored)
                pending_ids.add(stored.forecast_record_id)
        self._pending.sort(key=lambda row: (row.target_endpoint, row.forecast_record_id))
        self._last_sequence = item.sequence
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
                except Exception:
                    self.metrics.increment("evidence_ledger_worker.failure")
                    time.sleep(.1)  # off-path retry; the failed head never moves

    def start(self) -> threading.Thread:
        thread = threading.Thread(target=self.run, name="coin-evidence-ledger", daemon=True)
        thread.start()
        return thread

    def close(self) -> None:
        self._stop.set()
        close = getattr(self._connection, "close", None)
        if callable(close):
            close()

