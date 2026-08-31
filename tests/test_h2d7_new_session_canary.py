from __future__ import annotations

import json
from pathlib import Path
from types import SimpleNamespace

import pytest

from quant import historical_new_session_canary_h2d7 as canary


FRAMES = 2
FORECASTS = FRAMES * 72
OUTCOMES = FRAMES * 6


def _stages() -> dict[str, dict]:
    return {
        "H1": {
            "historical_session": canary.FROZEN_SESSION,
            "replay_run_id": canary.FROZEN_RUN_ID,
            "execution_stage": "REPLAY_COMPLETE",
            "data_status": "CERTIFIED",
            "data_reason_codes": [],
            "frame_count": FRAMES,
            "dataset_digest": "d" * 64,
            "configuration_digest": "c" * 64,
            "session_digest": "s" * 64,
            "persistence_writes": 1 + FORECASTS,
            "family_coverage": [{} for _ in range(72)],
        },
        "H2B": {"verification_status": "VERIFIED"},
        "H2C_RESOLVE": {"inserted": OUTCOMES},
        "H2C_SCORE": {"metrics": [{} for _ in range(72)]},
    }


def _batch() -> dict:
    return {
        "overall_status": "COMPLETED",
        "requested_dates": [canary.FROZEN_SESSION],
        "completed": [canary.FROZEN_SESSION],
        "skipped": [],
        "rejected": [],
        "failed": [],
        "replay_run_ids": [canary.FROZEN_RUN_ID],
        "sessions": [{
            "state": "COMPLETED",
            "replay_run_id": canary.FROZEN_RUN_ID,
            "forecast_count": FORECASTS,
            "outcome_count": OUTCOMES,
            "outcome_writes": OUTCOMES,
            "metrics_count": 72,
            "stage_timings": {"h1_seconds": 1.0},
        }],
        "peak_rss_kib": 100,
    }


def _control() -> tuple[dict, dict, str]:
    snapshot = {
        "historical_session": canary.FROZEN_SESSION,
        "replay_run_id": canary.FROZEN_RUN_ID,
        "git_commit": "a" * 40,
        "dataset_digest": "d" * 64,
        "configuration_digest": "c" * 64,
        "session_digest": "s" * 64,
        "frame_count": FRAMES,
        "forecast_count": FORECASTS,
        "outcome_count": OUTCOMES,
        "artifact_sha256": "1" * 64,
        "manifest_content_sha256": "2" * 64,
        "forecast_ordered_content_sha256": "3" * 64,
        "outcome_ordered_content_sha256": "4" * 64,
    }
    score = {
        "forecast_count": FORECASTS,
        "outcome_count": OUTCOMES,
        "metrics": [{} for _ in range(72)],
        "metric_sha256": "5" * 64,
        "content_hash_summary": "6" * 64,
    }
    return snapshot, score, "7" * 64


def _absent(_timeout: float) -> dict[str, int]:
    return {
        "session_manifest_count": 0,
        "run_manifest_count": 0,
        "forecast_count": 0,
        "outcome_count": 0,
    }


def _execute(*, target_reader=_absent, batch_receipt=None,
             stages=None, control=None) -> dict:
    return canary.execute_new_session_canary(
        target_reader=target_reader,
        batch_runner=lambda _timeout: (
            batch_receipt or _batch(), stages or _stages(),
        ),
        control_reader=lambda _timeout: control or _control(),
    )


def test_canary_admits_exactly_one_frozen_absent_session():
    receipt = _execute()
    assert canary.FROZEN_SESSION == "2026-07-23"
    assert canary.FROZEN_RUN_ID == "h2d-2026-07-23"
    assert receipt["status"] == "PASSED"
    assert receipt["manifest_writes"] == 1
    assert receipt["forecast_writes"] == FORECASTS
    assert receipt["persistence_writes"] == 1 + FORECASTS
    assert receipt["outcome_writes"] == OUTCOMES
    assert receipt["new_date_admission"] is True
    assert receipt["continuous_replay_enabled"] is False
    assert receipt["parallel_replay_enabled"] is False


def test_canary_records_exact_lineage_hashes_and_roles():
    receipt = _execute()
    assert receipt["artifact_sha256"] == "1" * 64
    assert receipt["manifest_content_sha256"] == "2" * 64
    assert receipt["forecast_ordered_content_sha256"] == "3" * 64
    assert receipt["outcome_ordered_content_sha256"] == "4" * 64
    assert receipt["metric_sha256"] == "5" * 64
    assert receipt["control_sha256"] == "7" * 64
    assert receipt["forecast_writer_role"] == "atom_historical_replay_writer"
    assert receipt["outcome_resolver_role"] == "atom_historical_outcome_resolver"
    assert receipt["score_reader_role"] == "atom_historical_score_reader"


def test_canary_fails_before_replay_if_target_is_not_absent():
    calls = []
    present = _absent(1)
    present["session_manifest_count"] = 1
    with pytest.raises(canary.NewSessionCanaryFailure,
                       match="TARGET_NOT_ABSENT"):
        canary.execute_new_session_canary(
            target_reader=lambda _timeout: present,
            batch_runner=lambda _timeout: calls.append(True),
        )
    assert calls == []


