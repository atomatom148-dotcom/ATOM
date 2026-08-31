from __future__ import annotations

from contextlib import nullcontext
from datetime import date
import json
from pathlib import Path
from types import SimpleNamespace

import pytest

from quant import historical_persistence_gate_h2d6 as gate


def _control():
    snapshot = {
        "historical_session": gate.FROZEN_SESSION,
        "replay_run_id": gate.FROZEN_RUN_ID,
        "git_commit": "a" * 40,
        "dataset_digest": "b" * 64,
        "configuration_digest": "c" * 64,
        "session_digest": "d" * 64,
        "artifact_sha256": "e" * 64,
        "manifest_content_sha256": "f" * 64,
        "forecast_ordered_content_sha256": "1" * 64,
        "outcome_ordered_content_sha256": "2" * 64,
        "frame_count": gate.FROZEN_FRAME_COUNT,
        "forecast_count": gate.FROZEN_FORECAST_COUNT,
        "forecast_available_count": 671_578,
        "forecast_unavailable_count": 72_326,
        "outcome_count": gate.FROZEN_OUTCOME_COUNT,
        "outcome_available_count": 58_000,
        "outcome_unavailable_count": 3_992,
    }
    score = {
        "metric_sha256": gate.FROZEN_METRIC_SHA256,
        "metrics": [{} for _ in range(72)],
    }
    return snapshot, score, gate.FROZEN_D5_CONTROL_SHA256


def test_gate_is_exactly_one_frozen_idempotent_retry():
    assert gate.FROZEN_SESSION == "2026-06-23"
    assert gate.FROZEN_RUN_ID == "h2d-2026-06-23"
    assert gate.FROZEN_FRAME_COUNT == 10_332
    assert gate.FROZEN_FORECAST_COUNT == 743_904
    assert gate.FROZEN_OUTCOME_COUNT == 61_992


def test_gate_passes_only_with_zero_writes_and_unchanged_control():
    control = _control()
    receipt = gate.execute_persistence_gate(
        control_reader=lambda _timeout: control,
        forecast_retry=lambda snapshot, _timeout: {
            "forecast_writes": 0,
            "artifact_sha256": snapshot["artifact_sha256"],
            "forecast_ordered_content_sha256": (
                snapshot["forecast_ordered_content_sha256"]
            ),
            "elapsed_seconds": 1.25,
        },
        outcome_retry=lambda _snapshot, _timeout: 0,
    )
    assert receipt["status"] == "PASSED"
    assert receipt["forecast_writes"] == 0
    assert receipt["outcome_writes"] == 0
    assert receipt["pre_post_unchanged"] is True
    assert receipt["new_date_admission"] is False
    assert receipt["continuous_replay_enabled"] is False


@pytest.mark.parametrize("stage", ["forecast", "outcome"])
def test_gate_fails_closed_if_an_exact_retry_writes(stage):
    control = _control()
    forecast_writes = 1 if stage == "forecast" else 0
    outcome_writes = 1 if stage == "outcome" else 0
    with pytest.raises(gate.PersistenceGateFailure, match="WROTE_EVIDENCE"):
        gate.execute_persistence_gate(
            control_reader=lambda _timeout: control,
            forecast_retry=lambda snapshot, _timeout: {
                "forecast_writes": forecast_writes,
                "artifact_sha256": snapshot["artifact_sha256"],
                "forecast_ordered_content_sha256": (
                    snapshot["forecast_ordered_content_sha256"]
                ),
                "elapsed_seconds": 1.0,
            },
            outcome_retry=lambda _snapshot, _timeout: outcome_writes,
        )


