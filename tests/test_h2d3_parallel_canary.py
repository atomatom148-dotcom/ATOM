import hashlib
import json
import multiprocessing
from dataclasses import asdict
from datetime import datetime, timedelta, timezone
from pathlib import Path
import time
from types import SimpleNamespace

import pytest

from quant import historical_parallel_canary_h2d3 as canary
from quant.historical_evidence_verifier import VerificationReceipt
from quant.historical_outcomes import (
    HistoricalOutcome,
    OUTCOME_VERIFICATION_COLUMNS,
    OutcomeVerificationReceipt,
    RESOLUTION_SPEC_VERSION,
    ScoreMetric,
    ScoringReceipt,
)
from quant.historical_replay_h1 import FamilyCoverage, ResolutionCoverage
from quant.historical_outcomes import verify_outcomes
from quant.historical_parallel_canary_h2d3 import (
    CanaryFailure,
    FROZEN_DATES,
    canonical_metric_projection,
    execute_canary,
    run_isolated,
)


BASELINES = Path(__file__).resolve().parents[1] / "docs" / "h2-d2-canary-baselines.json"


def _metric_rows():
    contract = json.loads(BASELINES.read_text())["metric_hash_contract"]
    rows = []
    for quant in contract["quant_order"]:
        for horizon in contract["horizon_order"]:
            q3 = quant == "q3_volatility"
            rows.append({
                "quant_id": quant,
                "horizon": horizon,
                "eligible_count": 2,
                "resolved_count": 1,
                "directional_wins": None if q3 else 1,
                "directional_losses": None if q3 else 0,
                "directional_accuracy": None if q3 else 1.0,
                "rmse": 0.0,
                "mae": -0.0,
                "bias": 0.0,
                "coverage": 0.5,
            })
    return contract, rows


def test_metric_projection_is_exact_ordered_and_signed_zero_safe():
    contract, rows = _metric_rows()
    projected, digest = canonical_metric_projection(reversed(rows), contract)
    assert len(projected) == 72
    assert projected[0]["quant_id"] == contract["quant_order"][0]
    assert projected[0]["horizon"] == contract["horizon_order"][0]
    assert projected[0]["mae"] == "-0x0.0p+0"
    expected = hashlib.sha256(json.dumps(
        projected, ensure_ascii=False, allow_nan=False, sort_keys=False,
        separators=(",", ":"),
    ).encode()).hexdigest()
    assert digest == expected


def test_metric_projection_rejects_wrong_types_and_duplicates():
    contract, rows = _metric_rows()
    rows[0]["eligible_count"] = True
    with pytest.raises(CanaryFailure, match="INVALID_METRIC_INTEGER"):
        canonical_metric_projection(rows, contract)
    _, rows = _metric_rows()
    rows[-1] = rows[0]
    with pytest.raises(CanaryFailure, match="DUPLICATE_METRIC"):
        canonical_metric_projection(rows, contract)


class _Cursor:
    def __init__(self, rows):
        self.rows = list(rows)
        self.executed = []
        self.itersize = None

    def execute(self, sql, params=None):
        self.executed.append((sql, params))

    def fetchmany(self, size):
        batch, self.rows = self.rows[:size], self.rows[size:]
        return batch

    def close(self):
        pass


class _Connection:
    def __init__(self, rows):
        self.setup = _Cursor(())
        self.stream = _Cursor(rows)

    def cursor(self, name=None):
        return self.stream if name else self.setup


def _stored_outcome(index, status):
    cutoff = datetime(2026, 6, 15, 14, 30, tzinfo=timezone.utc) + timedelta(seconds=index)
    available = status == "AVAILABLE"
    outcome = HistoricalOutcome(
        replay_run_id="frozen",
        cutoff_at=cutoff,
        horizon="30S",
        actual_return_bps=1.0 if available else None,
        availability_status=status,
        unavailable_reason=None if available else "TARGET_OUTSIDE_SESSION",
        cutoff_midpoint_at=cutoff,
        cutoff_midpoint=100.0,
        target_midpoint_at=cutoff + timedelta(seconds=30) if available else None,
        target_midpoint=101.0 if available else None,
        data_schema_version="test-data",
        source_schema_version="test-source",
        resolution_spec_version=RESOLUTION_SPEC_VERSION,
        outcome_source_dataset_digest="d" * 64,
        resolved_at=cutoff + timedelta(hours=1),
    )
    payload = outcome.payload()
    return tuple(payload[field] for field in OUTCOME_VERIFICATION_COLUMNS)


