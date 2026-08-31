from datetime import datetime, timedelta, timezone
from dataclasses import FrozenInstanceError, replace
from types import SimpleNamespace
import ast
import inspect
import threading
import time

import pytest

from quant.v9_sim1_contract import HORIZONS
from quant.v9_sim3_capture import (
    ACCEPTED, CAPTURE_UNAVAILABLE, DROPPED_QUEUE_FULL,
    FinalizedV4PersistenceResult, Sim3Telemetry,
    SimulationCaptureAdapter, SimulationCaptureWorkItem,
)
from quant.v9_v4d_integration import V4DCycleOutput
from quant.live_market import LiveMarketState
from quant.web import (
    SIMULATOR_DATABASE_URL_ENV,
    _configured_simulator_connection_factory,
    _start_sim3,
    create_app,
)


NOW = datetime(2026, 1, 1, tzinfo=timezone.utc)


def _cycle():
    v2 = SimpleNamespace(state_id="v2", state_hash="a" * 64)
    v3_rows = tuple(SimpleNamespace(
        horizon=horizon, horizon_seconds=seconds, status="MATURE",
    ) for horizon, seconds in zip(HORIZONS, (30, 60, 300, 900, 1800, 3600)))
    v3 = SimpleNamespace(horizon_results=v3_rows, model_version="v3")
    finals = tuple(SimpleNamespace(horizon=horizon, final_bps=1.0)
                   for horizon in HORIZONS)
    output = V4DCycleOutput("cycle", "COIN", NOW, SimpleNamespace(), v2, v3,
                            finals, (), (), "UNAVAILABLE")
    forecasts = tuple(SimpleNamespace(
        horizon=horizon, cycle_id="cycle", cutoff_at=NOW,
        v2_state_id="v2", v2_state_hash="a" * 64,
        v3_contract_version="v3-contract", v3_model_version="v3",
        forecast_record_id=f"v9v4f:{index:064x}",
        forecast_record_hash=f"{index:064x}",
    ) for index, horizon in enumerate(HORIZONS, 1))
    results = tuple(FinalizedV4PersistenceResult(horizon, "INSERTED", forecast)
                    for horizon, forecast in zip(HORIZONS, forecasts))
    return output, results


def test_whole_cycle_handoff_is_frozen_slotted_and_preserves_identity():
    output, results = _cycle()
    item = SimulationCaptureWorkItem(output, results, NOW)
    assert item.cycle_output is output
    assert item.persistence_results is results
    assert not hasattr(item, "__dict__")
    with pytest.raises(FrozenInstanceError):
        item.eligible_at = NOW


def test_stage_a_carries_exact_handler_output_without_simulator_work():
    output, _ = _cycle()

    class Outbox:
        work = None
        def put_nowait(self, work):
            self.work = work
            return True

    outbox = Outbox()
    state = LiveMarketState(clock=lambda: NOW.timestamp(), evidence_outbox=outbox,
                            v9_cycle_handler=lambda *_args: output)
    assert state.accept_quote(bid=99, ask=101, event_epoch=NOW.timestamp())
    assert outbox.work.v4d_output is output


def test_one_clock_read_and_exact_six_persisted_identities():
    output, results = _cycle()
    calls = []
    intents = []

    class Store:
        def insert(self, intent):
            intents.append(intent)
            return "INSERTED"

    adapter = SimulationCaptureAdapter(Store(), lambda: calls.append(1) or NOW)
    adapter.start()
    assert adapter.submit(output, results) == ACCEPTED
    deadline = time.monotonic() + 1
    while len(intents) != 6 and time.monotonic() < deadline:
        time.sleep(.001)
    adapter.stop()
    assert calls == [1]
    assert tuple(intent.horizon for intent in intents) == HORIZONS
    assert tuple(intent.source_forecast_record_id for intent in intents) == tuple(
        result.forecast.forecast_record_id for result in results)
    assert all(intent.decision == "LONG" and intent.status == "ACTIONABLE"
               for intent in intents)


