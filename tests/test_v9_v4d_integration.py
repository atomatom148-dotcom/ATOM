from dataclasses import asdict, replace
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace
import json
import threading
import time

import pytest

from quant.v9_v1_contract import HORIZONS, HORIZON_SECONDS
from quant.v9_v2d_evidence_state import DirectionalCalibrationState
from quant.v9_v3_synthesis import CANONICAL_FAMILIES
from quant.v9_v4a_evidence import (
    _canonical, build_forecast, build_outcome, canonical_sha256,
    canonical_target_identity, select_non_overlapping,
)
from quant.v9_v4c_predictive import (
    PROBABILITY_STATE_VERSION, CompactHorizonState, build_v4c_state,
)
from quant.v9_v4d_integration import (
    ImmutableStateCache, OfflineStateBuildScheduler, OperationalMetrics, V4DCoordinator,
    resolve_outcome,
)
from quant.evidence_outbox import (
    EVIDENCE_RECOVERY_CYCLE_QUERY_CHUNK, EVIDENCE_RECOVERY_OUTCOME_LIMIT,
    V4_STATE_BUILD_QUERY_CHUNK,
    EvidenceLedgerWorker, EvidenceOutbox, QuoteEvidenceWork, TerminalDeliveryError,
    PostgresV4BStateBuilder, PostgresV4CStateBuilder, PostgresV4StateBuilder,
    V4StateBuildWorker, V4StateCacheRefresher, _decode_v4_state_row,
    _iter_v4_state_pages,
    _prepare_v4_state_evidence, _prepare_v4_state_evidence_sets,
)
from quant.history import MidpointObservation
from quant.live_market import LiveMarketState

NOW = datetime(2026, 1, 1, tzinfo=timezone.utc)


def _inputs(family_count=1, unavailable_horizon=None):
    ids = CANONICAL_FAMILIES[:family_count]
    slots = []
    for horizon in HORIZONS:
        for quant_id in (*CANONICAL_FAMILIES, "q3_volatility"):
            fresh = quant_id in ids and horizon != unavailable_horizon
            slots.append(SimpleNamespace(
                quant_id=quant_id, horizon=horizon,
                horizon_seconds=HORIZON_SECONDS[horizon],
                numerical_type="MAGNITUDE_BPS" if quant_id == "q3_volatility" else "DIRECTIONAL_BPS",
                availability_state="FRESH" if fresh else "MISSING",
                value_bps=float(ids.index(quant_id) + 1) if fresh else None,
                formula_version="f1", data_schema_version="schema",
                source_spec_version="source", forecast_cutoff_at=NOW,
                source_as_of_at=NOW, available_at=NOW,
            ))
    v1 = SimpleNamespace(
        contract_version="V9-V1", horizons=HORIZONS, cutoff_at=NOW,
        target_spec_id="target", data_schema_version="schema",
        source_spec_version="source", evidence_state_as_of=NOW,
        evidence_state_id="v2", evidence_state_version="V9-V2D-2",
        evidence_state_hash="hash", cycle_id="cycle-1", symbol="COIN",
        slots=tuple(slots),
    )
    states = []
    for horizon in HORIZONS:
        active = horizon != unavailable_horizon
        calibrations = tuple(DirectionalCalibrationState(
            quant_id, "f1", "schema", "source", "dataset",
            0.0, 1.0, ((0.0, 0.0), (0.0, 0.0)),
            100.0, 1.0, 1.0, "PROVISIONAL", ()) for quant_id in ids) if active else ()
        n = len(calibrations)
        states.append(SimpleNamespace(
            horizon=horizon, status="PROVISIONAL" if active else "UNAVAILABLE",
            reason_codes=(), directional_calibrations=calibrations,
            ordered_quant_ids=ids if active else (),
            pair_support_boolean_matrix=tuple(tuple(True for _ in range(n)) for _ in range(n)),
            stabilized_covariance_matrix=tuple(tuple(float(i == j) for j in range(n)) for i in range(n)) if n > 1 else None,
            covariance_status="MATURE" if active else "UNAVAILABLE",
            dependence_modeled=True,
        ))
    v2 = SimpleNamespace(
        state_id="v2", state_version="V9-V2D-2", state_hash="hash",
        symbol="COIN", state_as_of=NOW.timestamp(), target_spec_id="target",
        target_data_schema_version="schema", target_source_spec_version="source",
        horizon_state_tuple=tuple(states), v2a_method_version="a",
        v2b_method_version="b", v2c_method_version="c",
        effective_n_method_version="n", calibration_method_version="cal",
        covariance_method_version="cov", numerical_canonicalization_version="num",
    )
    return v1, v2


class Writer:
    def __init__(self, fail_horizon=None):
        self.fail_horizon = fail_horizon
        self.forecasts = []
        self.outcomes = []
        self.last_write_status = None

    def persist_forecast(self, record, persisted_at):
        if record.horizon == self.fail_horizon:
            raise OSError("isolated")
        stored = replace(record, persisted_at=persisted_at,
                         persistence_proof_eligible=True)
        self.forecasts.append(stored)
        self.last_write_status = "INSERT"
        return stored

    def persist_outcome(self, record, created_at):
        stored = replace(record, created_at=created_at)
        self.outcomes.append(stored)
        self.last_write_status = "INSERT"
        return stored


def _empty_state():
    horizons = tuple(CompactHorizonState(
        horizon, "UNAVAILABLE", None, None, "UNAVAILABLE", None, None,
        "UNAVAILABLE", None, (), ("UNAVAILABLE",) * 6,
    ) for horizon in HORIZONS)
    return build_v4c_state(symbol="COIN", cohort_id="cohort", state_as_of=NOW,
        evidence_first_cutoff=None, evidence_last_cutoff=None, horizons=horizons)


def test_unattempted_persistence_and_failed_delivery_are_reported_truthfully():
    v1, v2 = _inputs()
    output = V4DCoordinator(
        capture_v1=lambda: v1, capture_v2=lambda _captured: v2,
        forecast_writer=None, compact_state_lookup=lambda **_kwargs: (None, "UNAVAILABLE"),
        state_cohort_id=lambda _one, _two: "cohort",
    ).run_cycle()
    assert {item.status for item in output.persistence} == {"PERSISTENCE_NOT_ATTEMPTED"}

    outbox = EvidenceOutbox()
    outbox.unavailable()
    state = LiveMarketState(clock=lambda: NOW.timestamp(), evidence_outbox=outbox,
                            v9_cycle_handler=lambda *_args: output)
    assert state.accept_quote(bid=99.0, ask=101.0, event_epoch=NOW.timestamp())
    published = state.v9_output()
    assert published.evidence_delivery_status == "DROPPED"
    assert "QUEUED" not in {item.status for item in published.persistence}
    assert any(item.final_bps is not None for item in published.final_numbers)


def test_background_cache_refresh_publishes_exact_compatible_state():
    compact = SimpleNamespace(symbol="COIN", cohort_id="cohort", state_as_of=NOW)
    accuracy = SimpleNamespace(symbol="COIN", cohort_id="cohort", state_as_of=NOW)

    class Cache:
        def __init__(self): self.values = []
        def publish(self, value): self.values.append(value)

    compact_cache, accuracy_cache = Cache(), Cache()

    class Store:
        def __init__(self, value): self.value = value; self.calls = 0
        def latest_json(self, **_kwargs):
            self.calls += 1
            return (self.value, "AVAILABLE") if self.value is not None else (None, "UNAVAILABLE")

    compact_store, accuracy_store = Store(compact), Store(accuracy)
    V4StateCacheRefresher(
        compact_store=compact_store, accuracy_store=accuracy_store,
        compact_cache=compact_cache, accuracy_cache=accuracy_cache,
    ).refresh(symbol="COIN", cohort_id="cohort", cutoff=NOW)
    assert compact_store.calls == accuracy_store.calls == 1
    assert compact_cache.values == [compact]
    assert accuracy_cache.values == [accuracy]


def test_background_cache_refresh_rejects_unpaired_generation():
    compact = SimpleNamespace(symbol="COIN", cohort_id="cohort", state_as_of=NOW)
    accuracy = SimpleNamespace(
        symbol="COIN", cohort_id="cohort", state_as_of=NOW - timedelta(seconds=1))

    class Store:
        def __init__(self, value): self.value = value
        def latest_json(self, **_kwargs): return self.value, "AVAILABLE"
    class Cache:
        def __init__(self): self.values = []
        def publish(self, value): self.values.append(value)

    metrics = OperationalMetrics()
    compact_cache, accuracy_cache = Cache(), Cache()
    V4StateCacheRefresher(
        compact_store=Store(compact), accuracy_store=Store(accuracy),
        compact_cache=compact_cache, accuracy_cache=accuracy_cache,
        metrics=metrics,
    ).refresh(symbol="COIN", cohort_id="cohort", cutoff=NOW)

    assert compact_cache.values == accuracy_cache.values == []
    assert dict(metrics.snapshot().statuses)["v4_state_pair_status"] == \
        "GENERATION_MISMATCH"


class _WorkerConnection:
    def cursor(self):
        return SimpleNamespace(execute=lambda *_args: None, fetchall=lambda: (),
                               fetchone=lambda: (True,),
                               close=lambda: None)
    def commit(self): pass
    def rollback(self): pass


def test_worker_recovers_only_persisted_proof_eligible_unresolved_forecasts():
    v1, v2 = _inputs()
    calculated = V4DCoordinator(
        capture_v1=lambda: v1, capture_v2=lambda _captured: v2,
        forecast_writer=None, compact_state_lookup=lambda **_kwargs: (None, "UNAVAILABLE"),
        state_cohort_id=lambda *_args: "cohort", cutoff_midpoint=lambda _value: 100.0,
    ).run_cycle()
    forecast = replace(calculated.persistence[0].forecast, persisted_at=NOW,
                       persistence_proof_eligible=True)
    payload = json.dumps(_canonical(asdict(forecast)), sort_keys=True)

    class Cursor:
        def execute(self, sql, _params):
            assert ("NOT EXISTS" in sql and "interval '1 hour'" in sql and
                    "f.symbol='COIN'" in sql)
        def fetchall(self): return ((forecast.forecast_record_hash, payload),)
        def close(self): pass
    class Connection(_WorkerConnection):
        def cursor(self): return Cursor()

    worker = EvidenceLedgerWorker(EvidenceOutbox(), evidence_store=_RawStore(),
                                  connection=Connection())
    assert worker._pending == [forecast]


def test_worker_recovers_pending_and_due_proofs_without_n_plus_one_reads():
    v1, v2 = _inputs()
    calculated = V4DCoordinator(
        capture_v1=lambda: v1, capture_v2=lambda _captured: v2,
        forecast_writer=None,
        compact_state_lookup=lambda **_kwargs: (None, "UNAVAILABLE"),
        state_cohort_id=lambda *_args: "cohort",
        cutoff_midpoint=lambda _value: 100.0,
    ).run_cycle()
    forecast = calculated.persistence[0].forecast
    payload = json.dumps(_canonical(asdict(forecast)), sort_keys=True)
    proof = (
        forecast.forecast_record_id,
        forecast.forecast_record_hash,
        NOW,
        forecast.target_endpoint,
        True,
        "POST_COMMIT_DB_OBSERVATION_V1",
    )

    class Cursor:
        def execute(self, sql, _params):
            connection.queries.append(sql)
            assert "JOIN LATERAL" in sql
            assert "read_forecast_commit_proof" in sql
        def fetchall(self):
            return ((forecast.forecast_record_hash, payload, *proof),)
        def fetchone(self):
            raise AssertionError("authoritative proofs must not use N+1 reads")
        def close(self): pass
    class Connection(_WorkerConnection):
        def __init__(self): self.queries = []
        def cursor(self): return Cursor()

    connection = Connection()
    worker = EvidenceLedgerWorker(
        EvidenceOutbox(), evidence_store=_RawStore(), connection=connection)

    assert len(connection.queries) == 1
    assert len(worker._pending) == 1
    assert worker._pending[0].persistence_proof_eligible is True
    due = worker._load_due(
        MidpointObservation(forecast.target_endpoint.timestamp() - 1, 100.0),
        MidpointObservation(forecast.target_endpoint.timestamp(), 101.0),
    )
    assert len(connection.queries) == 2
    assert "f.target_endpoint > %s" in connection.queries[1]
    assert due[0].persistence_proof_eligible is True


def test_worker_missing_proof_reader_starts_bounded_and_fail_closed():
    class MissingProofReader(Exception):
        sqlstate = "42883"

    class Cursor:
        def execute(self, sql, _params):
            connection.queries.append(sql)
            raise MissingProofReader("undefined proof function")
        def fetchall(self): raise AssertionError("query must fail closed")
        def close(self): pass
    class Connection(_WorkerConnection):
        def __init__(self):
            self.queries = []
            self.commits = 0
            self.rollbacks = 0
        def cursor(self): return Cursor()
        def commit(self): self.commits += 1
        def rollback(self): self.rollbacks += 1

    connection = Connection()
    worker = EvidenceLedgerWorker(
        EvidenceOutbox(), evidence_store=_RawStore(), connection=connection)

    assert worker._pending == []
    assert len(connection.queries) == 1
    assert "JOIN LATERAL" in connection.queries[0]
    assert connection.commits == 0
    assert connection.rollbacks == 1
    counters = dict(worker.metrics.snapshot().counters)
    assert counters["evidence_recovery.proof_reader_unavailable"] == 1
    assert "evidence_recovery.invalid_record" not in counters


