from __future__ import annotations

import json
from pathlib import Path

import pytest

from quant import historical_target_qualification_h2d8 as qualifier


def _payload(day: str, *, gap_seconds: int = 5,
             rejected: bool = False) -> dict:
    return {
        "historical_session": day,
        "frame_count": 0,
        "execution_stage": "PREFLIGHT_REJECTED" if rejected else "PREFLIGHT_ONLY",
        "data_status": "DATA_INCOMPLETE" if rejected else "DATA_COMPLETE",
        "data_reason_codes": ["COIN_OPEN_EDGE_GAP"] if rejected else [],
        "quote_coverage": [{
            "symbol": "COIN",
            "max_gap_ns": gap_seconds * 1_000_000_000,
        }],
        "retrieval_proof": {},
        "dataset_digest": "d" * 64,
        "configuration_digest": "c" * 64,
        "session_digest": "e" * 64,
    }


def _absent(_day: str, _run_id: str, _timeout: float) -> dict[str, int]:
    return dict(qualifier._ABSENT)


def _stable_control(_timeout: float):
    return (7, 8, 9)


def _execute(monkeypatch, payloads: dict[str, dict], *, calls=None):
    monkeypatch.setattr(qualifier.h1, "_qualifies_cached_result", lambda *_a, **_k: True)
    observed = calls if calls is not None else []

    def preflight(day, _timeout):
        observed.append(day)
        return payloads[day]

    return qualifier.execute_target_qualification(
        target_reader=_absent,
        preflight_runner=preflight,
        control_reader=_stable_control,
    )


def test_selects_first_two_qualifying_targets_then_stops(monkeypatch):
    payloads = {day: _payload(day) for day, _run_id in qualifier.FROZEN_TARGETS}
    calls = []
    receipt = _execute(monkeypatch, payloads, calls=calls)

    assert calls == ["2026-07-27", "2026-07-28"]
    assert receipt["status"] == "PASSED"
    assert receipt["selected_sessions"] == calls
    assert receipt["selected_replay_run_ids"] == [
        "h2d-2026-07-27", "h2d-2026-07-28",
    ]
    assert len(receipt["inspected_candidates"]) == 2
    assert receipt["manifest_writes"] == 0
    assert receipt["forecast_writes"] == 0
    assert receipt["persistence_writes"] == 0
    assert receipt["outcome_writes"] == 0
    assert receipt["pre_post_unchanged"] is True
    assert receipt["continuous_replay_enabled"] is False
    assert receipt["parallel_replay_enabled"] is False


def test_skips_honest_market_data_rejection_in_fixed_order(monkeypatch):
    payloads = {day: _payload(day) for day, _run_id in qualifier.FROZEN_TARGETS}
    payloads["2026-07-27"] = _payload("2026-07-27", rejected=True)
    calls = []
    receipt = _execute(monkeypatch, payloads, calls=calls)

    assert calls == ["2026-07-27", "2026-07-28", "2026-07-29"]
    assert receipt["selected_sessions"] == ["2026-07-28", "2026-07-29"]
    rejected = receipt["inspected_candidates"][0]
    assert rejected["status"] == "REJECTED"
    assert rejected["reason_codes"] == ["COIN_OPEN_EDGE_GAP"]
    assert rejected["result_source"] == "NEW_PREFLIGHT"


def test_independent_five_second_gate_rejects_six_seconds(monkeypatch):
    payloads = {day: _payload(day) for day, _run_id in qualifier.FROZEN_TARGETS}
    payloads["2026-07-27"] = _payload("2026-07-27", gap_seconds=6)
    receipt = _execute(monkeypatch, payloads)

    rejected = receipt["inspected_candidates"][0]
    assert rejected["status"] == "REJECTED"
    assert rejected["reason_codes"] == []
    assert rejected["qualification_reason_codes"] == [
        "H2D8_COIN_INTERIOR_GAP",
    ]
    assert rejected["maximum_interior_gap_seconds"] == 6
    assert receipt["selected_sessions"] == ["2026-07-28", "2026-07-29"]


def test_non_absent_target_fails_before_h1(monkeypatch):
    preflight_calls = []
    present = dict(qualifier._ABSENT, session_manifest_count=1)
    with pytest.raises(
        qualifier.TargetQualificationFailure, match="TARGET_NOT_ABSENT",
    ) as raised:
        qualifier.execute_target_qualification(
            target_reader=lambda *_args: present,
            preflight_runner=lambda *_args: preflight_calls.append(True),
            control_reader=_stable_control,
        )
    assert preflight_calls == []
    assert raised.value.pre_post_unchanged is True


