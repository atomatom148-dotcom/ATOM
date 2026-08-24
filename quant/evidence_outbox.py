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
from .v9_v4a_evidence import (
    CONTRACT_VERSION as V4_CONTRACT_VERSION, EVIDENCE_VERSION as V4_EVIDENCE_VERSION,
    canonical_sha256, deserialize_forecast_record, deserialize_outcome_record,
    select_non_overlapping,
)
from .v9_v4b_accuracy import AccuracyStateStore, build_accuracy_state
from .v9_v1_contract import HORIZONS
from .v9_v4c_predictive import (
    CalibrationObservation, CompactHorizonState, RangeValidationObservation,
    V4CStateStore, build_thresholds, build_v4c_state, calibrate_range,
    calibrate_scale,
)
from .v9_v4d_integration import (
    ImmutableStateCache, OfflineStateBuildScheduler, OperationalMetrics,
    V4DCycleOutput, resolve_outcome,
)
from .v9_sim3_capture import FinalizedV4PersistenceResult


EVIDENCE_OUTBOX_CAPACITY = 256


class TerminalDeliveryError(RuntimeError):
    """An immutable envelope cannot succeed if retried."""


def _transient_database_error(error: Exception) -> bool:
    """Recognize DB-API connection/operational failures without importing on path."""
    transient_names = {
        "OperationalError", "InterfaceError", "ConnectionError", "TimeoutError",
    }
    return any(base.__name__ in transient_names for base in type(error).__mro__)


class V4StateCacheRefresher:
    """Background-only reader which atomically publishes exact cohort entries."""

    def __init__(self, *, compact_store, accuracy_store,
                 compact_cache: ImmutableStateCache,
                 accuracy_cache: ImmutableStateCache):
        self._compact_store, self._accuracy_store = compact_store, accuracy_store
        self._compact_cache, self._accuracy_cache = compact_cache, accuracy_cache

    def rebind_connection(self, connection) -> None:
        """Replace both readers after their shared DB session is recovered."""

        for store, replacement in (
            (self._compact_store, V4CStateStore),
            (self._accuracy_store, AccuracyStateStore),
        ):
            rebind = getattr(store, "rebind_connection", None)
            if callable(rebind):
                rebind(connection)
            elif store is self._compact_store:
                self._compact_store = replacement(connection)
            else:
                self._accuracy_store = replacement(connection)

    def refresh(self, *, symbol: str, cohort_id: str, cutoff: datetime) -> None:
        compact, compact_status = self._compact_store.latest_json(
            symbol=symbol, cohort_id=cohort_id, requested_cutoff=cutoff)
        if compact_status == "AVAILABLE" and compact is not None:
            self._compact_cache.publish(compact)
        accuracy, accuracy_status = self._accuracy_store.latest_json(
            symbol=symbol, cohort_id=cohort_id, requested_cutoff=cutoff)
        if accuracy_status == "AVAILABLE" and accuracy is not None:
            self._accuracy_cache.publish(accuracy)


class PostgresV4BStateBuilder:
    """Build one frozen accuracy state from durable governed V4A evidence."""

    def __init__(self, connection, *, state_store=None,
                 wall_clock: Callable[[], datetime] = lambda: datetime.now(timezone.utc)):
        self._connection = connection
        self._store = state_store or AccuracyStateStore(connection)
        self._clock = wall_clock
        self._candidate = None

    def rebind_connection(self, connection) -> None:
        self._connection = connection
        rebind = getattr(self._store, "rebind_connection", None)
        if callable(rebind):
            rebind(connection)

    def prepare(self, *, symbol: str, state_as_of: datetime,
                cohorts: dict[str, tuple[str, str]]) -> None:
        self._candidate = (symbol, state_as_of, dict(cohorts))

    def build_and_publish(self) -> str:
        if self._candidate is None:
            return "SKIPPED_NO_CANDIDATE"
        symbol, state_as_of, cohorts = self._candidate
        cursor = self._connection.cursor()
        try:
            cursor.execute(
                """SELECT f.forecast_record_hash, f.record_json,
                          o.outcome_record_hash, o.record_json
                   FROM public.atom_v9_v4_forecasts AS f
                   JOIN public.atom_v9_v4_outcomes AS o
                     USING (forecast_record_id)
                   WHERE f.symbol=%s AND f.cutoff_at<=%s AND o.created_at<=%s
                   ORDER BY f.cutoff_at, f.forecast_record_id,
                            o.created_at, o.outcome_record_id""",
                (symbol, state_as_of, state_as_of),
            )
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
        evidence = tuple(
            (deserialize_forecast_record(forecast_json, expected_hash=str(forecast_hash)),
             deserialize_outcome_record(outcome_json, expected_hash=str(outcome_hash)))
            for forecast_hash, forecast_json, outcome_hash, outcome_json in rows
        )
        state = build_accuracy_state(
            symbol=symbol, state_as_of=state_as_of,
            cohorts=cohorts, evidence=evidence,
        )
        return self._store.insert(state, self._clock())