def test_gate_fails_on_control_drift():
    first = _control()
    changed_snapshot = dict(first[0], artifact_sha256="9" * 64)
    controls = iter((first, (changed_snapshot, first[1], first[2])))
    with pytest.raises(gate.PersistenceGateFailure):
        gate.execute_persistence_gate(
            control_reader=lambda _timeout: next(controls),
            forecast_retry=lambda snapshot, _timeout: {
                "forecast_writes": 0,
                "artifact_sha256": snapshot["artifact_sha256"],
                "forecast_ordered_content_sha256": (
                    snapshot["forecast_ordered_content_sha256"]
                ),
                "elapsed_seconds": 1.0,
            },
            outcome_retry=lambda _snapshot, _timeout: 0,
        )


@pytest.mark.parametrize("timeout", [0, -1, float("nan"), float("inf")])
def test_gate_rejects_unbounded_timeout(timeout):
    with pytest.raises(ValueError, match="positive and finite"):
        gate.execute_persistence_gate(timeout_seconds=timeout)


def test_gate_applies_one_deadline_to_both_retries(monkeypatch):
    now = [0.0]

    def monotonic():
        value = now[0]
        now[0] += 1.0
        return value

    observed = []
    monkeypatch.setattr(gate.time, "monotonic", monotonic)
    control = _control()
    receipt = gate.execute_persistence_gate(
        timeout_seconds=30,
        control_reader=lambda timeout: observed.append(("control", timeout)) or control,
        forecast_retry=lambda snapshot, timeout: (
            observed.append(("forecast", timeout)) or {
                "forecast_writes": 0,
                "artifact_sha256": snapshot["artifact_sha256"],
                "forecast_ordered_content_sha256": (
                    snapshot["forecast_ordered_content_sha256"]
                ),
                "elapsed_seconds": 1.0,
            }
        ),
        outcome_retry=lambda _snapshot, timeout: (
            observed.append(("outcome", timeout)) or 0
        ),
    )
    assert receipt["status"] == "PASSED"
    assert [stage for stage, _timeout in observed] == [
        "control", "forecast", "outcome", "control",
    ]
    assert all(0 < timeout <= 30 for _stage, timeout in observed)
    assert observed[-1][1] < observed[0][1]


def test_gate_stops_when_forecast_retry_exhausts_deadline(monkeypatch):
    now = [0.0]
    monkeypatch.setattr(gate.time, "monotonic", lambda: now[0])
    outcome_called = []

    def forecast(snapshot, _timeout):
        now[0] = 11.0
        return {
            "forecast_writes": 0,
            "artifact_sha256": snapshot["artifact_sha256"],
            "forecast_ordered_content_sha256": (
                snapshot["forecast_ordered_content_sha256"]
            ),
            "elapsed_seconds": 11.0,
        }

    with pytest.raises(gate.PersistenceGateFailure, match="H2D6_TIMEOUT"):
        gate.execute_persistence_gate(
            timeout_seconds=10,
            control_reader=lambda _timeout: _control(),
            forecast_retry=forecast,
            outcome_retry=lambda *_args: outcome_called.append(True) or 0,
        )
    assert outcome_called == []


