"""H2-D-6: one frozen idempotent historical-persistence gate."""

from __future__ import annotations

from datetime import date
import json
import math
import resource
import time
from typing import Callable, Iterable

from . import historical_parallel_canary_h2d3 as h2d3
from . import historical_scaled_replay_h2d5 as h2d5


H2D6_VERSION = "H2-D-6"
FROZEN_SESSION = "2026-06-23"
FROZEN_RUN_ID = "h2d-2026-06-23"
FROZEN_FRAME_COUNT = 10_332
FROZEN_FORECAST_COUNT = 743_904
FROZEN_OUTCOME_COUNT = 61_992
FROZEN_METRIC_SHA256 = (
    "80758914447775d02f9a247ee1e5593714345434ab5204cd43eb65be4a47dc0c"
)
FROZEN_D5_CONTROL_SHA256 = (
    "30e0ed37295ae8ff9be29bf818af259165314860aeb5e6468a04ac2eadde6c6b"
)
DEFAULT_TIMEOUT_SECONDS = 10_800.0


class PersistenceGateFailure(RuntimeError):
    pass


def _require_equal(actual: object, expected: object, reason: str) -> None:
    if actual != expected:
        raise PersistenceGateFailure(reason)


def _read_control(timeout_seconds: float) -> tuple[dict, dict, str]:
    return h2d5._capture_control(
        FROZEN_SESSION, FROZEN_RUN_ID, timeout_seconds,
    )


def _require_frozen_control(snapshot: dict, score: dict,
                            control_sha256: str) -> None:
    _require_equal(snapshot["historical_session"], FROZEN_SESSION,
                   "H2D6_HISTORICAL_SESSION")
    _require_equal(snapshot["replay_run_id"], FROZEN_RUN_ID,
                   "H2D6_REPLAY_RUN_ID")
    _require_equal(snapshot["frame_count"], FROZEN_FRAME_COUNT,
                   "H2D6_FRAME_COUNT")
    _require_equal(snapshot["forecast_count"], FROZEN_FORECAST_COUNT,
                   "H2D6_FORECAST_COUNT")
    _require_equal(snapshot["outcome_count"], FROZEN_OUTCOME_COUNT,
                   "H2D6_OUTCOME_COUNT")
    _require_equal(score["metric_sha256"], FROZEN_METRIC_SHA256,
                   "H2D6_METRIC_HASH")
    _require_equal(len(score["metrics"]), 72, "H2D6_METRIC_COUNT")
    _require_equal(control_sha256, FROZEN_D5_CONTROL_SHA256,
                   "H2D6_D5_CONTROL_HASH")


def _replay_and_retry_forecasts(snapshot: dict) -> dict:
    from .historical_evidence import (
        HistoricalEvidenceSpool, HistoricalEvidenceWriter, build_manifest,
        connect_writer_from_environment,
    )
    from .historical_replay import AlpacaHistoricalSipReader
    from .historical_replay_h1 import _session, run_h1_session

    started = time.monotonic()
    opened, closed = _session(date.fromisoformat(FROZEN_SESSION))
    with HistoricalEvidenceSpool() as evidence:
        report = run_h1_session(
            reader=AlpacaHistoricalSipReader.from_environment(),
            session_open=opened,
            session_close=closed,
            replay_run_id=FROZEN_RUN_ID,
            maximum_interior_gap_seconds=5,
            forecast_evidence=evidence,
        )
        artifact_sha256, ordered_sha256 = h2d3._fresh_forecast_hashes(evidence)
        for field, expected in (
            ("historical_session", FROZEN_SESSION),
            ("replay_run_id", FROZEN_RUN_ID),
            ("dataset_digest", snapshot["dataset_digest"]),
            ("configuration_digest", snapshot["configuration_digest"]),
            ("session_digest", snapshot["session_digest"]),
            ("frame_count", FROZEN_FRAME_COUNT),
            ("execution_stage", "REPLAY_COMPLETE"),
            ("data_status", "CERTIFIED"),
            ("persistence_writes", 0),
        ):
            _require_equal(getattr(report, field), expected,
                           f"H2D6_H1_{field.upper()}")
        _require_equal(tuple(report.data_reason_codes), (),
                       "H2D6_H1_REASON_CODES")
        _require_equal(len(report.family_coverage), 72,
                       "H2D6_H1_FAMILY_COUNT")
        _require_equal(
            sum(row.available for row in report.family_coverage),
            snapshot["forecast_available_count"], "H2D6_H1_AVAILABLE_COUNT",
        )
        _require_equal(
            sum(row.missing for row in report.family_coverage),
            snapshot["forecast_unavailable_count"],
            "H2D6_H1_UNAVAILABLE_COUNT",
        )
        _require_equal(artifact_sha256, snapshot["artifact_sha256"],
                       "H2D6_H1_ARTIFACT_HASH")
        _require_equal(ordered_sha256,
                       snapshot["forecast_ordered_content_sha256"],
                       "H2D6_H1_ORDERED_HASH")
        manifest = build_manifest(
            report, evidence, git_commit=snapshot["git_commit"],
        )
        _require_equal(manifest.content_sha256,
                       snapshot["manifest_content_sha256"],
                       "H2D6_MANIFEST_HASH")
        with connect_writer_from_environment() as connection:
            writes = HistoricalEvidenceWriter(connection).persist(
                manifest, evidence, require_existing=True,
            )
    _require_equal(writes, 0, "H2D6_FORECAST_RETRY_WROTE_EVIDENCE")
    return {
        "forecast_writes": writes,
        "artifact_sha256": artifact_sha256,
        "forecast_ordered_content_sha256": ordered_sha256,
        "elapsed_seconds": round(time.monotonic() - started, 6),
    }