class PostgresV4CStateBuilder:
    """Build the frozen compact V4C state from governed immutable V4A evidence."""

    def __init__(self, connection, *, state_store=None,
                 wall_clock: Callable[[], datetime] = lambda: datetime.now(timezone.utc)):
        self._connection = connection
        self._store = state_store or V4CStateStore(connection)
        self._clock = wall_clock
        self._candidate = None

    def rebind_connection(self, connection) -> None:
        self._connection = connection
        rebind = getattr(self._store, "rebind_connection", None)
        if callable(rebind):
            rebind(connection)

    def prepare(self, *, symbol: str, state_as_of: datetime,
                cohorts: dict[str, tuple[str, str]]) -> None:
        self._candidate = (symbol, state_as_of, dict(cohorts))

    def build_and_publish(self) -> str:
        if self._candidate is None:
            return "SKIPPED_NO_CANDIDATE"
        symbol, state_as_of, cohorts = self._candidate
        cursor = self._connection.cursor()
        try:
            cursor.execute(
                """SELECT f.forecast_record_hash, f.record_json,
                          o.outcome_record_hash, o.record_json
                   FROM public.atom_v9_v4_forecasts AS f
                   JOIN public.atom_v9_v4_outcomes AS o
                     USING (forecast_record_id)
                   WHERE f.symbol=%s AND f.cutoff_at<=%s AND o.created_at<=%s
                   ORDER BY f.cutoff_at, f.forecast_record_id,
                            o.created_at, o.outcome_record_id""",
                (symbol, state_as_of, state_as_of),
            )
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
        evidence = tuple(
            (deserialize_forecast_record(forecast_json, expected_hash=str(forecast_hash)),
             deserialize_outcome_record(outcome_json, expected_hash=str(outcome_hash)))
            for forecast_hash, forecast_json, outcome_hash, outcome_json in rows
        )
        state = self._build_state(symbol, state_as_of, cohorts, evidence)
        return self._store.insert(state, self._clock())

    @staticmethod
    def _build_state(symbol, state_as_of, cohorts, evidence):
        if tuple(cohorts) != HORIZONS:
            raise ValueError("cohorts must contain exactly six canonical horizons in order")
        compact = []
        selected_all = []
        for horizon in HORIZONS:
            cohort_id, cohort_hash = cohorts[horizon]
            governed = tuple((forecast, outcome) for forecast, outcome in evidence if
                forecast.horizon == horizon and forecast.cohort_id == cohort_id and
                forecast.cohort_hash == cohort_hash and forecast.symbol == symbol and
                forecast.contract_version == V4_CONTRACT_VERSION and
                forecast.evidence_version == V4_EVIDENCE_VERSION and
                outcome.contract_version == V4_CONTRACT_VERSION and
                outcome.evidence_version == V4_EVIDENCE_VERSION and
                forecast.evidence_origin == "PRODUCTION" and
                forecast.persistence_proof_eligible is True and outcome.proof_eligible and
                outcome.target_timing_status == "VERIFIED" and
                outcome.forecast_record_id == forecast.forecast_record_id and
                forecast.cutoff_at <= state_as_of and outcome.target_resolved_at <= state_as_of and
                forecast.expected_return_bps is not None and
                forecast.predictive_variance_bps2 is not None and
                outcome.actual_return_bps is not None and
                all(isinstance(value, (int, float)) and not isinstance(value, bool) and
                    math.isfinite(value) for value in (
                        forecast.expected_return_bps,
                        forecast.predictive_variance_bps2,
                        outcome.actual_return_bps)) and
                forecast.predictive_variance_bps2 > 0)
            selection = select_non_overlapping(governed)
            selected_ids = set(selection.selected_ids)
            selected = tuple(sorted(
                (pair for pair in governed if pair[0].forecast_record_id in selected_ids),
                key=lambda pair: (pair[0].cutoff_at, pair[0].forecast_record_id)))
            selected_all.extend(selected)

            split = max(0, len(selected) - 250)
            calibration_pairs, validation_pairs = selected[:split], selected[split:]
            calibration_end = (calibration_pairs[-1][0].cutoff_at
                               if calibration_pairs else state_as_of)
            observations = tuple(CalibrationObservation(
                forecast.cutoff_at, forecast.forecast_record_id,
                float(outcome.actual_return_bps), float(forecast.expected_return_bps),
                float(forecast.predictive_variance_bps2),
                forecast.cutoff_at.date().isoformat(), outcome.target_resolved_at)
                for forecast, outcome in calibration_pairs)
            thresholds = build_thresholds(observations, reference_end=calibration_end)
            scale = calibrate_scale(observations, calibration_end=calibration_end)
            scores = tuple(abs(observation.actual_bps - observation.mean_bps) /
                (scale.kappa * math.sqrt(observation.q0_bps2)) for observation in observations
                if scale.kappa is not None)
            provisional = calibrate_range(scores, (), (), validation_end=state_as_of)
            validation = tuple(RangeValidationObservation(
                forecast.cutoff_at, outcome.target_resolved_at,
                float(outcome.actual_return_bps),
                float(forecast.expected_return_bps) - provisional.quantile *
                    scale.kappa * math.sqrt(float(forecast.predictive_variance_bps2)),
                float(forecast.expected_return_bps) + provisional.quantile *
                    scale.kappa * math.sqrt(float(forecast.predictive_variance_bps2)),
                forecast.cutoff_at.date().isoformat())
                for forecast, outcome in validation_pairs
                if provisional.quantile is not None and scale.kappa is not None)
            sessions = tuple(dict.fromkeys(item.session_id for item in validation))
            range_result = calibrate_range(scores, validation, sessions,
                                           validation_end=state_as_of)
            residuals = tuple(sorted(
                (observation.actual_bps - observation.mean_bps) /
                (scale.kappa * math.sqrt(observation.q0_bps2)) for observation in observations
                if scale.kappa is not None))
            reasons = tuple(sorted(set(thresholds.reason_codes + scale.reason_codes +
                                       range_result.reason_codes)))
            compact.append(CompactHorizonState(
                horizon, thresholds.status, thresholds.medium_bps,
                thresholds.large_bps, scale.status, scale.kappa_squared, scale.kappa,
                range_result.status, range_result.quantile, residuals,
                ("UNAVAILABLE",) * 6, reasons))
        cutoffs = tuple(pair[0].cutoff_at for pair in selected_all)
        combined_cohort = "v9v4statecohort:" + canonical_sha256(
            tuple(cohorts[horizon] for horizon in HORIZONS))
        return build_v4c_state(
            symbol=symbol, cohort_id=combined_cohort, state_as_of=state_as_of,
            evidence_first_cutoff=min(cutoffs) if cutoffs else None,
            evidence_last_cutoff=max(cutoffs) if cutoffs else None,
            horizons=tuple(compact))