def test_forecast_retry_reuses_stored_manifest_not_fresh_timings(monkeypatch):
    import quant.historical_evidence as evidence_module
    import quant.historical_evidence_verifier as verifier_module
    import quant.historical_replay as replay_module
    import quant.historical_replay_h1 as h1_module

    snapshot = _control()[0]
    coverage = [SimpleNamespace(
        available=snapshot["forecast_available_count"],
        missing=snapshot["forecast_unavailable_count"],
    )] + [SimpleNamespace(available=0, missing=0) for _ in range(71)]
    report = SimpleNamespace(
        historical_session=gate.FROZEN_SESSION,
        replay_run_id=gate.FROZEN_RUN_ID,
        dataset_digest=snapshot["dataset_digest"],
        configuration_digest=snapshot["configuration_digest"],
        session_digest=snapshot["session_digest"],
        frame_count=gate.FROZEN_FRAME_COUNT,
        execution_stage="REPLAY_COMPLETE",
        data_status="CERTIFIED",
        persistence_writes=0,
        data_reason_codes=(),
        family_coverage=coverage,
    )

    class Manifest:
        def __init__(self, *, timings, created_at, content_sha256):
            self._payload = {
                "replay_run_id": gate.FROZEN_RUN_ID,
                "artifact_sha256": snapshot["artifact_sha256"],
                "stage_timings": timings,
                "family_timings": {"q1": timings["total"]},
                "created_at": created_at,
            }
            self.content_sha256 = content_sha256

        def payload(self):
            return dict(self._payload)

    fresh = Manifest(
        timings={"total": 999.0}, created_at="fresh",
        content_sha256="different-because-timings-change",
    )
    stored = Manifest(
        timings={"total": 1.0}, created_at="stored",
        content_sha256=snapshot["manifest_content_sha256"],
    )

    class Spool:
        def __enter__(self):
            return self

        def __exit__(self, *_args):
            return False

    class Cursor:
        def execute(self, sql, params):
            assert "statement_timeout" in sql
            assert params[0].endswith("ms")

        def close(self):
            pass

    connection = SimpleNamespace(cursor=lambda: Cursor())
    observed = {}

    class Writer:
        def __init__(self, supplied_connection):
            assert supplied_connection is connection

        def persist(self, manifest, forecasts, *, require_existing):
            observed.update(
                manifest=manifest, forecasts=forecasts,
                require_existing=require_existing,
            )
            return 0

    monkeypatch.setattr(evidence_module, "HistoricalEvidenceSpool", Spool)
    monkeypatch.setattr(evidence_module, "HistoricalEvidenceWriter", Writer)
    monkeypatch.setattr(evidence_module, "build_manifest", lambda *_args, **_kwargs: fresh)
    monkeypatch.setattr(
        evidence_module, "connect_writer_from_environment",
        lambda: nullcontext(connection),
    )
    monkeypatch.setattr(
        verifier_module, "read_manifest_from_score_environment",
        lambda *_args, **_kwargs: stored,
    )
    monkeypatch.setattr(
        replay_module.AlpacaHistoricalSipReader, "from_environment",
        classmethod(lambda _cls: object()),
    )
    monkeypatch.setattr(h1_module, "_session", lambda _day: ("open", "close"))
    monkeypatch.setattr(h1_module, "run_h1_session", lambda **_kwargs: report)
    monkeypatch.setattr(
        gate.h2d3, "_fresh_forecast_hashes",
        lambda _evidence: (
            snapshot["artifact_sha256"],
            snapshot["forecast_ordered_content_sha256"],
        ),
    )

    receipt = gate._replay_and_retry_forecasts(snapshot, 10)
    assert receipt["forecast_writes"] == 0
    assert observed["manifest"] is stored
    assert isinstance(observed["forecasts"], Spool)
    assert observed["require_existing"] is True


def test_control_and_outcome_helpers_forward_the_frozen_identity(monkeypatch):
    control = _control()
    control_call = []
    monkeypatch.setattr(
        gate.h2d5, "_capture_control",
        lambda *args: control_call.append(args) or control,
    )
    assert gate._read_control(9) == control
    assert control_call == [(gate.FROZEN_SESSION, gate.FROZEN_RUN_ID, 9)]

    import quant.historical_outcomes as outcomes
    outcome_call = {}
    monkeypatch.setattr(
        outcomes, "resolve_outcomes_from_environment",
        lambda run_id, **kwargs: outcome_call.update(
            run_id=run_id, **kwargs,
        ) or 0,
    )
    assert gate._retry_outcomes(control[0], 8) == 0
    assert outcome_call["run_id"] == gate.FROZEN_RUN_ID
    assert outcome_call["require_existing"] is True
    assert outcome_call["timeout_seconds"] == 8


