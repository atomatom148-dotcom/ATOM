"""H2-D-7: admit one frozen historical session through existing seams."""

from __future__ import annotations

from datetime import date
import json
import math
import resource
import subprocess
import time
from typing import Callable, Iterable

from . import historical_batch_h2d as batch
from . import historical_scaled_replay_h2d5 as h2d5


H2D7_VERSION = "H2-D-7"
FROZEN_SESSION = "2026-07-23"
FROZEN_RUN_ID = "h2d-2026-07-23"
DEFAULT_TIMEOUT_SECONDS = 10_800.0


class NewSessionCanaryFailure(RuntimeError):
    pass


def _require_equal(actual: object, expected: object, reason: str) -> None:
    if actual != expected:
        raise NewSessionCanaryFailure(reason)


def _remaining(deadline: float) -> float:
    value = deadline - time.monotonic()
    if value <= 0:
        raise NewSessionCanaryFailure("H2D7_TIMEOUT")
    return value


def _read_target_counts(timeout_seconds: float) -> dict[str, int]:
    from .historical_evidence_verifier import connect_score_reader_from_environment

    with connect_score_reader_from_environment() as connection:
        cursor = connection.cursor()
        cursor.execute(
            "SELECT set_config('statement_timeout',%s,true)",
            (f"{max(1, int(timeout_seconds * 1_000))}ms",),
        )
        cursor.execute(
            "SELECT "
            "(SELECT count(*) FROM public.atom_historical_replay_runs "
            " WHERE historical_session=%s),"
            "(SELECT count(*) FROM public.atom_historical_replay_runs "
            " WHERE replay_run_id=%s),"
            "(SELECT count(*) FROM public.atom_historical_replay_forecasts "
            " WHERE replay_run_id=%s),"
            "(SELECT count(*) FROM public.atom_historical_replay_outcomes "
            " WHERE replay_run_id=%s)",
            (date.fromisoformat(FROZEN_SESSION), FROZEN_RUN_ID,
             FROZEN_RUN_ID, FROZEN_RUN_ID),
        )
        row = cursor.fetchone()
        cursor.close()
    return dict(zip((
        "session_manifest_count", "run_manifest_count",
        "forecast_count", "outcome_count",
    ), map(int, row), strict=True))


def _run_frozen_batch(timeout_seconds: float) -> tuple[dict, dict[str, dict]]:
    deadline = time.monotonic() + timeout_seconds
    stage_receipts: dict[str, dict] = {}

    def run_json(command: list[str], stage: str) -> dict:
        if stage in stage_receipts:
            raise NewSessionCanaryFailure("H2D7_DUPLICATE_STAGE")
        if stage == "H2B":
            from .historical_evidence_verifier import verify_from_score_environment

            h1 = stage_receipts.get("H1", {})
            payload = verify_from_score_environment(
                FROZEN_RUN_ID,
                statement_timeout_seconds=_remaining(deadline),
                expected_dataset_digest=h1.get("dataset_digest"),
                expected_configuration_digest=h1.get("configuration_digest"),
                expected_frame_count=h1.get("frame_count"),
            ).payload()
        else:
            completed = subprocess.run(
                command, text=True, capture_output=True,
                timeout=_remaining(deadline),
            )
            lines = completed.stdout.strip().splitlines()
            try:
                payload = json.loads(lines[-1]) if lines else {}
            except json.JSONDecodeError as error:
                raise batch.StageFailure(stage, "INVALID_JSON_OUTPUT") from error
            if completed.returncode:
                stage_receipts[stage] = payload
                raise batch.StageFailure(
                    stage, f"EXIT_{completed.returncode}", payload,
                )
        stage_receipts[stage] = payload
        return payload

    receipt = batch.execute(
        (date.fromisoformat(FROZEN_SESSION),),
        continue_on_failure=False,
        run_json=run_json,
        existing=lambda _day: (),
    )
    return receipt, stage_receipts