class PostgresV4StateBuilder:
    """Publish V4B and V4C from the same new-outcome scheduler generation."""

    def __init__(self, accuracy_builder, compact_builder):
        self._accuracy_builder = accuracy_builder
        self._compact_builder = compact_builder

    def prepare(self, **candidate) -> None:
        self._accuracy_builder.prepare(**candidate)
        self._compact_builder.prepare(**candidate)

    def rebind_connection(self, connection) -> None:
        self._accuracy_builder.rebind_connection(connection)
        self._compact_builder.rebind_connection(connection)

    def build_and_publish(self) -> str:
        accuracy = self._accuracy_builder.build_and_publish()
        compact = self._compact_builder.build_and_publish()
        if "INSERT" in (accuracy, compact):
            return "INSERT"
        if accuracy == compact == "IDEMPOTENT":
            return "IDEMPOTENT"
        return compact if compact != "IDEMPOTENT" else accuracy


@dataclass(frozen=True, slots=True)
class V4StateBuildCandidate:
    """One immutable per-cohort request for the off-FIFO state builder."""

    symbol: str
    state_as_of: datetime
    cohorts: tuple[tuple[str, str, str], ...]
    new_outcome: bool


class V4StateBuildWorker:
    """Run full-history V4 state construction outside the evidence FIFO."""

    def __init__(self, state_builder: PostgresV4StateBuilder,
                 scheduler: OfflineStateBuildScheduler, *, connection=None,
                 connect: Callable | None = None, database_url: str | None = None,
                 metrics: OperationalMetrics | None = None):
        self._builder = state_builder
        self._scheduler = scheduler
        self._metrics = metrics or OperationalMetrics()
        self._connection = connection
        self._connect = connect
        self._database_url = database_url
        self._pending_candidates: dict[
            tuple[str, tuple[tuple[str, str, str], ...]], V4StateBuildCandidate
        ] = {}
        self._latest_lock = threading.Lock()
        self._wake = threading.Event()
        self._stop = threading.Event()
        self._thread: threading.Thread | None = None
        self._needs_reconnect = False

    def _reconnect(self) -> None:
        if self._connect is None or not self._database_url:
            raise RuntimeError("V4 state builder reconnect is not configured")
        connection = self._connect(self._database_url)
        try:
            self._builder.rebind_connection(connection)
        except Exception:
            close = getattr(connection, "close", None)
            if callable(close):
                close()
            raise
        old, self._connection = self._connection, connection
        rollback = getattr(old, "rollback", None)
        if callable(rollback):
            try:
                rollback()
            except Exception:
                pass
        close = getattr(old, "close", None)
        if callable(close):
            close()
        self._metrics.increment("v4_state_build_worker.reconnect_success")

    def _recover_if_needed(self) -> bool:
        if not self._needs_reconnect:
            return True
        try:
            self._reconnect()
        except Exception:
            self._metrics.increment("v4_state_build_worker.reconnect_failure")
            return False
        self._needs_reconnect = False
        return True

    def submit(self, *, symbol: str, state_as_of: datetime,
               cohorts: dict[str, tuple[str, str]], new_outcome: bool) -> None:
        ordered = tuple((horizon, *cohorts[horizon]) for horizon in HORIZONS)
        if tuple(cohorts) != HORIZONS:
            raise ValueError("cohorts must contain exactly six canonical horizons in order")
        candidate = V4StateBuildCandidate(
            symbol, state_as_of, ordered, bool(new_outcome))
        if not candidate.new_outcome:
            return
        key = (candidate.symbol, candidate.cohorts)
        with self._latest_lock:
            existing = self._pending_candidates.get(key)
            if existing is not None:
                latest = (candidate if candidate.state_as_of >= existing.state_as_of
                          else existing)
                candidate = V4StateBuildCandidate(
                    latest.symbol, latest.state_as_of, latest.cohorts, True,
                )
                self._metrics.increment("v4_state_build_worker.coalesced")
            self._pending_candidates[key] = candidate
        self._wake.set()

    def _take_next(self) -> V4StateBuildCandidate | None:
        with self._latest_lock:
            if not self._pending_candidates:
                return None
            key = next(iter(self._pending_candidates))
            return self._pending_candidates.pop(key)

    def _has_pending(self) -> bool:
        with self._latest_lock:
            return bool(self._pending_candidates)

    def run(self) -> None:
        active: V4StateBuildCandidate | None = None
        pending_generation = False
        while True:
            if self._stop.is_set() and active is None and not self._has_pending():
                break
            self._wake.wait(1.0)
            self._wake.clear()
            if not self._recover_if_needed():
                continue
            if active is None:
                active = self._take_next()
            if active is not None and not pending_generation:
                try:
                    self._builder.prepare(
                        symbol=active.symbol,
                        state_as_of=active.state_as_of,
                        cohorts={horizon: (cohort_id, cohort_hash)
                                 for horizon, cohort_id, cohort_hash in active.cohorts},
                    )
                    self._scheduler.note_new_outcome()
                    pending_generation = True
                except Exception as error:
                    self._metrics.increment("v4_state_build_worker.failure")
                    if _transient_database_error(error):
                        self._needs_reconnect = True
                        self._recover_if_needed()
                    else:
                        active = None
                    continue
            if not pending_generation:
                continue
            try:
                status = self._scheduler.run_if_due(force=self._stop.is_set())
            except Exception as error:
                self._metrics.increment("v4_state_build_worker.failure")
                if _transient_database_error(error):
                    self._needs_reconnect = True
                    self._recover_if_needed()
                continue
            if status in {"INSERT", "IDEMPOTENT", "SKIPPED_NO_NEW_OUTCOME"}:
                pending_generation = False
                active = None
                if self._has_pending():
                    self._wake.set()

    def start(self) -> threading.Thread:
        if self._thread is not None and self._thread.is_alive():
            return self._thread
        self._thread = threading.Thread(
            target=self.run, name="v4-state-builder", daemon=True)
        self._thread.start()
        return self._thread

    def stop(self) -> None:
        self._stop.set()
        self._wake.set()
        if self._thread is not None:
            # Never close a recovered connection underneath an active build.
            self._thread.join()
        close = getattr(self._connection, "close", None)
        if callable(close):
            close()
        self._connection = None

    def close(self) -> None:
        self.stop()


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
        self._availability_lock = threading.Lock()

    def put_nowait(self, item: QuoteEvidenceWork) -> bool:
        started = time.perf_counter()
        try:
            # Serialize the availability transition with the non-blocking put.
            # Once unavailable() returns, every previously accepted item is
            # therefore visible to join() and no later item can enter the FIFO.
            with self._availability_lock:
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

    def join(self) -> None:
        """Wait until every item accepted before shutdown is finalized."""

        self._queue.join()

    def has_unfinished(self) -> bool:
        """Report whether shutdown would need a live consumer to drain."""

        with self._queue.mutex:
            return self._queue.unfinished_tasks != 0

    def unavailable(self) -> None:
        with self._availability_lock:
            self._available = False


