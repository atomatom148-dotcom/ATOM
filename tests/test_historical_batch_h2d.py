from datetime import date

import pytest

from quant.historical_batch_h2d import execute, requested_dates

D = "d" * 64
C = "c" * 64


def stages(fail=None):
    calls = []
    def run(command, stage):
        calls.append(stage)
        if stage == fail:
            raise RuntimeError("boom")
        if stage == "H1":
            return {"execution_stage": "REPLAY_COMPLETE", "data_status": "CERTIFIED", "frame_count": 2}
        if stage == "H2B":
            return {"verification_status": "VERIFIED", "frame_count": 2, "forecast_count": 144,
                    "dataset_digest": D, "configuration_digest": C,
                    "stored_content_hash_summary": "f" * 64}
        if stage == "H2C_RESOLVE": return {"inserted": 12}
        return {"forecast_count": 144, "outcome_count": 12, "metrics": [{}] * 72,
                "content_hash_summary": "s" * 64}
    return calls, run


def test_one_certified_session_completes():
    calls, run = stages()
    result = execute((date(2026, 6, 15),), dataset_digest=D, configuration_digest=C,
                     continue_on_failure=False, run_json=run, existing=lambda _: ())
    assert calls == ["H1", "H2B", "H2C_RESOLVE", "H2C_SCORE"]
    assert result["completed"] == ["2026-06-15"]
    assert result["sessions"][0]["metrics_count"] == 72


def test_exact_retry_verifies_then_skips():
    calls, run = stages()
    result = execute((date(2026, 6, 15),), dataset_digest=D, configuration_digest=C,
                     continue_on_failure=False, run_json=run, existing=lambda _: ("frozen",))
    assert calls == ["H2B", "H2C_RESOLVE", "H2C_SCORE"]
    assert result["skipped"] == ["2026-06-15"]


def test_conflicting_retry_fails_closed():
    calls, run = stages()
    result = execute((date(2026, 6, 15),), dataset_digest=D, configuration_digest=C,
        continue_on_failure=False, run_json=run, existing=lambda _: ("one", "two"))
    assert result["overall_status"] == "FAILED" and not calls


def test_uncertified_h1_and_rejected_h2b_fail_closed():
    def uncertified(command, stage):
        return {"execution_stage": "REPLAY_COMPLETE", "data_status": "REJECTED"}
    first = execute((date(2026, 6, 15),), dataset_digest=D, configuration_digest=C,
        continue_on_failure=False, run_json=uncertified, existing=lambda _: ())
    assert first["sessions"][0]["reason"] == "NOT_CERTIFIED"

    calls, base = stages()
    def rejected(command, stage):
        if stage == "H2B":
            return {"verification_status": "REJECTED"}
        return base(command, stage)
    second = execute((date(2026, 6, 15),), dataset_digest=D, configuration_digest=C,
        continue_on_failure=False, run_json=rejected, existing=lambda _: ())
    assert second["sessions"][0]["reason"] == "NOT_VERIFIED"


@pytest.mark.parametrize("failed", ["H1", "H2B", "H2C_RESOLVE", "H2C_SCORE"])
def test_stage_failure_stops_later_sessions(failed):
    calls, run = stages(failed)
    result = execute((date(2026, 6, 15), date(2026, 6, 16)), dataset_digest=D,
        configuration_digest=C, continue_on_failure=False, run_json=run, existing=lambda _: ())
    assert result["failed"] == ["2026-06-15"]
    assert calls.count("H1") == 1


def test_continue_on_failure_is_explicit():
    calls, base = stages()
    failures = 0
    def run(command, stage):
        nonlocal failures
        if stage == "H1" and failures == 0:
            failures += 1; raise RuntimeError("first only")
        return base(command, stage)
    result = execute((date(2026, 6, 15), date(2026, 6, 16)), dataset_digest=D,
        configuration_digest=C, continue_on_failure=True, run_json=run, existing=lambda _: ())
    assert result["failed"] == ["2026-06-15"] and result["completed"] == ["2026-06-16"]


def test_ranges_future_maximum_and_closed_market():
    assert len(requested_dates(dates=None, start="2026-06-15", end="2026-06-19",
                               maximum=5, today=date(2026, 6, 20))) == 5
    with pytest.raises(ValueError): requested_dates(dates=None, start="2026-06-20", end="2026-06-15", maximum=5)
    with pytest.raises(ValueError): requested_dates(dates=["2027-01-01"], start=None, end=None, maximum=5, today=date(2026, 6, 20))
    with pytest.raises(ValueError): requested_dates(dates=["2026-06-15", "2026-06-16"], start=None, end=None, maximum=1, today=date(2026, 6, 20))
    calls, run = stages()
    result = execute((date(2026, 6, 20),), dataset_digest=D, configuration_digest=C,
                     continue_on_failure=False, run_json=run, existing=lambda _: ())
    assert result["rejected"] == ["2026-06-20"] and not calls


def test_orchestrator_does_not_import_live_ui_or_quant_paths():
    source = __import__("pathlib").Path("quant/historical_batch_h2d.py").read_text()
    for forbidden in ("quant.web", "live_market", "unified_quant", "q1_momentum"):
        assert forbidden not in source