def test_worker_recovery_does_not_hide_non_schema_query_failures():
    class Cursor:
        def execute(self, _sql, _params):
            raise RuntimeError("database unavailable")
        def close(self): pass
    class Connection(_WorkerConnection):
        def cursor(self): return Cursor()

    with pytest.raises(RuntimeError, match="database unavailable"):
        EvidenceLedgerWorker(
            EvidenceOutbox(), evidence_store=_RawStore(),
            connection=Connection(),
        )


def test_worker_recovers_cross_deploy_forecast_in_exact_provider_bracket():
    v1, v2 = _inputs()
    calculated = V4DCoordinator(
        capture_v1=lambda: v1, capture_v2=lambda _captured: v2,
        forecast_writer=None, compact_state_lookup=lambda **_kwargs: (None, "UNAVAILABLE"),
        state_cohort_id=lambda *_args: "cohort", cutoff_midpoint=lambda _value: 100.0,
    ).run_cycle()
    forecasts = tuple(replace(
        item.forecast, persisted_at=NOW, persistence_proof_eligible=True)
        for item in calculated.persistence)
    due = forecasts[0]
    rows = tuple((forecast.forecast_record_hash,
                  json.dumps(_canonical(asdict(forecast)), sort_keys=True))
                 for forecast in forecasts)

    class Cursor:
        def execute(self, sql, params):
            self.sql, self.params = sql, params
            connection.queries.append((sql, params))
        def fetchall(self):
            if "f.target_endpoint > %s" in self.sql:
                return (rows[0],)
            if "f.horizon IN" in self.sql:
                return rows
            return ()
        def fetchone(self):
            if "read_forecast_commit_proof" in self.sql:
                forecast = next(
                    item for item in forecasts
                    if item.forecast_record_id == self.params[0]
                )
                return (
                    forecast.forecast_record_id,
                    forecast.forecast_record_hash,
                    forecast.persisted_at,
                    forecast.target_endpoint,
                    True,
                    "POST_COMMIT_DB_OBSERVATION_V1",
                )
            return (True,)
        def close(self): pass
    class Connection(_WorkerConnection):
        def __init__(self): self.queries = []
        def cursor(self): return Cursor()

    connection = Connection()
    submitted = []
    worker = EvidenceLedgerWorker(
        EvidenceOutbox(), evidence_store=_RawStore(), connection=connection,
        state_build_submit=lambda **candidate: submitted.append(candidate),
        wall_clock=lambda: NOW + timedelta(seconds=31),
    )
    assert worker._pending == []
    worker._writer = Writer()
    previous = MidpointObservation(due.target_endpoint.timestamp() - 1, 100.0)
    current = MidpointObservation(due.target_endpoint.timestamp(), 101.0)
    worker.process(QuoteEvidenceWork(
        1, "replacement-cycle", previous, current,
        NOW + timedelta(seconds=31), (), (), (),
    ))

    assert len(worker._writer.outcomes) == 1
    assert worker._writer.outcomes[0].forecast_record_id == due.forecast_record_id
    due_sql, due_params = next(
        (sql, params) for sql, params in connection.queries
        if "f.target_endpoint > %s" in sql)
    assert ("f.target_endpoint <= %s" in due_sql and "NOT EXISTS" in due_sql and
            "f.symbol='COIN'" in due_sql and
            "now()" not in due_sql and "interval" not in due_sql)
    assert due_params == (
        datetime.fromtimestamp(previous.event_epoch, timezone.utc),
        datetime.fromtimestamp(current.event_epoch, timezone.utc),
    )
    assert submitted == [{
        "symbol": "COIN", "state_as_of": NOW + timedelta(seconds=31),
        "cohorts": {forecast.horizon: (forecast.cohort_id, forecast.cohort_hash)
                    for forecast in forecasts},
        "new_outcome": True,
    }]


def test_coin_ledger_never_loads_foreign_symbol_pending_or_due_forecasts():
    class Cursor:
        def execute(self, sql, _params): self.sql = sql
        def fetchall(self):
            # A shared-table foreign row would be visible to a query that forgot
            # the official COIN-writer predicate.
            return () if "f.symbol='COIN'" in self.sql else (("hash", "{}"),)
        def close(self): pass
    class Connection(_WorkerConnection):
        def cursor(self): return Cursor()

    worker = EvidenceLedgerWorker(
        EvidenceOutbox(), evidence_store=_RawStore(), connection=Connection())
    assert worker._pending == []
    assert worker._load_due(
        MidpointObservation(1.0, 100.0),
        MidpointObservation(2.0, 101.0),
    ) == []


def test_due_reconciliation_deduplicates_local_pending_and_rejects_ineligible():
    v1, v2 = _inputs()
    calculated = V4DCoordinator(
        capture_v1=lambda: v1, capture_v2=lambda _captured: v2,
        forecast_writer=None, compact_state_lookup=lambda **_kwargs: (None, "UNAVAILABLE"),
        state_cohort_id=lambda *_args: "cohort", cutoff_midpoint=lambda _value: 100.0,
    ).run_cycle()
    forecasts = tuple(replace(
        item.forecast, persisted_at=NOW, persistence_proof_eligible=True)
        for item in calculated.persistence)
    due = forecasts[0]
    ineligible = replace(
        due, persisted_at=due.target_endpoint + timedelta(microseconds=1),
        persistence_proof_eligible=False)
    eligible_payload = json.dumps(_canonical(asdict(due)), sort_keys=True)
    ineligible_payload = json.dumps(_canonical(asdict(ineligible)), sort_keys=True)

    class Cursor:
        def execute(self, sql, _params): self.sql = sql
        def fetchall(self):
            if "f.target_endpoint > %s" in self.sql:
                return ((due.forecast_record_hash, eligible_payload),
                        (ineligible.forecast_record_hash, ineligible_payload))
            if "f.horizon IN" in self.sql:
                return tuple((forecast.forecast_record_hash,
                              json.dumps(_canonical(asdict(forecast)), sort_keys=True))
                             for forecast in forecasts)
            return ()
        def fetchone(self): return (True,)
        def close(self): pass
    class Connection(_WorkerConnection):
        def cursor(self): return Cursor()

    worker = EvidenceLedgerWorker(
        EvidenceOutbox(), evidence_store=_RawStore(), connection=Connection(),
        wall_clock=lambda: NOW + timedelta(seconds=31),
    )
    worker._pending = [due]
    worker._writer = Writer()
    previous = MidpointObservation(due.target_endpoint.timestamp() - 1, 100.0)
    current = MidpointObservation(due.target_endpoint.timestamp(), 101.0)
    worker.process(QuoteEvidenceWork(
        1, due.cycle_id, previous, current, NOW + timedelta(seconds=31),
        (), (), forecasts,
    ))

    assert len(worker._writer.outcomes) == 1
    assert worker._writer.outcomes[0].forecast_record_id == due.forecast_record_id


def test_outcome_state_attachment_ignores_unpersisted_same_cycle_lineage():
    v1, v2 = _inputs()
    calculated = V4DCoordinator(
        capture_v1=lambda: v1, capture_v2=lambda _captured: v2,
        forecast_writer=None,
        compact_state_lookup=lambda **_kwargs: (None, "UNAVAILABLE"),
        state_cohort_id=lambda *_args: "cohort",
        cutoff_midpoint=lambda _value: 100.0,
    ).run_cycle()
    durable = tuple(replace(
        item.forecast, persisted_at=NOW, persistence_proof_eligible=True)
        for item in calculated.persistence)
    due = durable[0]
    unpersisted = tuple(replace(
        forecast, cohort_id="unpersisted-cohort", cohort_hash="f" * 64)
        for forecast in durable)
    rows = tuple((forecast.forecast_record_hash,
                  json.dumps(_canonical(asdict(forecast)), sort_keys=True))
                 for forecast in durable)

    class Cursor:
        def execute(self, sql, _params): self.sql = sql
        def fetchall(self):
            if "f.horizon IN" in self.sql:
                return rows
            return ()
        def close(self): pass
    class Connection(_WorkerConnection):
        def cursor(self): return Cursor()

    submitted = []
    worker = EvidenceLedgerWorker(
        EvidenceOutbox(), evidence_store=_RawStore(), connection=Connection(),
        state_build_submit=lambda **candidate: submitted.append(candidate),
        wall_clock=lambda: NOW + timedelta(seconds=31),
    )
    worker._pending = [due]
    worker._writer = Writer()
    previous = MidpointObservation(
        due.target_endpoint.timestamp() - 1, 100.0)
    current = MidpointObservation(due.target_endpoint.timestamp(), 101.0)
    worker.process(QuoteEvidenceWork(
        1, due.cycle_id, previous, current, NOW + timedelta(seconds=31),
        (), (), unpersisted,
    ))

    assert submitted[0]["new_outcome"] is True
    assert submitted[0]["cohorts"] == {
        forecast.horizon: (forecast.cohort_id, forecast.cohort_hash)
        for forecast in durable
    }
    assert "unpersisted-cohort" not in {
        cohort_id for cohort_id, _hash in submitted[0]["cohorts"].values()}


class _RawStore:
    def __init__(self): self.calls = []
    def record_cycle_and_resolve(self, *_args, **kwargs): self.calls.append(kwargs)


def _work(sequence, previous, current, received_at):
    return QuoteEvidenceWork(sequence, f"COIN:{current.event_epoch:.9f}",
        previous, current, received_at, (), (), ())


def test_reacquired_worker_discards_stale_fifo_prefix_then_accepts_exact_bridge(
        monkeypatch):
    monkeypatch.setattr(EvidenceLedgerWorker, "_load_pending", lambda _self: [])
    raw = _RawStore()
    worker = EvidenceLedgerWorker(
        EvidenceOutbox(), evidence_store=raw, connection=_WorkerConnection())
    anchor = MidpointObservation(12.0, 103.0)
    worker._handoff_anchor = anchor
    worker._handoff_fence_anchor = anchor

    stale = _work(
        1, MidpointObservation(9.0, 100.0),
        MidpointObservation(10.0, 101.0), NOW)
    with pytest.raises(TerminalDeliveryError, match="HANDOFF_SUPERSEDED"):
        worker.process(stale)
    worker._last_sequence = 1
    worker._resolution_contiguous = False

    bridge = _work(2, anchor, MidpointObservation(13.0, 105.0), NOW)
    worker.process(bridge)
    following = _work(
        3, bridge.current_observation,
        MidpointObservation(14.0, 106.0), NOW)
    worker.process(following)

    assert worker._handoff_fence_anchor is None
    assert worker._handoff_anchor == following.current_observation
    assert [call["resolution_enabled"] for call in raw.calls] == [True, True]
    assert dict(worker.metrics.snapshot().counters)[
        "evidence_ledger_worker.handoff_superseded"] == 1


def test_worker_rejects_non_coin_v4_before_any_evidence_write(monkeypatch):
    monkeypatch.setattr(EvidenceLedgerWorker, "_load_pending", lambda _self: [])
    v1, v2 = _inputs()
    calculated = V4DCoordinator(
        capture_v1=lambda: v1, capture_v2=lambda _captured: v2,
        forecast_writer=None,
        compact_state_lookup=lambda **_kwargs: (None, "UNAVAILABLE"),
        state_cohort_id=lambda *_args: "cohort",
        cutoff_midpoint=lambda _value: 100.0,
    ).run_cycle()
    malformed = tuple(
        replace(item.forecast, symbol="QQQ") for item in calculated.persistence)
    raw = _RawStore()
    writer = Writer()
    worker = EvidenceLedgerWorker(
        EvidenceOutbox(), evidence_store=raw, connection=_WorkerConnection())
    worker._writer = writer

    with pytest.raises(TerminalDeliveryError, match="MALFORMED_EVIDENCE_ENVELOPE"):
        worker.process(QuoteEvidenceWork(
            1, calculated.cycle_id, None,
            MidpointObservation(NOW.timestamp(), 100.0), NOW,
            (), (), malformed,
        ))

    assert raw.calls == []
    assert writer.forecasts == [] and writer.outcomes == []


