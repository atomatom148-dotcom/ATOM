"""H2-D-8: qualify the first two frozen, absent historical targets."""

from __future__ import annotations

from contextlib import contextmanager
from datetime import date
import json
import math
import resource
import signal
import time
from typing import Callable, Iterable

from quant import historical_replay_h1 as h1


H2D8_VERSION = "H2-D-8"
FROZEN_TARGETS = (
    ("2026-08-10", "h2d-2026-08-10"),
    ("2026-08-11", "h2d-2026-08-11"),
    ("2026-08-12", "h2d-2026-08-12"),
    ("2026-08-13", "h2d-2026-08-13"),
    ("2026-08-14", "h2d-2026-08-14"),
    ("2026-08-17", "h2d-2026-08-17"),
    ("2026-08-18", "h2d-2026-08-18"),
    ("2026-08-19", "h2d-2026-08-19"),
    ("2026-08-20", "h2d-2026-08-20"),
    ("2026-08-21", "h2d-2026-08-21"),
    ("2026-08-24", "h2d-2026-08-24"),
    ("2026-08-25", "h2d-2026-08-25"),
    ("2026-08-26", "h2d-2026-08-26"),
    ("2026-08-27", "h2d-2026-08-27"),
    ("2026-08-28", "h2d-2026-08-28"),
    ("2026-08-31", "h2d-2026-08-31"),
)
MAX_QUALIFYING_TARGETS = 2
MAX_INTERIOR_GAP_SECONDS = 5
DEFAULT_TIMEOUT_SECONDS = 14_400.0
_NANOSECONDS = 1_000_000_000
_ABSENT = {
    "session_manifest_count": 0,
    "run_manifest_count": 0,
    "forecast_count": 0,
    "outcome_count": 0,
}


class TargetQualificationFailure(RuntimeError):
    """Fail-closed D8 error carrying the bounded receipt state."""

    def __init__(
        self, reason: str, *, inspected: Iterable[dict] = (),
        selected: Iterable[dict] = (), pre_post_unchanged: bool = False,
        elapsed_seconds: float = 0.0,
    ) -> None:
        super().__init__(reason)
        self.inspected = list(inspected)
        self.selected = list(selected)
        self.pre_post_unchanged = pre_post_unchanged
        self.elapsed_seconds = elapsed_seconds


def _remaining(deadline: float) -> float:
    remaining = deadline - time.monotonic()
    if remaining <= 0:
        raise TargetQualificationFailure("H2D8_TIMEOUT")
    return remaining


def _set_timeout(cursor: object, timeout_seconds: float) -> None:
    cursor.execute(
        "SELECT set_config('statement_timeout',%s,true)",
        (f"{max(1, int(timeout_seconds * 1_000))}ms",),
    )


@contextmanager
def _deadline(timeout_seconds: float, reason: str):
    def deadline_expired(_signum: int, _frame: object) -> None:
        raise TargetQualificationFailure(reason)

    previous_handler = signal.signal(signal.SIGALRM, deadline_expired)
    signal.setitimer(signal.ITIMER_REAL, timeout_seconds)
    try:
        yield
    finally:
        signal.setitimer(signal.ITIMER_REAL, 0)
        signal.signal(signal.SIGALRM, previous_handler)


def _read_target_counts(
    historical_session: str, replay_run_id: str, timeout_seconds: float,
) -> dict[str, int]:
    from quant.historical_evidence_verifier import (
        connect_score_reader_from_environment,
    )

    with _deadline(timeout_seconds, "H2D8_DATABASE_TIMEOUT"):
        with connect_score_reader_from_environment() as connection:
            cursor = connection.cursor()
            _set_timeout(cursor, timeout_seconds)
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
                (date.fromisoformat(historical_session), replay_run_id,
                 replay_run_id, replay_run_id),
            )
            row = cursor.fetchone()
            cursor.close()
    return dict(zip(_ABSENT, map(int, row), strict=True))


