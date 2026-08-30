"""H2-D-3: bounded two-date, read-only historical parity canary."""

from __future__ import annotations

from dataclasses import asdict
from datetime import date
import hashlib
import json
import math
import multiprocessing
from multiprocessing.connection import wait
from pathlib import Path
import resource
import time
from typing import Callable, Iterable


H2D3_VERSION = "H2-D-3"
FROZEN_DATES = ("2026-06-15", "2026-07-22")
BASELINES = Path(__file__).resolve().parents[1] / "docs" / "h2-d2-canary-baselines.json"
DEFAULT_DATE_TIMEOUT_SECONDS = 7_200.0
DEFAULT_CANARY_TIMEOUT_SECONDS = 21_600.0
SNAPSHOT_FIELDS = (
    "historical_session", "replay_run_id", "git_commit", "dataset_digest",
    "configuration_digest", "session_digest", "artifact_sha256",
    "manifest_content_sha256", "forecast_ordered_content_sha256",
    "outcome_ordered_content_sha256", "frame_count", "forecast_count",
    "forecast_available_count", "forecast_unavailable_count", "outcome_count",
    "outcome_available_count", "outcome_unavailable_count",
)


class CanaryFailure(RuntimeError):
    pass


def _baseline_bundle(path: Path = BASELINES) -> tuple[dict, dict[str, dict]]:
    bundle = json.loads(path.read_text(encoding="utf-8"))
    sessions = {item["historical_session"]: item for item in bundle["sessions"]}
    if tuple(sessions) != FROZEN_DATES:
        raise CanaryFailure("H2D3_BASELINE_DATES_MISMATCH")
    return bundle, sessions


def canonical_metric_projection(metrics: Iterable[object], contract: dict) -> tuple[list[dict], str]:
    fields = contract["field_order"]
    by_identity: dict[tuple[str, str], dict] = {}
    for raw in metrics:
        row = asdict(raw) if hasattr(raw, "__dataclass_fields__") else dict(raw)
        if set(row) != set(fields):
            raise CanaryFailure("H2D3_METRIC_FIELDS_MISMATCH")
        identity = (row["quant_id"], row["horizon"])
        if identity in by_identity:
            raise CanaryFailure("H2D3_DUPLICATE_METRIC")
        by_identity[identity] = row

    expected = [(quant, horizon) for quant in contract["quant_order"]
                for horizon in contract["horizon_order"]]
    if set(by_identity) != set(expected) or len(by_identity) != 72:
        raise CanaryFailure("H2D3_METRIC_IDENTITIES_MISMATCH")

    projected = []
    integer_fields = set(contract["integer_fields"])
    nullable_integer_fields = set(contract["nullable_integer_fields"])
    nullable_float_fields = set(contract["nullable_float_fields"])
    required_float_fields = set(contract["required_float_fields"])
    for identity in expected:
        source = by_identity[identity]
        output = {}
        for field in fields:
            value = source[field]
            if field in integer_fields:
                if isinstance(value, bool) or not isinstance(value, int):
                    raise CanaryFailure("H2D3_INVALID_METRIC_INTEGER")
            elif field in nullable_integer_fields:
                if value is not None and (isinstance(value, bool) or not isinstance(value, int)):
                    raise CanaryFailure("H2D3_INVALID_METRIC_INTEGER")
            elif field in nullable_float_fields | required_float_fields:
                if value is None and field in nullable_float_fields:
                    pass
                elif not isinstance(value, float) or not math.isfinite(value):
                    raise CanaryFailure("H2D3_INVALID_METRIC_FLOAT")
                else:
                    value = value.hex()
            output[field] = value
        projected.append(output)

    encoding = contract["json_encoding"]
    serialized = json.dumps(
        projected,
        ensure_ascii=encoding["ensure_ascii"],
        allow_nan=encoding["allow_nan"],
        sort_keys=encoding["sort_keys"],
        separators=(encoding["item_separator"], encoding["key_separator"]),
    ).encode("utf-8")
    return projected, hashlib.sha256(serialized).hexdigest()


def _require_equal(actual: object, expected: object, reason: str) -> None:
    if actual != expected:
        raise CanaryFailure(reason)


