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
        forecast_retry=lambda snapshot: {
            "forecast_writes": 0,
            "artifact_sha256": snapshot["artifact_sha256"],
            "forecast_ordered_content_sha256": (
                snapshot["forecast_ordered_content_sha256"]
            ),
            "elapsed_seconds": 1.25,
        },
        outcome_retry=lambda _snapshot: 0,
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
            forecast_retry=lambda snapshot: {
                "forecast_writes": forecast_writes,
                "artifact_sha256": snapshot["artifact_sha256"],
                "forecast_ordered_content_sha256": (
                    snapshot["forecast_ordered_content_sha256"]
                ),
                "elapsed_seconds": 1.0,
            },
            outcome_retry=lambda _snapshot: outcome_writes,
        )


def test_gate_fails_on_control_drift():
    first = _control()
    changed_snapshot = dict(first[0], artifact_sha256="9" * 64)
    controls = iter((first, (changed_snapshot, first[1], first[2])))
    with pytest.raises(gate.PersistenceGateFailure):
        gate.execute_persistence_gate(
            control_reader=lambda _timeout: next(controls),
            forecast_retry=lambda snapshot: {
                "forecast_writes": 0,
                "artifact_sha256": snapshot["artifact_sha256"],
                "forecast_ordered_content_sha256": (
                    snapshot["forecast_ordered_content_sha256"]
                ),
                "elapsed_seconds": 1.0,
            },
            outcome_retry=lambda _snapshot: 0,
        )


@pytest.mark.parametrize("timeout", [0, -1, float("nan"), float("inf")])
def test_gate_rejects_unbounded_timeout(timeout):
    with pytest.raises(ValueError, match="positive and finite"):
        gate.execute_persistence_gate(timeout_seconds=timeout)


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

    class Cursor:
        def execute(self, sql, params):
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
    ) == 0
    assert observed == {
        "environment": "HISTORICAL_OUTCOME_DATABASE_URL",
        "role": "atom_historical_outcome_resolver",
    }


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


def test_cli_failure_receipt_is_single_json(monkeypatch, capsys):
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