def _retry_outcomes(snapshot: dict) -> int:
    from .historical_outcomes import resolve_outcomes_from_environment

    return resolve_outcomes_from_environment(
        FROZEN_RUN_ID,
        expected_dataset_digest=snapshot["dataset_digest"],
        expected_configuration_digest=snapshot["configuration_digest"],
        expected_frame_count=FROZEN_FRAME_COUNT,
        require_existing=True,
    )


def execute_persistence_gate(
        *, timeout_seconds: float = DEFAULT_TIMEOUT_SECONDS,
        control_reader: Callable[[float], tuple[dict, dict, str]] | None = None,
        forecast_retry: Callable[[dict], dict] | None = None,
        outcome_retry: Callable[[dict], int] | None = None) -> dict:
    if not math.isfinite(timeout_seconds) or timeout_seconds <= 0:
        raise ValueError("timeout_seconds must be positive and finite")
    control_reader = control_reader or _read_control
    forecast_retry = forecast_retry or _replay_and_retry_forecasts
    outcome_retry = outcome_retry or _retry_outcomes
    started = time.monotonic()

    pre_snapshot, pre_score, pre_sha256 = control_reader(timeout_seconds)
    _require_frozen_control(pre_snapshot, pre_score, pre_sha256)
    forecast_receipt = forecast_retry(pre_snapshot)
    _require_equal(forecast_receipt["forecast_writes"], 0,
                   "H2D6_FORECAST_RETRY_WROTE_EVIDENCE")
    outcome_started = time.monotonic()
    outcome_writes = outcome_retry(pre_snapshot)
    outcome_seconds = time.monotonic() - outcome_started
    _require_equal(outcome_writes, 0,
                   "H2D6_OUTCOME_RETRY_WROTE_EVIDENCE")
    post_snapshot, post_score, post_sha256 = control_reader(timeout_seconds)
    _require_frozen_control(post_snapshot, post_score, post_sha256)
    _require_equal(post_snapshot, pre_snapshot, "H2D6_EVIDENCE_DRIFT")
    _require_equal(post_score, pre_score, "H2D6_SCORE_DRIFT")
    _require_equal(post_sha256, pre_sha256, "H2D6_CONTROL_DRIFT")

    return {
        "persistence_gate_version": H2D6_VERSION,
        "status": "PASSED",
        "historical_session": FROZEN_SESSION,
        "replay_run_id": FROZEN_RUN_ID,
        "frame_count": FROZEN_FRAME_COUNT,
        "forecast_count": FROZEN_FORECAST_COUNT,
        "outcome_count": FROZEN_OUTCOME_COUNT,
        "metric_sha256": FROZEN_METRIC_SHA256,
        "control_sha256": FROZEN_D5_CONTROL_SHA256,
        "artifact_sha256": forecast_receipt["artifact_sha256"],
        "forecast_ordered_content_sha256": (
            forecast_receipt["forecast_ordered_content_sha256"]
        ),
        "forecast_writes": 0,
        "outcome_writes": 0,
        "forecast_writer_role": "atom_historical_replay_writer",
        "outcome_resolver_role": "atom_historical_outcome_resolver",
        "score_reader_role": "atom_historical_score_reader",
        "pre_post_unchanged": True,
        "new_date_admission": False,
        "continuous_replay_enabled": False,
        "elapsed_seconds": round(time.monotonic() - started, 6),
        "replay_seconds": forecast_receipt["elapsed_seconds"],
        "outcome_retry_seconds": round(outcome_seconds, 6),
        "peak_rss_kib": resource.getrusage(resource.RUSAGE_SELF).ru_maxrss,
    }


def main(argv: Iterable[str] | None = None) -> int:
    import argparse

    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--timeout-seconds", type=float,
                        default=DEFAULT_TIMEOUT_SECONDS)
    args = parser.parse_args(None if argv is None else tuple(argv))
    try:
        receipt = execute_persistence_gate(timeout_seconds=args.timeout_seconds)
    except Exception as error:
        print(json.dumps({
            "persistence_gate_version": H2D6_VERSION,
            "status": "FAILED",
            "reason": type(error).__name__,
            "detail": str(error),
        }, sort_keys=True, separators=(",", ":")))
        return 1
    print(json.dumps(receipt, sort_keys=True, separators=(",", ":")))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