def _fresh_forecast_hashes(rows) -> tuple[str, str]:
    artifact = hashlib.sha256()
    ordered = hashlib.sha256()
    first = True
    current_cutoff = None
    cutoff_hashes = {}

    def flush() -> None:
        nonlocal first
        for key in sorted(cutoff_hashes, key=lambda item: (item[0].encode(), item[1].encode())):
            if not first:
                ordered.update(b"\n")
            ordered.update(cutoff_hashes[key].encode("ascii"))
            first = False

    for row in rows:
        artifact.update(row.content_sha256.encode("ascii"))
        if current_cutoff is None:
            current_cutoff = row.cutoff_at
        elif row.cutoff_at != current_cutoff:
            flush()
            cutoff_hashes = {}
            current_cutoff = row.cutoff_at
        cutoff_hashes[(row.quant_id, row.horizon)] = row.content_sha256
    if cutoff_hashes:
        flush()
    return artifact.hexdigest(), ordered.hexdigest()


def _frozen_evidence_snapshot(baseline: dict) -> dict:
    return {field: baseline[field] for field in SNAPSHOT_FIELDS}


def _observed_evidence_snapshot(h2b, outcomes) -> dict:
    _require_equal(outcomes.replay_run_id, h2b.replay_run_id,
                   "H2D3_EVIDENCE_RECEIPT_CORRELATION")
    return {
        "historical_session": h2b.historical_session,
        "replay_run_id": h2b.replay_run_id,
        "git_commit": h2b.git_commit,
        "dataset_digest": h2b.dataset_digest,
        "configuration_digest": h2b.configuration_digest,
        "session_digest": h2b.session_digest,
        "artifact_sha256": h2b.stored_content_hash_summary,
        "manifest_content_sha256": h2b.manifest_content_sha256,
        "forecast_ordered_content_sha256": h2b.forecast_ordered_content_sha256,
        "outcome_ordered_content_sha256": outcomes.outcome_ordered_content_sha256,
        "frame_count": h2b.frame_count,
        "forecast_count": h2b.forecast_count,
        "forecast_available_count": h2b.forecast_count - h2b.unavailable_null_count,
        "forecast_unavailable_count": h2b.unavailable_null_count,
        "outcome_count": outcomes.outcome_count,
        "outcome_available_count": outcomes.outcome_available_count,
        "outcome_unavailable_count": outcomes.outcome_unavailable_count,
    }


def read_evidence_snapshot(day: str) -> dict:
    """Read and verify the post-canary evidence state without running V9."""
    _, baselines = _baseline_bundle()
    if day not in baselines:
        raise CanaryFailure("H2D3_DATE_NOT_FROZEN")
    baseline = baselines[day]
    from .historical_evidence_verifier import verify_from_environment
    from .historical_outcomes import verify_outcomes_from_environment

    h2b = verify_from_environment(
        baseline["replay_run_id"],
        expected_dataset_digest=baseline["dataset_digest"],
        expected_configuration_digest=baseline["configuration_digest"],
        expected_frame_count=baseline["frame_count"],
    )
    _require_equal(h2b.verification_status, "VERIFIED", "H2D3_POST_H2B_REJECTED")
    _require_equal(h2b.reason_codes, (), "H2D3_POST_H2B_REASON_CODES")
    outcomes = verify_outcomes_from_environment(baseline["replay_run_id"])
    observed = _observed_evidence_snapshot(h2b, outcomes)
    _require_equal(observed, _frozen_evidence_snapshot(baseline),
                   "H2D3_POST_EVIDENCE_SNAPSHOT_DRIFT")
    return observed