@pytest.mark.parametrize("drift", ["forecast_writes", "outcome_writes", "control"])
def test_canary_fails_closed_on_write_or_control_drift(drift):
    stages = _stages()
    batch_receipt = _batch()
    control = _control()
    if drift == "forecast_writes":
        stages["H1"]["persistence_writes"] -= 1
    elif drift == "outcome_writes":
        stages["H2C_RESOLVE"]["inserted"] -= 1
    else:
        snapshot = dict(control[0], replay_run_id="wrong")
        control = (snapshot, control[1], control[2])
    with pytest.raises(canary.NewSessionCanaryFailure):
        _execute(batch_receipt=batch_receipt, stages=stages, control=control)


def test_canary_requires_the_exact_sequential_stage_set():
    stages = _stages()
    stages["EXTRA"] = {}
    with pytest.raises(canary.NewSessionCanaryFailure, match="STAGE_SEQUENCE"):
        _execute(stages=stages)


@pytest.mark.parametrize("timeout", [0, -1, float("nan"), float("inf")])
def test_canary_rejects_unbounded_timeout(timeout):
    with pytest.raises(ValueError, match="positive and finite"):
        canary.execute_new_session_canary(timeout_seconds=timeout)


def test_canary_scope_does_not_touch_v9_or_add_parallel_runtime():
    source = Path("quant/historical_new_session_canary_h2d7.py").read_text()
    assert "multiprocessing" not in source
    assert "quant.v9" not in source
    freeze = Path("docs/h2-d7-one-session-write-freeze.md").read_text()
    assert "adds no migration" in freeze
    assert "Parallel replay and continuous replay remain off" in freeze


def test_runtime_seam_pins_one_date_and_uses_score_reader_for_h2b(monkeypatch):
    import quant.historical_evidence_verifier as verifier

    stages = _stages()
    stages["H2B"] = {
        "replay_run_id": canary.FROZEN_RUN_ID,
        "historical_session": canary.FROZEN_SESSION,
        "verification_status": "VERIFIED",
        "reason_codes": [],
        "manifest_count": 1,
        "frame_count": FRAMES,
        "forecast_count": FORECASTS,
        "quant_count": 12,
        "horizon_count": 6,
        "dataset_digest": "d" * 64,
        "configuration_digest": "c" * 64,
        "stored_content_hash_summary": "1" * 64,
    }
    stages["H2C_SCORE"] = {
        "replay_run_id": canary.FROZEN_RUN_ID,
        "forecast_count": FORECASTS,
        "outcome_count": OUTCOMES,
        "metrics": [{} for _ in range(72)],
        "dataset_digest": "d" * 64,
        "configuration_digest": "c" * 64,
        "content_hash_summary": "6" * 64,
    }
    commands = []
    score_reads = []

    def subprocess_run(command, **_kwargs):
        commands.append(command)
        if "quant.historical_replay_h1" in command:
            payload = stages["H1"]
        elif "resolve-outcomes" in command:
            payload = stages["H2C_RESOLVE"]
        else:
            payload = stages["H2C_SCORE"]
        return SimpleNamespace(stdout=json.dumps(payload), returncode=0)

    def score_verify(run_id, **expected):
        score_reads.append((run_id, expected))
        return SimpleNamespace(payload=lambda: stages["H2B"])

    monkeypatch.setattr(canary.subprocess, "run", subprocess_run)
    monkeypatch.setattr(verifier, "verify_from_score_environment", score_verify)
    receipt, observed = canary._run_frozen_batch(30)

    assert receipt["completed"] == [canary.FROZEN_SESSION]
    assert tuple(observed) == ("H1", "H2B", "H2C_RESOLVE", "H2C_SCORE")
    h1_command = commands[0]
    assert canary.FROZEN_SESSION in h1_command
    assert h1_command[h1_command.index("--max-interior-gap-seconds") + 1] == "5"
    assert "--persist-certified" in h1_command
    assert all("quant.historical_evidence_verifier" not in row for row in commands)
    assert score_reads[0][0] == canary.FROZEN_RUN_ID
    assert score_reads[0][1]["expected_frame_count"] == FRAMES


def test_preflight_queries_all_target_tables_through_score_reader(monkeypatch):
    import quant.historical_evidence_verifier as verifier

    statements = []

    class Cursor:
        def execute(self, statement, params):
            statements.append((statement, params))

        def fetchone(self):
            return (0, 0, 0, 0)

        def close(self):
            pass

    class Connection:
        def __enter__(self):
            return self

        def __exit__(self, *_args):
            return False

        def cursor(self):
            return Cursor()

    monkeypatch.setattr(
        verifier, "connect_score_reader_from_environment", Connection,
    )
    assert canary._read_target_counts(5) == _absent(5)
    query, params = statements[1]
    for table in (
        "atom_historical_replay_runs",
        "atom_historical_replay_forecasts",
        "atom_historical_replay_outcomes",
    ):
        assert table in query
    assert params[1:] == (canary.FROZEN_RUN_ID,) * 3


def test_cli_emits_one_final_json_receipt(monkeypatch, capsys):
    monkeypatch.setattr(
        canary, "execute_new_session_canary",
        lambda **_kwargs: {"status": "PASSED"},
    )
    assert canary.main(()) == 0
    assert json.loads(capsys.readouterr().out) == {"status": "PASSED"}

    monkeypatch.setattr(
        canary, "execute_new_session_canary",
        lambda **_kwargs: (_ for _ in ()).throw(RuntimeError("blocked")),
    )
    assert canary.main(()) == 1
    assert json.loads(capsys.readouterr().out)["status"] == "FAILED"