class EvidenceLedgerWorker:
    """The one serial FIFO owner of COIN evidence persistence and resolution."""

    def __init__(self, outbox: EvidenceOutbox, *, evidence_store,
                 connection=None, connect: Callable | None = None,
                 database_url: str | None = None,
                 metrics: OperationalMetrics | None = None,
                 cache_refresher: V4StateCacheRefresher | None = None,
                 state_build_submit: Callable | None = None,
                 simulation_submit: Callable | None = None,
                 wall_clock: Callable[[], datetime] = lambda: datetime.now(timezone.utc)):
        if connection is None:
            if connect is None:
                import psycopg
                connect = psycopg.connect
            connection = connect(database_url)
        self.outbox, self._store, self._connection = outbox, evidence_store, connection
        self._connect, self._database_url = connect, database_url
        self._writer = V4AWriter(connection)
        self.metrics = metrics or outbox.metrics
        self._clock = wall_clock
        self._cache_refresher = cache_refresher
        self._state_build_submit = state_build_submit
        self._simulation_submit = simulation_submit
        self._pending: list[V4ForecastRecord] = self._load_pending()
        self._last_sequence: int | None = None
        self._resolution_contiguous = True
        self._stop = threading.Event()
        self._thread: threading.Thread | None = None
        self._needs_reconnect = False

    def _reconnect(self) -> None:
        """Replace every dependency bound to the failed shared connection."""

        if self._connect is None or not self._database_url:
            raise RuntimeError("evidence ledger reconnect is not configured")
        connection = self._connect(self._database_url)
        old = self._connection
        rebind_store = None
        try:
            writer = V4AWriter(connection)
            rebind_store = getattr(self._store, "rebind_connection", None)
            if not callable(rebind_store):
                raise RuntimeError("evidence store cannot rebind its connection")
            rebind_store(connection)
            if self._cache_refresher is not None:
                self._cache_refresher.rebind_connection(connection)
        except Exception:
            try:
                if callable(rebind_store):
                    rebind_store(old)
                if self._cache_refresher is not None:
                    self._cache_refresher.rebind_connection(old)
            except Exception:
                pass
            close = getattr(connection, "close", None)
            if callable(close):
                close()
            raise
        self._connection = connection
        self._writer = writer
        rollback = getattr(old, "rollback", None)
        if callable(rollback):
            try:
                rollback()
            except Exception:
                pass
        close = getattr(old, "close", None)
        if callable(close):
            close()
        self.metrics.increment("evidence_ledger_worker.reconnect_success")

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
        new_outcome = False
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
                    new_outcome = new_outcome or self._writer.last_write_status == "INSERT"
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
        # SIM-3's single eligibility clock read is the first operation after
        # all six forecast persistence results are final.  State construction,
        # cache refresh, and every other derived action happen afterwards.
        if (self._simulation_submit is not None and
                isinstance(item.v4d_output, V4DCycleOutput)
                and len(finalized) == 6):
            try:
                self._simulation_submit(item.v4d_output, tuple(finalized))
            except Exception:
                pass
        remaining.sort(key=lambda row: (row.target_endpoint, row.forecast_record_id))
        self._pending = remaining
        self._last_sequence = item.sequence
        self._resolution_contiguous = True
        refresh_cutoff = max(
            item.received_at,
            datetime.fromtimestamp(current.event_epoch, timezone.utc),
        )
        if self._state_build_submit is not None and len(item.v4) == 6:
            try:
                self._state_build_submit(
                    symbol=item.v4[0].symbol, state_as_of=refresh_cutoff,
                    cohorts={forecast.horizon: (forecast.cohort_id, forecast.cohort_hash)
                             for forecast in item.v4},
                    new_outcome=new_outcome,
                )
            except Exception:
                self.metrics.increment("v4_state_build_submit.failure")
        if self._cache_refresher is not None and item.state_cohort_id is not None:
            try:
                self._cache_refresher.refresh(
                    symbol="COIN", cohort_id=item.state_cohort_id,
                    cutoff=refresh_cutoff)
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
                if self._needs_reconnect:
                    try:
                        self._reconnect()
                    except Exception:
                        self.metrics.increment(
                            "evidence_ledger_worker.reconnect_failure")
                        time.sleep(.1)
                        continue
                    self._needs_reconnect = False
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
                    self._needs_reconnect = True
                    time.sleep(.1)  # transient off-path retry of the same FIFO head

    def start(self) -> threading.Thread:
        if self._thread is not None and self._thread.is_alive():
            return self._thread
        self._thread = threading.Thread(
            target=self.run, name="coin-evidence-ledger", daemon=True)
        self._thread.start()
        return self._thread

    def close(self) -> None:
        self.outbox.unavailable()
        if self._thread is not None and self._thread.is_alive():
            # Keep retrying the exact FIFO head until all accepted work has a
            # durable or terminal disposition.  Stopping first would silently
            # abandon queued evidence.
            self.outbox.join()
        elif self.outbox.has_unfinished():
            raise RuntimeError("cannot drain evidence outbox without a live worker")
        self._stop.set()
        if self._thread is not None:
            self._thread.join()
        close = getattr(self._connection, "close", None)
        if callable(close):
            close()
        self._connection = None