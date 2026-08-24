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
    _canonical, build_forecast, build_outcome, canonical_target_identity,
)
from quant.v9_v4c_predictive import (
    PROBABILITY_STATE_VERSION, CompactHorizonState, build_v4c_state,
)
from quant.v9_v4d_integration import (
    ImmutableStateCache, OfflineStateBuildScheduler, OperationalMetrics, V4DCoordinator,
    resolve_outcome,
)
from quant.evidence_outbox import (
    EvidenceLedgerWorker, EvidenceOutbox, QuoteEvidenceWork, TerminalDeliveryError,
    PostgresV4BStateBuilder, PostgresV4CStateBuilder, PostgresV4StateBuilder,
    V4StateBuildWorker, V4StateCacheRefresher,
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
    compact = _empty_state()
    compact_cache, accuracy_cache = ImmutableStateCache(), ImmutableStateCache()

    class Store:
        def __init__(self, value): self.value = value; self.calls = 0
        def latest_json(self, **_kwargs):
            self.calls += 1
            return (self.value, "AVAILABLE") if self.value is not None else (None, "UNAVAILABLE")

    compact_store, accuracy_store = Store(compact), Store(None)
    V4StateCacheRefresher(
        compact_store=compact_store, accuracy_store=accuracy_store,
        compact_cache=compact_cache, accuracy_cache=accuracy_cache,
    ).refresh(symbol="COIN", cohort_id="cohort", cutoff=NOW)
    assert compact_store.calls == accuracy_store.calls == 1
    assert compact_cache.latest(symbol="COIN", cohort_id="cohort",
                                requested_cutoff=NOW) == (compact, "AVAILABLE")
    assert compact_cache.latest(symbol="COIN", cohort_id="other",
                                requested_cutoff=NOW) == (None, "UNAVAILABLE")


class _WorkerConnection:
    def cursor(self):
        return SimpleNamespace(execute=lambda *_args: None, fetchall=lambda: (),
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
            assert "NOT EXISTS" in sql and "interval '1 hour'" in sql
        def fetchall(self): return ((forecast.forecast_record_hash, payload),)
        def close(self): pass
    class Connection(_WorkerConnection):
        def cursor(self): return Cursor()

    worker = EvidenceLedgerWorker(EvidenceOutbox(), evidence_store=_RawStore(),
                                  connection=Connection())
    assert worker._pending == [forecast]


class _RawStore:
    def __init__(self): self.calls = []
    def record_cycle_and_resolve(self, *_args, **kwargs): self.calls.append(kwargs)


def _work(sequence, previous, current, received_at):
    return QuoteEvidenceWork(sequence, f"COIN:{current.event_epoch:.9f}",
        previous, current, received_at, (), (), ())


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


def test_offline_builder_requires_new_outcome_and_sixty_seconds():
    clock = [0.0]
    calls = []
    scheduler = OfflineStateBuildScheduler(lambda: calls.append(1) or "INSERT",
                                            monotonic_clock=lambda: clock[0])
    assert scheduler.run_if_due() == "SKIPPED_NO_NEW_OUTCOME"
    scheduler.note_new_outcome()
    assert scheduler.run_if_due() == "INSERT"
    scheduler.note_new_outcome(); clock[0] = 59
    assert scheduler.run_if_due() == "SKIPPED_RATE_LIMIT"
    clock[0] = 60
    assert scheduler.run_if_due() == "INSERT" and len(calls) == 2


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

    class Cursor:
        def execute(self, sql, params):
            assert "atom_v9_v4_forecasts" in sql and "atom_v9_v4_outcomes" in sql
            assert "o.created_at<=%s" in sql
            self.params = params
        def fetchall(self):
            return ((forecast.forecast_record_hash,
                     json.dumps(_canonical(asdict(forecast))),
                     outcome.outcome_record_hash,
                     json.dumps(_canonical(asdict(outcome)))),)
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
    cohorts = {h: ("cohort", "b" * 64) for h in HORIZONS}
    as_of = NOW + timedelta(minutes=1)
    builder.prepare(symbol="COIN", state_as_of=as_of, cohorts=cohorts)

    assert builder.build_and_publish() == "INSERT"
    assert captured == {"symbol": "COIN", "state_as_of": as_of,
                        "cohorts": cohorts, "evidence": ((forecast, outcome),)}
    assert store.calls == [(state, NOW + timedelta(minutes=2))]


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
        def fetchall(self):
            return ((forecast.forecast_record_hash, json.dumps(_canonical(asdict(forecast))),
                     outcome.outcome_record_hash, json.dumps(_canonical(asdict(outcome)))),)
        def close(self): pass
    class Connection(_WorkerConnection):
        def cursor(self): return Cursor()

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
    builder = PostgresV4CStateBuilder(Connection(), state_store=store,
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
    assert state.horizons[0].range_status == "UNAVAILABLE"
    assert all(item.range_status == "UNAVAILABLE" for item in state.horizons)
    assert store.calls[0][1] == NOW + timedelta(minutes=2)


def test_combined_builder_keeps_accuracy_and_compact_in_one_generation():
    class Builder:
        def __init__(self, result):
            self.result = result; self.prepared = []; self.calls = 0; self.connections = []
        def prepare(self, **candidate): self.prepared.append(candidate)
        def rebind_connection(self, connection): self.connections.append(connection)
        def build_and_publish(self): self.calls += 1; return self.result
    accuracy, compact = Builder("IDEMPOTENT"), Builder("INSERT")
    builder = PostgresV4StateBuilder(accuracy, compact)
    candidate = {"symbol": "COIN", "state_as_of": NOW,
                 "cohorts": {h: ("c", "h") for h in HORIZONS}}
    builder.prepare(**candidate)
    replacement = object()
    builder.rebind_connection(replacement)
    assert builder.build_and_publish() == "INSERT"
    assert accuracy.prepared == compact.prepared == [candidate]
    assert accuracy.calls == compact.calls == 1
    assert accuracy.connections == compact.connections == [replacement]


def test_compact_failure_does_not_suppress_accuracy_publication():
    class Accuracy:
        calls = 0
        def build_and_publish(self):
            self.calls += 1
            return "INSERT"
    class Compact:
        def build_and_publish(self): raise RuntimeError("compact build failed")
    accuracy = Accuracy()
    with pytest.raises(RuntimeError, match="compact build failed"):
        PostgresV4StateBuilder(accuracy, Compact()).build_and_publish()
    assert accuracy.calls == 1


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

    submitted = []
    worker = EvidenceLedgerWorker(
        EvidenceOutbox(), evidence_store=_RawStore(), connection=_WorkerConnection(),
        state_build_submit=lambda **candidate: submitted.append(candidate),
    )
    worker._pending = [due]
    worker._writer = Writer()
    item = QuoteEvidenceWork(
        1, "cycle", previous, current, due.target_endpoint,
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
        1, "cycle", previous if previous_present else None, current,
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
        1, "cycle", previous, current, due.target_endpoint,
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
            (), (), forecasts, "cohort", calculated,
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