def run_read_only_date(day: str) -> dict:
    """Run H1/H2B/H2C verification/scoring in-process without persistence."""
    bundle, baselines = _baseline_bundle()
    if day not in baselines:
        raise CanaryFailure("H2D3_DATE_NOT_FROZEN")
    baseline = baselines[day]

    from .historical_evidence_verifier import verify_from_environment
    from .historical_evidence import HistoricalEvidenceSpool
    from .historical_outcomes import (score_from_environment,
                                      verify_outcomes_from_environment)
    from .historical_replay import AlpacaHistoricalSipReader
    from .historical_replay_h1 import _session, run_h1_session

    opened, closed = _session(date.fromisoformat(day))
    with HistoricalEvidenceSpool() as evidence:
        h1 = run_h1_session(
            reader=AlpacaHistoricalSipReader.from_environment(),
            session_open=opened,
            session_close=closed,
            replay_run_id=baseline["replay_run_id"],
            maximum_interior_gap_seconds=5,
            forecast_evidence=evidence,
        )
        fresh_artifact_sha256, fresh_forecast_ordered_sha256 = _fresh_forecast_hashes(evidence)
    for field, expected in (
        ("historical_session", day),
        ("replay_run_id", baseline["replay_run_id"]),
        ("dataset_digest", baseline["dataset_digest"]),
        ("configuration_digest", baseline["configuration_digest"]),
        ("session_digest", baseline["session_digest"]),
        ("frame_count", baseline["frame_count"]),
        ("execution_stage", "REPLAY_COMPLETE"),
        ("data_status", "CERTIFIED"),
        ("persistence_writes", 0),
    ):
        _require_equal(getattr(h1, field), expected, f"H2D3_H1_{field.upper()}_MISMATCH")
    _require_equal(tuple(h1.data_reason_codes), (), "H2D3_H1_REASON_CODES")
    _require_equal(len(h1.family_coverage), 72, "H2D3_H1_FAMILY_COUNT")
    _require_equal(sum(row.available for row in h1.family_coverage),
                   baseline["forecast_available_count"], "H2D3_H1_AVAILABLE_COUNT")
    _require_equal(sum(row.missing for row in h1.family_coverage),
                   baseline["forecast_unavailable_count"], "H2D3_H1_UNAVAILABLE_COUNT")
    _require_equal(fresh_artifact_sha256, baseline["artifact_sha256"],
                   "H2D3_H1_ARTIFACT_HASH")
    _require_equal(fresh_forecast_ordered_sha256,
                   baseline["forecast_ordered_content_sha256"],
                   "H2D3_H1_FORECAST_ORDERED_HASH")

    h2b = verify_from_environment(
        baseline["replay_run_id"],
        expected_dataset_digest=baseline["dataset_digest"],
        expected_configuration_digest=baseline["configuration_digest"],
        expected_frame_count=baseline["frame_count"],
    )
    _require_equal(h2b.verification_status, "VERIFIED", "H2D3_H2B_REJECTED")
    _require_equal(h2b.reason_codes, (), "H2D3_H2B_REASON_CODES")
    _require_equal(h2b.forecast_count, baseline["forecast_count"], "H2D3_FORECAST_COUNT")
    _require_equal(h2b.unavailable_null_count, baseline["forecast_unavailable_count"],
                   "H2D3_FORECAST_AVAILABILITY")
    _require_equal(h2b.stored_content_hash_summary, baseline["artifact_sha256"],
                   "H2D3_FORECAST_CONTENT_HASH")
    _require_equal(h2b.git_commit, baseline["git_commit"], "H2D3_GIT_COMMIT")
    _require_equal(h2b.session_digest, baseline["session_digest"], "H2D3_MANIFEST_SESSION")
    _require_equal(h2b.manifest_content_sha256, baseline["manifest_content_sha256"],
                   "H2D3_MANIFEST_CONTENT_HASH")
    _require_equal(h2b.forecast_ordered_content_sha256,
                   baseline["forecast_ordered_content_sha256"],
                   "H2D3_FORECAST_ORDERED_CONTENT_HASH")

    outcomes = verify_outcomes_from_environment(baseline["replay_run_id"])
    for field in ("outcome_count", "outcome_available_count",
                  "outcome_unavailable_count", "outcome_ordered_content_sha256"):
        _require_equal(getattr(outcomes, field), baseline[field],
                       f"H2D3_{field.upper()}_MISMATCH")

    scoring = score_from_environment(baseline["replay_run_id"])
    _require_equal(scoring.dataset_digest, baseline["dataset_digest"], "H2D3_SCORE_DATASET")
    _require_equal(scoring.configuration_digest, baseline["configuration_digest"],
                   "H2D3_SCORE_CONFIGURATION")
    _require_equal(scoring.forecast_count, baseline["forecast_count"], "H2D3_SCORE_FORECASTS")
    _require_equal(scoring.outcome_count, baseline["outcome_count"], "H2D3_SCORE_OUTCOMES")
    metric_rows, metric_sha256 = canonical_metric_projection(
        scoring.metrics, bundle["metric_hash_contract"],
    )

    frozen_snapshot = _frozen_evidence_snapshot(baseline)
    observed_snapshot = _observed_evidence_snapshot(h2b, outcomes)
    _require_equal(observed_snapshot, frozen_snapshot, "H2D3_EVIDENCE_SNAPSHOT_DRIFT")

    h1_projection = h1.to_dict()
    for performance_field in ("timings", "replay_factor", "projected_seconds"):
        h1_projection.pop(performance_field, None)
    h1_projection["artifact_sha256"] = fresh_artifact_sha256
    h1_projection["forecast_ordered_content_sha256"] = fresh_forecast_ordered_sha256
    h2b_projection = h2b.payload()
    h2b_projection.pop("verified_at", None)
    projection = {
        "historical_session": day,
        "replay_run_id": baseline["replay_run_id"],
        "evidence_snapshot": observed_snapshot,
        "pre_post_unchanged": True,
        "h1": h1_projection,
        "h2b": h2b_projection,
        "h2c": outcomes.payload(),
        "score": {
            "dataset_digest": scoring.dataset_digest,
            "configuration_digest": scoring.configuration_digest,
            "forecast_count": scoring.forecast_count,
            "outcome_count": scoring.outcome_count,
            "scorer_version": scoring.scorer_version,
            "content_hash_summary": scoring.content_hash_summary,
            "metric_sha256": metric_sha256,
            "metrics": metric_rows,
        },
    }
    projection["parity_sha256"] = hashlib.sha256(json.dumps(
        projection, sort_keys=True, separators=(",", ":"),
    ).encode("utf-8")).hexdigest()
    return projection