def test_worker_uses_captured_resolution_time_and_gap_disables_resolution(monkeypatch):
    monkeypatch.setattr(EvidenceLedgerWorker, "_load_pending", lambda _self: [])
    raw = _RawStore()
    worker = EvidenceLedgerWorker(EvidenceOutbox(), evidence_store=raw,
                                  connection=_WorkerConnection())
    v1, v2 = _inputs()
    calculated = V4DCoordinator(
        capture_v1=lambda: v1, capture_v2=lambda _captured: v2,
        forecast_writer=None, compact_state_lookup=lambda **_kwargs: (None, "UNAVAILABLE"),
        state_cohort_id=lambda *_args: "cohort", cutoff_midpoint=lambda _value: 100.0,
    ).run_cycle()
    forecast = replace(calculated.persistence[1].forecast, persisted_at=NOW,
                       persistence_proof_eligible=True)
    worker._pending = [forecast]

    class OutcomeWriter:
        last_write_status = "INSERT"
        outcomes = []
        def persist_outcome(self, record, created_at):
            self.outcomes.append(record)
            return record
        def persist_forecast(self, record, persisted_at): return record

    writer = OutcomeWriter()
    worker._writer = writer
    previous = MidpointObservation(forecast.target_endpoint.timestamp() - 1, 100.0)
    current = MidpointObservation(forecast.target_endpoint.timestamp() + 1, 101.0)
    received = datetime.fromtimestamp(current.event_epoch + 7, timezone.utc)
    worker.process(_work(1, previous, current, received))
    assert writer.outcomes[0].target_resolved_at == received

    # Losing sequence 2 makes the sequence-3 bracket resolution-disabled.
    worker._pending = [forecast]
    later = MidpointObservation(current.event_epoch + 10, 102.0)
    worker.process(_work(3, current, later, received + timedelta(seconds=10)))
    assert len(writer.outcomes) == 1
    assert raw.calls[-1]["resolution_enabled"] is False
    counters = dict(worker.metrics.snapshot().counters)
    assert counters["EVIDENCE_SEQUENCE_GAP"] == 1


def test_terminal_failure_advances_fifo_while_transient_retries_same_head(monkeypatch):
    monkeypatch.setattr(EvidenceLedgerWorker, "_load_pending", lambda _self: [])
    previous = MidpointObservation(NOW.timestamp(), 100.0)
    current = MidpointObservation(NOW.timestamp() + 1, 101.0)

    terminal_outbox = EvidenceOutbox()
    terminal = EvidenceLedgerWorker(terminal_outbox, evidence_store=_RawStore(),
                                    connection=_WorkerConnection())
    first, second = (_work(n, previous, current, NOW + timedelta(seconds=n))
                     for n in (1, 2))
    terminal_outbox.put_nowait(first); terminal_outbox.put_nowait(second)
    terminal_calls = []
    def terminal_process(item):
        terminal_calls.append(item.sequence)
        if item.sequence == 1:
            raise TerminalDeliveryError("FORECAST_DUPLICATE_CONFLICT")
        terminal._stop.set()
    terminal.process = terminal_process
    thread = terminal.start(); thread.join(timeout=1)
    assert terminal_calls == [1, 2]
    terminal_telemetry = terminal.metrics.snapshot()
    assert dict(terminal_telemetry.statuses)[
        "evidence_ledger_worker.last_terminal_failure"] == \
        "FORECAST_DUPLICATE_CONFLICT"

    class OperationalError(Exception): pass
    class AdminShutdown(OperationalError): pass
    class RecoverableConnection(_WorkerConnection):
        def __init__(self, name):
            self.name = name
            self.close_calls = 0
            self.rollback_calls = 0
        def close(self): self.close_calls += 1
        def rollback(self): self.rollback_calls += 1
    class RebindStore(_RawStore):
        def __init__(self): super().__init__(); self.connections = []
        def rebind_connection(self, connection): self.connections.append(connection)
    class RebindRefresher:
        def __init__(self): self.connections = []
        def rebind_connection(self, connection): self.connections.append(connection)

    dead, recovered = RecoverableConnection("dead"), RecoverableConnection("recovered")
    attempts = []
    def connect(_database_url):
        attempts.append(1)
        if len(attempts) == 1:
            raise AdminShutdown("database still unavailable")
        return recovered
    store, refresher = RebindStore(), RebindRefresher()
    transient_outbox = EvidenceOutbox()
    transient = EvidenceLedgerWorker(
        transient_outbox, evidence_store=store, connection=dead,
        connect=connect, database_url="postgresql://runtime",
        cache_refresher=refresher,
    )
    pending = [object()]
    transient._pending = pending
    def acquire_for_test():
        transient._owns_runtime = True
        return True
    transient._acquire_runtime_ownership = acquire_for_test
    transient_outbox.put_nowait(first)
    transient_calls = []
    def transient_process(item):
        transient_calls.append(item.sequence)
        if len(transient_calls) == 1:
            raise AdminShutdown("database unavailable")
        assert transient._connection is recovered
        assert transient._writer.connection is recovered
        transient._stop.set()
    transient.process = transient_process
    thread = transient.start(); thread.join(timeout=1)
    assert transient_calls == [1, 1]
    assert attempts == [1, 1]
    assert store.connections == refresher.connections == [recovered]
    assert transient._pending is pending
    assert (dead.rollback_calls, dead.close_calls) == (1, 1)
    counters = dict(transient.metrics.snapshot().counters)
    assert counters["evidence_ledger_worker.reconnect_failure"] == 1
    assert counters["evidence_ledger_worker.reconnect_success"] == 1
    transient.close()
    assert recovered.close_calls == 1


def test_runtime_ownership_uses_one_session_advisory_lock(monkeypatch):
    monkeypatch.setattr(EvidenceLedgerWorker, "_load_pending", lambda _self: [])

    class Cursor:
        def execute(self, sql, params):
            connection.calls.append((sql, params))
        def fetchone(self): return (True,)
        def fetchall(self): return ()
        def close(self): pass
    class Connection(_WorkerConnection):
        def __init__(self): self.calls = []
        def cursor(self): return Cursor()

    connection = Connection()
    worker = EvidenceLedgerWorker(
        EvidenceOutbox(), evidence_store=_RawStore(), connection=connection)

    assert worker._try_acquire_runtime_ownership() is True
    assert connection.calls == [(
        "SELECT pg_try_advisory_lock(%s)",
        (int.from_bytes(b"ATOMV9EL", "big"),),
    )]


def test_runtime_ownership_lock_query_failure_sets_error_without_unlock(
        monkeypatch):
    monkeypatch.setattr(EvidenceLedgerWorker, "_load_pending", lambda _self: [])

    class Cursor:
        def __init__(self): self.calls = []
        def execute(self, sql, params):
            self.calls.append((sql, params))
            raise RuntimeError("lock query unavailable")
        def close(self): pass
    cursor = Cursor()
    class Connection(_WorkerConnection):
        def cursor(self): return cursor

    worker = EvidenceLedgerWorker(
        EvidenceOutbox(), evidence_store=_RawStore(), connection=Connection())
    released = []
    worker._release_runtime_ownership = lambda: released.append(True)

    with pytest.raises(RuntimeError, match="lock query unavailable"):
        worker._acquire_runtime_ownership()
    assert released == []
    assert all("pg_advisory_unlock" not in sql for sql, _params in cursor.calls)
    assert dict(worker.metrics.snapshot().statuses)[
        "evidence_runtime_owner_status"] == "ERROR"


def test_runtime_ownership_reconnect_failure_sets_error(monkeypatch):
    monkeypatch.setattr(EvidenceLedgerWorker, "_load_pending", lambda _self: [])
    worker = EvidenceLedgerWorker(
        EvidenceOutbox(), evidence_store=_RawStore(),
        connection=_WorkerConnection(),
        connect=lambda _url: (_ for _ in ()).throw(
            RuntimeError("database unavailable")),
        database_url="postgresql://runtime",
    )

    with pytest.raises(RuntimeError, match="database unavailable"):
        worker._reconnect()
    assert dict(worker.metrics.snapshot().statuses)[
        "evidence_runtime_owner_status"] == "ERROR"


def test_cycle_lineage_lookup_chunks_below_postgres_bind_limit(monkeypatch):
    monkeypatch.setattr(EvidenceLedgerWorker, "_load_pending", lambda _self: [])

    class Cursor:
        def execute(self, sql, params):
            connection.calls.append((sql, params))
        def fetchall(self): return ()
        def close(self): pass
    class Connection(_WorkerConnection):
        def __init__(self): self.calls = []
        def cursor(self): return Cursor()

    connection = Connection()
    worker = EvidenceLedgerWorker(
        EvidenceOutbox(), evidence_store=_RawStore(), connection=connection)
    keys = tuple(
        ("COIN", NOW + timedelta(microseconds=index), f"cycle-{index}", "v3")
        for index in range(16_383)
    )

    assert worker._load_cycle_forecasts(keys) == {}
    assert len(connection.calls) == 4
    assert all(len(params) <= EVIDENCE_RECOVERY_CYCLE_QUERY_CHUNK * 4 + 6
               for _sql, params in connection.calls)
    assert all(len(params) < 65_535 for _sql, params in connection.calls)


def test_handoff_anchor_uses_authoritative_commit_proofs_not_stored_json(
        monkeypatch):
    monkeypatch.setattr(EvidenceLedgerWorker, "_load_pending", lambda _self: [])

    class Cursor:
        sql = ""
        params = ()
        def execute(self, sql, params): self.sql, self.params = sql, params
        def fetchall(self): return ()
        def close(self): pass
    cursor = Cursor()
    class Connection(_WorkerConnection):
        def cursor(self): return cursor

    worker = EvidenceLedgerWorker(
        EvidenceOutbox(), evidence_store=_RawStore(), connection=Connection())
    assert worker._load_handoff_anchor() is None
    assert "read_forecast_commit_proof" in cursor.sql
    assert "p.proof_eligible" in cursor.sql
    assert "persistence_proof_eligible" not in cursor.sql
    assert "recent_cycles AS MATERIALIZED" in cursor.sql
    assert cursor.params[-2:] == (256, len(HORIZONS))


def test_handoff_anchor_rehydrates_false_stored_json_from_authoritative_proof(
        monkeypatch):
    monkeypatch.setattr(EvidenceLedgerWorker, "_load_pending", lambda _self: [])
    v1, v2 = _inputs()
    calculated = V4DCoordinator(
        capture_v1=lambda: v1,
        capture_v2=lambda _captured: v2,
        forecast_writer=None,
        compact_state_lookup=lambda **_kwargs: (None, "UNAVAILABLE"),
        state_cohort_id=lambda *_args: "cohort",
        cutoff_midpoint=lambda _value: 100.0,
    ).run_cycle()
    forecast = calculated.persistence[0].forecast
    stored = replace(
        forecast, persisted_at=None, persistence_proof_eligible=False,
        persistence_reason="FORECAST_COMMIT_PROOF_MISSING",
    )
    row = (
        stored.forecast_record_hash,
        json.dumps(_canonical(asdict(stored)), sort_keys=True),
    )

    class Cursor:
        def __init__(self, proof):
            self.proof = proof
            self.sql = ""
            self.params = ()

        def execute(self, sql, params):
            self.sql, self.params = sql, params

        def fetchall(self):
            return (row,) if "complete_cycle AS" in self.sql else ()

        def fetchone(self):
            if "read_forecast_commit_proof" not in self.sql or not self.proof:
                return None
            return (
                forecast.forecast_record_id,
                forecast.forecast_record_hash,
                NOW,
                forecast.target_endpoint,
                True,
                "POST_COMMIT_DB_OBSERVATION_V1",
            )

        def close(self):
            pass

    class Connection(_WorkerConnection):
        def __init__(self, proof):
            self.proof = proof

        def cursor(self):
            return Cursor(self.proof)

    proven = EvidenceLedgerWorker(
        EvidenceOutbox(), evidence_store=_RawStore(),
        connection=Connection(True),
    )
    unproven = EvidenceLedgerWorker(
        EvidenceOutbox(), evidence_store=_RawStore(),
        connection=Connection(False),
    )

    assert proven._load_handoff_anchor() == MidpointObservation(
        forecast.cutoff_at.timestamp(), 100.0,
    )
    assert unproven._load_handoff_anchor() is None


@pytest.mark.parametrize("database_url", (
    "postgresql://user:secret@aws-0-us-west-1.pooler.supabase.com:6543/postgres",
    "host=aws-0-us-west-1.pooler.supabase.com port=6543 dbname=postgres user=x",
))
def test_runtime_ownership_rejects_supabase_transaction_pooler(database_url):
    with pytest.raises(ValueError, match="session mode"):
        EvidenceLedgerWorker(
            EvidenceOutbox(), evidence_store=_RawStore(),
            connection=_WorkerConnection(), database_url=database_url)


def test_runtime_ownership_allows_supabase_session_pooler(monkeypatch):
    monkeypatch.setattr(EvidenceLedgerWorker, "_load_pending", lambda _self: [])
    worker = EvidenceLedgerWorker(
        EvidenceOutbox(), evidence_store=_RawStore(),
        connection=_WorkerConnection(),
        database_url=(
            "postgresql://user:secret@aws-0-us-west-1.pooler.supabase.com:5432/postgres"),
    )
    assert worker.is_runtime_owner() is False


def test_legacy_writer_must_be_quiescent_before_runtime_ownership(monkeypatch):
    monkeypatch.setattr(EvidenceLedgerWorker, "_load_pending", lambda _self: [])
    monkeypatch.setattr("quant.evidence_outbox.time.sleep", lambda _seconds: None)
    worker = EvidenceLedgerWorker(
        EvidenceOutbox(), evidence_store=_RawStore(),
        connection=_WorkerConnection(), database_url="postgresql://runtime",
    )
    anchors = iter((MidpointObservation(1.0, 100.0),
                    MidpointObservation(2.0, 101.0)))
    released = []
    worker._try_acquire_runtime_ownership = lambda: True
    worker._load_handoff_anchor = lambda: next(anchors)
    worker._release_runtime_ownership = lambda: released.append(True)

    assert worker._acquire_runtime_ownership() is False
    assert released == [True]
    assert worker.is_runtime_owner() is False
    assert dict(worker.metrics.snapshot().statuses)[
        "evidence_runtime_owner_status"] == "WAITING_FOR_LEGACY_WRITER"