def _read_evidence_control(timeout_seconds: float) -> tuple[int, int, int]:
    from quant.historical_evidence_verifier import (
        connect_score_reader_from_environment,
    )

    with _deadline(timeout_seconds, "H2D8_DATABASE_TIMEOUT"):
        with connect_score_reader_from_environment() as connection:
            cursor = connection.cursor()
            _set_timeout(cursor, timeout_seconds)
            cursor.execute(
                "SELECT "
                "(SELECT count(*) FROM public.atom_historical_replay_runs),"
                "(SELECT count(*) FROM public.atom_historical_replay_forecasts),"
                "(SELECT count(*) FROM public.atom_historical_replay_outcomes)"
            )
            row = cursor.fetchone()
            cursor.close()
    return tuple(map(int, row))


def _run_preflight(reader: object, historical_session: str, timeout: float) -> dict:
    day = date.fromisoformat(historical_session)
    opened, closed = h1._session(day)

    with _deadline(timeout, "H2D8_PREFLIGHT_TIMEOUT"):
        return h1.run_h1_session(
            reader=reader,
            session_open=opened,
            session_close=closed,
            replay_run_id=f"h1-preflight-{historical_session}",
            preflight_only=True,
            maximum_interior_gap_seconds=MAX_INTERIOR_GAP_SECONDS,
        ).to_dict()


def _hex_digest(payload: dict, field: str) -> str:
    value = payload.get(field)
    if (not isinstance(value, str) or len(value) != 64 or
            any(character not in "0123456789abcdef" for character in value)):
        raise TargetQualificationFailure(f"H2D8_RECEIPT_{field.upper()}")
    return value


def _coin_gap_ns(payload: dict, *, allow_none: bool = False) -> int | None:
    coverage = payload.get("quote_coverage")
    if not isinstance(coverage, (list, tuple)):
        raise TargetQualificationFailure("H2D8_RECEIPT_QUOTE_COVERAGE")
    coin = [row for row in coverage
            if isinstance(row, dict) and row.get("symbol") == "COIN"]
    if len(coin) != 1:
        raise TargetQualificationFailure("H2D8_RECEIPT_COIN_COVERAGE")
    maximum_gap = coin[0].get("max_gap_ns")
    if maximum_gap is None and allow_none:
        return None
    if (isinstance(maximum_gap, bool) or
            not isinstance(maximum_gap, int) or maximum_gap < 0):
        raise TargetQualificationFailure("H2D8_RECEIPT_COIN_GAP")
    return maximum_gap


def _valid_lineage(payload: dict, historical_session: str) -> bool:
    day = date.fromisoformat(historical_session)
    opened, closed = h1._session(day)
    open_ns, close_ns = h1._ns(opened), h1._ns(closed)
    reasons = payload.get("data_reason_codes")
    counts = payload.get("quote_counts")
    if (not isinstance(counts, (list, tuple)) or
            tuple(row[0] for row in counts
                  if isinstance(row, (list, tuple)) and len(row) == 2) !=
            ("COIN", "QQQ") or
            any(not isinstance(row, (list, tuple)) or len(row) != 2 or
                isinstance(row[1], bool) or not isinstance(row[1], int) or
                row[1] < 0 for row in counts)):
        return False
    coverage = payload.get("quote_coverage")
    if (not isinstance(coverage, (list, tuple)) or len(coverage) != 2 or
            tuple(row.get("symbol") for row in coverage
                  if isinstance(row, dict)) != ("COIN", "QQQ") or
            any(row.get("count") != dict(counts)[row["symbol"]]
                for row in coverage)):
        return False
    expected_configuration = h1._configuration_digest(
        session_open_ns=open_ns, session_close_ns=close_ns,
    )
    expected_session = h1.canonical_sha256({
        "dataset_digest": payload.get("dataset_digest"),
        "configuration_digest": expected_configuration,
        "execution_stage": payload.get("execution_stage"),
        "data_status": payload.get("data_status"),
        "data_reason_codes": reasons,
        "quote_coverage": coverage,
        "retrieval_proof": payload.get("retrieval_proof"),
    })
    return (
        payload.get("runner_version") == h1.H1_RUNNER_VERSION and
        payload.get("replay_run_id") == f"h1-preflight-{historical_session}" and
        payload.get("session_open_ns") == open_ns and
        payload.get("session_close_ns") == close_ns and
        payload.get("configuration_digest") == expected_configuration and
        payload.get("session_digest") == expected_session and
        isinstance(reasons, (list, tuple)) and
        list(reasons) == sorted(set(reasons)) and
        h1._retrieval_proof_valid(
            payload.get("retrieval_proof"), open_ns=open_ns,
            close_ns=close_ns, retained_count=sum(row[1] for row in counts),
        )
    )


