from __future__ import annotations

from datetime import date
import json
from pathlib import Path
import signal

import pytest

from quant import historical_target_qualification_h2d8 as qualifier


def _payload(day: str, *, gap_seconds: int = 5,
             rejected: bool = False) -> dict:
    opened, closed = qualifier.h1._session(date.fromisoformat(day))
    open_ns = qualifier.h1._ns(opened)
    close_ns = qualifier.h1._ns(closed)
    configuration_digest = qualifier.h1._configuration_digest(
        session_open_ns=open_ns, session_close_ns=close_ns,
    )
    coin_count = 1 if rejected else 2
    reason_codes = ["COIN_INSUFFICIENT_QUOTES"] if rejected else []
    quote_coverage = [
        {"symbol": "COIN", "count": coin_count,
         "max_gap_ns": None if rejected else gap_seconds * 1_000_000_000},
        {"symbol": "QQQ", "count": 2,
         "max_gap_ns": gap_seconds * 1_000_000_000},
    ]
    payload = {
        "runner_version": qualifier.h1.H1_RUNNER_VERSION,
        "replay_run_id": f"h1-preflight-{day}",
        "historical_session": day,
        "session_open_ns": open_ns,
        "session_close_ns": close_ns,
        "frame_count": 0,
        "execution_stage": "PREFLIGHT_REJECTED" if rejected else "PREFLIGHT_ONLY",
        "data_status": "DATA_INCOMPLETE" if rejected else "DATA_COMPLETE",
        "data_reason_codes": reason_codes,
        "quote_counts": [("COIN", coin_count), ("QQQ", 2)],
        "quote_coverage": quote_coverage,
        "retrieval_proof": {},
        "dataset_digest": "d" * 64,
        "configuration_digest": configuration_digest,
    }
    payload["session_digest"] = qualifier.h1.canonical_sha256({
        "dataset_digest": payload["dataset_digest"],
        "configuration_digest": configuration_digest,
        "execution_stage": payload["execution_stage"],
        "data_status": payload["data_status"],
        "data_reason_codes": reason_codes,
        "quote_coverage": quote_coverage,
        "retrieval_proof": {},
    })
    return payload


def _absent(_day: str, _run_id: str, _timeout: float) -> dict[str, int]:
    return dict(qualifier._ABSENT)


def _stable_control(_timeout: float):
    return (7, 8, 9)