def test_writer_connection_requires_the_dedicated_role(monkeypatch):
    import quant.historical_evidence as evidence

    class Cursor:
        def execute(self, sql):
            assert sql == "SELECT current_user"

        def fetchone(self):
            return ("wrong_role",)

        def close(self):
            pass

    connection = SimpleNamespace(
        cursor=lambda: Cursor(), close=lambda: None, commit=lambda: None,
    )
    monkeypatch.setenv("HISTORICAL_EVIDENCE_DATABASE_URL", "postgresql://test")
    monkeypatch.setitem(
        __import__("sys").modules, "psycopg",
        SimpleNamespace(connect=lambda _url: connection),
    )
    with pytest.raises(RuntimeError, match="H2A_DATABASE_ROLE_MISMATCH"):
        evidence.connect_writer_from_environment()


def test_outcome_environment_helper_uses_only_resolver_role(monkeypatch):
    import quant.historical_outcomes as outcomes

    timeout_calls = []

    class Cursor:
        def execute(self, sql, params):
            if "statement_timeout" in sql:
                timeout_calls.append(params[0])
                return
            assert "historical_session" in sql
            assert params == (gate.FROZEN_RUN_ID,)

        def fetchone(self):
            return (date.fromisoformat(gate.FROZEN_SESSION),)

        def close(self):
            pass

    connection = SimpleNamespace(cursor=lambda: Cursor())
    observed = {}

    def connect(environment, role):
        observed.update(environment=environment, role=role)
        return nullcontext(connection)

    reader = SimpleNamespace(
        last_retrieval_proof="proof",
        read_session=lambda **_kwargs: ("quotes",),
    )
    monkeypatch.setattr(outcomes, "_connect", connect)
    monkeypatch.setattr(
        outcomes.AlpacaHistoricalSipReader, "from_environment",
        classmethod(lambda _cls: reader),
    )
    monkeypatch.setattr(
        outcomes.HistoricalOutcomeResolver, "resolve",
        lambda _self, _run_id, _quotes, **kwargs:
            0 if kwargs["require_existing"] is True else 1,
    )
    assert outcomes.resolve_outcomes_from_environment(
        gate.FROZEN_RUN_ID,
        expected_dataset_digest="b" * 64,
        expected_configuration_digest="c" * 64,
        expected_frame_count=gate.FROZEN_FRAME_COUNT,
        require_existing=True,
        timeout_seconds=10,
    ) == 0
    assert observed == {
        "environment": "HISTORICAL_OUTCOME_DATABASE_URL",
        "role": "atom_historical_outcome_resolver",
    }
    assert len(timeout_calls) == 2
    assert all(value.endswith("ms") for value in timeout_calls)


def test_freeze_forbids_new_schema_v9_and_continuous_replay():
    law = Path("docs/h2-d6-persistence-gate-freeze.md").read_text()
    phases = Path("PHASES.md").read_text()
    source = Path("quant/historical_persistence_gate_h2d6.py").read_text()
    assert "adds no migration" in law
    assert "changes no V9 mathematics" in law
    assert "No new date or continuous replay is authorized" in " ".join(
        phases.split()
    )
    assert "new_date_admission\": False" in source
    assert "continuous_replay_enabled\": False" in source
    assert "atom-v9-thin" not in source


def test_cli_receipt_is_single_json_for_success_and_failure(monkeypatch, capsys):
    monkeypatch.setattr(
        gate, "execute_persistence_gate",
        lambda **_kwargs: {"status": "PASSED"},
    )
    assert gate.main(()) == 0
    assert json.loads(capsys.readouterr().out) == {"status": "PASSED"}

    monkeypatch.setattr(
        gate, "execute_persistence_gate",
        lambda **_kwargs: (_ for _ in ()).throw(RuntimeError("blocked")),
    )
    assert gate.main(()) == 1
    receipt = json.loads(capsys.readouterr().out)
    assert receipt == {
        "detail": "blocked",
        "persistence_gate_version": "H2-D-6",
        "reason": "RuntimeError",
        "status": "FAILED",
    }