def _read_control(timeout_seconds: float) -> tuple[dict, dict, str]:
    return h2d5._capture_control(FROZEN_SESSION, FROZEN_RUN_ID, timeout_seconds)


def execute_new_session_canary(
        *, timeout_seconds: float = DEFAULT_TIMEOUT_SECONDS,
        target_reader: Callable[[float], dict[str, int]] | None = None,
        batch_runner: Callable[[float], tuple[dict, dict[str, dict]]] | None = None,
        control_reader: Callable[[float], tuple[dict, dict, str]] | None = None,
) -> dict:
    if not math.isfinite(timeout_seconds) or timeout_seconds <= 0:
        raise ValueError("timeout_seconds must be positive and finite")
    target_reader = target_reader or _read_target_counts
    batch_runner = batch_runner or _run_frozen_batch
    control_reader = control_reader or _read_control
    started = time.monotonic()
    deadline = started + timeout_seconds

    before = target_reader(_remaining(deadline))
    _require_equal(before, {
        "session_manifest_count": 0,
        "run_manifest_count": 0,
        "forecast_count": 0,
        "outcome_count": 0,
    }, "H2D7_TARGET_NOT_ABSENT")

    batch_receipt, stages = batch_runner(_remaining(deadline))
    _remaining(deadline)
    if batch_receipt.get("overall_status") != "COMPLETED":
        failed_session = next(
            (item for item in batch_receipt.get("sessions", ())
             if item.get("state") == "FAILED"),
            {},
        )
        failed_stage = failed_session.get("failed_stage", "UNKNOWN")
        failed_payload = stages.get(failed_stage, {})
        h1_detail = ""
        if failed_stage == "H1":
            h1_detail = (
                f":{failed_payload.get('data_status', 'UNKNOWN')}:"
                f"{','.join(failed_payload.get('data_reason_codes', ()))}"
            )
        raise NewSessionCanaryFailure(
            "H2D7_BATCH_STATUS:"
            f"{failed_stage}:{failed_session.get('reason', 'UNKNOWN')}"
            f"{h1_detail}"
        )
    for field, expected in (
        ("requested_dates", [FROZEN_SESSION]),
        ("completed", [FROZEN_SESSION]),
        ("skipped", []), ("rejected", []), ("failed", []),
        ("replay_run_ids", [FROZEN_RUN_ID]),
    ):
        _require_equal(batch_receipt.get(field), expected,
                       f"H2D7_BATCH_{field.upper()}")
    _require_equal(tuple(stages), ("H1", "H2B", "H2C_RESOLVE", "H2C_SCORE"),
                   "H2D7_STAGE_SEQUENCE")
    _require_equal(len(batch_receipt.get("sessions", ())), 1,
                   "H2D7_SESSION_COUNT")

    session = batch_receipt["sessions"][0]
    h1 = stages["H1"]
    frame_count = h1.get("frame_count")
    if isinstance(frame_count, bool) or not isinstance(frame_count, int) or frame_count < 1:
        raise NewSessionCanaryFailure("H2D7_FRAME_COUNT")
    forecast_writes = frame_count * 72
    outcome_writes = frame_count * 6
    for field, expected in (
        ("historical_session", FROZEN_SESSION),
        ("replay_run_id", FROZEN_RUN_ID),
        ("execution_stage", "REPLAY_COMPLETE"),
        ("data_status", "CERTIFIED"),
        ("data_reason_codes", []),
        ("persistence_writes", 1 + forecast_writes),
    ):
        _require_equal(h1.get(field), expected, f"H2D7_H1_{field.upper()}")
    _require_equal(len(h1.get("family_coverage", ())), 72,
                   "H2D7_H1_FAMILY_COUNT")
    for field, expected in (
        ("state", "COMPLETED"),
        ("replay_run_id", FROZEN_RUN_ID),
        ("forecast_count", forecast_writes),
        ("outcome_count", outcome_writes),
        ("outcome_writes", outcome_writes),
        ("metrics_count", 72),
    ):
        _require_equal(session.get(field), expected,
                       f"H2D7_SESSION_{field.upper()}")
    _require_equal(stages["H2C_RESOLVE"].get("inserted"), outcome_writes,
                   "H2D7_OUTCOME_WRITES")

    snapshot, score, control_sha256 = control_reader(_remaining(deadline))
    for field, expected in (
        ("historical_session", FROZEN_SESSION),
        ("replay_run_id", FROZEN_RUN_ID),
        ("frame_count", frame_count),
        ("forecast_count", forecast_writes),
        ("outcome_count", outcome_writes),
        ("dataset_digest", h1.get("dataset_digest")),
        ("configuration_digest", h1.get("configuration_digest")),
        ("session_digest", h1.get("session_digest")),
    ):
        _require_equal(snapshot.get(field), expected,
                       f"H2D7_CONTROL_{field.upper()}")
    _require_equal(score.get("forecast_count"), forecast_writes,
                   "H2D7_SCORE_FORECAST_COUNT")
    _require_equal(score.get("outcome_count"), outcome_writes,
                   "H2D7_SCORE_OUTCOME_COUNT")
    _require_equal(len(score.get("metrics", ())), 72,
                   "H2D7_SCORE_METRIC_COUNT")

    return {
        "new_session_canary_version": H2D7_VERSION,
        "status": "PASSED",
        "historical_session": FROZEN_SESSION,
        "replay_run_id": FROZEN_RUN_ID,
        "git_commit": snapshot["git_commit"],
        "dataset_digest": snapshot["dataset_digest"],
        "configuration_digest": snapshot["configuration_digest"],
        "session_digest": snapshot["session_digest"],
        "frame_count": frame_count,
        "forecast_count": forecast_writes,
        "outcome_count": outcome_writes,
        "manifest_writes": 1,
        "forecast_writes": forecast_writes,
        "persistence_writes": 1 + forecast_writes,
        "outcome_writes": outcome_writes,
        "artifact_sha256": snapshot["artifact_sha256"],
        "manifest_content_sha256": snapshot["manifest_content_sha256"],
        "forecast_ordered_content_sha256": (
            snapshot["forecast_ordered_content_sha256"]
        ),
        "outcome_ordered_content_sha256": (
            snapshot["outcome_ordered_content_sha256"]
        ),
        "metric_sha256": score["metric_sha256"],
        "scoring_content_sha256": score["content_hash_summary"],
        "control_sha256": control_sha256,
        "forecast_writer_role": "atom_historical_replay_writer",
        "outcome_resolver_role": "atom_historical_outcome_resolver",
        "score_reader_role": "atom_historical_score_reader",
        "new_date_admission": True,
        "continuous_replay_enabled": False,
        "parallel_replay_enabled": False,
        "stage_timings": session["stage_timings"],
        "elapsed_seconds": round(time.monotonic() - started, 6),
        "peak_rss_kib": max(
            resource.getrusage(resource.RUSAGE_SELF).ru_maxrss,
            int(batch_receipt.get("peak_rss_kib", 0)),
        ),
    }


def main(argv: Iterable[str] | None = None) -> int:
    import argparse

    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--timeout-seconds", type=float,
                        default=DEFAULT_TIMEOUT_SECONDS)
    args = parser.parse_args(None if argv is None else tuple(argv))
    try:
        receipt = execute_new_session_canary(timeout_seconds=args.timeout_seconds)
    except Exception as error:
        print(json.dumps({
            "new_session_canary_version": H2D7_VERSION,
            "status": "FAILED",
            "reason": type(error).__name__,
            "detail": str(error),
        }, sort_keys=True, separators=(",", ":")))
        return 1
    print(json.dumps(receipt, sort_keys=True, separators=(",", ":")))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