def test_runtime_ingress_stays_closed_when_recovery_submission_fails(monkeypatch):
    monkeypatch.setattr(EvidenceLedgerWorker, "_load_pending", lambda _self: [])
    worker = EvidenceLedgerWorker(
        EvidenceOutbox(), evidence_store=_RawStore(),
        connection=_WorkerConnection(),
        state_build_submit=lambda **_candidate: (_ for _ in ()).throw(
            RuntimeError("submit failed")),
    )
    worker._try_acquire_runtime_ownership = lambda: True
    worker._load_handoff_anchor = lambda: None
    worker._resolved_recovery_cohorts = lambda: ((
        "COIN", {h: ("cohort", "a" * 64) for h in HORIZONS}, NOW),)
    released = []
    worker._release_runtime_ownership = lambda: released.append(True)

    with pytest.raises(RuntimeError, match="submissions failed"):
        worker._acquire_runtime_ownership()
    assert released == [True]
    assert worker.is_runtime_owner() is False
    assert dict(worker.metrics.snapshot().statuses)[
        "evidence_runtime_owner_status"] == "ERROR"


def test_runtime_owner_replays_latest_resolved_cohort_after_shutdown():
    v1, v2 = _inputs()
    calculated = V4DCoordinator(
        capture_v1=lambda: v1, capture_v2=lambda _captured: v2,
        forecast_writer=None, compact_state_lookup=lambda **_kwargs: (None, "UNAVAILABLE"),
        state_cohort_id=lambda *_args: "cohort", cutoff_midpoint=lambda _value: 100.0,
    ).run_cycle()
    forecasts = tuple(replace(
        item.forecast, persisted_at=NOW, persistence_proof_eligible=True)
        for item in calculated.persistence)
    rows = tuple((forecast.forecast_record_hash,
                  json.dumps(_canonical(asdict(forecast)), sort_keys=True))
                 for forecast in forecasts)
    latest_created_at = NOW + timedelta(minutes=2)
    outcome = replace(build_outcome(
        forecast=forecasts[0],
        target_identity=canonical_target_identity(forecasts[0]),
        previous_observation_at=forecasts[0].target_endpoint - timedelta(seconds=1),
        endpoint_observation_at=forecasts[0].target_endpoint,
        target_resolved_at=forecasts[0].target_endpoint,
        actual_return_bps=1.0,
    ), created_at=latest_created_at)
    newer_created_at = latest_created_at + timedelta(seconds=1)
    newer_unproven_outcome = replace(build_outcome(
        forecast=forecasts[1],
        target_identity=canonical_target_identity(forecasts[1]),
        previous_observation_at=(
            forecasts[1].target_endpoint - timedelta(seconds=1)),
        endpoint_observation_at=forecasts[1].target_endpoint,
        target_resolved_at=forecasts[1].target_endpoint,
        actual_return_bps=1.0,
    ), created_at=newer_created_at)
    recovery_row = (
        forecasts[0].symbol, forecasts[0].cutoff_at, forecasts[0].cycle_id,
        forecasts[0].v3_model_version, outcome.outcome_record_hash,
        json.dumps(_canonical(asdict(outcome)), sort_keys=True),
        latest_created_at, tuple(forecast.cohort_id for forecast in forecasts),
        tuple(forecast.cohort_hash for forecast in forecasts), 4,
    )
    newer_unproven_row = (
        forecasts[0].symbol, forecasts[0].cutoff_at, forecasts[0].cycle_id,
        forecasts[0].v3_model_version,
        newer_unproven_outcome.outcome_record_hash,
        json.dumps(_canonical(asdict(newer_unproven_outcome)), sort_keys=True),
        newer_created_at, tuple(forecast.cohort_id for forecast in forecasts),
        tuple(forecast.cohort_hash for forecast in forecasts), 4,
    )
    invalid_newer_row = (
        forecasts[0].symbol, forecasts[0].cutoff_at, forecasts[0].cycle_id,
        forecasts[0].v3_model_version, "b" * 64, "{}",
        newer_created_at + timedelta(seconds=1),
        tuple(forecast.cohort_id for forecast in forecasts),
        tuple(forecast.cohort_hash for forecast in forecasts), 4,
    )
    combined_id = "v9v4statecohort:" + canonical_sha256(tuple(
        (forecast.cohort_id, forecast.cohort_hash) for forecast in forecasts))
    proof_requests = []

    class Cursor:
        def execute(self, sql, params):
            self.sql, self.params = sql, params
        def fetchall(self):
            if "WITH recent_outcomes" in self.sql:
                assert "LEFT JOIN eligible_cycles" in self.sql
                assert "DISTINCT ON" not in self.sql
                candidate_sql, remainder = self.sql.split("cycle_cohorts AS", 1)
                cycle_sql = remainder.split("eligible_cycles AS", 1)[0]
                assert "f.persisted_at <= f.target_endpoint" in candidate_sql
                assert "read_forecast_commit_proof" not in candidate_sql
                assert "f.persisted_at <= f.target_endpoint" not in cycle_sql
                return (
                    recovery_row, recovery_row, newer_unproven_row,
                    invalid_newer_row,
                )
            if "f.horizon IN" in self.sql:
                return rows
            if "WITH ORDINALITY" in self.sql:
                requested = tuple(self.params[0])
                proof_requests.append(requested)
                forecast = forecasts[0]
                if forecast.forecast_record_id not in requested:
                    return ()
                return ((
                    forecast.forecast_record_id,
                    forecast.forecast_record_id,
                    forecast.forecast_record_hash,
                    forecast.persisted_at,
                    forecast.target_endpoint,
                    True,
                    "POST_COMMIT_DB_OBSERVATION_V1",
                ),)
            if "FROM public.atom_v9_v4_states" in self.sql:
                assert "SELECT s.symbol, s.cohort_id" in self.sql
                assert "count(*) FILTER" in self.sql and "count(*)=2" in self.sql
                return (("QQQ", combined_id,
                         latest_created_at + timedelta(minutes=1)),)
            return ()
        def fetchone(self):
            if "read_forecast_commit_proof" in self.sql:
                forecast = next(
                    item for item in forecasts
                    if item.forecast_record_id == self.params[0]
                )
                return (
                    forecast.forecast_record_id,
                    forecast.forecast_record_hash,
                    forecast.persisted_at,
                    forecast.target_endpoint,
                    True,
                    "POST_COMMIT_DB_OBSERVATION_V1",
                )
            return (True,)
        def close(self): pass
    class Connection(_WorkerConnection):
        def cursor(self): return Cursor()

    submitted = []
    worker = EvidenceLedgerWorker(
        EvidenceOutbox(), evidence_store=_RawStore(), connection=Connection(),
        state_build_submit=lambda **candidate: submitted.append(candidate),
        wall_clock=lambda: NOW + timedelta(minutes=3),
    )
    worker._submit_recovery_state_build()

    assert proof_requests == [
        (forecasts[1].forecast_record_id,),
        (forecasts[0].forecast_record_id,),
    ]
    assert submitted == [{
        "symbol": "COIN", "state_as_of": NOW + timedelta(minutes=3),
        "cohorts": {forecast.horizon: (forecast.cohort_id, forecast.cohort_hash)
                    for forecast in forecasts},
        "new_outcome": True,
    }]
    assert dict(worker.metrics.snapshot().counters)[
        "v4_state_build_recovery.submitted"] == 1


def test_recovery_proof_fallback_depth_and_work_are_bounded(monkeypatch):
    def exercise(labels):
        worker = EvidenceLedgerWorker(
            EvidenceOutbox(), evidence_store=_RawStore(),
            connection=_WorkerConnection(),
        )
        candidates_by_identity = {}
        for label in labels:
            cohorts = {
                horizon: (f"{label}-{horizon}", "a" * 64)
                for horizon in HORIZONS
            }
            identity = (
                "COIN",
                tuple((horizon, *cohorts[horizon]) for horizon in HORIZONS),
            )
            representatives = tuple(
                SimpleNamespace(forecast_record_id=f"{label}-{index}")
                for index in range(5)
            )
            candidates_by_identity[identity] = [
                (cohorts, NOW + timedelta(seconds=index), representative)
                for index, representative in enumerate(representatives)
            ]
        proof_requests = []

        def validate(records):
            proof_requests.append(tuple(
                record.forecast_record_id for record in records))
            return frozenset()

        worker._validated_recovery_proof_ids = validate
        assert worker._latest_proven_recovery_cohorts(
            candidates_by_identity) == {}
        counters = dict(worker.metrics.snapshot().counters)
        return proof_requests, counters

    monkeypatch.setattr(
        "quant.evidence_outbox.EVIDENCE_RECOVERY_PROOF_FALLBACK_DEPTH", 2)
    monkeypatch.setattr(
        "quant.evidence_outbox.EVIDENCE_RECOVERY_PROOF_WORK_LIMIT", 100)
    depth_requests, depth_counters = exercise(("depth",))
    assert depth_requests == [
        ("depth-4",),
        ("depth-3",),
        ("depth-2",),
    ]
    assert depth_counters[
        "v4_state_build_recovery.proof_fallback_truncated"] == 1

    monkeypatch.setattr(
        "quant.evidence_outbox.EVIDENCE_RECOVERY_PROOF_FALLBACK_DEPTH", 4)
    monkeypatch.setattr(
        "quant.evidence_outbox.EVIDENCE_RECOVERY_PROOF_WORK_LIMIT", 3)
    work_requests, work_counters = exercise(("first", "second"))
    assert work_requests == [
        ("first-4", "second-4"),
        ("first-3",),
    ]
    assert work_counters[
        "v4_state_build_recovery.proof_fallback_truncated"] == 1

    monkeypatch.setattr(
        "quant.evidence_outbox.EVIDENCE_RECOVERY_PROOF_WORK_LIMIT", 256)
    high_cardinality_requests, high_cardinality_counters = exercise(tuple(
        f"cohort-{index:03d}" for index in range(300)
    ))
    assert len(high_cardinality_requests) == 1
    assert len(high_cardinality_requests[0]) == 256
    assert sum(map(len, high_cardinality_requests)) == 256
    assert high_cardinality_counters[
        "v4_state_build_recovery.proof_fallback_truncated"] == 1


def test_runtime_owner_replays_every_distinct_uncovered_shutdown_cohort():
    def cycle(*, cycle_id, formula_version):
        v1, v2 = _inputs()
        slots = tuple(SimpleNamespace(**{
            **vars(slot), "formula_version": formula_version,
        }) for slot in v1.slots)
        v1 = SimpleNamespace(**{
            **vars(v1), "cycle_id": cycle_id, "slots": slots,
        })
        calculated = V4DCoordinator(
            capture_v1=lambda: v1, capture_v2=lambda _captured: v2,
            forecast_writer=None,
            compact_state_lookup=lambda **_kwargs: (None, "UNAVAILABLE"),
            state_cohort_id=lambda *_args: "cohort",
            cutoff_midpoint=lambda _value: 100.0,
        ).run_cycle()
        return tuple(replace(
            item.forecast, persisted_at=NOW,
            persistence_proof_eligible=True)
            for item in calculated.persistence)

    first = cycle(cycle_id="cycle-1", formula_version="f1")
    second = cycle(cycle_id="cycle-2", formula_version="f2")
    created = (NOW + timedelta(minutes=2), NOW + timedelta(minutes=3))

    def recovery_row(forecasts, created_at, count):
        outcome = replace(build_outcome(
            forecast=forecasts[0],
            target_identity=canonical_target_identity(forecasts[0]),
            previous_observation_at=(
                forecasts[0].target_endpoint - timedelta(seconds=1)),
            endpoint_observation_at=forecasts[0].target_endpoint,
            target_resolved_at=forecasts[0].target_endpoint,
            actual_return_bps=1.0,
        ), created_at=created_at)
        return (
            forecasts[0].symbol, forecasts[0].cutoff_at,
            forecasts[0].cycle_id, forecasts[0].v3_model_version,
            outcome.outcome_record_hash,
            json.dumps(_canonical(asdict(outcome)), sort_keys=True),
            created_at, tuple(item.cohort_id for item in forecasts),
            tuple(item.cohort_hash for item in forecasts), count,
        )

    recovery_rows = (
        recovery_row(first, created[0], 2),
        recovery_row(second, created[1], 2),
    )
    lineage_rows = tuple(
        (forecast.forecast_record_hash,
         json.dumps(_canonical(asdict(forecast)), sort_keys=True))
        for forecasts in (first, second) for forecast in forecasts)

    class Cursor:
        def execute(self, sql, params): self.sql, self.params = sql, params
        def fetchall(self):
            if "WITH recent_outcomes" in self.sql:
                return recovery_rows
            if "f.horizon IN" in self.sql:
                return lineage_rows
            if "WITH ORDINALITY" in self.sql:
                representatives = (first[0], second[0])
                assert self.params == ([
                    item.forecast_record_id for item in representatives
                ],)
                return tuple((
                    item.forecast_record_id,
                    item.forecast_record_id,
                    item.forecast_record_hash,
                    item.persisted_at,
                    item.target_endpoint,
                    True,
                    "POST_COMMIT_DB_OBSERVATION_V1",
                ) for item in representatives)
            if "FROM public.atom_v9_v4_states" in self.sql:
                return ()
            return ()
        def close(self): pass
    class Connection(_WorkerConnection):
        def cursor(self): return Cursor()

    submitted = []
    worker = EvidenceLedgerWorker(
        EvidenceOutbox(), evidence_store=_RawStore(), connection=Connection(),
        state_build_submit=lambda **candidate: submitted.append(candidate),
        wall_clock=lambda: NOW + timedelta(minutes=4),
    )
    worker._submit_recovery_state_build()

    assert len(submitted) == 2
    assert [candidate["cohorts"] for candidate in submitted] == [
        {item.horizon: (item.cohort_id, item.cohort_hash) for item in first},
        {item.horizon: (item.cohort_id, item.cohort_hash) for item in second},
    ]
    assert all(candidate["new_outcome"] is True for candidate in submitted)