def test_per_horizon_store_failure_is_isolated_and_telemetry_is_bounded():
    output, results = _cycle()
    calls = []

    class Store:
        def insert(self, intent):
            calls.append(intent.horizon)
            if intent.horizon == "1M":
                raise RuntimeError("isolated")
            return "IDEMPOTENT"

    telemetry = Sim3Telemetry()
    adapter = SimulationCaptureAdapter(Store(), lambda: NOW, telemetry=telemetry)
    adapter.start()
    for _ in range(300):
        telemetry.observe_capture(0.1)
    assert adapter.submit(output, results) == ACCEPTED
    deadline = time.monotonic() + 1
    while len(calls) != 6 and time.monotonic() < deadline:
        time.sleep(.001)
    adapter.stop()
    snapshot = telemetry.snapshot()
    assert tuple(calls) == HORIZONS
    assert snapshot.sim3_horizon_failures_total == 1
    assert len(snapshot.sim3_capture_latency_ms) == 256


def test_stage_b_hook_is_after_complete_persistence_loop():
    from quant.evidence_outbox import EvidenceLedgerWorker
    source = inspect.getsource(EvidenceLedgerWorker.process)
    persist = source.index("for forecast in item.v4:")
    completion = source.index("len(finalized) == 6")
    submit = source.index("self._simulation_submit(")
    assert persist < completion < submit


def test_eligibility_clock_is_immediate_after_six_persistence_results(monkeypatch):
    from quant.evidence_outbox import (
        EvidenceLedgerWorker, EvidenceOutbox, QuoteEvidenceWork,
        TerminalDeliveryError,
    )
    from quant.history import MidpointObservation

    monkeypatch.setattr(EvidenceLedgerWorker, "_load_pending", lambda _self: [])
    output, results = _cycle()
    events = []
    forecasts = tuple(SimpleNamespace(
        **vars(result.forecast),
        target_endpoint=NOW + timedelta(seconds=seconds),
        persistence_proof_eligible=True,
        symbol="COIN",
        cohort_id="cohort",
        cohort_hash="a" * 64,
    ) for result, seconds in zip(results, (30, 60, 300, 900, 1800, 3600)))

    class Connection:
        def close(self): pass

    class RawStore:
        def record_cycle_and_resolve(self, *_args, **_kwargs):
            events.append("raw")

    class Writer:
        last_write_status = None
        def persist_forecast(self, forecast, _persisted_at):
            events.append("persist:" + forecast.horizon)
            self.last_write_status = "INSERT"
            return forecast

    class Refresher:
        def refresh(self, **_kwargs):
            events.append("cache")

    adapter = SimulationCaptureAdapter(
        SimpleNamespace(insert=lambda _intent: "INSERTED"),
        lambda: events.append("eligible_at") or NOW,
    )
    worker = EvidenceLedgerWorker(
        EvidenceOutbox(), evidence_store=RawStore(), connection=Connection(),
        state_build_submit=lambda **_kwargs: events.append("state_build"),
        cache_refresher=Refresher(), simulation_submit=adapter.submit,
    )
    worker._writer = Writer()
    observation = MidpointObservation(NOW.timestamp(), 100.0)
    worker.process(QuoteEvidenceWork(
        1, "cycle", None, observation, NOW, (), (), forecasts,
        "cohort", output,
    ))

    assert events == [
        "raw", *("persist:" + horizon for horizon in HORIZONS),
        "eligible_at", "state_build", "cache",
    ]

    events.clear()
    invalid_worker = EvidenceLedgerWorker(
        EvidenceOutbox(), evidence_store=RawStore(), connection=Connection(),
        state_build_submit=lambda **_kwargs: events.append("state_build"),
        cache_refresher=Refresher(),
        simulation_submit=lambda *_args: events.append("invalid_submit"),
    )
    invalid_worker._writer = Writer()
    with pytest.raises(TerminalDeliveryError, match="MALFORMED_EVIDENCE_ENVELOPE"):
        invalid_worker.process(QuoteEvidenceWork(
            1, "cycle", None, observation, NOW, (), (), forecasts,
            "cohort", object(),
        ))
    assert events == []


