"""H2-D-5: one bounded four-date, read-only scaled replay proof."""

from __future__ import annotations

import hashlib
import json
import math
from pathlib import Path
import time
from typing import Callable, Iterable

from . import historical_parallel_canary_h2d3 as h2d3


H2D5_VERSION = "H2-D-5"
FROZEN_SESSIONS = (
    ("2026-06-17", "h2d-2026-06-17"),
    ("2026-06-18", "h2d-2026-06-18"),
    ("2026-06-22", "h2d-2026-06-22"),
    ("2026-06-23", "h2d-2026-06-23"),
)
FROZEN_DATES = tuple(day for day, _run_id in FROZEN_SESSIONS)
RUN_IDS = dict(FROZEN_SESSIONS)
CONTRACT = Path(__file__).resolve().parents[1] / "docs" / "h2-d2-canary-baselines.json"
DEFAULT_DATE_TIMEOUT_SECONDS = 7_200.0
DEFAULT_SCALE_TIMEOUT_SECONDS = 21_600.0


class ScaledReplayFailure(RuntimeError):
    pass


def _sha256(payload: object) -> str:
    return hashlib.sha256(json.dumps(
        payload, sort_keys=True, separators=(",", ":"),
    ).encode("utf-8")).hexdigest()


def _metric_contract() -> dict:
    return json.loads(CONTRACT.read_text(encoding="utf-8"))["metric_hash_contract"]


def _capture_control(day: str, replay_run_id: str,
                     timeout_seconds: float) -> tuple[dict, dict, str]:
    if not math.isfinite(timeout_seconds) or timeout_seconds <= 0:
        raise ValueError("timeout_seconds must be positive and finite")
    deadline = time.monotonic() + timeout_seconds

    def remaining() -> float:
        value = deadline - time.monotonic()
        if value <= 0:
            raise ScaledReplayFailure("H2D5_CONTROL_TIMEOUT")
        return value

    from .historical_evidence_verifier import verify_from_environment
    from .historical_outcomes import (score_from_environment,
                                      verify_outcomes_from_environment)

    h2b = h2d3._retry_database_read(
        verify_from_environment, replay_run_id,
        retry_result=h2d3._database_interrupted,
        statement_timeout_seconds=remaining(),
    )
    h2d3._require_equal(h2b.verification_status, "VERIFIED", "H2D5_H2B_REJECTED")
    h2d3._require_equal(h2b.reason_codes, (), "H2D5_H2B_REASON_CODES")
    h2d3._require_equal(h2b.historical_session, day, "H2D5_HISTORICAL_SESSION")
    h2d3._require_equal(h2b.replay_run_id, replay_run_id, "H2D5_REPLAY_RUN_ID")
    h2d3._require_equal(h2b.forecast_count, h2b.frame_count * 72,
                       "H2D5_FORECAST_COUNT")
    h2d3._require_equal((h2b.quant_count, h2b.horizon_count), (12, 6),
                       "H2D5_IDENTITIES")

    outcomes = h2d3._retry_database_read(
        verify_outcomes_from_environment, replay_run_id,
        statement_timeout_seconds=remaining(),
    )
    h2d3._require_equal(outcomes.outcome_count, h2b.frame_count * 6,
                       "H2D5_OUTCOME_COUNT")
    scoring = h2d3._retry_database_read(score_from_environment, replay_run_id)
    remaining()
    h2d3._require_equal(scoring.dataset_digest, h2b.dataset_digest,
                       "H2D5_SCORE_DATASET")
    h2d3._require_equal(scoring.configuration_digest, h2b.configuration_digest,
                       "H2D5_SCORE_CONFIGURATION")
    h2d3._require_equal(scoring.forecast_count, h2b.forecast_count,
                       "H2D5_SCORE_FORECASTS")
    h2d3._require_equal(scoring.outcome_count, outcomes.outcome_count,
                       "H2D5_SCORE_OUTCOMES")
    metrics, metric_sha256 = h2d3.canonical_metric_projection(
        scoring.metrics, _metric_contract(),
    )
    snapshot = h2d3._observed_evidence_snapshot(h2b, outcomes)
    score = {
        "dataset_digest": scoring.dataset_digest,
        "configuration_digest": scoring.configuration_digest,
        "forecast_count": scoring.forecast_count,
        "outcome_count": scoring.outcome_count,
        "scorer_version": scoring.scorer_version,
        "content_hash_summary": scoring.content_hash_summary,
        "metric_sha256": metric_sha256,
        "metrics": metrics,
    }
    control_sha256 = _sha256({"evidence_snapshot": snapshot, "score": score})
    return snapshot, score, control_sha256


def run_scaled_date(day: str) -> dict:
    """Recompute one frozen session against its current immutable control."""
    if day not in RUN_IDS:
        raise ScaledReplayFailure("H2D5_DATE_NOT_FROZEN")
    snapshot, score, control_sha256 = _capture_control(
        day, RUN_IDS[day], DEFAULT_DATE_TIMEOUT_SECONDS,
    )
    receipt = h2d3.run_read_only_session(day, snapshot, _metric_contract())
    h2d3._require_equal(receipt["score"], score, "H2D5_SCORE_PARITY_DRIFT")
    receipt["stored_control_sha256"] = control_sha256
    return receipt