def test_recovery_refuses_to_open_ingress_when_hourly_bound_is_truncated():
    class Cursor:
        def execute(self, sql, _params):
            self.sql = sql
            if "WITH recent_outcomes" in sql:
                assert "recent_count" in sql
                assert "LEFT JOIN eligible_cycles" in sql
        def fetchall(self):
            if "WITH recent_outcomes" in self.sql:
                return ((None, None, None, None, None, None, None, None, None,
                         EVIDENCE_RECOVERY_OUTCOME_LIMIT + 1),)
            return ()
        def close(self): pass
    class Connection(_WorkerConnection):
        def cursor(self): return Cursor()

    worker = EvidenceLedgerWorker(
        EvidenceOutbox(), evidence_store=_RawStore(), connection=Connection(),
        state_build_submit=lambda **_candidate: None,
    )
    with pytest.raises(RuntimeError, match="exceeded"):
        worker._resolved_recovery_cohorts()
    assert dict(worker.metrics.snapshot().counters)[
        "v4_state_build_recovery.truncated"] == 1


def test_state_builder_reconnects_both_builders_and_preserves_generation():
    class OperationalError(Exception): pass
    class AdminShutdown(OperationalError): pass
    class Connection:
        def __init__(self, name): self.name = name; self.close_calls = 0
        def close(self): self.close_calls += 1
    class Builder:
        def __init__(self):
            self.prepared = []
            self.connections = []
            self.build_calls = 0
        def prepare(self, **candidate): self.prepared.append(candidate)
        def rebind_connection(self, connection): self.connections.append(connection)
        def build_and_publish(self):
            self.build_calls += 1
            if self.build_calls == 1:
                clock[0] = 61.0
                raise AdminShutdown("state connection lost")
            return "INSERT"

    clock = [0.0]
    dead, recovered = Connection("dead"), Connection("recovered")
    builder = Builder()
    scheduler = OfflineStateBuildScheduler(
        builder.build_and_publish, monotonic_clock=lambda: clock[0],
    )
    metrics = OperationalMetrics()
    worker = V4StateBuildWorker(
        builder, scheduler, connection=dead,
        connect=lambda _database_url: recovered,
        database_url="postgresql://runtime", metrics=metrics,
    )
    worker.start()
    worker.submit(
        symbol="COIN", state_as_of=NOW,
        cohorts={horizon: ("cohort", "a" * 64) for horizon in HORIZONS},
        new_outcome=True,
    )
    deadline = time.monotonic() + 2.5
    while builder.build_calls < 2 and time.monotonic() < deadline:
        time.sleep(.01)
    worker.close()

    assert builder.build_calls == 2
    assert len(builder.prepared) == 1
    assert builder.connections == [recovered]
    assert scheduler._latest_outcome_generation == scheduler._built_generation == 1
    assert dead.close_calls == recovered.close_calls == 1
    assert dict(metrics.snapshot().counters)[
        "v4_state_build_worker.reconnect_success"] == 1


def test_recovery_only_reader_does_not_load_live_pending_forecasts(monkeypatch):
    monkeypatch.setattr(
        EvidenceLedgerWorker,
        "_load_pending",
        lambda _self: (_ for _ in ()).throw(AssertionError("unexpected load")),
    )

    worker = EvidenceLedgerWorker(
        EvidenceOutbox(),
        evidence_store=_RawStore(),
        connection=_WorkerConnection(),
        load_pending=False,
    )

    assert worker._pending == []
    worker.close()


def test_state_builder_rate_limit_retains_exact_candidate_until_insert():
    class Connection:
        def close(self): pass
    class Builder:
        def __init__(self): self.prepared = []
        def prepare(self, **candidate): self.prepared.append(candidate)
    class Scheduler:
        def __init__(self): self.calls = 0; self.noted = 0
        def note_new_outcome(self): self.noted += 1
        def run_if_due(self, *, force):
            self.calls += 1
            return "SKIPPED_RATE_LIMIT" if self.calls == 1 else "INSERT"

    builder, scheduler = Builder(), Scheduler()
    worker = V4StateBuildWorker(
        builder, scheduler, connection=Connection(),
        shutdown_timeout_seconds=1.0)
    worker.start()
    worker.submit(
        symbol="COIN", state_as_of=NOW,
        cohorts={h: ("cohort-a", "a" * 64) for h in HORIZONS},
        new_outcome=True)
    deadline = time.monotonic() + 2.5
    while scheduler.calls < 1 and time.monotonic() < deadline:
        time.sleep(.01)
    worker._wake.set()
    while scheduler.calls < 2 and time.monotonic() < deadline:
        time.sleep(.01)
    worker.close()

    assert scheduler.calls == 2
    assert scheduler.noted == 1
    assert len(builder.prepared) == 1


def test_state_builder_terminal_status_does_not_starve_later_cohort():
    class Connection:
        def close(self): pass
    class Builder:
        def __init__(self): self.prepared = []
        def prepare(self, **candidate): self.prepared.append(candidate)
    class Scheduler:
        def __init__(self): self.results = iter(("STATE_CONFLICT", "INSERT")); self.calls = 0
        def note_new_outcome(self): pass
        def run_if_due(self, *, force):
            self.calls += 1
            return next(self.results)

    builder, scheduler, metrics = Builder(), Scheduler(), OperationalMetrics()
    worker = V4StateBuildWorker(
        builder, scheduler, connection=Connection(), metrics=metrics,
        shutdown_timeout_seconds=1.0)
    worker.start()
    for cohort_id, digest in (("cohort-a", "a" * 64),
                              ("cohort-b", "b" * 64)):
        worker.submit(
            symbol="COIN", state_as_of=NOW,
            cohorts={h: (cohort_id, digest) for h in HORIZONS},
            new_outcome=True)
    deadline = time.monotonic() + 2.5
    while scheduler.calls < 2 and time.monotonic() < deadline:
        time.sleep(.01)
    worker.close()

    assert scheduler.calls == 2
    assert len(builder.prepared) == 2
    telemetry = metrics.snapshot()
    assert dict(telemetry.counters)[
        "v4_state_build_worker.terminal_status"] == 1
    assert dict(telemetry.statuses)[
        "v4_state_build_worker.last_terminal_status"] == "STATE_CONFLICT"


def test_state_builder_nontransient_exception_does_not_busy_loop_or_starve():
    class Connection:
        def close(self): pass
    class Builder:
        def __init__(self): self.prepared = []
        def prepare(self, **candidate): self.prepared.append(candidate)
    class Scheduler:
        def __init__(self): self.calls = 0
        def note_new_outcome(self): pass
        def run_if_due(self, *, force):
            self.calls += 1
            if self.calls == 1:
                raise ValueError("deterministic failure")
            return "INSERT"

    builder, scheduler, metrics = Builder(), Scheduler(), OperationalMetrics()
    worker = V4StateBuildWorker(
        builder, scheduler, connection=Connection(), metrics=metrics,
        shutdown_timeout_seconds=1.0)
    worker.start()
    for cohort_id, digest in (("cohort-a", "a" * 64),
                              ("cohort-b", "b" * 64)):
        worker.submit(
            symbol="COIN", state_as_of=NOW,
            cohorts={h: (cohort_id, digest) for h in HORIZONS},
            new_outcome=True)
    deadline = time.monotonic() + 2.5
    while scheduler.calls < 2 and time.monotonic() < deadline:
        time.sleep(.01)
    worker.close()

    assert scheduler.calls == 2
    assert len(builder.prepared) == 2
    assert dict(metrics.snapshot().counters)[
        "v4_state_build_worker.terminal_exception"] == 1


def test_ledger_close_drains_every_accepted_item_before_closing_connection(monkeypatch):
    monkeypatch.setattr(EvidenceLedgerWorker, "_load_pending", lambda _self: [])
    started, release = threading.Event(), threading.Event()

    class Connection(_WorkerConnection):
        def __init__(self): self.close_calls = 0
        def close(self): self.close_calls += 1

    connection = Connection()
    outbox = EvidenceOutbox()
    worker = EvidenceLedgerWorker(
        outbox, evidence_store=_RawStore(), connection=connection)
    previous = MidpointObservation(NOW.timestamp(), 100.0)
    current = MidpointObservation(NOW.timestamp() + 1, 101.0)
    items = tuple(_work(n, previous, current, NOW + timedelta(seconds=n))
                  for n in (1, 2))
    for item in items:
        assert outbox.put_nowait(item)
    processed = []

    def process(item):
        processed.append(item.sequence)
        if item.sequence == 1:
            started.set()
            assert release.wait(2)

    worker.process = process
    worker.start()
    assert started.wait(1)
    closer = threading.Thread(target=worker.close)
    closer.start()
    time.sleep(.02)
    assert closer.is_alive()
    assert connection.close_calls == 0
    assert outbox.put_nowait(items[0]) is False
    release.set()
    closer.join(timeout=2)

    assert not closer.is_alive()
    assert processed == [1, 2]
    assert connection.close_calls == 1


def test_state_builder_close_never_closes_connection_under_active_build():
    started, release = threading.Event(), threading.Event()

    class Connection:
        def __init__(self): self.close_calls = 0
        def close(self): self.close_calls += 1

    class Builder:
        def prepare(self, **_candidate): pass
        def build_and_publish(self):
            started.set()
            assert release.wait(2)
            return "INSERT"

    connection = Connection()
    builder = Builder()
    worker = V4StateBuildWorker(
        builder, OfflineStateBuildScheduler(builder.build_and_publish),
        connection=connection,
    )
    worker.start()
    worker.submit(
        symbol="COIN", state_as_of=NOW,
        cohorts={horizon: ("cohort", "a" * 64) for horizon in HORIZONS},
        new_outcome=True,
    )
    assert started.wait(1)
    closer = threading.Thread(target=worker.close)
    closer.start()
    time.sleep(.02)
    assert closer.is_alive()
    assert connection.close_calls == 0
    release.set()
    closer.join(timeout=2)

    assert not closer.is_alive()
    assert connection.close_calls == 1


def test_state_builder_keeps_outcome_trigger_bound_to_its_cohort():
    class Builder:
        def __init__(self): self.prepared = []
        def prepare(self, **candidate): self.prepared.append(candidate)
        def build_and_publish(self): return "INSERT"

    def cohorts(name):
        return {horizon: (name, name * 64) for horizon in HORIZONS}

    builder = Builder()
    worker = V4StateBuildWorker(
        builder, OfflineStateBuildScheduler(builder.build_and_publish),
    )
    worker.submit(symbol="COIN", state_as_of=NOW, cohorts=cohorts("a"),
                  new_outcome=True)
    worker.submit(symbol="COIN", state_as_of=NOW + timedelta(seconds=1),
                  cohorts=cohorts("b"), new_outcome=False)
    worker.start()
    deadline = time.monotonic() + 1
    while not builder.prepared and time.monotonic() < deadline:
        time.sleep(.01)
    worker.stop()

    assert len(builder.prepared) == 1
    assert builder.prepared[0]["cohorts"] == cohorts("a")


def test_state_builder_shutdown_drains_pending_outcome_cohorts():
    started, release = threading.Event(), threading.Event()

    class Builder:
        def __init__(self): self.prepared = []; self.build_calls = 0
        def prepare(self, **candidate): self.prepared.append(candidate)
        def build_and_publish(self):
            self.build_calls += 1
            if self.build_calls == 1:
                started.set()
                assert release.wait(2)
            return "INSERT"

    def cohorts(name):
        return {horizon: (name, name * 64) for horizon in HORIZONS}

    builder = Builder()
    worker = V4StateBuildWorker(
        builder, OfflineStateBuildScheduler(builder.build_and_publish),
    )
    worker.start()
    worker.submit(symbol="COIN", state_as_of=NOW, cohorts=cohorts("a"),
                  new_outcome=True)
    assert started.wait(1)
    worker.submit(symbol="COIN", state_as_of=NOW + timedelta(seconds=1),
                  cohorts=cohorts("b"), new_outcome=True)
    closer = threading.Thread(target=worker.stop)
    closer.start()
    release.set()
    closer.join(timeout=2)

    assert not closer.is_alive()
    assert builder.build_calls == 2
    assert [item["cohorts"] for item in builder.prepared] == [
        cohorts("a"), cohorts("b"),
    ]