def test_read_only_outcome_receipt_streams_all_rows_in_frozen_order():
    rows = [_stored_outcome(0, "AVAILABLE"), _stored_outcome(1, "UNAVAILABLE"),
            _stored_outcome(2, "AVAILABLE")]
    hashes = [row[-1] for row in rows]
    connection = _Connection(rows)
    receipt = verify_outcomes(connection, "frozen", fetch_size=2)
    assert receipt.outcome_count == 3
    assert receipt.outcome_available_count == 2
    assert receipt.outcome_unavailable_count == 1
    assert receipt.outcome_ordered_content_sha256 == hashlib.sha256(
        "\n".join(hashes).encode(),
    ).hexdigest()
    sql = connection.stream.executed[0][0]
    assert "convert_to(horizon,'UTF8')" in sql
    assert all(word not in sql.upper() for word in ("INSERT", "UPDATE", "DELETE", "LOCK"))


@pytest.mark.parametrize("field,value", [
    ("availability_status", "BROKEN"),
    ("content_sha256", "A" * 64),
    ("actual_return_bps", 99.0),
])
def test_read_only_outcome_receipt_rejects_malformed_rows(field, value):
    row = list(_stored_outcome(0, "AVAILABLE"))
    row[OUTCOME_VERIFICATION_COLUMNS.index(field)] = value
    with pytest.raises(RuntimeError):
        verify_outcomes(_Connection([tuple(row)]), "frozen")


def _receipt(day):
    return {
        "historical_session": day,
        "parity_sha256": day.replace("-", ""),
        "evidence_snapshot": {"historical_session": day},
    }


def test_canary_runs_controls_one_at_a_time_then_exactly_two_and_orders_receipt():
    calls = []
    def runner(dates, *, timeout_seconds):
        calls.append((dates, timeout_seconds))
        return ([_receipt(day) for day in dates],
                [{"historical_session": day, "exit_code": 0, "peak_rss_kib": 10}
                 for day in dates])
    result = execute_canary(date_timeout_seconds=10, canary_timeout_seconds=30,
                            isolated_runner=runner,
                            snapshot_reader=lambda day: _receipt(day)["evidence_snapshot"])
    assert [call[0] for call in calls] == [
        (FROZEN_DATES[0],), (FROZEN_DATES[1],), FROZEN_DATES,
    ]
    assert result["status"] == "PASSED"
    assert result["historical_sessions"] == list(FROZEN_DATES)
    assert result["worker_limit"] == 2
    assert result["read_only"] is True and result["evidence_writes"] == 0


def test_canary_fails_on_any_parallel_parity_drift():
    calls = 0
    def runner(dates, *, timeout_seconds):
        nonlocal calls
        calls += 1
        receipts = [_receipt(day) for day in dates]
        if calls == 3:
            receipts[0] = receipts[0] | {"parity_sha256": "drift"}
        return receipts, [{"historical_session": day, "exit_code": 0,
                           "peak_rss_kib": 10} for day in dates]
    with pytest.raises(CanaryFailure, match="PARITY_DRIFT"):
        execute_canary(isolated_runner=runner)


def _hang(_day):
    time.sleep(5)
    return _receipt(_day)


def _fail_or_hang(day):
    if day == FROZEN_DATES[0]:
        raise RuntimeError("failed")
    time.sleep(5)
    return _receipt(day)


def test_worker_timeout_terminates_and_joins_the_process():
    started = time.monotonic()
    with pytest.raises(CanaryFailure, match="WORKER_TIMEOUT"):
        run_isolated((FROZEN_DATES[0],), timeout_seconds=0.05,
                     run_date=_hang, context=multiprocessing.get_context("fork"))
    assert time.monotonic() - started < 2


