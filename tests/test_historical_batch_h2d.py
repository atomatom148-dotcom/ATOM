from datetime import date
from pathlib import Path

import pytest

from quant.historical_batch_h2d import execute, requested_dates

D1, D2, C = "d" * 64, "e" * 64, "c" * 64


def manifest(run_id="frozen", digest=D1, frames=2):
    return {"replay_run_id": run_id, "dataset_digest": digest,
            "configuration_digest": C, "frame_count": frames}


def stages(*, fail=None, mutate=None):
    calls = []
    current_digest = D1
    def run(command, stage):
        nonlocal current_digest
        calls.append((stage, command))
        if stage == fail:
            raise RuntimeError("boom")
        if stage == "H1":
            current_digest = D2 if "2026-06-16" in command else D1
        session_digest = current_digest
        if stage == "H1":
            value = {"execution_stage": "REPLAY_COMPLETE", "data_status": "CERTIFIED",
                     "frame_count": 2, "dataset_digest": session_digest,
                     "configuration_digest": C}
        elif stage == "H2B":
            value = {"verification_status": "VERIFIED", "manifest_count": 1,
                     "frame_count": 2, "forecast_count": 144, "quant_count": 12,
                     "horizon_count": 6, "dataset_digest": session_digest,
                     "configuration_digest": C,
                     "stored_content_hash_summary": "f" * 64}
        elif stage == "H2C_RESOLVE":
            value = {"inserted": 12}
        else:
            value = {"forecast_count": 144, "outcome_count": 12,
                     "metrics": [{}] * 72, "dataset_digest": session_digest,
                     "configuration_digest": C, "content_hash_summary": "s" * 64}
        return mutate(stage, value) if mutate else value
    return calls, run


def test_one_certified_session_completes_with_explicit_frozen_arguments():
    calls, run = stages()
    result = execute((date(2026, 6, 15),), continue_on_failure=False,
                     run_json=run, existing=lambda _: ())
    assert [stage for stage, _ in calls] == ["H1", "H2B", "H2C_RESOLVE", "H2C_SCORE"]
    assert ["--max-interior-gap-seconds", "5"] == calls[0][1][-3:-1]
    assert calls[1][1][-2:] == ["--frame-count", "2"]
    assert result["completed"] == ["2026-06-15"]


def test_two_sessions_with_distinct_dataset_digests_complete():
    calls, run = stages()
    result = execute((date(2026, 6, 15), date(2026, 6, 16)),
                     continue_on_failure=False, run_json=run, existing=lambda _: ())
    assert result["completed"] == ["2026-06-15", "2026-06-16"]
    assert [row["dataset_digest"] for row in result["sessions"]] == [D1, D2]
    h2b = [command for stage, command in calls if stage == "H2B"]
    assert D1 in h2b[0] and D2 in h2b[1]


def test_exact_retry_uses_manifest_lineage_then_skips():
    calls, run = stages()
    result = execute((date(2026, 6, 15),), continue_on_failure=False,
                     run_json=run, existing=lambda _: (manifest(),))
    assert [stage for stage, _ in calls] == ["H2B", "H2C_RESOLVE", "H2C_SCORE"]
    assert result["skipped"] == ["2026-06-15"]
    assert D1 in calls[0][1] and C in calls[0][1]


def test_conflicting_retry_fails_closed():
    calls, run = stages()
    result = execute((date(2026, 6, 15),), continue_on_failure=False,
        run_json=run, existing=lambda _: (manifest("one"), manifest("two")))
    assert result["overall_status"] == "FAILED" and not calls