def test_state_builder_shutdown_is_bounded_during_database_outage():
    started = threading.Event()

    class OperationalError(Exception): pass
    class Connection:
        def __init__(self): self.close_calls = 0
        def close(self): self.close_calls += 1
    class Builder:
        def prepare(self, **_candidate): pass
        def rebind_connection(self, _connection): pass
        def build_and_publish(self):
            started.set()
            raise OperationalError("database unavailable")

    connection = Connection()
    builder = Builder()
    metrics = OperationalMetrics()
    worker = V4StateBuildWorker(
        builder, OfflineStateBuildScheduler(builder.build_and_publish),
        connection=connection,
        connect=lambda _url: (_ for _ in ()).throw(
            OperationalError("database unavailable")),
        database_url="postgresql://runtime", metrics=metrics,
        shutdown_timeout_seconds=.05,
    )
    worker.start()
    worker.submit(
        symbol="COIN", state_as_of=NOW,
        cohorts={horizon: ("cohort", "a" * 64) for horizon in HORIZONS},
        new_outcome=True,
    )
    assert started.wait(1)

    before = time.monotonic()
    worker.stop()

    assert time.monotonic() - before < .5
    assert not worker._thread.is_alive()
    assert connection.close_calls == 1
    assert dict(metrics.snapshot().counters)[
        "v4_state_build_worker.shutdown_abandoned"] == 1


@pytest.mark.parametrize("family_count", (11, 10, 7, 3, 1, 0))
def test_continuous_cycle_uses_current_subset_without_readiness_gate(family_count):
    v1, v2 = _inputs(family_count)
    writer = Writer()
    coordinator = V4DCoordinator(
        capture_v1=lambda: v1, capture_v2=lambda captured: v2,
        forecast_writer=writer, compact_state_lookup=lambda **kwargs: (None, "UNAVAILABLE"),
        state_cohort_id=lambda one, two: "cohort",
    )
    output = coordinator.run_cycle()
    assert output.v1 is v1 and output.v2 is v2
    assert tuple(x.horizon for x in output.final_numbers) == HORIZONS
    assert len(writer.forecasts) == 6
    for v3, final in zip(output.v3.horizon_results, output.final_numbers):
        assert v3.directional_input_count == family_count
        assert final.final_bps == v3.expected_return_bps
        assert (final.gamma, final.phi, final.gamma_status) == (0, 1, "INACTIVE")
        assert (v3.status == "UNAVAILABLE") == (family_count == 0)


def test_one_horizon_and_one_persistence_failure_do_not_block_other_five():
    v1, v2 = _inputs(1, unavailable_horizon="30S")
    writer = Writer(fail_horizon="1M")
    output = V4DCoordinator(
        capture_v1=lambda: v1, capture_v2=lambda captured: v2,
        forecast_writer=writer, compact_state_lookup=lambda **kwargs: (None, "UNAVAILABLE"),
        state_cohort_id=lambda one, two: "cohort",
    ).run_cycle()
    assert output.final_numbers[0].final_bps is None
    assert all(item.final_bps is not None for item in output.final_numbers[1:])
    assert [item.status for item in output.persistence].count("FAILED") == 1
    assert len(writer.forecasts) == 5


def test_latest_compact_state_is_consumed_and_conflict_fails_closed():
    v1, v2 = _inputs(1)
    state = _empty_state()
    available = V4DCoordinator(
        capture_v1=lambda: v1, capture_v2=lambda captured: v2,
        forecast_writer=Writer(), compact_state_lookup=lambda **kwargs: (state, "AVAILABLE"),
        state_cohort_id=lambda one, two: "cohort",
    ).run_cycle()
    conflicted = V4DCoordinator(
        capture_v1=lambda: v1, capture_v2=lambda captured: v2,
        forecast_writer=Writer(), compact_state_lookup=lambda **kwargs: (None, "STATE_CONFLICT"),
        state_cohort_id=lambda one, two: "cohort",
    ).run_cycle()
    assert available.v4_state_status == "AVAILABLE"
    assert conflicted.v4_state_status == "STATE_CONFLICT"
    assert [x.final_bps for x in available.final_numbers] == [x.final_bps for x in conflicted.final_numbers]


def test_v4d_rejects_mismatched_accuracy_and_compact_generations():
    v1, v2 = _inputs(1)
    compact = _empty_state()
    accuracy = SimpleNamespace(
        symbol="COIN", cohort_id="cohort",
        state_as_of=NOW - timedelta(microseconds=1), horizon_states=(),
    )
    output = V4DCoordinator(
        capture_v1=lambda: v1, capture_v2=lambda captured: v2,
        forecast_writer=Writer(),
        compact_state_lookup=lambda **kwargs: (compact, "AVAILABLE"),
        accuracy_state_lookup=lambda **kwargs: (accuracy, "AVAILABLE"),
        state_cohort_id=lambda one, two: "cohort",
    ).run_cycle()

    assert output.v4_state_status == "STATE_GENERATION_MISMATCH"
    assert output.accuracy == (None,) * 6


def test_outcome_is_separate_unverified_append_and_cannot_mutate_forecast():
    v1, v2 = _inputs(1)
    from quant.v9_v3_synthesis import synthesize_v3
    forecast = build_forecast(v1=v1, v2=v2,
        result=synthesize_v3(v1, v2).horizon_results[0], evidence_origin="PRODUCTION")
    writer = Writer()
    outcome = resolve_outcome(writer=writer, forecast=forecast,
        target_identity="target/source/schema/endpoint", endpoint_observation_at=NOW+timedelta(seconds=31),
        target_resolved_at=NOW+timedelta(seconds=32), actual_return_bps=2.0)
    assert outcome.forecast_record_id == forecast.forecast_record_id
    assert outcome.endpoint_observation_delay == 1
    assert outcome.target_timing_status == "UNVERIFIED" and not outcome.proof_eligible
    assert forecast.persisted_at is None and len(writer.outcomes) == 1


def test_offline_builder_requires_new_outcome_and_thirty_seconds():
    clock = [0.0]
    calls = []
    scheduler = OfflineStateBuildScheduler(lambda: calls.append(1) or "INSERT",
                                            monotonic_clock=lambda: clock[0])
    assert scheduler.run_if_due() == "SKIPPED_NO_NEW_OUTCOME"
    scheduler.note_new_outcome()
    assert scheduler.run_if_due() == "INSERT"
    scheduler.note_new_outcome(); clock[0] = 29
    assert scheduler.run_if_due() == "SKIPPED_RATE_LIMIT"
    clock[0] = 30
    assert scheduler.run_if_due() == "INSERT" and len(calls) == 2


def test_offline_builder_cooldown_starts_after_slow_build_finishes():
    clock = [0.0]
    calls = []

    def slow_build():
        calls.append(clock[0])
        clock[0] += 70.0
        return "INSERT"

    scheduler = OfflineStateBuildScheduler(
        slow_build, monotonic_clock=lambda: clock[0],
    )
    scheduler.note_new_outcome()
    assert scheduler.run_if_due() == "INSERT"

    scheduler.note_new_outcome()
    assert scheduler.run_if_due() == "SKIPPED_RATE_LIMIT"
    clock[0] = 99.0
    assert scheduler.run_if_due() == "SKIPPED_RATE_LIMIT"
    clock[0] = 100.0
    assert scheduler.run_if_due() == "INSERT"
    assert calls == [0.0, 100.0]


def test_postgres_v4b_builder_reads_governed_v4a_and_invokes_frozen_build(monkeypatch):
    v1, v2 = _inputs()
    calculated = V4DCoordinator(
        capture_v1=lambda: v1, capture_v2=lambda _captured: v2,
        forecast_writer=None, compact_state_lookup=lambda **_kwargs: (None, "UNAVAILABLE"),
        state_cohort_id=lambda *_args: "cohort", cutoff_midpoint=lambda _value: 100.0,
    ).run_cycle()
    forecast = replace(calculated.persistence[0].forecast, persisted_at=NOW,
                       persistence_proof_eligible=True)
    previous = forecast.target_endpoint - timedelta(seconds=1)
    outcome = build_outcome(
        forecast=forecast, target_identity=canonical_target_identity(forecast),
        previous_observation_at=previous,
        endpoint_observation_at=forecast.target_endpoint,
        target_resolved_at=forecast.target_endpoint,
        actual_return_bps=2.0,
    )
    row = (
        forecast.horizon, forecast.cutoff_at,
        forecast.forecast_record_hash,
        json.dumps(_canonical(asdict(forecast))),
        outcome.outcome_record_hash,
        json.dumps(_canonical(asdict(outcome))),
        forecast.forecast_record_id, forecast.forecast_record_hash,
        NOW, forecast.target_endpoint, True,
        "POST_COMMIT_DB_OBSERVATION_V1",
    )

    class Cursor:
        def execute(self, sql, params):
            assert "atom_v9_v4_forecasts" in sql and "atom_v9_v4_outcomes" in sql
            assert "o.created_at<=%s" in sql
            proof_filter = "o.record_json->>'proof_eligible'='true'"
            assert proof_filter in sql
            assert "f.record_json->>'cohort_id'=%s" in sql
            assert "f.record_json->>'cohort_hash'=%s" in sql
            assert "read_forecast_commit_proof" in sql and "LIMIT" not in sql
            assert "ORDER BY f.horizon, f.cutoff_at" in sql
            self.params = params
        def fetchall(self):
            return (row,)
        def close(self): pass
    class Connection(_WorkerConnection):
        def __init__(self): self.cursor_value = Cursor()
        def cursor(self): return self.cursor_value

    captured = {}
    state = SimpleNamespace(state_id="state")
    def frozen_build(**kwargs):
        captured.update(kwargs)
        return state
    monkeypatch.setattr("quant.evidence_outbox.build_accuracy_state", frozen_build)
    store = SimpleNamespace(
        calls=[], insert=lambda candidate, created: store.calls.append((candidate, created)) or "INSERT")
    connection = Connection()
    builder = PostgresV4BStateBuilder(connection, state_store=store,
                                      wall_clock=lambda: NOW + timedelta(minutes=2))
    cohorts = {item.forecast.horizon:
               (item.forecast.cohort_id, item.forecast.cohort_hash)
               for item in calculated.persistence}
    as_of = NOW + timedelta(minutes=1)
    builder.prepare(symbol="COIN", state_as_of=as_of, cohorts=cohorts)

    assert builder.build_and_publish() == "INSERT"
    assert captured["symbol"] == "COIN"
    assert captured["state_as_of"] == as_of
    assert captured["cohorts"] == cohorts
    assert captured["evidence"] == ((forecast, outcome),)
    selections = captured["overlap_selections"]
    assert tuple(selections) == HORIZONS
    assert selections[forecast.horizon].raw_resolved_n == 1
    assert selections[forecast.horizon].selected_ids == (
        forecast.forecast_record_id,)
    assert all(
        selection.raw_resolved_n == 0
        for horizon, selection in selections.items()
        if horizon != forecast.horizon)
    assert connection.cursor_value.params == (
        "COIN", as_of, as_of,
        *(value for horizon in HORIZONS for value in (horizon, *cohorts[horizon])),
    )
    assert store.calls == [(state, NOW + timedelta(minutes=2))]
    with pytest.raises(
            RuntimeError, match="V4_STATE_EVIDENCE_RELATIONAL_MISMATCH"):
        _decode_v4_state_row(("1H", *row[1:]))


def test_v4_state_pages_continue_past_former_total_evidence_bound(monkeypatch):
    total = 65_537

    class Cursor:
        def __init__(self):
            self.index = 0
            self.calls = 0

        def fetchmany(self, size):
            assert size == V4_STATE_BUILD_QUERY_CHUNK
            self.calls += 1
            start = self.index
            self.index = min(total, start + size)
            return tuple(range(start, self.index))

    def decode(index):
        return (
            SimpleNamespace(
                horizon="30S",
                cutoff_at=NOW + timedelta(microseconds=index),
            ),
            SimpleNamespace(),
        )

    monkeypatch.setattr("quant.evidence_outbox._decode_v4_state_row", decode)
    cursor = Cursor()
    page_sizes = tuple(len(page) for page in _iter_v4_state_pages(cursor))

    assert sum(page_sizes) == total
    assert max(page_sizes) <= V4_STATE_BUILD_QUERY_CHUNK
    assert cursor.calls > total // V4_STATE_BUILD_QUERY_CHUNK


