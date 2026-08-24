"""Bounded, non-blocking handoff from the COIN quote path to its ledger.

The envelope is deliberately made entirely from frozen values.  In particular the
worker is never allowed to go looking for a quote with which to resolve a target.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
import math
from queue import Empty, Full, Queue
import shlex
import threading
import time
from typing import Callable
from urllib.parse import urlparse

from .evidence import ForecastRecord as RawForecastRecord, VolatilityForecastRecord
from .history import MidpointObservation
from .v9_v4a_evidence import ForecastRecord as V4ForecastRecord, V4AWriter, canonical_target_identity
from .v9_v4a_evidence import (
    CONTRACT_VERSION as V4_CONTRACT_VERSION, EVIDENCE_VERSION as V4_EVIDENCE_VERSION,
    canonical_sha256, deserialize_forecast_record, deserialize_outcome_record,
    select_non_overlapping,
)
from .v9_v4b_accuracy import (
    AccuracyStateStore, STATE_VERSION as ACCURACY_STATE_VERSION,
    MODEL_VERSION as STATE_MODEL_VERSION,
    build_accuracy_state,
)
from .v9_v1_contract import HORIZONS
from .v9_v4c_predictive import (
    CalibrationObservation, CompactHorizonState, RangeValidationObservation,
    PROBABILITY_STATE_VERSION, V4CStateStore, build_thresholds,
    build_v4c_state, calibrate_range, calibrate_scale,
)
from .v9_v4d_integration import (
    ImmutableStateCache, OfflineStateBuildScheduler, OperationalMetrics,
    V4DCycleOutput, resolve_outcome,
)
from .v9_sim3_capture import FinalizedV4PersistenceResult


EVIDENCE_OUTBOX_CAPACITY = 256
STATE_BUILD_SHUTDOWN_TIMEOUT_SECONDS = 20.0
STATE_BUILD_SHUTDOWN_JOIN_GRACE_SECONDS = 0.25
EVIDENCE_RUNTIME_LOCK_ID = int.from_bytes(b"ATOMV9EL", "big")
EVIDENCE_RECOVERY_OUTCOME_LIMIT = 65_536
EVIDENCE_RECOVERY_CYCLE_QUERY_CHUNK = 4_096
EVIDENCE_LEGACY_WRITER_QUIESCENCE_SECONDS = 2.5
_TERMINAL_FAILURE_REASONS = frozenset({
    "MALFORMED_EVIDENCE_ENVELOPE",
    "EVIDENCE_EVENT_ORDER_VIOLATION",
    "EVIDENCE_HANDOFF_SUPERSEDED",
    "OUTCOME_CONFLICT",
    "FORECAST_DUPLICATE_CONFLICT",
})


def _v4_cohort_scope(cohorts: dict[str, tuple[str, str]]) -> tuple[str, tuple[str, ...]]:
    """Return a bound SQL predicate for the exact six state cohorts."""

    if tuple(cohorts) != HORIZONS:
        raise ValueError("cohorts must contain exactly six canonical horizons in order")
    clause = " OR ".join(
        "(f.horizon=%s AND f.record_json->>'cohort_id'=%s "
        "AND f.record_json->>'cohort_hash'=%s)" for _horizon in HORIZONS)
    params = tuple(value for horizon in HORIZONS
                   for value in (horizon, *cohorts[horizon]))
    return clause, params


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
                 accuracy_cache: ImmutableStateCache,
                 metrics: OperationalMetrics | None = None):
        self._compact_store, self._accuracy_store = compact_store, accuracy_store
        self._compact_cache, self._accuracy_cache = compact_cache, accuracy_cache
        self._metrics = metrics or OperationalMetrics()

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
        accuracy, accuracy_status = self._accuracy_store.latest_json(
            symbol=symbol, cohort_id=cohort_id, requested_cutoff=cutoff)
        if not (compact_status == accuracy_status == "AVAILABLE" and
                compact is not None and accuracy is not None):
            self._metrics.set_status("v4_state_pair_status", "UNAVAILABLE")
            return
        compact_key = (compact.symbol, compact.cohort_id, compact.state_as_of)
        accuracy_key = (accuracy.symbol, accuracy.cohort_id, accuracy.state_as_of)
        if compact_key != accuracy_key or compact_key[:2] != (symbol, cohort_id):
            self._metrics.increment("v4_state_pair.generation_mismatch")
            self._metrics.set_status(
                "v4_state_pair_status", "GENERATION_MISMATCH")
            return
        self._compact_cache.publish(compact)
        self._accuracy_cache.publish(accuracy)
        self._metrics.set_status("v4_state_pair_status", "AVAILABLE")


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
        cohort_scope, cohort_params = _v4_cohort_scope(cohorts)
        cursor = self._connection.cursor()
        try:
            cursor.execute(
                f"""SELECT f.forecast_record_hash, f.record_json,
                          o.outcome_record_hash, o.record_json
                   FROM public.atom_v9_v4_forecasts AS f
                   JOIN public.atom_v9_v4_outcomes AS o
                     USING (forecast_record_id)
                   WHERE f.symbol=%s AND f.cutoff_at<=%s AND o.created_at<=%s
                     AND ({cohort_scope})
                   ORDER BY f.cutoff_at, f.forecast_record_id,
                            o.created_at, o.outcome_record_id""",
                (symbol, state_as_of, state_as_of, *cohort_params),
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
        cohort_scope, cohort_params = _v4_cohort_scope(cohorts)
        cursor = self._connection.cursor()
        try:
            cursor.execute(
                f"""SELECT f.forecast_record_hash, f.record_json,
                          o.outcome_record_hash, o.record_json
                   FROM public.atom_v9_v4_forecasts AS f
                   JOIN public.atom_v9_v4_outcomes AS o
                     USING (forecast_record_id)
                   WHERE f.symbol=%s AND f.cutoff_at<=%s AND o.created_at<=%s
                     AND ({cohort_scope})
                   ORDER BY f.cutoff_at, f.forecast_record_id,
                            o.created_at, o.outcome_record_id""",
                (symbol, state_as_of, state_as_of, *cohort_params),
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

    class _CommitSuppressingConnection:
        """Share one transaction while preserving the two frozen store APIs."""

        def __init__(self, connection):
            self._connection = connection

        def cursor(self, *args, **kwargs):
            return self._connection.cursor(*args, **kwargs)

        def commit(self) -> None:
            return None

        def rollback(self) -> None:
            rollback = getattr(self._connection, "rollback", None)
            if callable(rollback):
                rollback()

        def __getattr__(self, name):
            return getattr(self._connection, name)

    def __init__(self, accuracy_builder, compact_builder, *, connection=None):
        self._accuracy_builder = accuracy_builder
        self._compact_builder = compact_builder
        inferred = getattr(accuracy_builder, "_connection", None)
        self._connection = connection if connection is not None else inferred
        if self._connection is None:
            raise ValueError("combined V4 state builder requires one shared connection")
        compact_connection = getattr(compact_builder, "_connection", self._connection)
        if inferred is not None and inferred is not self._connection:
            raise ValueError("accuracy builder is not bound to the shared connection")
        if compact_connection is not self._connection:
            raise ValueError("compact builder is not bound to the shared connection")
        if bool(getattr(self._connection, "autocommit", False)):
            raise ValueError("atomic V4 state publication requires autocommit disabled")

    def prepare(self, **candidate) -> None:
        self._accuracy_builder.prepare(**candidate)
        self._compact_builder.prepare(**candidate)

    def rebind_connection(self, connection) -> None:
        if bool(getattr(connection, "autocommit", False)):
            raise ValueError("atomic V4 state publication requires autocommit disabled")
        self._connection = connection
        self._accuracy_builder.rebind_connection(connection)
        self._compact_builder.rebind_connection(connection)

    def build_and_publish(self) -> str:
        connection = self._connection
        if bool(getattr(connection, "autocommit", False)):
            raise RuntimeError("atomic V4 state publication requires autocommit disabled")
        for builder in (self._accuracy_builder, self._compact_builder):
            bound = getattr(builder, "_connection", connection)
            if bound is not connection:
                raise RuntimeError("V4 state builders lost their shared connection")
        proxy = self._CommitSuppressingConnection(connection)
        self._accuracy_builder.rebind_connection(proxy)
        self._compact_builder.rebind_connection(proxy)
        try:
            cursor = connection.cursor()
            try:
                # PostgreSQL READ COMMITTED takes a new snapshot for every
                # statement.  Both frozen builders must instead see exactly the
                # same evidence generation before their writes commit together.
                cursor.execute("SET TRANSACTION ISOLATION LEVEL REPEATABLE READ")
            finally:
                close = getattr(cursor, "close", None)
                if callable(close):
                    close()
            accuracy = self._accuracy_builder.build_and_publish()
            if accuracy not in {"INSERT", "IDEMPOTENT"}:
                rollback = getattr(connection, "rollback", None)
                if callable(rollback):
                    rollback()
                return accuracy
            compact = self._compact_builder.build_and_publish()
            if compact not in {"INSERT", "IDEMPOTENT"}:
                rollback = getattr(connection, "rollback", None)
                if callable(rollback):
                    rollback()
                return compact
            commit = getattr(connection, "commit", None)
            if not callable(commit):
                raise RuntimeError("shared V4 state connection cannot commit")
            commit()
            return "INSERT" if "INSERT" in (accuracy, compact) else "IDEMPOTENT"
        except Exception:
            rollback = getattr(connection, "rollback", None)
            if callable(rollback):
                rollback()
            raise
        finally:
            self._accuracy_builder.rebind_connection(connection)
            self._compact_builder.rebind_connection(connection)


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
                 metrics: OperationalMetrics | None = None,
                 shutdown_timeout_seconds: float = STATE_BUILD_SHUTDOWN_TIMEOUT_SECONDS):
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
        self._shutdown_timeout_seconds = float(shutdown_timeout_seconds)
        self._shutdown_deadline: float | None = None
        self._shutdown_abandonment_recorded = threading.Event()
        self._shutdown_abandonment_lock = threading.Lock()

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

    def _shutdown_expired(self) -> bool:
        return (self._stop.is_set() and self._shutdown_deadline is not None and
                time.monotonic() >= self._shutdown_deadline)

    def _record_shutdown_abandonment(self) -> None:
        with self._shutdown_abandonment_lock:
            if not self._shutdown_abandonment_recorded.is_set():
                self._shutdown_abandonment_recorded.set()
                self._metrics.increment("v4_state_build_worker.shutdown_abandoned")

    def _close_connection(self) -> None:
        connection, self._connection = self._connection, None
        close = getattr(connection, "close", None)
        if callable(close):
            close()

    def run(self) -> None:
        active: V4StateBuildCandidate | None = None
        pending_generation = False
        try:
            while True:
                if self._shutdown_expired():
                    if active is not None or pending_generation or self._has_pending():
                        self._record_shutdown_abandonment()
                    break
                if self._stop.is_set() and active is None and not self._has_pending():
                    break
                wait_seconds = 1.0
                if self._stop.is_set() and self._shutdown_deadline is not None:
                    wait_seconds = max(
                        0.0, min(wait_seconds,
                                 self._shutdown_deadline - time.monotonic()))
                self._wake.wait(wait_seconds)
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
                    else:
                        self._metrics.increment(
                            "v4_state_build_worker.terminal_exception")
                        self._metrics.set_status(
                            "v4_state_build_worker.last_terminal_status",
                            "UNEXPECTED_EXCEPTION",
                        )
                        pending_generation = False
                        active = None
                        if self._has_pending():
                            self._wake.set()
                    continue
                if status == "SKIPPED_RATE_LIMIT":
                    continue
                if status in {"INSERT", "IDEMPOTENT", "SKIPPED_NO_NEW_OUTCOME"}:
                    pending_generation = False
                    active = None
                    if self._has_pending():
                        self._wake.set()
                else:
                    # A deterministic fail-closed status cannot become
                    # successful through an in-process retry.  Do not let one
                    # cohort starve every later pending cohort.
                    self._metrics.increment(
                        "v4_state_build_worker.terminal_status")
                    self._metrics.set_status(
                        "v4_state_build_worker.last_terminal_status",
                        status if isinstance(status, str) and status in {
                            "STATE_CONFLICT", "STATE_HASH_MISMATCH",
                            "STATE_TIME_INVALID", "STATE_GENERATION_INCOMPLETE",
                            "STATE_GENERATION_MISMATCH",
                        } else "UNEXPECTED_STATUS",
                    )
                    pending_generation = False
                    active = None
                    if self._has_pending():
                        self._wake.set()
        finally:
            self._close_connection()

    def start(self) -> threading.Thread:
        if self._thread is not None and self._thread.is_alive():
            return self._thread
        self._thread = threading.Thread(
            target=self.run, name="v4-state-builder", daemon=True)
        self._thread.start()
        return self._thread

    def stop(self) -> None:
        if self._shutdown_deadline is None:
            self._shutdown_deadline = (
                time.monotonic() + self._shutdown_timeout_seconds)
        self._stop.set()
        self._wake.set()
        if self._thread is not None:
            # Never close a recovered connection underneath an active build.
            # Its own deadline ends retries.  A small, still-bounded scheduling
            # grace lets the worker execute ``finally`` and close its connection.
            self._thread.join(timeout=(self._shutdown_timeout_seconds +
                                       STATE_BUILD_SHUTDOWN_JOIN_GRACE_SECONDS))
            if self._thread.is_alive():
                self._record_shutdown_abandonment()
        if self._thread is None or not self._thread.is_alive():
            self._close_connection()

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

    def remaining_capacity(self) -> int:
        """Return a producer-side bound; the single consumer can only increase it."""

        with self._queue.mutex:
            return max(0, self._queue.maxsize - self._queue._qsize())

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
        self._validate_runtime_database_url(database_url)
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
        self._handoff_anchor: MidpointObservation | None = None
        self._handoff_fence_anchor: MidpointObservation | None = None
        self._last_sequence: int | None = None
        self._resolution_contiguous = True
        self._stop = threading.Event()
        self._thread: threading.Thread | None = None
        self._needs_reconnect = False
        self._owns_runtime = False
        self._ownership_generation = 0
        self.metrics.set_status("evidence_runtime_owner_status", "WAITING")

    @staticmethod
    def _validate_runtime_database_url(database_url: str | None) -> None:
        """Fail closed when Supavisor transaction mode cannot own a session lock."""

        if not database_url:
            return
        if "://" in database_url:
            parsed = urlparse(database_url)
            hostname = (parsed.hostname or "").lower()
            port = parsed.port
        else:
            fields = {}
            for token in shlex.split(database_url):
                if "=" in token:
                    key, value = token.split("=", 1)
                    fields[key.strip().lower()] = value.strip()
            hostname = fields.get("host", "").lower()
            try:
                port = int(fields["port"]) if "port" in fields else None
            except ValueError as error:
                raise ValueError("invalid database port") from error
        if hostname.endswith(".pooler.supabase.com") and port == 6543:
            raise ValueError(
                "evidence runtime ownership requires Supabase session mode, not port 6543")

    def _reconnect(self) -> None:
        """Replace every dependency bound to the failed shared connection."""

        if self._connect is None or not self._database_url:
            raise RuntimeError("evidence ledger reconnect is not configured")
        self._owns_runtime = False
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

    @staticmethod
    def _cycle_key(record: V4ForecastRecord) -> tuple[str, datetime, str, str]:
        return (record.symbol, record.cutoff_at, record.cycle_id,
                record.v3_model_version)

    def _validated_forecasts(self, rows, *, invalid_metric: str) -> list[V4ForecastRecord]:
        recovered = []
        for expected_hash, payload in rows:
            try:
                record = deserialize_forecast_record(
                    payload, expected_hash=str(expected_hash))
            except ValueError:
                self.metrics.increment(invalid_metric)
                continue
            if record.persistence_proof_eligible is True:
                recovered.append(record)
        return recovered

    @staticmethod
    def _close_cursor(cursor) -> None:
        close = getattr(cursor, "close", None)
        if callable(close):
            close()

    def _load_pending(self) -> list[V4ForecastRecord]:
        """Recover only durable, unresolved forecasts in the conservative window."""
        cursor = self._connection.cursor()
        try:
            cursor.execute(
                """SELECT f.forecast_record_hash, f.record_json
                   FROM public.atom_v9_v4_forecasts AS f
                   WHERE f.symbol='COIN'
                     AND f.target_endpoint >= now() - interval '1 hour'
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
            self._close_cursor(cursor)
        return self._validated_forecasts(
            rows, invalid_metric="evidence_recovery.invalid_record")

    def _load_due(self, previous: MidpointObservation,
                  current: MidpointObservation) -> list[V4ForecastRecord]:
        """Load only durable unresolved forecasts in this exact provider bracket."""

        lower = datetime.fromtimestamp(previous.event_epoch, timezone.utc)
        upper = datetime.fromtimestamp(current.event_epoch, timezone.utc)
        cursor = self._connection.cursor()
        try:
            cursor.execute(
                """SELECT f.forecast_record_hash, f.record_json
                   FROM public.atom_v9_v4_forecasts AS f
                   WHERE f.symbol='COIN'
                     AND f.target_endpoint > %s
                     AND f.target_endpoint <= %s
                     AND f.persisted_at <= f.target_endpoint
                     AND NOT EXISTS (
                         SELECT 1 FROM public.atom_v9_v4_outcomes AS o
                         WHERE o.forecast_record_id=f.forecast_record_id)
                   ORDER BY f.target_endpoint, f.forecast_record_id""",
                (lower, upper),
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
            self._close_cursor(cursor)
        return self._validated_forecasts(
            rows, invalid_metric="evidence_recovery.invalid_due_record")

    def _merge_pending(self, *groups) -> list[V4ForecastRecord]:
        merged: dict[str, V4ForecastRecord] = {}
        for records in groups:
            for record in records:
                merged.setdefault(record.forecast_record_id, record)
        values = sorted(
            merged.values(),
            key=lambda row: (row.target_endpoint, row.forecast_record_id),
        )
        return values

    def _load_cycle_forecasts(
        self, keys: tuple[tuple[str, datetime, str, str], ...],
    ) -> dict[tuple[str, datetime, str, str], tuple[V4ForecastRecord, ...]]:
        keys = tuple(dict.fromkeys(keys))
        if not keys:
            return {}
        cursor = self._connection.cursor()
        try:
            rows = []
            # Four binds per cycle plus six horizon binds must remain below
            # PostgreSQL's 65,535-parameter protocol ceiling even when the
            # independently bounded recovery window is completely populated.
            for start in range(0, len(keys), EVIDENCE_RECOVERY_CYCLE_QUERY_CHUNK):
                chunk = keys[start:start + EVIDENCE_RECOVERY_CYCLE_QUERY_CHUNK]
                clauses = " OR ".join(
                    "(f.symbol=%s AND f.cutoff_at=%s AND f.cycle_id=%s "
                    "AND f.v3_model_version=%s)" for _key in chunk)
                params = tuple(value for key in chunk for value in key) + HORIZONS
                cursor.execute(
                    f"""SELECT f.forecast_record_hash, f.record_json
                       FROM public.atom_v9_v4_forecasts AS f
                       WHERE ({clauses})
                         AND f.horizon IN (%s,%s,%s,%s,%s,%s)
                       ORDER BY f.symbol, f.cutoff_at, f.cycle_id,
                                f.v3_model_version, CASE f.horizon
                         WHEN '30S' THEN 0 WHEN '1M' THEN 1 WHEN '5M' THEN 2
                         WHEN '15M' THEN 3 WHEN '30M' THEN 4 WHEN '1H' THEN 5
                         ELSE 6 END""",
                    params,
                )
                rows.extend(cursor.fetchall())
            commit = getattr(self._connection, "commit", None)
            if callable(commit):
                commit()
        except Exception:
            rollback = getattr(self._connection, "rollback", None)
            if callable(rollback):
                rollback()
            raise
        finally:
            self._close_cursor(cursor)
        siblings = self._validated_forecasts(
            tuple(rows), invalid_metric="v4_state_build_lineage.invalid_record")
        grouped: dict[
            tuple[str, datetime, str, str], list[V4ForecastRecord]
        ] = {key: [] for key in keys}
        for record in siblings:
            key = self._cycle_key(record)
            if key in grouped:
                grouped[key].append(record)
        complete = {}
        for key in keys:
            records = grouped[key]
            if (len(records) != len(HORIZONS) or
                    tuple(record.horizon for record in records) != HORIZONS):
                self.metrics.increment("v4_state_build_lineage.unavailable")
                continue
            complete[key] = tuple(records)
        return complete

    def _complete_cycles_cohorts(
        self, forecasts: tuple[V4ForecastRecord, ...],
    ) -> dict[tuple[str, datetime, str, str], dict[str, tuple[str, str]]]:
        records_by_key = self._load_cycle_forecasts(tuple(
            self._cycle_key(forecast) for forecast in forecasts))
        return {
            key: {
                record.horizon: (record.cohort_id, record.cohort_hash)
                for record in records
            }
            for key, records in records_by_key.items()
        }

    def _complete_cycle_cohorts(
            self, forecast: V4ForecastRecord) -> dict[str, tuple[str, str]] | None:
        return self._complete_cycles_cohorts((forecast,)).get(
            self._cycle_key(forecast))

    def _try_acquire_runtime_ownership(self) -> bool:
        cursor = self._connection.cursor()
        try:
            cursor.execute(
                "SELECT pg_try_advisory_lock(%s)",
                (EVIDENCE_RUNTIME_LOCK_ID,),
            )
            row = cursor.fetchone()
            commit = getattr(self._connection, "commit", None)
            if callable(commit):
                commit()
        except Exception:
            rollback = getattr(self._connection, "rollback", None)
            if callable(rollback):
                rollback()
            raise
        finally:
            self._close_cursor(cursor)
        return bool(row and row[0] is True)

    def _load_handoff_anchor(self) -> MidpointObservation | None:
        cursor = self._connection.cursor()
        try:
            cursor.execute(
                """WITH complete_cycle AS (
                       SELECT f.symbol, f.cutoff_at, f.cycle_id,
                              f.v3_model_version
                       FROM public.atom_v9_v4_forecasts AS f
                       WHERE f.symbol='COIN'
                         AND f.persisted_at <= f.target_endpoint
                         AND f.horizon IN (%s,%s,%s,%s,%s,%s)
                       GROUP BY f.symbol, f.cutoff_at, f.cycle_id,
                                f.v3_model_version
                       HAVING count(*)=%s
                          AND bool_and(
                              f.record_json->>'persistence_proof_eligible'='true')
                          AND array_agg(f.horizon ORDER BY CASE f.horizon
                                WHEN '30S' THEN 0 WHEN '1M' THEN 1
                                WHEN '5M' THEN 2 WHEN '15M' THEN 3
                                WHEN '30M' THEN 4 WHEN '1H' THEN 5 ELSE 6 END
                              )=ARRAY[%s,%s,%s,%s,%s,%s]::text[]
                       ORDER BY f.cutoff_at DESC, f.cycle_id DESC
                       LIMIT 1
                   )
                   SELECT f.forecast_record_hash, f.record_json
                   FROM complete_cycle AS c
                   JOIN public.atom_v9_v4_forecasts AS f
                     ON f.symbol=c.symbol AND f.cutoff_at=c.cutoff_at
                    AND f.cycle_id=c.cycle_id
                    AND f.v3_model_version=c.v3_model_version
                   ORDER BY CASE f.horizon
                     WHEN '30S' THEN 0 WHEN '1M' THEN 1 WHEN '5M' THEN 2
                     WHEN '15M' THEN 3 WHEN '30M' THEN 4 WHEN '1H' THEN 5
                     ELSE 6 END
                   LIMIT 1""",
                (*HORIZONS, len(HORIZONS), *HORIZONS),
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
            self._close_cursor(cursor)
        records = self._validated_forecasts(
            rows, invalid_metric="evidence_handoff.invalid_anchor")
        if len(records) != 1 or records[0].cutoff_midpoint is None:
            return None
        return MidpointObservation(
            records[0].cutoff_at.timestamp(), records[0].cutoff_midpoint)

    def _release_runtime_ownership(self) -> None:
        cursor = self._connection.cursor()
        try:
            cursor.execute(
                "SELECT pg_advisory_unlock(%s)",
                (EVIDENCE_RUNTIME_LOCK_ID,),
            )
            commit = getattr(self._connection, "commit", None)
            if callable(commit):
                commit()
        except Exception:
            rollback = getattr(self._connection, "rollback", None)
            if callable(rollback):
                rollback()
            raise
        finally:
            self._close_cursor(cursor)

    def _resolved_recovery_cohorts(
            self) -> tuple[tuple[str, dict[str, tuple[str, str]], datetime], ...]:
        """Recover uncovered cohorts from a bounded set of latest durable outcomes."""

        cursor = self._connection.cursor()
        try:
            cursor.execute(
                """WITH recent_outcomes AS (
                       SELECT o.outcome_record_id, o.outcome_record_hash,
                              o.forecast_record_id, o.record_json, o.created_at
                       FROM public.atom_v9_v4_outcomes AS o
                       WHERE o.created_at >= (
                           SELECT max(anchor.created_at) - interval '1 hour'
                           FROM public.atom_v9_v4_outcomes AS anchor)
                       ORDER BY o.created_at DESC, o.outcome_record_id DESC
                       LIMIT %s
                   ), recent_count AS (
                       SELECT count(*) AS outcome_count FROM recent_outcomes
                   ), candidate_cycles AS (
                       SELECT f.symbol, f.cutoff_at, f.cycle_id,
                              f.v3_model_version, r.outcome_record_id,
                              r.outcome_record_hash, r.record_json AS outcome_json,
                              r.created_at AS latest_outcome_created_at
                       FROM recent_outcomes AS r
                       JOIN public.atom_v9_v4_forecasts AS f
                         USING (forecast_record_id)
                       WHERE f.symbol='COIN'
                         AND f.persisted_at <= f.target_endpoint
                   ), cycle_cohorts AS (
                       SELECT r.symbol, r.cutoff_at, r.cycle_id,
                              r.v3_model_version, r.outcome_record_id,
                              r.outcome_record_hash,
                              r.outcome_json, r.latest_outcome_created_at,
                              array_agg(f.horizon ORDER BY CASE f.horizon
                                WHEN '30S' THEN 0 WHEN '1M' THEN 1
                                WHEN '5M' THEN 2 WHEN '15M' THEN 3
                                WHEN '30M' THEN 4 WHEN '1H' THEN 5 ELSE 6 END
                              ) AS horizons,
                              array_agg(f.record_json->>'cohort_id'
                                ORDER BY CASE f.horizon
                                  WHEN '30S' THEN 0 WHEN '1M' THEN 1
                                  WHEN '5M' THEN 2 WHEN '15M' THEN 3
                                  WHEN '30M' THEN 4 WHEN '1H' THEN 5 ELSE 6 END
                              ) AS cohort_ids,
                              array_agg(f.record_json->>'cohort_hash'
                                ORDER BY CASE f.horizon
                                  WHEN '30S' THEN 0 WHEN '1M' THEN 1
                                  WHEN '5M' THEN 2 WHEN '15M' THEN 3
                                  WHEN '30M' THEN 4 WHEN '1H' THEN 5 ELSE 6 END
                              ) AS cohort_hashes
                       FROM candidate_cycles AS r
                       JOIN public.atom_v9_v4_forecasts AS f
                         ON f.symbol=r.symbol AND f.cutoff_at=r.cutoff_at
                        AND f.cycle_id=r.cycle_id
                        AND f.v3_model_version=r.v3_model_version
                       WHERE f.persisted_at <= f.target_endpoint
                         AND f.horizon IN (%s,%s,%s,%s,%s,%s)
                       GROUP BY r.symbol, r.cutoff_at, r.cycle_id,
                                r.v3_model_version, r.outcome_record_id,
                                r.outcome_record_hash,
                                r.outcome_json, r.latest_outcome_created_at
                       HAVING count(*)=%s
                   ), eligible_cycles AS (
                       SELECT symbol, cutoff_at, cycle_id, v3_model_version,
                              outcome_record_hash, outcome_json,
                              latest_outcome_created_at, cohort_ids,
                              cohort_hashes
                       FROM cycle_cohorts
                       WHERE horizons=ARRAY[%s,%s,%s,%s,%s,%s]::text[]
                   )
                   SELECT d.symbol, d.cutoff_at, d.cycle_id,
                          d.v3_model_version, d.outcome_record_hash,
                          d.outcome_json, d.latest_outcome_created_at,
                          d.cohort_ids, d.cohort_hashes,
                          c.outcome_count
                   FROM recent_count AS c
                   LEFT JOIN eligible_cycles AS d ON true
                   ORDER BY d.latest_outcome_created_at NULLS FIRST, d.symbol,
                            d.cohort_ids, d.cohort_hashes""",
                (EVIDENCE_RECOVERY_OUTCOME_LIMIT + 1, *HORIZONS,
                 len(HORIZONS), *HORIZONS),
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
            self._close_cursor(cursor)
        if not rows or not isinstance(rows[0][9], int):
            self.metrics.increment("v4_state_build_recovery.invalid_bound")
            raise RuntimeError("V4 recovery did not return its outcome bound")
        if rows[0][9] > EVIDENCE_RECOVERY_OUTCOME_LIMIT:
            self.metrics.increment("v4_state_build_recovery.truncated")
            raise RuntimeError("V4 recovery outcome window exceeded its bound")

        candidates = []
        for row in rows:
            (symbol, cutoff_at, cycle_id, model_version, outcome_hash,
             outcome_json, created_at, cohort_ids, cohort_hashes, _count) = row
            if symbol is None:
                continue
            try:
                outcome = deserialize_outcome_record(
                    outcome_json, expected_hash=str(outcome_hash))
            except ValueError:
                self.metrics.increment(
                    "v4_state_build_recovery.invalid_outcome")
                continue
            if (not isinstance(created_at, datetime) or created_at.tzinfo is None or
                    outcome.created_at != created_at or
                    outcome.proof_eligible is not True or
                    outcome.target_timing_status != "VERIFIED" or
                    not isinstance(cutoff_at, datetime) or cutoff_at.tzinfo is None or
                    tuple(cohort_ids or ()) == () or
                    len(tuple(cohort_ids or ())) != len(HORIZONS) or
                    len(tuple(cohort_hashes or ())) != len(HORIZONS)):
                self.metrics.increment("v4_state_build_recovery.unavailable")
                continue
            key = (str(symbol), cutoff_at, str(cycle_id), str(model_version))
            candidates.append((key, outcome, created_at,
                               tuple(cohort_ids), tuple(cohort_hashes)))

        forecasts_by_key = self._load_cycle_forecasts(tuple(
            candidate[0] for candidate in candidates))
        distinct: dict[
            tuple[str, tuple[tuple[str, str, str], ...]],
            tuple[dict[str, tuple[str, str]], datetime],
        ] = {}
        for key, outcome, created_at, expected_ids, expected_hashes in candidates:
            forecasts = forecasts_by_key.get(key)
            if (forecasts is None or
                    outcome.forecast_record_id not in {
                        record.forecast_record_id for record in forecasts} or
                    tuple(record.cohort_id for record in forecasts) != expected_ids or
                    tuple(record.cohort_hash for record in forecasts) != expected_hashes):
                self.metrics.increment("v4_state_build_recovery.unavailable")
                continue
            cohorts = {
                record.horizon: (record.cohort_id, record.cohort_hash)
                for record in forecasts
            }
            cohort_key = tuple(
                (horizon, *cohorts[horizon]) for horizon in HORIZONS)
            identity = (forecasts[0].symbol, cohort_key)
            prior = distinct.get(identity)
            if prior is None or created_at > prior[1]:
                distinct[identity] = (cohorts, created_at)

        combined_ids = {
            identity: "v9v4statecohort:" + canonical_sha256(
                tuple((cohort_id, cohort_hash)
                      for _horizon, cohort_id, cohort_hash in identity[1]))
            for identity in distinct
        }
        covered: dict[tuple[str, str], datetime] = {}
        if combined_ids:
            cursor = self._connection.cursor()
            try:
                cursor.execute(
                    """SELECT s.symbol, s.cohort_id, s.state_as_of
                       FROM public.atom_v9_v4_states AS s
                       WHERE s.cohort_id=ANY(%s)
                         AND s.state_version IN (%s,%s)
                         AND s.model_version=%s
                       GROUP BY s.symbol, s.cohort_id, s.state_as_of
                       HAVING count(*) FILTER (
                                  WHERE s.state_version=%s)=1
                          AND count(*) FILTER (
                                  WHERE s.state_version=%s)=1
                          AND count(*)=2""",
                    (list(combined_ids.values()), ACCURACY_STATE_VERSION,
                     PROBABILITY_STATE_VERSION, STATE_MODEL_VERSION,
                     ACCURACY_STATE_VERSION, PROBABILITY_STATE_VERSION),
                )
                for symbol, cohort_id, state_as_of in cursor.fetchall():
                    coverage_key = (str(symbol), str(cohort_id))
                    if (isinstance(state_as_of, datetime) and
                            state_as_of.tzinfo is not None and
                            (coverage_key not in covered or
                             state_as_of > covered[coverage_key])):
                        covered[coverage_key] = state_as_of
                commit = getattr(self._connection, "commit", None)
                if callable(commit):
                    commit()
            except Exception:
                rollback = getattr(self._connection, "rollback", None)
                if callable(rollback):
                    rollback()
                raise
            finally:
                self._close_cursor(cursor)
        return tuple(
            (symbol, cohorts, created_at)
            for identity, (cohorts, created_at) in sorted(
                distinct.items(), key=lambda item: (
                    item[1][1], item[0][0], item[0][1]))
            for symbol in (identity[0],)
            if covered.get((identity[0], combined_ids[identity]),
                           datetime.min.replace(
                tzinfo=timezone.utc)) < created_at
        )

    def _submit_recovery_state_build(self) -> None:
        if self._state_build_submit is None:
            return
        recovery_clock = self._clock()
        failed = False
        for symbol, cohorts, outcome_created_at in self._resolved_recovery_cohorts():
            try:
                self._state_build_submit(
                    symbol=symbol,
                    state_as_of=max(recovery_clock, outcome_created_at),
                    cohorts=cohorts, new_outcome=True,
                )
                self.metrics.increment("v4_state_build_recovery.submitted")
            except Exception:
                failed = True
                self.metrics.increment("v4_state_build_recovery.failure")
        if failed:
            raise RuntimeError("one or more recovery state submissions failed")

    def _acquire_runtime_ownership(self) -> bool:
        if not self._try_acquire_runtime_ownership():
            self.metrics.set_status("evidence_runtime_owner_status", "WAITING")
            return False
        try:
            anchor = self._load_handoff_anchor()
            if self._database_url:
                time.sleep(EVIDENCE_LEGACY_WRITER_QUIESCENCE_SECONDS)
                confirmed_anchor = self._load_handoff_anchor()
                if confirmed_anchor != anchor:
                    self.metrics.increment(
                        "evidence_runtime_owner.legacy_writer_active")
                    self.metrics.set_status(
                        "evidence_runtime_owner_status",
                        "WAITING_FOR_LEGACY_WRITER",
                    )
                    self._release_runtime_ownership()
                    return False
                anchor = confirmed_anchor
            self._pending = self._merge_pending(self._pending, self._load_pending())
            self._submit_recovery_state_build()
        except Exception:
            self._release_runtime_ownership()
            raise
        self._handoff_anchor = anchor
        self._handoff_fence_anchor = anchor
        self._ownership_generation += 1
        self._owns_runtime = True
        self.metrics.increment("evidence_runtime_owner.acquired")
        self.metrics.set_status("evidence_runtime_owner_status", "ACTIVE")
        return True

    def is_runtime_owner(self) -> bool:
        """Gate quote/evidence ingress on this process's live DB session lock."""

        return self._owns_runtime and not self._needs_reconnect

    def runtime_handoff_anchor(self) -> MidpointObservation | None:
        return self._handoff_anchor if self.is_runtime_owner() else None

    def runtime_ownership_generation(self) -> int | None:
        """Expose only this process's acquisition generation."""

        return self._ownership_generation if self.is_runtime_owner() else None

    def _record_terminal_failure(self, error: Exception) -> None:
        reason = (str(error) if isinstance(error, TerminalDeliveryError)
                  else "UNEXPECTED_NONTRANSIENT")
        if reason not in _TERMINAL_FAILURE_REASONS:
            reason = "UNEXPECTED_NONTRANSIENT"
        self.metrics.increment("evidence_ledger_worker.terminal_failure")
        self.metrics.increment("evidence_ledger_worker.terminal_failure." + reason)
        self.metrics.set_status(
            "evidence_ledger_worker.last_terminal_failure", reason)

    def process(self, item: QuoteEvidenceWork) -> None:
        """Process exactly one bracket; callers may retry this same item."""
        started = time.perf_counter()
        if not isinstance(item, QuoteEvidenceWork) or item.sequence < 1:
            raise TerminalDeliveryError("MALFORMED_EVIDENCE_ENVELOPE")
        records = (*item.directional, *item.q3, *item.v4)
        if (any(getattr(record, "symbol", None) != "COIN" or
                getattr(record, "cycle_id", None) != item.cycle_id
                for record in records) or
                (item.v4d_output is not None and
                 (not isinstance(item.v4d_output, V4DCycleOutput) or
                  item.v4d_output.symbol != "COIN" or
                  item.v4d_output.cycle_id != item.cycle_id))):
            raise TerminalDeliveryError("MALFORMED_EVIDENCE_ENVELOPE")
        if self._last_sequence is not None and item.sequence <= self._last_sequence:
            raise TerminalDeliveryError("EVIDENCE_EVENT_ORDER_VIOLATION")
        previous, current = item.previous_observation, item.current_observation
        if self._handoff_fence_anchor is not None:
            # A reconnect can lose the session lock while this process still
            # owns an accepted FIFO head.  If another runtime advances the
            # durable anchor, never append the obsolete bracket afterwards.
            # Only the exact durable predecessor may restore contiguity.
            if (previous != self._handoff_fence_anchor or
                    current.event_epoch <= self._handoff_fence_anchor.event_epoch):
                self.metrics.increment(
                    "evidence_ledger_worker.handoff_superseded")
                raise TerminalDeliveryError("EVIDENCE_HANDOFF_SUPERSEDED")
            self._resolution_contiguous = True
            # This fence guards only the pre-acquisition FIFO prefix.  Normal
            # sequential work after the first exact bracket must not be
            # compared with the original durable handoff anchor.
            self._handoff_fence_anchor = None
        gap = (not self._resolution_contiguous or
               (self._last_sequence is not None and
                item.sequence != self._last_sequence + 1))
        if gap:
            self.metrics.increment("EVIDENCE_SEQUENCE_GAP")
        if previous is not None:
            self._pending = self._merge_pending(
                self._pending, self._load_due(previous, current))
        remaining = []
        state_candidates: dict[
            tuple[tuple[str, str, str], ...], tuple[str, datetime]
        ] = {}
        cycle_cohorts = {}
        if previous is not None:
            if not gap:
                resolution_forecasts = tuple(
                    forecast for forecast in self._pending
                    if (forecast.target_endpoint.timestamp() <= current.event_epoch and
                        forecast.target_endpoint.timestamp() > previous.event_epoch and
                        forecast.cutoff_midpoint is not None)
                )
                cycle_cohorts = self._complete_cycles_cohorts(
                    resolution_forecasts)
            for forecast in self._pending:
                endpoint = forecast.target_endpoint.timestamp()
                if endpoint > current.event_epoch:
                    remaining.append(forecast)
                elif endpoint <= previous.event_epoch or forecast.cutoff_midpoint is None:
                    # A missing exact bracket is intentionally never reconstructed.
                    continue
                elif not gap:
                    cohorts = cycle_cohorts.get(self._cycle_key(forecast))
                    outcome_created_at = self._clock()
                    resolve_outcome(
                        writer=self._writer, forecast=forecast,
                        target_identity=canonical_target_identity(forecast),
                        previous_observation_at=datetime.fromtimestamp(previous.event_epoch, timezone.utc),
                        endpoint_observation_at=datetime.fromtimestamp(current.event_epoch, timezone.utc),
                        target_resolved_at=item.received_at,
                        actual_return_bps=10_000.0 * math.log(
                            current.midpoint / forecast.cutoff_midpoint),
                        created_at=outcome_created_at,
                        metrics=self.metrics,
                    )
                    inserted = self._writer.last_write_status == "INSERT"
                    if inserted and cohorts is not None:
                        cohort_key = tuple(
                            (horizon, *cohorts[horizon]) for horizon in HORIZONS)
                        existing = state_candidates.get(cohort_key)
                        if existing is None or outcome_created_at > existing[1]:
                            state_candidates[cohort_key] = (
                                forecast.symbol, outcome_created_at)
                    if self._writer.last_write_status == "OUTCOME_CONFLICT":
                        raise TerminalDeliveryError("OUTCOME_CONFLICT")
        else:
            remaining.extend(self._pending)
        # The legacy raw ledger operation is wholly worker-owned.  Its capture
        # timestamp remains capture time; no availability timestamp is invented.
        self._store.record_cycle_and_resolve(
            item.directional, observation_epoch=current.event_epoch,
            observation_midpoint=current.midpoint, resolution_symbol="COIN",
            volatility_forecasts=item.q3,
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
        self._handoff_anchor = current
        self._resolution_contiguous = True
        refresh_cutoff = max(
            item.received_at,
            datetime.fromtimestamp(current.event_epoch, timezone.utc),
        )
        if self._state_build_submit is not None:
            for cohort_key, (symbol, outcome_created_at) in state_candidates.items():
                try:
                    self._state_build_submit(
                        symbol=symbol,
                        state_as_of=max(refresh_cutoff, outcome_created_at),
                        cohorts={horizon: (cohort_id, cohort_hash)
                                 for horizon, cohort_id, cohort_hash in cohort_key},
                        new_outcome=True,
                    )
                except Exception:
                    self.metrics.increment("v4_state_build_submit.failure")
            if not state_candidates and len(item.v4) == len(HORIZONS):
                try:
                    # Preserve the existing post-SIM handoff ordering.  The
                    # background owner rejects this inert candidate because it
                    # carries no newly inserted outcome.
                    self._state_build_submit(
                        symbol=item.v4[0].symbol, state_as_of=refresh_cutoff,
                        cohorts={forecast.horizon:
                                 (forecast.cohort_id, forecast.cohort_hash)
                                 for forecast in item.v4},
                        new_outcome=False,
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
            if not self._owns_runtime:
                if self._needs_reconnect:
                    try:
                        self._reconnect()
                    except Exception:
                        self.metrics.increment(
                            "evidence_ledger_worker.reconnect_failure")
                        time.sleep(.1)
                        continue
                    self._needs_reconnect = False
                if not self._owns_runtime:
                    try:
                        if not self._acquire_runtime_ownership():
                            time.sleep(.1)
                            continue
                    except Exception as error:
                        self.metrics.increment("evidence_runtime_owner.failure")
                        if _transient_database_error(error):
                            self._needs_reconnect = True
                        time.sleep(.1)
                        continue
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
                if not self._owns_runtime:
                    try:
                        if not self._acquire_runtime_ownership():
                            time.sleep(.1)
                            continue
                    except Exception as error:
                        self.metrics.increment("evidence_runtime_owner.failure")
                        if _transient_database_error(error):
                            self._needs_reconnect = True
                        time.sleep(.1)
                        continue
                try:
                    self.process(item)
                    self.outbox.task_done()
                    break
                except TerminalDeliveryError as error:
                    self._record_terminal_failure(error)
                    sequence = getattr(item, "sequence", None)
                    if isinstance(sequence, int):
                        self._last_sequence = sequence
                    self._resolution_contiguous = False
                    self.outbox.task_done()
                    break
                except Exception as error:
                    self.metrics.increment("evidence_ledger_worker.failure")
                    if not _transient_database_error(error):
                        self._record_terminal_failure(error)
                        sequence = getattr(item, "sequence", None)
                        if isinstance(sequence, int):
                            self._last_sequence = sequence
                        self._resolution_contiguous = False
                        self.outbox.task_done()
                        break
                    self._needs_reconnect = True
                    self._owns_runtime = False
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