def test_worker_failure_stops_peer_immediately_and_reverse_pair_is_rejected():
    with pytest.raises(ValueError):
        run_isolated(tuple(reversed(FROZEN_DATES)), timeout_seconds=1,
                     context=multiprocessing.get_context("fork"))
    started = time.monotonic()
    with pytest.raises(CanaryFailure, match="WORKER_FAILED"):
        run_isolated(FROZEN_DATES, timeout_seconds=4, run_date=_fail_or_hang,
                     context=multiprocessing.get_context("fork"))
    assert time.monotonic() - started < 2


def test_read_only_date_builds_complete_frozen_projection(monkeypatch):
    bundle = json.loads(BASELINES.read_text())
    baseline = bundle["sessions"][0]
    family_rows = tuple(
        FamilyCoverage(
            quant_id=quant,
            horizon=horizon,
            total=baseline["frame_count"],
            available=baseline["forecast_available_count"] if index == 0 else 0,
            missing=baseline["forecast_unavailable_count"] if index == 0 else 0,
        )
        for index, (quant, horizon) in enumerate(
            (q, h) for q in bundle["metric_hash_contract"]["quant_order"]
            for h in bundle["metric_hash_contract"]["horizon_order"]
        )
    )
    resolution_rows = tuple(
        ResolutionCoverage(horizon, baseline["frame_count"], 0, 0, 0, 0, None, None)
        for horizon in bundle["metric_hash_contract"]["horizon_order"]
    )
    h1 = SimpleNamespace(
        runner_version="test-h1",
        evidence_origin="historical_test",
        historical_session=baseline["historical_session"],
        replay_run_id=baseline["replay_run_id"],
        dataset_digest=baseline["dataset_digest"],
        configuration_digest=baseline["configuration_digest"],
        session_digest=baseline["session_digest"],
        execution_stage="REPLAY_COMPLETE",
        data_status="CERTIFIED",
        data_reason_codes=(),
        frame_count=baseline["frame_count"],
        persistence_writes=0,
        family_coverage=family_rows,
        resolution_coverage=resolution_rows,
    )
    h1.to_dict = lambda: {
        "runner_version": h1.runner_version,
        "evidence_origin": h1.evidence_origin,
        "historical_session": h1.historical_session,
        "replay_run_id": h1.replay_run_id,
        "dataset_digest": h1.dataset_digest,
        "configuration_digest": h1.configuration_digest,
        "session_digest": h1.session_digest,
        "execution_stage": h1.execution_stage,
        "data_status": h1.data_status,
        "data_reason_codes": h1.data_reason_codes,
        "frame_count": h1.frame_count,
        "persistence_writes": h1.persistence_writes,
        "family_coverage": tuple(asdict(row) for row in family_rows),
        "resolution_coverage": tuple(asdict(row) for row in resolution_rows),
        "quote_counts": (("COIN", 1), ("QQQ", 1)),
        "frame_coverage": 1.0,
        "timings": {"total_seconds": 1.0},
        "replay_factor": 2.0,
        "projected_seconds": (("1D", 1.0),),
    }
    h2b = VerificationReceipt(
        baseline["replay_run_id"], baseline["historical_session"], "VERIFIED", (),
        1, baseline["frame_count"], baseline["forecast_count"],
        baseline["frame_count"], 12, 6, baseline["forecast_unavailable_count"],
        baseline["forecast_count"], 0, baseline["dataset_digest"],
        baseline["configuration_digest"], baseline["artifact_sha256"],
        "test-h2b", "2026-08-30T00:00:00+00:00", baseline["git_commit"],
        baseline["session_digest"], baseline["manifest_content_sha256"],
        baseline["forecast_ordered_content_sha256"],
    )
    outcomes = OutcomeVerificationReceipt(
        baseline["replay_run_id"], baseline["outcome_count"],
        baseline["outcome_available_count"], baseline["outcome_unavailable_count"],
        baseline["outcome_ordered_content_sha256"],
    )
    metrics = tuple(ScoreMetric(**row) for row in _metric_rows()[1])
    scoring = ScoringReceipt(
        baseline["replay_run_id"], baseline["dataset_digest"],
        baseline["configuration_digest"], baseline["forecast_count"],
        baseline["outcome_count"], metrics, "score-hash",
    )

    class Spool:
        def __enter__(self):
            return self

        def __exit__(self, *_args):
            return False

    import quant.historical_evidence as evidence_module
    import quant.historical_evidence_verifier as verifier_module
    import quant.historical_outcomes as outcomes_module
    import quant.historical_replay as replay_module
    import quant.historical_replay_h1 as h1_module

    monkeypatch.setattr(evidence_module, "HistoricalEvidenceSpool", Spool)
    monkeypatch.setattr(
        replay_module.AlpacaHistoricalSipReader,
        "from_environment",
        classmethod(lambda cls: object()),
    )
    monkeypatch.setattr(h1_module, "run_h1_session", lambda **_kwargs: h1)
    monkeypatch.setattr(verifier_module, "verify_from_environment", lambda *_a, **_k: h2b)
    monkeypatch.setattr(outcomes_module, "verify_outcomes_from_environment", lambda *_a: outcomes)
    monkeypatch.setattr(outcomes_module, "score_from_environment", lambda *_a: scoring)
    monkeypatch.setattr(
        canary,
        "_fresh_forecast_hashes",
        lambda _rows: (
            baseline["artifact_sha256"],
            baseline["forecast_ordered_content_sha256"],
        ),
    )

    receipt = canary.run_read_only_date(baseline["historical_session"])
    assert receipt["historical_session"] == baseline["historical_session"]
    assert receipt["evidence_snapshot"]["manifest_content_sha256"] == baseline["manifest_content_sha256"]
    assert receipt["score"]["metric_sha256"]
    assert len(receipt["score"]["metrics"]) == 72
    assert receipt["pre_post_unchanged"] is True
    assert receipt["h1"]["quote_counts"] == (("COIN", 1), ("QQQ", 1))
    assert "timings" not in receipt["h1"]
    assert canary.read_evidence_snapshot(baseline["historical_session"]) == receipt["evidence_snapshot"]