def test_capacity_64_atomic_incoming_drop_and_fifo_order():
    output, results = _cycle()
    release = threading.Event()
    entered = threading.Event()
    seen = []

    class Store:
        def insert(self, intent):
            if not entered.is_set():
                entered.set()
                release.wait(2)
            seen.append(intent.source_cycle_id)
            return "INSERTED"

    adapter = SimulationCaptureAdapter(Store(), lambda: NOW)
    adapter.start()
    assert adapter.submit(output, results) == ACCEPTED
    assert entered.wait(1)
    queued = []
    for index in range(64):
        cycle_id = f"cycle-{index}"
        cycle = replace(output, cycle_id=cycle_id)
        cycle_results = tuple(FinalizedV4PersistenceResult(
            row.horizon, row.status,
            SimpleNamespace(**dict(vars(row.forecast), cycle_id=cycle_id)))
            for row in results)
        queued.append(adapter.submit(cycle, cycle_results))
    assert queued == [ACCEPTED] * 64
    assert adapter.submit(output, results) == DROPPED_QUEUE_FULL
    assert adapter._queue.qsize() == 64
    release.set()
    adapter.stop()
    assert seen[0] == "cycle"
    assert seen[6::6] == [f"cycle-{index}" for index in range(64)]


def test_malformed_cycle_fails_closed_before_store_access():
    output, results = _cycle()
    calls = []

    class Store:
        def insert(self, intent):
            calls.append(intent)
            return "INSERTED"

    adapter = SimulationCaptureAdapter(Store(), lambda: NOW)
    adapter.start()
    malformed = (results[1], results[0], *results[2:])
    assert adapter.submit(output, malformed) == ACCEPTED
    deadline = time.monotonic() + 1
    while adapter.telemetry.snapshot().sim3_cycles_processed_total < 1:
        assert time.monotonic() < deadline
        time.sleep(.001)
    adapter.stop()
    assert calls == []
    assert adapter.telemetry.snapshot().sim3_worker_failures_total == 1


def test_start_and_stop_are_permanently_idempotent():
    adapter = SimulationCaptureAdapter(SimpleNamespace(insert=lambda _: "INSERTED"),
                                       lambda: NOW)
    adapter.start()
    original = adapter._thread
    adapter.start()
    assert adapter._thread is original
    adapter.stop()
    adapter.stop()
    adapter.start()
    assert adapter._thread is original


@pytest.mark.filterwarnings("ignore::pytest.PytestUnhandledThreadExceptionWarning")
def test_unexpected_worker_death_is_failed_and_never_restarted():
    class CrashAdapter(SimulationCaptureAdapter):
        def _process(self, item):
            raise KeyboardInterrupt()

    output, results = _cycle()
    adapter = CrashAdapter(SimpleNamespace(insert=lambda _: "INSERTED"), lambda: NOW)
    adapter.start()
    original = adapter._thread
    assert adapter.submit(output, results) == ACCEPTED
    original.join(1)
    assert not original.is_alive()
    assert adapter.telemetry.snapshot().sim3_submit_status == "FAILED"
    assert adapter.submit(output, results) == CAPTURE_UNAVAILABLE
    adapter.start()
    assert adapter._thread is original