def _honest_rejection(payload: dict, historical_session: str) -> bool:
    reasons = payload.get("data_reason_codes")
    allowed_reasons = {
        "COIN_INSUFFICIENT_QUOTES", "COIN_OPEN_EDGE_GAP",
        "COIN_CLOSE_EDGE_GAP",
        *(f"{horizon}_ENDPOINT_GAP" for horizon in h1.HORIZONS),
    }
    return (
        payload.get("execution_stage") == "PREFLIGHT_REJECTED" and
        payload.get("data_status") == "DATA_INCOMPLETE" and
        isinstance(reasons, (list, tuple)) and reasons and
        set(reasons).issubset(allowed_reasons) and
        _valid_lineage(payload, historical_session)
    )


def _failed_candidate(
    historical_session: str, replay_run_id: str,
    absence_counts: dict[str, int] | None, reason: str,
) -> dict:
    return {
        "historical_session": historical_session,
        "replay_run_id": replay_run_id,
        "status": "FAILED",
        "reason_codes": [],
        "qualification_reason_codes": [reason],
        "result_source": None,
        "maximum_interior_gap_seconds": None,
        "frame_count": None,
        "dataset_digest": None,
        "configuration_digest": None,
        "session_digest": None,
        "absence_counts": absence_counts,
    }


def _candidate_receipt(
    historical_session: str, replay_run_id: str,
    absence_counts: dict[str, int], payload: dict,
) -> dict:
    if not isinstance(payload, dict):
        raise TargetQualificationFailure("H2D8_INVALID_H1_RECEIPT")
    if payload.get("historical_session") != historical_session:
        raise TargetQualificationFailure("H2D8_RECEIPT_SESSION")
    frame_count = payload.get("frame_count")
    if (isinstance(frame_count, bool) or not isinstance(frame_count, int) or
            frame_count != 0):
        raise TargetQualificationFailure("H2D8_RECEIPT_FRAME_COUNT")
    reason_codes = payload.get("data_reason_codes")
    if (not isinstance(reason_codes, (list, tuple)) or
            any(not isinstance(code, str) for code in reason_codes)):
        raise TargetQualificationFailure("H2D8_RECEIPT_REASON_CODES")
    stage = payload.get("execution_stage")
    data_status = payload.get("data_status")
    rejected_stage = stage == "PREFLIGHT_REJECTED"
    gap_ns = _coin_gap_ns(payload, allow_none=rejected_stage)
    qualification_reasons: list[str] = []

    if stage == "PREFLIGHT_ONLY" and data_status == "DATA_COMPLETE" and not reason_codes:
        if not _valid_lineage(payload, historical_session):
            raise TargetQualificationFailure("H2D8_LINEAGE_OR_RECEIPT_ERROR")
        if gap_ns > MAX_INTERIOR_GAP_SECONDS * _NANOSECONDS:
            status = "REJECTED"
            qualification_reasons.append("H2D8_COIN_INTERIOR_GAP")
        elif not h1._qualifies_cached_result(
            payload, day=date.fromisoformat(historical_session),
            maximum_gap_seconds=MAX_INTERIOR_GAP_SECONDS,
        ):
            raise TargetQualificationFailure("H2D8_LINEAGE_OR_RECEIPT_ERROR")
        else:
            status = "QUALIFYING"
    elif (stage == "PREFLIGHT_REJECTED" and
          data_status != "DATA_COMPLETE" and reason_codes and
          _honest_rejection(payload, historical_session)):
        status = "REJECTED"
    else:
        raise TargetQualificationFailure("H2D8_PROVIDER_SYSTEM_OR_RECEIPT_ERROR")

    return {
        "historical_session": historical_session,
        "replay_run_id": replay_run_id,
        "status": status,
        "reason_codes": list(reason_codes),
        "qualification_reason_codes": qualification_reasons,
        "result_source": "NEW_PREFLIGHT",
        "maximum_interior_gap_seconds": (
            None if gap_ns is None else gap_ns / _NANOSECONDS
        ),
        "frame_count": frame_count,
        "dataset_digest": _hex_digest(payload, "dataset_digest"),
        "configuration_digest": _hex_digest(payload, "configuration_digest"),
        "session_digest": _hex_digest(payload, "session_digest"),
        "absence_counts": dict(absence_counts),
    }