@pytest.mark.parametrize("page_size", (1, 2, 3, 4_096))
@pytest.mark.parametrize(
    ("stored_horizon_seconds", "offsets"),
    ((60, (0, 30, 60)), (30, (0, 30))),
)
def test_streamed_overlap_selection_matches_frozen_whole_history(
        monkeypatch, page_size, stored_horizon_seconds, offsets):
    v1, v2 = _inputs()
    calculated = V4DCoordinator(
        capture_v1=lambda: v1, capture_v2=lambda _captured: v2,
        forecast_writer=None,
        compact_state_lookup=lambda **_kwargs: (None, "UNAVAILABLE"),
        state_cohort_id=lambda *_args: "unused",
        cutoff_midpoint=lambda _value: 100.0,
    ).run_cycle()
    base = next(
        item.forecast for item in calculated.persistence
        if item.forecast.horizon == "1M")
    base = replace(base, predictive_variance_bps2=4.0)
    pairs = []
    for index, offset in enumerate(offsets):
        cutoff = NOW + timedelta(seconds=offset)
        forecast = replace(
            base,
            forecast_record_id=f"stream-f-{index}",
            forecast_record_hash=f"{index + 1:064x}",
            cutoff_at=cutoff,
            target_endpoint=cutoff + timedelta(
                seconds=stored_horizon_seconds),
            horizon_seconds=stored_horizon_seconds,
            cycle_id=f"stream-cycle-{index}",
            persisted_at=cutoff,
            persistence_proof_eligible=True,
        )
        outcome = build_outcome(
            forecast=forecast,
            target_identity=canonical_target_identity(forecast),
            previous_observation_at=forecast.target_endpoint - timedelta(seconds=1),
            endpoint_observation_at=forecast.target_endpoint,
            target_resolved_at=forecast.target_endpoint,
            actual_return_bps=2.0,
        )
        pairs.append((forecast, outcome))

    class Cursor:
        def __init__(self):
            self.index = 0

        def execute(self, _sql, _params):
            pass

        def fetchmany(self, size):
            assert size == page_size
            start = self.index
            self.index = min(len(pairs), start + size)
            return tuple(pairs[start:self.index])

        def close(self):
            pass

    class Connection(_WorkerConnection):
        def __init__(self):
            self.cursor_value = Cursor()

        def cursor(self, *args, **kwargs):
            return self.cursor_value

    monkeypatch.setattr(
        "quant.evidence_outbox.V4_STATE_BUILD_QUERY_CHUNK", page_size)
    decoded = []
    def decode(row):
        decoded.append(row)
        return row
    monkeypatch.setattr(
        "quant.evidence_outbox._decode_v4_state_row", decode)
    cohorts = {
        horizon: (base.cohort_id, base.cohort_hash)
        for horizon in HORIZONS
    }

    prepared_sets = _prepare_v4_state_evidence_sets(
        Connection(), symbol="COIN", state_as_of=NOW + timedelta(hours=1),
        cohorts=cohorts,
        governed_sets={
            "all": lambda **kwargs: tuple(kwargs["pairs"]),
            "later": lambda **kwargs: tuple(
                pair for pair in kwargs["pairs"]
                if pair[0].cutoff_at > NOW),
        },
    )
    prepared = prepared_sets["all"]
    expected = select_non_overlapping(pairs)
    later_expected = select_non_overlapping(pairs[1:])

    assert len(decoded) == len(pairs)
    assert prepared.selection_map()["1M"] == expected
    assert prepared_sets["later"].selection_map()["1M"] == later_expected
    assert tuple(pair[0].forecast_record_id for pair in prepared.evidence) == \
        expected.selected_ids
    as_of = NOW + timedelta(hours=1)
    assert PostgresV4CStateBuilder._build_state(
        "COIN", as_of, cohorts, tuple(pairs)) == \
        PostgresV4CStateBuilder._build_state(
            "COIN", as_of, cohorts, prepared.evidence)


def test_streaming_preserves_conflicting_pairs_across_fetch_boundaries(
        monkeypatch):
    v1, v2 = _inputs()
    calculated = V4DCoordinator(
        capture_v1=lambda: v1, capture_v2=lambda _captured: v2,
        forecast_writer=None,
        compact_state_lookup=lambda **_kwargs: (None, "UNAVAILABLE"),
        state_cohort_id=lambda *_args: "unused",
        cutoff_midpoint=lambda _value: 100.0,
    ).run_cycle()
    base = next(
        item.forecast for item in calculated.persistence
        if item.forecast.horizon == "1M")

    def make_forecast(index, offset):
        cutoff = NOW + timedelta(seconds=offset)
        return replace(
            base,
            forecast_record_id=f"conflict-f-{index}",
            forecast_record_hash=f"{index + 1:064x}",
            cutoff_at=cutoff,
            target_endpoint=cutoff + timedelta(seconds=60),
            cycle_id=f"conflict-cycle-{index}",
            persisted_at=cutoff,
            persistence_proof_eligible=True,
        )

    first = make_forecast(0, 0)
    later = make_forecast(1, 60)

    def make_outcome(forecast, actual):
        return build_outcome(
            forecast=forecast,
            target_identity=canonical_target_identity(forecast),
            previous_observation_at=forecast.target_endpoint - timedelta(seconds=1),
            endpoint_observation_at=forecast.target_endpoint,
            target_resolved_at=forecast.target_endpoint,
            actual_return_bps=actual,
        )

    first_outcome = make_outcome(first, 1.0)
    alternate_outcome = replace(
        first_outcome,
        outcome_record_id="alternate-outcome",
        outcome_record_hash="f" * 64,
        target_identity="alternate-target",
    )
    pairs = (
        (first, first_outcome),
        (first, make_outcome(first, 2.0)),
        (first, alternate_outcome),
        (later, make_outcome(later, 4.0)),
    )

    class Cursor:
        def __init__(self):
            self.index = 0

        def execute(self, _sql, _params):
            pass

        def fetchmany(self, size):
            assert size == 1
            if self.index == len(pairs):
                return ()
            pair = pairs[self.index]
            self.index += 1
            return (pair,)

        def close(self):
            pass

    class Connection(_WorkerConnection):
        def cursor(self, *args, **kwargs):
            return Cursor()

    monkeypatch.setattr("quant.evidence_outbox.V4_STATE_BUILD_QUERY_CHUNK", 1)
    monkeypatch.setattr(
        "quant.evidence_outbox._decode_v4_state_row", lambda row: row)
    cohorts = {
        horizon: (base.cohort_id, base.cohort_hash)
        for horizon in HORIZONS
    }
    prepared = _prepare_v4_state_evidence(
        Connection(), symbol="COIN", state_as_of=NOW + timedelta(hours=1),
        cohorts=cohorts,
        governed=lambda **kwargs: tuple(kwargs["pairs"]),
    )
    expected = select_non_overlapping(pairs)
    selected_ids = set(expected.selected_ids)

    assert prepared.selection_map()["1M"] == expected
    assert prepared.evidence == tuple(
        pair for pair in pairs
        if pair[0].forecast_record_id in selected_ids)
    assert len(prepared.evidence) == 4


def test_postgres_v4c_builder_runs_frozen_components_and_persists_combined_state(monkeypatch):
    v1, v2 = _inputs()
    calculated = V4DCoordinator(
        capture_v1=lambda: v1, capture_v2=lambda _captured: v2,
        forecast_writer=None, compact_state_lookup=lambda **_kwargs: (None, "UNAVAILABLE"),
        state_cohort_id=lambda *_args: "unused", cutoff_midpoint=lambda _value: 100.0,
    ).run_cycle()
    forecast = replace(calculated.persistence[0].forecast, persisted_at=NOW,
                       persistence_proof_eligible=True)
    outcome = build_outcome(
        forecast=forecast, target_identity=canonical_target_identity(forecast),
        previous_observation_at=forecast.target_endpoint - timedelta(seconds=1),
        endpoint_observation_at=forecast.target_endpoint,
        target_resolved_at=forecast.target_endpoint, actual_return_bps=2.0)

    class Cursor:
        def execute(self, sql, params):
            assert "atom_v9_v4_forecasts" in sql and "atom_v9_v4_outcomes" in sql
            assert "o.created_at<=%s" in sql
            proof_filter = "o.record_json->>'proof_eligible'='true'"
            assert proof_filter in sql
            assert "f.record_json->>'cohort_id'=%s" in sql
            assert "f.record_json->>'cohort_hash'=%s" in sql
            assert "read_forecast_commit_proof" in sql and "LIMIT" not in sql
            assert "ORDER BY f.horizon, f.cutoff_at" in sql
            self.params = params
        def fetchall(self):
            return ((forecast.horizon, forecast.cutoff_at,
                     forecast.forecast_record_hash,
                     json.dumps(_canonical(asdict(forecast))),
                     outcome.outcome_record_hash, json.dumps(_canonical(asdict(outcome))),
                     forecast.forecast_record_id, forecast.forecast_record_hash,
                     NOW, forecast.target_endpoint, True,
                     "POST_COMMIT_DB_OBSERVATION_V1"),)
        def close(self): pass
    class Connection(_WorkerConnection):
        def __init__(self): self.cursor_value = Cursor()
        def cursor(self): return self.cursor_value

    import quant.evidence_outbox as module
    calls = {"threshold": 0, "scale": 0, "range": 0, "state": 0}
    for name in ("build_thresholds", "calibrate_scale", "calibrate_range", "build_v4c_state"):
        original = getattr(module, name)
        key = {"build_thresholds": "threshold", "calibrate_scale": "scale",
               "calibrate_range": "range", "build_v4c_state": "state"}[name]
        def spy(*args, _original=original, _key=key, **kwargs):
            calls[_key] += 1
            return _original(*args, **kwargs)
        monkeypatch.setattr(module, name, spy)

    store = SimpleNamespace(calls=[])
    store.insert = lambda state, created: store.calls.append((state, created)) or "INSERT"
    connection = Connection()
    builder = PostgresV4CStateBuilder(connection, state_store=store,
                                      wall_clock=lambda: NOW + timedelta(minutes=2))
    cohorts = {item.forecast.horizon:
               (item.forecast.cohort_id, item.forecast.cohort_hash)
               for item in calculated.persistence}
    as_of = NOW + timedelta(hours=2)
    builder.prepare(symbol="COIN", state_as_of=as_of, cohorts=cohorts)

    assert builder.build_and_publish() == "INSERT"
    state = store.calls[0][0]
    assert calls == {"threshold": 6, "scale": 6, "range": 12, "state": 1}
    assert state.state_version == PROBABILITY_STATE_VERSION
    assert state.cohort_id == "v9v4statecohort:" + module.canonical_sha256(
        tuple(cohorts[horizon] for horizon in HORIZONS))
    assert connection.cursor_value.params == (
        "COIN", as_of, as_of,
        *(value for horizon in HORIZONS for value in (horizon, *cohorts[horizon])),
    )
    assert state.horizons[0].range_status == "UNAVAILABLE"
    assert all(item.range_status == "UNAVAILABLE" for item in state.horizons)
    assert store.calls[0][1] == NOW + timedelta(minutes=2)


def test_combined_builder_keeps_accuracy_and_compact_in_one_generation():
    class Connection:
        autocommit = False
        def __init__(self):
            self.commits = 0; self.rollbacks = 0; self.events = []
        def cursor(self):
            connection = self
            class Cursor:
                def execute(self, sql): connection.events.append(sql)
                def close(self): pass
            return Cursor()
        def commit(self): self.commits += 1; self.events.append("COMMIT")
        def rollback(self): self.rollbacks += 1
    class Builder:
        def __init__(self, result):
            self.result = result; self.prepared = []; self.calls = 0; self.connections = []
        def prepare(self, **candidate): self.prepared.append(candidate)
        def rebind_connection(self, connection):
            self._connection = connection
            self.connections.append(connection)
        def build_and_publish(self):
            self.calls += 1
            self._connection.commit()
            return self.result
    accuracy, compact = Builder("IDEMPOTENT"), Builder("INSERT")
    connection = Connection()
    builder = PostgresV4StateBuilder(
        accuracy, compact, connection=connection)
    candidate = {"symbol": "COIN", "state_as_of": NOW,
                 "cohorts": {h: ("c", "h") for h in HORIZONS}}
    builder.prepare(**candidate)
    replacement = Connection()
    builder.rebind_connection(replacement)
    assert builder.build_and_publish() == "INSERT"
    assert accuracy.prepared == compact.prepared == [candidate]
    assert accuracy.calls == compact.calls == 1
    assert replacement.commits == 1 and replacement.rollbacks == 0
    assert replacement.events[0] == \
        "SET TRANSACTION ISOLATION LEVEL REPEATABLE READ"
    assert replacement.events[-1] == "COMMIT"
    assert accuracy.connections[0] is compact.connections[0] is replacement
    assert accuracy.connections[-1] is compact.connections[-1] is replacement
    assert accuracy.connections[-2].__class__.__name__ == \
        compact.connections[-2].__class__.__name__ == "_CommitSuppressingConnection"


def test_combined_builder_streams_one_snapshot_for_both_frozen_states(monkeypatch):
    class Connection:
        autocommit = False
        def __init__(self):
            self.commits = 0; self.rollbacks = 0; self.events = []
        def cursor(self):
            connection = self
            class Cursor:
                def execute(self, sql): connection.events.append(sql)
                def close(self): pass
            return Cursor()
        def commit(self): self.commits += 1; self.events.append("COMMIT")
        def rollback(self): self.rollbacks += 1

    accuracy_prepared = SimpleNamespace(name="accuracy")
    compact_prepared = SimpleNamespace(name="compact")
    shared_calls = []
    def prepare_sets(connection, **kwargs):
        shared_calls.append((connection, kwargs))
        return {"accuracy": accuracy_prepared, "compact": compact_prepared}
    monkeypatch.setattr(
        "quant.evidence_outbox._prepare_v4_state_evidence_sets", prepare_sets)

    class Builder:
        def __init__(self, result):
            self.result = result; self.prepared = []; self.received = []
        def prepare(self, **candidate): self.prepared.append(candidate)
        def rebind_connection(self, connection): self._connection = connection
        def build_and_publish(self):
            raise AssertionError("combined builder repeated the history scan")
        def build_and_publish_prepared(self, prepared):
            self.received.append(prepared)
            self._connection.commit()
            return self.result

    accuracy, compact = Builder("INSERT"), Builder("IDEMPOTENT")
    connection = Connection()
    builder = PostgresV4StateBuilder(
        accuracy, compact, connection=connection)
    candidate = {"symbol": "COIN", "state_as_of": NOW,
                 "cohorts": {h: ("c", "h") for h in HORIZONS}}
    builder.prepare(**candidate)

    assert builder.build_and_publish() == "INSERT"
    assert len(shared_calls) == 1
    shared_connection, shared_kwargs = shared_calls[0]
    assert shared_connection.__class__.__name__ == "_CommitSuppressingConnection"
    assert shared_kwargs["symbol"] == "COIN"
    assert shared_kwargs["state_as_of"] == NOW
    assert shared_kwargs["cohorts"] == candidate["cohorts"]
    assert tuple(shared_kwargs["governed_sets"]) == ("accuracy", "compact")
    assert accuracy.received == [accuracy_prepared]
    assert compact.received == [compact_prepared]
    assert connection.commits == 1 and connection.rollbacks == 0