def test_submit_and_stop_are_atomic_and_shutdown_is_bounded():
    output, results = _cycle()
    clock_entered, release_clock = threading.Event(), threading.Event()

    def clock():
        clock_entered.set()
        release_clock.wait(2)
        return NOW

    adapter = SimulationCaptureAdapter(
        SimpleNamespace(insert=lambda _: "INSERTED"), clock)
    adapter.start()
    submit_result = []
    submitter = threading.Thread(
        target=lambda: submit_result.append(adapter.submit(output, results)))
    submitter.start()
    assert clock_entered.wait(1)
    stopper = threading.Thread(target=adapter.stop)
    started = time.monotonic()
    stopper.start()
    stopper.join(1.0)
    assert not stopper.is_alive()
    assert time.monotonic() - started < 1.0
    release_clock.set()
    submitter.join(1)
    assert submit_result == [CAPTURE_UNAVAILABLE]
    assert adapter.submit(output, results) == CAPTURE_UNAVAILABLE


def test_missing_configuration_startup_failure_and_request_path_isolation():
    assert _start_sim3(None, lambda: NOW) is None
    assert _start_sim3("not-callable", lambda: NOW) is None
    source = inspect.getsource(create_app)
    assert "SimulationCapture" not in source
    assert "SimulationIntentStore" not in source


def test_default_entrypoint_uses_only_dedicated_simulator_configuration():
    connections = []

    def connect(database_url):
        connections.append(database_url)
        return object()

    assert _configured_simulator_connection_factory(
        {"DATABASE_URL": "production-runtime"}, connect) is None
    assert connections == []

    factory = _configured_simulator_connection_factory(
        {SIMULATOR_DATABASE_URL_ENV: "sim-runtime"}, connect)
    assert factory is not None
    assert factory() is not None
    assert connections == ["sim-runtime"]

    import quant.web as web
    startup = ast.parse(inspect.getsource(web.main))
    configured_calls = [
        node for node in ast.walk(startup)
        if isinstance(node, ast.Call)
        and isinstance(node.func, ast.Name)
        and node.func.id == "_configured_simulator_connection_factory"
    ]
    assert len(configured_calls) == 1
    assert tuple(ast.unparse(arg) for arg in configured_calls[0].args) == (
        "os.environ", "runtime_connect")


def test_positive_sim3_startup_lifecycle():
    adapter = _start_sim3(lambda: object(), lambda: NOW)
    assert adapter is not None
    assert adapter.telemetry.snapshot().sim3_submit_status == "READY"
    adapter.stop()
    assert adapter.telemetry.snapshot().sim3_submit_status == "STOPPED"


def test_sim3_integration_boundary_is_static_and_history_independent():
    import quant.evidence_outbox as evidence_outbox
    import quant.live_market as live_market
    import quant.web as web

    live_tree = ast.parse(inspect.getsource(live_market))
    sim_imports = [node for node in ast.walk(live_tree)
                   if isinstance(node, ast.ImportFrom) and
                   node.module and "sim" in node.module]
    assert sim_imports == []
    handoffs = [
        keyword for node in ast.walk(live_tree) if isinstance(node, ast.Call)
        for keyword in node.keywords if keyword.arg == "v4d_output"
    ]
    assert len(handoffs) == 1
    assert isinstance(handoffs[0].value, ast.Name)
    assert handoffs[0].value.id == "output"

    outbox_tree = ast.parse(inspect.getsource(evidence_outbox))
    imports = [node for node in ast.walk(outbox_tree)
               if isinstance(node, ast.ImportFrom) and
               node.module == "v9_sim3_capture"]
    assert len(imports) == 1
    assert [alias.name for alias in imports[0].names] == [
        "FinalizedV4PersistenceResult",
    ]
    submit_calls = [node for node in ast.walk(outbox_tree)
                    if isinstance(node, ast.Call) and
                    isinstance(node.func, ast.Attribute) and
                    node.func.attr == "_simulation_submit"]
    assert len(submit_calls) == 1

    assert "SimulationCapture" not in inspect.getsource(web.create_app)
    startup = inspect.getsource(web._start_sim3)
    assert "SimulationIntentStore" in startup
    assert "SimulationCaptureAdapter" in startup