def test_canary_rejects_post_run_evidence_drift():
    def runner(dates, *, timeout_seconds):
        return ([_receipt(day) for day in dates],
                [{"historical_session": day, "exit_code": 0, "peak_rss_kib": 10}
                 for day in dates])

    with pytest.raises(CanaryFailure, match="POST_EVIDENCE_DRIFT"):
        execute_canary(
            isolated_runner=runner,
            snapshot_reader=lambda day: {"historical_session": day, "changed": True},
        )


def test_fresh_forecast_hashes_use_byte_order_with_no_trailing_separator():
    rows = [
        SimpleNamespace(cutoff_at=1, quant_id="q2", horizon="1M", content_sha256="b" * 64),
        SimpleNamespace(cutoff_at=1, quant_id="q1", horizon="30S", content_sha256="a" * 64),
        SimpleNamespace(cutoff_at=2, quant_id="q1", horizon="30S", content_sha256="c" * 64),
    ]
    artifact, ordered = canary._fresh_forecast_hashes(rows)
    assert artifact == hashlib.sha256((("b" * 64) + ("a" * 64) + ("c" * 64)).encode()).hexdigest()
    assert ordered == hashlib.sha256("\n".join(("a" * 64, "b" * 64, "c" * 64)).encode()).hexdigest()


def test_worker_reports_success_failure_and_closes_sender():
    class Sender:
        def __init__(self):
            self.messages = []
            self.closed = False

        def send(self, message):
            self.messages.append(message)

        def close(self):
            self.closed = True

    success = Sender()
    canary._worker(success, FROZEN_DATES[0], lambda day: {"day": day})
    assert success.closed and success.messages[0]["ok"] is True
    assert success.messages[0]["peak_rss_kib"] > 0

    failure = Sender()
    canary._worker(failure, FROZEN_DATES[1], lambda _day: (_ for _ in ()).throw(ValueError("bad")))
    assert failure.closed and failure.messages[0]["ok"] is False
    assert failure.messages[0]["error"] == "ValueError"


def test_canary_cli_emits_bounded_success_and_failure(monkeypatch, capsys):
    monkeypatch.setattr(canary, "execute_canary", lambda **_kwargs: {"status": "PASSED"})
    assert canary.main(()) == 0
    assert json.loads(capsys.readouterr().out)["status"] == "PASSED"

    def fail(**_kwargs):
        raise CanaryFailure("blocked")

    monkeypatch.setattr(canary, "execute_canary", fail)
    assert canary.main(()) == 1
    assert json.loads(capsys.readouterr().out)["status"] == "FAILED"