def test_compact_failure_rolls_back_staged_accuracy_publication():
    class Connection:
        autocommit = False
        def __init__(self): self.commits = 0; self.rollbacks = 0
        def cursor(self):
            class Cursor:
                def execute(self, _sql): pass
                def close(self): pass
            return Cursor()
        def commit(self): self.commits += 1
        def rollback(self): self.rollbacks += 1
    class Accuracy:
        def __init__(self): self.calls = 0
        def rebind_connection(self, connection): self.connection = connection
        def build_and_publish(self):
            self.calls += 1
            self.connection.commit()
            return "INSERT"
    class Compact:
        def rebind_connection(self, _connection): pass
        def build_and_publish(self): raise RuntimeError("compact build failed")
    accuracy, connection = Accuracy(), Connection()
    with pytest.raises(RuntimeError, match="compact build failed"):
        PostgresV4StateBuilder(
            accuracy, Compact(), connection=connection).build_and_publish()
    assert accuracy.calls == 1
    assert connection.commits == 0 and connection.rollbacks == 1


def test_new_worker_outcome_submits_v4_state_build_off_fifo(monkeypatch):
    monkeypatch.setattr(EvidenceLedgerWorker, "_load_pending", lambda _self: [])
    v1, v2 = _inputs()
    calculated = V4DCoordinator(
        capture_v1=lambda: v1, capture_v2=lambda _captured: v2,
        forecast_writer=None, compact_state_lookup=lambda **_kwargs: (None, "UNAVAILABLE"),
        state_cohort_id=lambda *_args: "cohort", cutoff_midpoint=lambda _value: 100.0,
    ).run_cycle()
    forecasts = tuple(replace(item.forecast, persisted_at=NOW,
                              persistence_proof_eligible=True)
                      for item in calculated.persistence)
    due = forecasts[0]
    previous = MidpointObservation(due.target_endpoint.timestamp() - 1, 100.0)
    current = MidpointObservation(due.target_endpoint.timestamp(), 101.0)
    lineage = tuple(
        replace(
            forecast,
            persisted_at=forecast.target_endpoint + timedelta(microseconds=1),
            persistence_proof_eligible=False,
            persistence_reason="FORECAST_COMMIT_PROOF_OBSERVED_LATE",
        ) if forecast.horizon == "1M" else forecast
        for forecast in forecasts
    )
    lineage_rows = tuple((forecast.forecast_record_hash,
                          json.dumps(_canonical(asdict(forecast)), sort_keys=True))
                         for forecast in lineage)

    class LineageCursor:
        def execute(self, sql, _params): self.sql = sql
        def fetchall(self):
            return lineage_rows if "f.horizon IN" in self.sql else ()
        def close(self): pass
    class LineageConnection(_WorkerConnection):
        def cursor(self): return LineageCursor()

    submitted = []
    worker = EvidenceLedgerWorker(
        EvidenceOutbox(), evidence_store=_RawStore(), connection=LineageConnection(),
        state_build_submit=lambda **candidate: submitted.append(candidate),
    )
    worker._pending = [due]
    worker._writer = Writer()
    item = QuoteEvidenceWork(
        1, calculated.cycle_id, previous, current, due.target_endpoint,
        (), (), forecasts, "cohort", calculated,
    )

    worker.process(item)
    assert len(submitted) == 1 and submitted[0]["new_outcome"] is True
    assert submitted[0]["state_as_of"] == worker._writer.outcomes[0].created_at
    assert submitted[0]["state_as_of"] >= due.target_endpoint
    assert submitted[0]["cohorts"] == {
        forecast.horizon: (forecast.cohort_id, forecast.cohort_hash)
        for forecast in forecasts
    }


@pytest.mark.parametrize("outcome_status,previous_present,expected_notes,raises", (
    ("IDEMPOTENT", True, 0, False),
    ("OUTCOME_CONFLICT", True, 0, True),
    ("INSERT", False, 0, False),
))
def test_non_new_outcomes_do_not_create_v4b_generation(
        monkeypatch, outcome_status, previous_present, expected_notes, raises):
    monkeypatch.setattr(EvidenceLedgerWorker, "_load_pending", lambda _self: [])
    v1, v2 = _inputs()
    calculated = V4DCoordinator(
        capture_v1=lambda: v1, capture_v2=lambda _captured: v2,
        forecast_writer=None, compact_state_lookup=lambda **_kwargs: (None, "UNAVAILABLE"),
        state_cohort_id=lambda *_args: "cohort", cutoff_midpoint=lambda _value: 100.0,
    ).run_cycle()
    forecasts = tuple(replace(item.forecast, persisted_at=NOW,
                              persistence_proof_eligible=True)
                      for item in calculated.persistence)
    due = forecasts[0]
    previous = MidpointObservation(due.target_endpoint.timestamp() - 1, 100.0)
    current = MidpointObservation(due.target_endpoint.timestamp(), 101.0)

    class StatusWriter(Writer):
        def persist_outcome(self, record, created_at):
            self.last_write_status = outcome_status
            return record
    submitted = []
    worker = EvidenceLedgerWorker(
        EvidenceOutbox(), evidence_store=_RawStore(), connection=_WorkerConnection(),
        state_build_submit=lambda **candidate: submitted.append(candidate),
    )
    worker._pending = [due]
    worker._writer = StatusWriter()
    item = QuoteEvidenceWork(
        1, calculated.cycle_id, previous if previous_present else None, current,
        due.target_endpoint, (), (), forecasts, "cohort", calculated,
    )

    if raises:
        with pytest.raises(TerminalDeliveryError, match="OUTCOME_CONFLICT"):
            worker.process(item)
        assert submitted == []
    else:
        worker.process(item)
        assert len(submitted) == 1
        assert submitted[0]["new_outcome"] is bool(expected_notes)


def test_v4_state_build_submit_failure_isolated_from_forecast_delivery(monkeypatch):
    monkeypatch.setattr(EvidenceLedgerWorker, "_load_pending", lambda _self: [])
    v1, v2 = _inputs()
    calculated = V4DCoordinator(
        capture_v1=lambda: v1, capture_v2=lambda _captured: v2,
        forecast_writer=None, compact_state_lookup=lambda **_kwargs: (None, "UNAVAILABLE"),
        state_cohort_id=lambda *_args: "cohort", cutoff_midpoint=lambda _value: 100.0,
    ).run_cycle()
    forecasts = tuple(replace(item.forecast, persisted_at=NOW,
                              persistence_proof_eligible=True)
                      for item in calculated.persistence)
    due = forecasts[0]
    previous = MidpointObservation(due.target_endpoint.timestamp() - 1, 100.0)
    current = MidpointObservation(due.target_endpoint.timestamp(), 101.0)

    def failing_submit(**_kwargs):
        raise RuntimeError("offline builder unavailable")
    writer = Writer()
    worker = EvidenceLedgerWorker(
        EvidenceOutbox(), evidence_store=_RawStore(), connection=_WorkerConnection(),
        state_build_submit=failing_submit,
    )
    worker._pending = [due]
    worker._writer = writer
    item = QuoteEvidenceWork(
        1, calculated.cycle_id, previous, current, due.target_endpoint,
        (), (), forecasts, "cohort", calculated,
    )

    worker.process(item)
    assert len(writer.outcomes) == 1
    assert len(writer.forecasts) == 6
    assert any(number.final_bps is not None for number in calculated.final_numbers)
    assert dict(worker.metrics.snapshot().counters)["v4_state_build_submit.failure"] == 1


def test_blocked_full_history_builder_cannot_cause_evidence_outbox_drops(monkeypatch):
    monkeypatch.setattr(EvidenceLedgerWorker, "_load_pending", lambda _self: [])
    v1, v2 = _inputs()
    calculated = V4DCoordinator(
        capture_v1=lambda: v1, capture_v2=lambda _captured: v2,
        forecast_writer=None, compact_state_lookup=lambda **_kwargs: (None, "UNAVAILABLE"),
        state_cohort_id=lambda *_args: "cohort", cutoff_midpoint=lambda _value: 100.0,
    ).run_cycle()
    forecasts = tuple(item.forecast for item in calculated.persistence)
    started, release = threading.Event(), threading.Event()

    class BlockingBuilder:
        def prepare(self, **_candidate): pass
        def build_and_publish(self):
            started.set()
            assert release.wait(2)
            return "INSERT"

    metrics = OperationalMetrics()
    builder = BlockingBuilder()
    scheduler = OfflineStateBuildScheduler(builder.build_and_publish, metrics=metrics)
    background = V4StateBuildWorker(builder, scheduler, metrics=metrics)
    background.start()
    cohorts = {forecast.horizon: (forecast.cohort_id, forecast.cohort_hash)
               for forecast in forecasts}
    background.submit(symbol="COIN", state_as_of=NOW, cohorts=cohorts,
                      new_outcome=True)
    assert started.wait(1)

    outbox = EvidenceOutbox(metrics=metrics)
    worker = EvidenceLedgerWorker(
        outbox, evidence_store=_RawStore(), connection=_WorkerConnection(),
        state_build_submit=background.submit,
    )
    worker._writer = Writer()
    observation = MidpointObservation(NOW.timestamp(), 100.0)
    for sequence in range(1, 513):
        item = QuoteEvidenceWork(
            sequence, f"cycle-{sequence}", None, observation, NOW,
            (), (), (), None, None,
        )
        assert outbox.put_nowait(item) is True
        worker.process(outbox.get())
        outbox.task_done()

    assert dict(metrics.snapshot().counters).get("EVIDENCE_OUTBOX_FULL", 0) == 0
    release.set()
    background.stop()


def test_metrics_have_percentiles_and_do_not_change_forecast():
    metrics = OperationalMetrics(retained_samples=10)
    for value in (5, 1, 3, 2, 4):
        metrics.observe("latency", value)
    distribution = dict(metrics.snapshot().distributions)["latency"]
    assert (distribution.count, distribution.minimum, distribution.p50,
            distribution.p95, distribution.p99, distribution.maximum) == (5, 1, 3, 5, 5, 5)


@pytest.mark.parametrize("status", ("MATURE", "PROVISIONAL", "UNAVAILABLE"))
def test_v3_horizon_status_is_recorded_exactly(monkeypatch, status):
    import quant.v9_v4d_integration as integration
    from quant.v9_v3_synthesis import synthesize_v3

    v1, v2 = _inputs(1)
    original = synthesize_v3(v1, v2)
    replaced = replace(original, horizon_results=tuple(
        replace(result, status=status) for result in original.horizon_results))
    monkeypatch.setattr(integration, "synthesize_v3", lambda one, two: replaced)
    metrics = OperationalMetrics()
    V4DCoordinator(
        capture_v1=lambda: v1, capture_v2=lambda captured: v2,
        forecast_writer=Writer(), compact_state_lookup=lambda **kwargs: (None, "UNAVAILABLE"),
        state_cohort_id=lambda one, two: "cohort", metrics=metrics,
    ).run_cycle()
    counters = dict(metrics.snapshot().counters)
    assert counters[f"horizon.30S.{status}"] == 1
    assert not any(key.startswith("horizon.") and key.endswith(".AVAILABLE")
                   for key in counters)


def test_unexpected_v3_horizon_status_is_rejected(monkeypatch):
    import quant.v9_v4d_integration as integration
    from quant.v9_v3_synthesis import synthesize_v3

    v1, v2 = _inputs(1)
    original = synthesize_v3(v1, v2)
    unexpected = replace(original, horizon_results=(
        replace(original.horizon_results[0], status="AVAILABLE"),
        *original.horizon_results[1:],
    ))
    monkeypatch.setattr(integration, "synthesize_v3", lambda one, two: unexpected)
    metrics = OperationalMetrics()
    coordinator = V4DCoordinator(
        capture_v1=lambda: v1, capture_v2=lambda captured: v2,
        forecast_writer=Writer(), compact_state_lookup=lambda **kwargs: (None, "UNAVAILABLE"),
        state_cohort_id=lambda one, two: "cohort", metrics=metrics,
    )
    with pytest.raises(RuntimeError, match="UNEXPECTED_V3_HORIZON_STATUS"):
        coordinator.run_cycle()
    assert not any(key.startswith("horizon.") for key, _ in metrics.snapshot().counters)