def _receipt(
    *, status: str, inspected: Iterable[dict], selected: Iterable[dict],
    pre_post_unchanged: bool, elapsed_seconds: float,
) -> dict:
    inspected_rows = list(inspected)
    selected_rows = list(selected)
    return {
        "target_qualification_version": H2D8_VERSION,
        "status": status,
        "inspected_candidates": inspected_rows,
        "selected_sessions": [row["historical_session"] for row in selected_rows],
        "selected_replay_run_ids": [row["replay_run_id"] for row in selected_rows],
        "manifest_writes": 0,
        "forecast_writes": 0,
        "persistence_writes": 0,
        "outcome_writes": 0,
        "pre_post_unchanged": pre_post_unchanged,
        "continuous_replay_enabled": False,
        "parallel_replay_enabled": False,
        "score_reader_role": "atom_historical_score_reader",
        "elapsed_seconds": round(elapsed_seconds, 6),
        "peak_rss_kib": resource.getrusage(resource.RUSAGE_SELF).ru_maxrss,
    }


def execute_target_qualification(
    *, timeout_seconds: float = DEFAULT_TIMEOUT_SECONDS,
    target_reader: Callable[[str, str, float], dict[str, int]] | None = None,
    preflight_runner: Callable[[str, float], dict] | None = None,
    control_reader: Callable[[float], object] | None = None,
) -> dict:
    if not math.isfinite(timeout_seconds) or timeout_seconds <= 0:
        raise ValueError("timeout_seconds must be positive and finite")
    target_reader = target_reader or _read_target_counts
    control_reader = control_reader or _read_evidence_control
    if preflight_runner is None:
        reader = None

        def default_preflight(day: str, timeout: float) -> dict:
            nonlocal reader
            if reader is None:
                from quant.historical_replay import AlpacaHistoricalSipReader
                reader = AlpacaHistoricalSipReader.from_environment()
            return _run_preflight(reader, day, timeout)

        preflight_runner = default_preflight

    started = time.monotonic()
    deadline = started + timeout_seconds
    inspected: list[dict] = []
    selected: list[dict] = []
    before = control_reader(_remaining(deadline))
    try:
        for historical_session, replay_run_id in FROZEN_TARGETS:
            try:
                counts = target_reader(
                    historical_session, replay_run_id, _remaining(deadline),
                )
            except Exception as error:
                inspected.append(_failed_candidate(
                    historical_session, replay_run_id, None,
                    f"H2D8_TARGET_READ_ERROR:{type(error).__name__}",
                ))
                raise
            if counts != _ABSENT:
                inspected.append(_failed_candidate(
                    historical_session, replay_run_id, counts,
                    "H2D8_TARGET_NOT_ABSENT",
                ))
                raise TargetQualificationFailure(
                    f"H2D8_TARGET_NOT_ABSENT:{historical_session}"
                )
            try:
                payload = preflight_runner(
                    historical_session, _remaining(deadline),
                )
                candidate = _candidate_receipt(
                    historical_session, replay_run_id, counts, payload,
                )
            except Exception as error:
                reason = (str(error)
                          if isinstance(error, TargetQualificationFailure)
                          else f"H2D8_RUNTIME_ERROR:{type(error).__name__}")
                inspected.append(_failed_candidate(
                    historical_session, replay_run_id, counts, reason,
                ))
                raise
            inspected.append(candidate)
            if candidate["status"] == "QUALIFYING":
                selected.append(candidate)
                if len(selected) == MAX_QUALIFYING_TARGETS:
                    break
    except Exception as error:
        remaining = deadline - time.monotonic()
        if remaining <= 0:
            reason = (str(error)
                      if isinstance(error, TargetQualificationFailure)
                      else f"H2D8_RUNTIME_ERROR:{type(error).__name__}")
            raise TargetQualificationFailure(
                reason, inspected=inspected, selected=selected,
                elapsed_seconds=time.monotonic() - started,
            ) from error
        try:
            unchanged = control_reader(remaining) == before
        except Exception as control_error:
            raise TargetQualificationFailure(
                f"H2D8_POST_CONTROL_ERROR:{type(control_error).__name__}",
                inspected=inspected, selected=selected,
                elapsed_seconds=time.monotonic() - started,
            ) from control_error
        if not unchanged:
            raise TargetQualificationFailure(
                "H2D8_EVIDENCE_DRIFT", inspected=inspected,
                selected=selected, elapsed_seconds=time.monotonic() - started,
            ) from error
        reason = str(error) if isinstance(error, TargetQualificationFailure) else (
            f"H2D8_RUNTIME_ERROR:{type(error).__name__}"
        )
        raise TargetQualificationFailure(
            reason, inspected=inspected, selected=selected,
            pre_post_unchanged=True,
            elapsed_seconds=time.monotonic() - started,
        ) from error

    try:
        unchanged = control_reader(_remaining(deadline)) == before
    except Exception as error:
        raise TargetQualificationFailure(
            f"H2D8_POST_CONTROL_ERROR:{type(error).__name__}",
            inspected=inspected, selected=selected,
            elapsed_seconds=time.monotonic() - started,
        ) from error
    if not unchanged:
        raise TargetQualificationFailure(
            "H2D8_EVIDENCE_DRIFT", inspected=inspected,
            selected=selected, elapsed_seconds=time.monotonic() - started,
        )
    if len(selected) != MAX_QUALIFYING_TARGETS:
        raise TargetQualificationFailure(
            "H2D8_TWO_TARGETS_NOT_QUALIFIED", inspected=inspected,
            selected=selected, pre_post_unchanged=True,
            elapsed_seconds=time.monotonic() - started,
        )
    return _receipt(
        status="PASSED", inspected=inspected, selected=selected,
        pre_post_unchanged=True, elapsed_seconds=time.monotonic() - started,
    )


def main(argv: Iterable[str] | None = None) -> int:
    import argparse

    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--timeout-seconds", type=float, default=DEFAULT_TIMEOUT_SECONDS,
    )
    args = parser.parse_args(None if argv is None else tuple(argv))
    try:
        receipt = execute_target_qualification(
            timeout_seconds=args.timeout_seconds,
        )
    except Exception as error:
        if isinstance(error, TargetQualificationFailure):
            inspected = error.inspected
            selected = error.selected
            pre_post_unchanged = error.pre_post_unchanged
            elapsed_seconds = error.elapsed_seconds
        else:
            inspected = []
            selected = []
            pre_post_unchanged = False
            elapsed_seconds = 0.0
        receipt = _receipt(
            status="FAILED", inspected=inspected, selected=selected,
            pre_post_unchanged=pre_post_unchanged,
            elapsed_seconds=elapsed_seconds,
        )
        receipt.update(reason=type(error).__name__, detail=str(error))
        print(json.dumps(receipt, sort_keys=True, separators=(",", ":")))
        return 1
    print(json.dumps(receipt, sort_keys=True, separators=(",", ":")))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