def read_control_sha256(day: str, timeout_seconds: float) -> str:
    if day not in RUN_IDS:
        raise ScaledReplayFailure("H2D5_DATE_NOT_FROZEN")
    return _capture_control(day, RUN_IDS[day], timeout_seconds)[2]


def _default_isolated_runner(dates: tuple[str, ...], *, timeout_seconds: float):
    return h2d3.run_isolated(
        dates, timeout_seconds=timeout_seconds, run_date=run_scaled_date,
        allowed_dates=FROZEN_DATES, process_name="h2d5",
    )


def execute_scaled_replay(
        *, date_timeout_seconds: float = DEFAULT_DATE_TIMEOUT_SECONDS,
        scale_timeout_seconds: float = DEFAULT_SCALE_TIMEOUT_SECONDS,
        isolated_runner: Callable[..., tuple[list[dict], list[dict]]] | None = None,
        post_reader: Callable[[str, float], str] = read_control_sha256) -> dict:
    if (not math.isfinite(date_timeout_seconds) or date_timeout_seconds <= 0 or
            not math.isfinite(scale_timeout_seconds) or scale_timeout_seconds <= 0):
        raise ValueError("timeouts must be positive and finite")
    isolated_runner = isolated_runner or _default_isolated_runner
    started = time.monotonic()
    receipts: list[dict] = []
    statuses: list[dict] = []
    batch_seconds: list[float] = []
    batches = (FROZEN_DATES[:2], FROZEN_DATES[2:])
    for batch in batches:
        remaining = scale_timeout_seconds - (time.monotonic() - started)
        if remaining <= 0:
            raise ScaledReplayFailure("H2D5_SCALE_TIMEOUT")
        batch_started = time.monotonic()
        rows, worker_statuses = isolated_runner(
            batch, timeout_seconds=min(date_timeout_seconds, remaining),
        )
        receipts.extend(rows)
        statuses.extend(worker_statuses)
        batch_seconds.append(time.monotonic() - batch_started)

    post_control_sha256 = []
    for receipt in receipts:
        remaining = scale_timeout_seconds - (time.monotonic() - started)
        if remaining <= 0:
            raise ScaledReplayFailure("H2D5_SCALE_TIMEOUT")
        observed = post_reader(receipt["historical_session"], remaining)
        h2d3._require_equal(
            observed, receipt["stored_control_sha256"],
            f"H2D5_POST_CONTROL_DRIFT:{receipt['historical_session']}",
        )
        post_control_sha256.append(observed)

    return {
        "scaled_replay_version": H2D5_VERSION,
        "status": "PASSED",
        "historical_sessions": list(FROZEN_DATES),
        "replay_run_ids": [RUN_IDS[day] for day in FROZEN_DATES],
        "batch_count": 2,
        "batch_size": 2,
        "worker_limit": 2,
        "read_only": True,
        "evidence_writes": 0,
        "pre_post_unchanged": True,
        "surviving_workers": 0,
        "elapsed_seconds": round(time.monotonic() - started, 6),
        "batch_seconds": [round(value, 6) for value in batch_seconds],
        "session_receipts": [{
            "historical_session": row["historical_session"],
            "replay_run_id": row["replay_run_id"],
            "frame_count": row["evidence_snapshot"]["frame_count"],
            "forecast_count": row["evidence_snapshot"]["forecast_count"],
            "outcome_count": row["evidence_snapshot"]["outcome_count"],
            "metric_sha256": row["score"]["metric_sha256"],
            "parity_sha256": row["parity_sha256"],
            "stored_control_sha256": row["stored_control_sha256"],
        } for row in receipts],
        "session_parity_sha256": [row["parity_sha256"] for row in receipts],
        "stored_control_sha256": post_control_sha256,
        "worker_statuses": statuses,
        "peak_worker_rss_kib": max(item["peak_rss_kib"] for item in statuses),
    }


def main(argv: Iterable[str] | None = None) -> int:
    import argparse

    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--date-timeout-seconds", type=float,
                        default=DEFAULT_DATE_TIMEOUT_SECONDS)
    parser.add_argument("--scale-timeout-seconds", type=float,
                        default=DEFAULT_SCALE_TIMEOUT_SECONDS)
    args = parser.parse_args(None if argv is None else tuple(argv))
    try:
        receipt = execute_scaled_replay(
            date_timeout_seconds=args.date_timeout_seconds,
            scale_timeout_seconds=args.scale_timeout_seconds,
        )
    except Exception as error:
        print(json.dumps({"scaled_replay_version": H2D5_VERSION, "status": "FAILED",
                          "reason": type(error).__name__, "detail": str(error)},
                         sort_keys=True, separators=(",", ":")))
        return 1
    print(json.dumps(receipt, sort_keys=True, separators=(",", ":")))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
