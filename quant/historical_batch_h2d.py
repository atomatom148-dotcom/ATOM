"""H2-D bounded, sequential orchestration of the frozen historical pipeline.

This module deliberately contains no replay, resolution, or scoring logic.  Each
stage is invoked through its frozen command-line interface and only one session's
JSON receipts are retained at a time.
"""
from __future__ import annotations

import argparse
from datetime import date, timedelta, timezone, datetime
import hashlib
import json
import os
import resource
import subprocess
import sys
import time
from typing import Callable, Iterable

H2D_VERSION = "H2-D-1"
DEFAULT_MAX_SESSIONS = 20


class StageFailure(RuntimeError):
    def __init__(self, stage: str, reason: str, payload: dict | None = None):
        super().__init__(f"{stage}:{reason}")
        self.stage, self.reason, self.payload = stage, reason, payload or {}


def requested_dates(*, dates: Iterable[str] | None, start: str | None,
                    end: str | None, maximum: int, today: date | None = None) -> tuple[date, ...]:
    """Validate an explicit list or inclusive range without consulting live data."""
    if isinstance(maximum, bool) or maximum < 1:
        raise ValueError("maximum sessions must be positive")
    values = tuple(dates or ())
    if bool(values) == bool(start or end):
        raise ValueError("provide either --dates or both --start and --end")
    try:
        if values:
            result = tuple(date.fromisoformat(value) for value in values)
            if len(set(result)) != len(result):
                raise ValueError("duplicate dates are not allowed")
        else:
            if not start or not end:
                raise ValueError("both --start and --end are required")
            first, last = date.fromisoformat(start), date.fromisoformat(end)
            if first > last:
                raise ValueError("start date must not follow end date")
            result = tuple(first + timedelta(days=offset)
                           for offset in range((last - first).days + 1))
    except (TypeError, ValueError) as error:
        raise ValueError(f"invalid date selection: {error}") from error
    if len(result) > maximum:
        raise ValueError(f"maximum-session guard exceeded ({len(result)} > {maximum})")
    current = today or datetime.now(timezone.utc).date()
    if any(day > current for day in result):
        raise ValueError("future sessions are not allowed")
    return result


def _run_json(command: list[str], stage: str) -> dict:
    completed = subprocess.run(command, text=True, capture_output=True)
    lines = completed.stdout.strip().splitlines()
    try:
        payload = json.loads(lines[-1]) if lines else {}
    except json.JSONDecodeError as error:
        raise StageFailure(stage, "INVALID_JSON_OUTPUT") from error
    if completed.returncode:
        raise StageFailure(stage, f"EXIT_{completed.returncode}", payload)
    return payload


def _existing_manifests(day: date) -> tuple[dict[str, object], ...]:
    url = os.environ.get("HISTORICAL_EVIDENCE_DATABASE_URL")
    if not url:
        raise RuntimeError("HISTORICAL_EVIDENCE_DATABASE_URL is required")
    import psycopg
    with psycopg.connect(url) as connection:
        connection.read_only = True
        with connection.cursor() as cursor:
            cursor.execute(
                "SELECT replay_run_id,dataset_digest,configuration_digest,frame_count "
                "FROM public.atom_historical_replay_runs "
                "WHERE historical_session=%s ORDER BY replay_run_id", (day,))
            return tuple({"replay_run_id": row[0], "dataset_digest": row[1],
                          "configuration_digest": row[2], "frame_count": row[3]}
                         for row in cursor.fetchall())


def _digest(payload: object) -> str:
    return hashlib.sha256(json.dumps(payload, sort_keys=True, separators=(",", ":"),
                                     default=str).encode()).hexdigest()