def test_provider_or_system_error_fails_complete_phase(monkeypatch):
    with pytest.raises(
        qualifier.TargetQualificationFailure, match="RUNTIME_ERROR:RuntimeError",
    ) as raised:
        qualifier.execute_target_qualification(
            target_reader=_absent,
            preflight_runner=lambda *_args: (_ for _ in ()).throw(
                RuntimeError("provider unavailable")
            ),
            control_reader=_stable_control,
        )
    assert raised.value.pre_post_unchanged is True
    assert raised.value.selected == []


def test_fails_if_evidence_control_changes(monkeypatch):
    controls = iter(((1, 2, 3), (1, 2, 4)))
    payloads = {day: _payload(day) for day, _run_id in qualifier.FROZEN_TARGETS}
    monkeypatch.setattr(qualifier.h1, "_qualifies_cached_result", lambda *_a, **_k: True)

    with pytest.raises(
        qualifier.TargetQualificationFailure, match="EVIDENCE_DRIFT",
    ):
        qualifier.execute_target_qualification(
            target_reader=_absent,
            preflight_runner=lambda day, _timeout: payloads[day],
            control_reader=lambda _timeout: next(controls),
        )


def test_fails_after_fixed_list_if_two_targets_do_not_qualify(monkeypatch):
    payloads = {
        day: _payload(day, rejected=True)
        for day, _run_id in qualifier.FROZEN_TARGETS
    }
    with pytest.raises(
        qualifier.TargetQualificationFailure,
        match="TWO_TARGETS_NOT_QUALIFIED",
    ) as raised:
        _execute(monkeypatch, payloads)
    assert len(raised.value.inspected) == 5
    assert raised.value.selected == []
    assert raised.value.pre_post_unchanged is True


@pytest.mark.parametrize("timeout", [0, -1, float("nan"), float("inf")])
def test_rejects_unbounded_timeout(timeout):
    with pytest.raises(ValueError, match="positive and finite"):
        qualifier.execute_target_qualification(timeout_seconds=timeout)


def test_target_query_uses_exact_score_reader_tables(monkeypatch):
    from quant import historical_evidence_verifier as verifier

    statements = []

    class Cursor:
        def execute(self, statement, params=None):
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
    day, run_id = qualifier.FROZEN_TARGETS[0]
    assert qualifier._read_target_counts(day, run_id, 5) == qualifier._ABSENT
    query, params = statements[1]
    for table in (
        "atom_historical_replay_runs",
        "atom_historical_replay_forecasts",
        "atom_historical_replay_outcomes",
    ):
        assert table in query
    assert params[1:] == (run_id, run_id, run_id)


def test_scope_stays_read_only_and_outside_v9():
    source = Path("quant/historical_target_qualification_h2d8.py").read_text()
    assert "multiprocessing" not in source
    assert "quant.v9" not in source
    assert "HistoricalEvidenceWriter" not in source
    assert "resolve_outcomes" not in source
    assert "INSERT " not in source
    assert qualifier.FROZEN_TARGETS == (
        ("2026-07-27", "h2d-2026-07-27"),
        ("2026-07-28", "h2d-2026-07-28"),
        ("2026-07-29", "h2d-2026-07-29"),
        ("2026-07-30", "h2d-2026-07-30"),
        ("2026-07-31", "h2d-2026-07-31"),
    )


def test_cli_emits_one_final_json_receipt(monkeypatch, capsys):
    monkeypatch.setattr(
        qualifier, "execute_target_qualification",
        lambda **_kwargs: {"status": "PASSED"},
    )
    assert qualifier.main(()) == 0
    assert json.loads(capsys.readouterr().out) == {"status": "PASSED"}

    error = qualifier.TargetQualificationFailure(
        "blocked", pre_post_unchanged=True,
    )
    monkeypatch.setattr(
        qualifier, "execute_target_qualification",
        lambda **_kwargs: (_ for _ in ()).throw(error),
    )
    assert qualifier.main(()) == 1
    failed = json.loads(capsys.readouterr().out)
    assert failed["status"] == "FAILED"
    assert failed["detail"] == "blocked"
    assert failed["pre_post_unchanged"] is True