def _worker(send, day: str, run_date: Callable[[str], dict]) -> None:
    try:
        receipt = run_date(day)
        send.send({"ok": True, "day": day, "receipt": receipt,
                   "peak_rss_kib": resource.getrusage(resource.RUSAGE_SELF).ru_maxrss})
    except BaseException as error:
        send.send({"ok": False, "day": day, "error": type(error).__name__,
                   "message": str(error),
                   "peak_rss_kib": resource.getrusage(resource.RUSAGE_SELF).ru_maxrss})
    finally:
        send.close()


def _stop_processes(processes) -> None:
    for process in processes:
        if process.is_alive():
            process.terminate()
    for process in processes:
        process.join(5)
    for process in processes:
        if process.is_alive():
            process.kill()
            process.join(5)
    if any(process.is_alive() for process in processes):
        raise CanaryFailure("H2D3_WORKER_SURVIVED_CLEANUP")


def run_isolated(dates: tuple[str, ...], *, timeout_seconds: float,
                 run_date: Callable[[str], dict] = run_read_only_date,
                 context=None) -> tuple[list[dict], list[dict]]:
    if (not dates or len(dates) > 2 or len(set(dates)) != len(dates) or
            any(day not in FROZEN_DATES for day in dates) or
            (len(dates) == 2 and dates != FROZEN_DATES)):
        raise ValueError("one or two unique dates are required")
    if not math.isfinite(timeout_seconds) or timeout_seconds <= 0:
        raise ValueError("timeout_seconds must be positive and finite")
    ctx = context or multiprocessing.get_context("spawn")
    processes = []
    receivers = {}
    started = time.monotonic()
    try:
        for day in dates:
            receive, send = ctx.Pipe(duplex=False)
            process = ctx.Process(target=_worker, args=(send, day, run_date),
                                  name=f"h2d3-{day}")
            process.start()
            send.close()
            processes.append(process)
            receivers[receive] = day
        messages = {}
        while receivers:
            remaining = timeout_seconds - (time.monotonic() - started)
            if remaining <= 0:
                raise CanaryFailure("H2D3_WORKER_TIMEOUT")
            ready = wait(tuple(receivers), timeout=remaining)
            if not ready:
                raise CanaryFailure("H2D3_WORKER_TIMEOUT")
            for receive in ready:
                day = receivers.pop(receive)
                try:
                    message = receive.recv()
                    messages[day] = message
                    if not message["ok"]:
                        raise CanaryFailure(
                            f"H2D3_WORKER_FAILED:{day}:{message['error']}:{message['message']}"
                        )
                except EOFError as error:
                    raise CanaryFailure(f"H2D3_WORKER_EOF:{day}") from error
                finally:
                    receive.close()
        for process in processes:
            remaining = max(0.0, timeout_seconds - (time.monotonic() - started))
            process.join(remaining)
            if process.is_alive():
                raise CanaryFailure("H2D3_WORKER_TIMEOUT")
        statuses = [{"historical_session": day, "exit_code": process.exitcode,
                     "peak_rss_kib": messages[day]["peak_rss_kib"]}
                    for day, process in zip(dates, processes, strict=True)]
        if any(item["exit_code"] != 0 for item in statuses):
            raise CanaryFailure("H2D3_WORKER_EXIT_NONZERO")
        return [messages[day]["receipt"] for day in dates], statuses
    except BaseException:
        _stop_processes(processes)
        raise
    finally:
        for receive in tuple(receivers):
            receive.close()