def _execute(monkeypatch, payloads: dict[str, dict], *, calls=None):
    monkeypatch.setattr(qualifier.h1, "_qualifies_cached_result", lambda *_a, **_k: True)
    monkeypatch.setattr(qualifier.h1, "_retrieval_proof_valid", lambda *_a, **_k: True)
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

    assert calls == ["2026-08-03", "2026-08-04"]
    assert receipt["status"] == "PASSED"
    assert receipt["selected_sessions"] == calls
    assert receipt["selected_replay_run_ids"] == [
        "h2d-2026-08-03", "h2d-2026-08-04",
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
    payloads["2026-08-03"] = _payload("2026-08-03", rejected=True)
    calls = []
    receipt = _execute(monkeypatch, payloads, calls=calls)

    assert calls == ["2026-08-03", "2026-08-04", "2026-08-05"]
    assert receipt["selected_sessions"] == ["2026-08-04", "2026-08-05"]
    rejected = receipt["inspected_candidates"][0]
    assert rejected["status"] == "REJECTED"
    assert rejected["reason_codes"] == ["COIN_INSUFFICIENT_QUOTES"]
    assert rejected["result_source"] == "NEW_PREFLIGHT"
    assert rejected["maximum_interior_gap_seconds"] is None


def test_independent_five_second_gate_rejects_six_seconds(monkeypatch):
    payloads = {day: _payload(day) for day, _run_id in qualifier.FROZEN_TARGETS}
    payloads["2026-08-03"] = _payload("2026-08-03", gap_seconds=6)
    receipt = _execute(monkeypatch, payloads)

    rejected = receipt["inspected_candidates"][0]
    assert rejected["status"] == "REJECTED"
    assert rejected["reason_codes"] == []
    assert rejected["qualification_reason_codes"] == [
        "H2D8_COIN_INTERIOR_GAP",
    ]
    assert rejected["maximum_interior_gap_seconds"] == 6
    assert receipt["selected_sessions"] == ["2026-08-04", "2026-08-05"]


def test_over_gap_receipt_still_requires_valid_lineage(monkeypatch):
    payloads = {day: _payload(day) for day, _run_id in qualifier.FROZEN_TARGETS}
    payloads["2026-08-03"] = _payload("2026-08-03", gap_seconds=6)
    payloads["2026-08-03"]["configuration_digest"] = "0" * 64
    with pytest.raises(
        qualifier.TargetQualificationFailure, match="LINEAGE_OR_RECEIPT_ERROR",
    ):
        _execute(monkeypatch, payloads)


def test_qualifying_receipt_requires_expected_preflight_run_id(monkeypatch):
    payloads = {day: _payload(day) for day, _run_id in qualifier.FROZEN_TARGETS}
    payloads["2026-08-03"]["replay_run_id"] = "h1-preflight-wrong"
    with pytest.raises(
        qualifier.TargetQualificationFailure, match="LINEAGE_OR_RECEIPT_ERROR",
    ):
        _execute(monkeypatch, payloads)


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
    assert raised.value.inspected[0]["status"] == "FAILED"
    assert raised.value.inspected[0]["absence_counts"] == present


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
    assert raised.value.inspected[0]["status"] == "FAILED"


def test_rejected_receipt_with_lineage_drift_fails_closed(monkeypatch):
    payloads = {day: _payload(day) for day, _run_id in qualifier.FROZEN_TARGETS}
    payloads["2026-08-03"] = _payload("2026-08-03", rejected=True)
    payloads["2026-08-03"]["runner_version"] = "drifted"
    with pytest.raises(
        qualifier.TargetQualificationFailure,
        match="PROVIDER_SYSTEM_OR_RECEIPT_ERROR",
    ) as raised:
        _execute(monkeypatch, payloads)
    assert raised.value.inspected[0]["status"] == "FAILED"


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


def test_final_control_error_retains_inspected_candidates(monkeypatch):
    payloads = {day: _payload(day) for day, _run_id in qualifier.FROZEN_TARGETS}
    monkeypatch.setattr(qualifier.h1, "_qualifies_cached_result", lambda *_a, **_k: True)
    monkeypatch.setattr(qualifier.h1, "_retrieval_proof_valid", lambda *_a, **_k: True)
    controls = iter(((1, 2, 3), RuntimeError("database unavailable")))

    def control(_timeout):
        value = next(controls)
        if isinstance(value, Exception):
            raise value
        return value

    with pytest.raises(
        qualifier.TargetQualificationFailure, match="POST_CONTROL_ERROR",
    ) as raised:
        qualifier.execute_target_qualification(
            target_reader=_absent,
            preflight_runner=lambda day, _timeout: payloads[day],
            control_reader=control,
        )
    assert len(raised.value.inspected) == 2
    assert len(raised.value.selected) == 2


def test_expired_budget_preserves_original_failure(monkeypatch):
    now = iter((0.0, 0.0, 0.0, 0.0, 2.0, 2.0))
    monkeypatch.setattr(qualifier.time, "monotonic", lambda: next(now))

    with pytest.raises(
        qualifier.TargetQualificationFailure, match="PREFLIGHT_TIMEOUT",
    ) as raised:
        qualifier.execute_target_qualification(
            timeout_seconds=1,
            target_reader=_absent,
            preflight_runner=lambda *_args: (_ for _ in ()).throw(
                qualifier.TargetQualificationFailure("H2D8_PREFLIGHT_TIMEOUT")
            ),
            control_reader=_stable_control,
        )
    assert "POST_CONTROL_ERROR" not in str(raised.value)


def test_default_preflight_enforces_and_clears_deadline(monkeypatch):
    handler = {}
    timer_calls = []

    def set_handler(_signal, value):
        previous = handler.get("value", "previous")
        handler["value"] = value
        return previous

    def run_h1_session(**_kwargs):
        handler["value"](signal.SIGALRM, None)

    monkeypatch.setattr(qualifier.signal, "signal", set_handler)
    monkeypatch.setattr(
        qualifier.signal, "setitimer",
        lambda which, seconds: timer_calls.append((which, seconds)),
    )
    monkeypatch.setattr(qualifier.h1, "run_h1_session", run_h1_session)

    with pytest.raises(
        qualifier.TargetQualificationFailure, match="PREFLIGHT_TIMEOUT",
    ):
        qualifier._run_preflight(object(), "2026-08-03", 2.5)
    assert timer_calls == [
        (signal.ITIMER_REAL, 2.5), (signal.ITIMER_REAL, 0),
    ]
    assert handler["value"] == "previous"


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
        ("2026-08-03", "h2d-2026-08-03"),
        ("2026-08-04", "h2d-2026-08-04"),
        ("2026-08-05", "h2d-2026-08-05"),
        ("2026-08-06", "h2d-2026-08-06"),
        ("2026-08-07", "h2d-2026-08-07"),
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