def execute(days: tuple[date, ...], *, continue_on_failure: bool,
            run_json: Callable[[list[str], str], dict] = _run_json,
            existing: Callable[[date], tuple[dict[str, object], ...]] = _existing_manifests) -> dict:
    receipt: dict[str, object] = {
        "orchestrator_version": H2D_VERSION,
        "requested_dates": [day.isoformat() for day in days],
        "completed": [], "skipped": [], "rejected": [], "failed": [],
        "replay_run_ids": [], "sessions": [],
    }
    py = sys.executable
    for day in days:
        session_started = time.monotonic()
        stages: dict[str, float] = {}
        item: dict[str, object] = {"session": day.isoformat(), "state": "REQUESTED"}
        try:
            # Weekends are closed under the existing RTH session convention.  Other
            # exchange closures flow through H1's frozen quote-coverage decision.
            if day.weekday() >= 5:
                item.update(state="REJECTED", reason="MARKET_CLOSED_WEEKEND")
                receipt["rejected"].append(day.isoformat())
                receipt["sessions"].append(item)
                continue
            manifests = existing(day)
            if len(manifests) > 1:
                raise StageFailure("EXISTING", "CONFLICTING_SESSION_RUNS")
            known = bool(manifests)
            manifest = manifests[0] if known else None
            run_id = str(manifest["replay_run_id"]) if manifest else f"h2d-{day.isoformat()}"
            item["replay_run_id"] = run_id
            receipt["replay_run_ids"].append(run_id)
            if not known:
                started = time.monotonic()
                h1 = run_json([py, "-m", "quant.historical_replay_h1", day.isoformat(),
                    "--run-id", run_id, "--max-interior-gap-seconds", "5",
                    "--persist-certified"], "H1")
                stages["h1_seconds"] = round(time.monotonic() - started, 6)
                if h1.get("execution_stage") != "REPLAY_COMPLETE" or h1.get("data_status") != "CERTIFIED":
                    raise StageFailure("H1", "NOT_CERTIFIED", h1)
                manifest = {key: h1.get(key) for key in
                            ("dataset_digest", "configuration_digest", "frame_count")}
            dataset_digest = manifest.get("dataset_digest")
            configuration_digest = manifest.get("configuration_digest")
            frame_count = manifest.get("frame_count")
            if (not isinstance(dataset_digest, str) or not isinstance(configuration_digest, str)
                    or isinstance(frame_count, bool) or not isinstance(frame_count, int)
                    or frame_count < 1):
                raise StageFailure("MANIFEST", "INVALID_SESSION_LINEAGE")
            started = time.monotonic()
            verified = run_json([py, "-m", "quant.historical_evidence_verifier", run_id,
                "--dataset-digest", dataset_digest, "--configuration-digest", configuration_digest,
                "--frame-count", str(frame_count)], "H2B")
            stages["h2b_seconds"] = round(time.monotonic() - started, 6)
            expected_forecasts = frame_count * 72
            if (verified.get("verification_status") != "VERIFIED" or
                    verified.get("manifest_count") != 1 or
                    verified.get("frame_count") != frame_count or
                    verified.get("forecast_count") != expected_forecasts or
                    verified.get("quant_count") != 12 or
                    verified.get("horizon_count") != 6 or
                    verified.get("dataset_digest") != dataset_digest or
                    verified.get("configuration_digest") != configuration_digest):
                raise StageFailure("H2B", "VERIFIED_RECEIPT_MISMATCH", verified)
            item.update(forecast_count=verified.get("forecast_count"),
                        dataset_digest=verified.get("dataset_digest"),
                        configuration_digest=verified.get("configuration_digest"),
                        forecast_hash_summary=verified.get("stored_content_hash_summary"))
            started = time.monotonic()
            outcome = run_json([py, "-m", "quant.historical_outcomes", "resolve-outcomes", run_id,
                "--dataset-digest", dataset_digest, "--configuration-digest", configuration_digest,
                "--frame-count", str(frame_count)], "H2C_RESOLVE")
            stages["h2c_resolution_seconds"] = round(time.monotonic() - started, 6)
            started = time.monotonic()
            scoring = run_json([py, "-m", "quant.historical_outcomes", "score", run_id], "H2C_SCORE")
            stages["scoring_seconds"] = round(time.monotonic() - started, 6)
            if (len(scoring.get("metrics", ())) != 72 or
                    scoring.get("forecast_count") != expected_forecasts or
                    scoring.get("dataset_digest") != dataset_digest or
                    scoring.get("configuration_digest") != configuration_digest):
                raise StageFailure("H2C_SCORE", "SCORING_RECEIPT_MISMATCH", scoring)
            state = "SKIPPED_VERIFIED" if known else "COMPLETED"
            item.update(state=state, outcome_count=scoring.get("outcome_count"),
                        metrics_count=len(scoring.get("metrics", ())),
                        outcome_writes=outcome.get("inserted"),
                        scoring_hash_summary=scoring.get("content_hash_summary"),
                        stage_timings=stages,
                        elapsed_seconds=round(time.monotonic() - session_started, 6))
            item["receipt_sha256"] = _digest(item)
            receipt["skipped" if known else "completed"].append(day.isoformat())
            receipt["sessions"].append(item)
        except Exception as error:
            stage = error.stage if isinstance(error, StageFailure) else "ORCHESTRATOR"
            reason = error.reason if isinstance(error, StageFailure) else type(error).__name__
            item.update(state="FAILED", failed_stage=stage, reason=reason,
                        stage_timings=stages,
                        elapsed_seconds=round(time.monotonic() - session_started, 6))
            receipt["failed"].append(day.isoformat())
            receipt["sessions"].append(item)
            if not continue_on_failure:
                break
    receipt["peak_rss_kib"] = resource.getrusage(resource.RUSAGE_CHILDREN).ru_maxrss
    receipt["overall_status"] = "FAILED" if receipt["failed"] else "COMPLETED"
    receipt["receipt_sha256"] = _digest(receipt)
    return receipt


def main(argv: Iterable[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    selection = parser.add_mutually_exclusive_group(required=True)
    selection.add_argument("--dates", nargs="+", metavar="YYYY-MM-DD")
    selection.add_argument("--start", metavar="YYYY-MM-DD")
    parser.add_argument("--end", metavar="YYYY-MM-DD")
    parser.add_argument("--max-sessions", type=int, default=DEFAULT_MAX_SESSIONS)
    parser.add_argument("--persist-certified", action="store_true",
                        help="required explicit authorization for append-only writes")
    parser.add_argument("--continue-on-failure", action="store_true")
    args = parser.parse_args(tuple(argv) if argv is not None else None)
    if not args.persist_certified:
        parser.error("--persist-certified is required")
    try:
        days = requested_dates(dates=args.dates, start=args.start, end=args.end,
                               maximum=args.max_sessions)
    except ValueError as error:
        parser.error(str(error))
    output = execute(days, continue_on_failure=args.continue_on_failure)
    print(json.dumps(output, sort_keys=True, separators=(",", ":")))
    return 1 if output["overall_status"] == "FAILED" else 0


if __name__ == "__main__":
    raise SystemExit(main())