def execute_canary(*, date_timeout_seconds: float = DEFAULT_DATE_TIMEOUT_SECONDS,
                   canary_timeout_seconds: float = DEFAULT_CANARY_TIMEOUT_SECONDS,
                   isolated_runner: Callable[..., tuple[list[dict], list[dict]]] = run_isolated,
                   snapshot_reader: Callable[[str], dict] | None = None) -> dict:
    if (not math.isfinite(date_timeout_seconds) or date_timeout_seconds <= 0 or
            not math.isfinite(canary_timeout_seconds) or canary_timeout_seconds <= 0):
        raise ValueError("timeouts must be positive and finite")
    started = time.monotonic()
    snapshot_reader = snapshot_reader or read_evidence_snapshot
    controls = []
    control_statuses = []
    sequential_started = time.monotonic()
    for day in FROZEN_DATES:
        remaining = canary_timeout_seconds - (time.monotonic() - started)
        if remaining <= 0:
            raise CanaryFailure("H2D3_CANARY_TIMEOUT")
        rows, statuses = isolated_runner((day,), timeout_seconds=min(date_timeout_seconds, remaining))
        controls.extend(rows)
        control_statuses.extend(statuses)
    sequential_seconds = time.monotonic() - sequential_started

    remaining = canary_timeout_seconds - (time.monotonic() - started)
    if remaining <= 0:
        raise CanaryFailure("H2D3_CANARY_TIMEOUT")
    parallel_started = time.monotonic()
    parallel, parallel_statuses = isolated_runner(
        FROZEN_DATES, timeout_seconds=min(date_timeout_seconds, remaining),
    )
    parallel_seconds = time.monotonic() - parallel_started
    for expected, actual in zip(controls, parallel, strict=True):
        if expected != actual:
            raise CanaryFailure(f"H2D3_PARITY_DRIFT:{expected['historical_session']}")

    post_snapshots = []
    for control in controls:
        if canary_timeout_seconds - (time.monotonic() - started) <= 0:
            raise CanaryFailure("H2D3_CANARY_TIMEOUT")
        observed = snapshot_reader(control["historical_session"])
        _require_equal(observed, control["evidence_snapshot"],
                       f"H2D3_POST_EVIDENCE_DRIFT:{control['historical_session']}")
        post_snapshots.append(observed)
    snapshot_sha256 = [hashlib.sha256(json.dumps(
        snapshot, sort_keys=True, separators=(",", ":"),
    ).encode("utf-8")).hexdigest() for snapshot in post_snapshots]

    return {
        "canary_version": H2D3_VERSION,
        "status": "PASSED",
        "historical_sessions": list(FROZEN_DATES),
        "worker_limit": 2,
        "read_only": True,
        "evidence_writes": 0,
        "pre_post_unchanged": True,
        "surviving_workers": 0,
        "sequential_seconds": round(sequential_seconds, 6),
        "parallel_seconds": round(parallel_seconds, 6),
        "speedup": None if parallel_seconds == 0 else sequential_seconds / parallel_seconds,
        "session_parity_sha256": [row["parity_sha256"] for row in parallel],
        "evidence_snapshot_sha256": snapshot_sha256,
        "control_worker_statuses": control_statuses,
        "parallel_worker_statuses": parallel_statuses,
        "peak_worker_rss_kib": max(
            item["peak_rss_kib"] for item in control_statuses + parallel_statuses
        ),
    }


def main(argv: Iterable[str] | None = None) -> int:
    import argparse

    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--date-timeout-seconds", type=float,
                        default=DEFAULT_DATE_TIMEOUT_SECONDS)
    parser.add_argument("--canary-timeout-seconds", type=float,
                        default=DEFAULT_CANARY_TIMEOUT_SECONDS)
    args = parser.parse_args(None if argv is None else tuple(argv))
    try:
        receipt = execute_canary(
            date_timeout_seconds=args.date_timeout_seconds,
            canary_timeout_seconds=args.canary_timeout_seconds,
        )
    except Exception as error:
        print(json.dumps({"canary_version": H2D3_VERSION, "status": "FAILED",
                          "reason": type(error).__name__, "detail": str(error)},
                         sort_keys=True, separators=(",", ":")))
        return 1
    print(json.dumps(receipt, sort_keys=True, separators=(",", ":")))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
