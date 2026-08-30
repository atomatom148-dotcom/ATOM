import hashlib
import json
import multiprocessing
from pathlib import Path
import time

import pytest

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


def test_read_only_outcome_receipt_streams_all_rows_in_frozen_order():
    hashes = ["a" * 64, "b" * 64, "c" * 64]
    connection = _Connection([
        ("AVAILABLE", hashes[0]),
        ("UNAVAILABLE", hashes[1]),
        ("AVAILABLE", hashes[2]),
    ])
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


@pytest.mark.parametrize("row", [("BROKEN", "a" * 64), ("AVAILABLE", "A" * 64)])
def test_read_only_outcome_receipt_rejects_malformed_rows(row):
    with pytest.raises(RuntimeError):
        verify_outcomes(_Connection([row]), "frozen")


def _receipt(day):
    return {"historical_session": day, "parity_sha256": day.replace("-", "")}


def test_canary_runs_controls_one_at_a_time_then_exactly_two_and_orders_receipt():
    calls = []
    def runner(dates, *, timeout_seconds):
        calls.append((dates, timeout_seconds))
        return ([_receipt(day) for day in dates],
                [{"historical_session": day, "exit_code": 0, "peak_rss_kib": 10}
                 for day in dates])
    result = execute_canary(date_timeout_seconds=10, canary_timeout_seconds=30,
                            isolated_runner=runner)
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


def test_worker_timeout_terminates_and_joins_the_process():
    started = time.monotonic()
    with pytest.raises(CanaryFailure, match="WORKER_TIMEOUT"):
        run_isolated((FROZEN_DATES[0],), timeout_seconds=0.05,
                     run_date=_hang, context=multiprocessing.get_context("fork"))
    assert time.monotonic() - started < 2
