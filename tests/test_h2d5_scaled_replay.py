import json

import pytest

from quant import historical_scaled_replay_h2d5 as scaled


def _receipt(day: str) -> dict:
    return {
        "historical_session": day,
        "replay_run_id": f"h2d-{day}",
        "evidence_snapshot": {
            "frame_count": 1,
            "forecast_count": 72,
            "outcome_count": 6,
        },
        "score": {"metric_sha256": f"metric-{day}"},
        "parity_sha256": f"parity-{day}",
        "stored_control_sha256": f"control-{day}",
    }


def test_frozen_sessions_are_exactly_four_new_certified_dates():
    assert scaled.FROZEN_SESSIONS == (
        ("2026-06-17", "h2d-2026-06-17"),
        ("2026-06-18", "h2d-2026-06-18"),
        ("2026-06-22", "h2d-2026-06-22"),
        ("2026-06-23", "h2d-2026-06-23"),
    )


def test_scaled_replay_runs_two_ordered_batches_and_verifies_post_controls():
    calls = []

    def runner(dates, *, timeout_seconds):
        calls.append((dates, timeout_seconds))
        return ([_receipt(day) for day in dates], [
            {"historical_session": day, "exit_code": 0, "peak_rss_kib": 10}
            for day in dates
        ])

    result = scaled.execute_scaled_replay(
        date_timeout_seconds=10,
        scale_timeout_seconds=30,
        isolated_runner=runner,
        post_reader=lambda day, _timeout: f"control-{day}",
    )
    assert [dates for dates, _timeout in calls] == [
        scaled.FROZEN_DATES[:2], scaled.FROZEN_DATES[2:],
    ]
    assert result["status"] == "PASSED"
    assert result["historical_sessions"] == list(scaled.FROZEN_DATES)
    assert result["worker_limit"] == result["batch_size"] == 2
    assert result["batch_count"] == 2
    assert result["read_only"] is True and result["evidence_writes"] == 0
    assert result["pre_post_unchanged"] is True
    assert result["surviving_workers"] == 0
    assert [row["historical_session"] for row in result["session_receipts"]] == list(
        scaled.FROZEN_DATES,
    )
    assert all(row["forecast_count"] == 72 for row in result["session_receipts"])


def test_scaled_replay_fails_closed_on_post_control_drift():
    def runner(dates, *, timeout_seconds):
        return ([_receipt(day) for day in dates], [
            {"historical_session": day, "exit_code": 0, "peak_rss_kib": 10}
            for day in dates
        ])

    with pytest.raises(Exception, match="POST_CONTROL_DRIFT"):
        scaled.execute_scaled_replay(
            isolated_runner=runner,
            post_reader=lambda _day, _timeout: "drift",
        )


def test_scaled_date_compares_fresh_score_to_stored_control(monkeypatch):
    day = scaled.FROZEN_DATES[0]
    snapshot = {"historical_session": day}
    score = {"metric_sha256": "a" * 64}
    monkeypatch.setattr(
        scaled, "_capture_control",
        lambda *_args: (snapshot, score, "b" * 64),
    )
    monkeypatch.setattr(
        scaled.h2d3, "run_read_only_session",
        lambda *_args: {
            "historical_session": day,
            "score": score,
            "parity_sha256": "c" * 64,
        },
    )
    receipt = scaled.run_scaled_date(day)
    assert receipt["stored_control_sha256"] == "b" * 64

    monkeypatch.setattr(
        scaled.h2d3, "run_read_only_session",
        lambda *_args: {"score": {"metric_sha256": "drift"}},
    )
    with pytest.raises(Exception, match="SCORE_PARITY_DRIFT"):
        scaled.run_scaled_date(day)


def test_cli_emits_one_final_json_receipt(monkeypatch, capsys):
    monkeypatch.setattr(
        scaled, "execute_scaled_replay", lambda **_kwargs: {"status": "PASSED"},
    )
    assert scaled.main(()) == 0
    assert json.loads(capsys.readouterr().out) == {"status": "PASSED"}

    monkeypatch.setattr(
        scaled, "execute_scaled_replay",
        lambda **_kwargs: (_ for _ in ()).throw(RuntimeError("blocked")),
    )
    assert scaled.main(()) == 1
    assert json.loads(capsys.readouterr().out)["status"] == "FAILED"