def test_uncertified_h1_and_rejected_h2b_fail_closed():
    def uncertified(stage, value):
        if stage == "H1": value["data_status"] = "REJECTED"
        return value
    _, run = stages(mutate=uncertified)
    first = execute((date(2026, 6, 15),), continue_on_failure=False,
                    run_json=run, existing=lambda _: ())
    assert first["sessions"][0]["reason"] == "NOT_CERTIFIED"
    def rejected(stage, value):
        if stage == "H2B": value["verification_status"] = "REJECTED"
        return value
    _, run = stages(mutate=rejected)
    second = execute((date(2026, 6, 15),), continue_on_failure=False,
                     run_json=run, existing=lambda _: ())
    assert second["sessions"][0]["reason"] == "VERIFIED_RECEIPT_MISMATCH"


@pytest.mark.parametrize("field,value", [
    ("forecast_count", 143), ("quant_count", 11), ("horizon_count", 5),
    ("manifest_count", 0), ("frame_count", 3),
])
def test_wrong_verification_counts_fail_closed(field, value):
    def wrong(stage, receipt):
        if stage == "H2B": receipt[field] = value
        return receipt
    _, run = stages(mutate=wrong)
    result = execute((date(2026, 6, 15),), continue_on_failure=False,
                     run_json=run, existing=lambda _: ())
    assert result["failed"] == ["2026-06-15"]


@pytest.mark.parametrize("failure", ["missing_metrics", "verifier_digest", "scorer_digest"])
def test_missing_metrics_or_digest_drift_fails_closed(failure):
    def wrong(stage, receipt):
        if failure == "missing_metrics" and stage == "H2C_SCORE": receipt["metrics"] = [{}] * 71
        if failure == "verifier_digest" and stage == "H2B": receipt["dataset_digest"] = D2
        if failure == "scorer_digest" and stage == "H2C_SCORE": receipt["configuration_digest"] = "x" * 64
        return receipt
    _, run = stages(mutate=wrong)
    result = execute((date(2026, 6, 15),), continue_on_failure=False,
                     run_json=run, existing=lambda _: ())
    assert result["overall_status"] == "FAILED"


@pytest.mark.parametrize("failed", ["H1", "H2B", "H2C_RESOLVE", "H2C_SCORE"])
def test_stage_failure_stops_later_sessions(failed):
    calls, run = stages(fail=failed)
    result = execute((date(2026, 6, 15), date(2026, 6, 16)),
        continue_on_failure=False, run_json=run, existing=lambda _: ())
    assert result["failed"] == ["2026-06-15"]
    assert sum(stage == "H1" for stage, _ in calls) == 1


def test_continue_on_failure_is_explicit():
    calls, base = stages(); failures = 0
    def run(command, stage):
        nonlocal failures
        if stage == "H1" and failures == 0:
            failures += 1; raise RuntimeError("first only")
        return base(command, stage)
    result = execute((date(2026, 6, 15), date(2026, 6, 16)),
        continue_on_failure=True, run_json=run, existing=lambda _: ())
    assert result["failed"] == ["2026-06-15"] and result["completed"] == ["2026-06-16"]


def test_ranges_future_maximum_and_closed_market():
    assert len(requested_dates(dates=None, start="2026-06-15", end="2026-06-19",
                               maximum=5, today=date(2026, 6, 20))) == 5
    with pytest.raises(ValueError): requested_dates(dates=None, start="2026-06-20", end="2026-06-15", maximum=5)
    with pytest.raises(ValueError): requested_dates(dates=["2027-01-01"], start=None, end=None, maximum=5, today=date(2026, 6, 20))
    with pytest.raises(ValueError): requested_dates(dates=["2026-06-15", "2026-06-16"], start=None, end=None, maximum=1, today=date(2026, 6, 20))
    calls, run = stages()
    result = execute((date(2026, 6, 20),), continue_on_failure=False,
                     run_json=run, existing=lambda _: ())
    assert result["rejected"] == ["2026-06-20"] and not calls


def test_orchestrator_does_not_import_live_ui_or_quant_paths():
    source = Path("quant/historical_batch_h2d.py").read_text()
    for forbidden in ("quant.web", "live_market", "unified_quant", "q1_momentum"):
        assert forbidden not in source
