"""Read-only one-session H1 runner for ATOM TRUE V9 historical replay.

The runner keeps all evidence in memory.  It does not import a database
writer, the production runtime, Render wiring, or SIM code.
"""

from __future__ import annotations

import argparse
from bisect import bisect_left
from collections import deque
from dataclasses import asdict, dataclass, replace
from datetime import date, datetime, time as datetime_time, timezone
import hashlib
import json
import math
import os
from pathlib import Path
import subprocess
import time
from typing import Callable, Iterable
from zoneinfo import ZoneInfo

from .historical_replay import (
    ALLOWED_FORMULA_VERSIONS, DATA_SCHEMA_VERSION, EVIDENCE_ORIGIN,
    MAX_TARGET_RESOLUTION_DELAY_SECONDS, REPLAY_METHOD_VERSION, SOURCE,
    TARGET_SPEC_ID, AlpacaHistoricalSipReader, HistoricalSipQuote,
    HistoricalSipRetrievalProof, OneSessionReplayClock, ReplayFamilyResults,
    ReplayFrame, build_replay_v2_as_of,
)
from .q1_momentum import calculate_momentum
from .q2_mean_reversion import calculate_mean_reversion
from .q3_volatility import calculate_volatility
from .q4_stat_arb import calculate_stat_arb
from .q5_microstructure import calculate_microstructure
from .q6_volume_liquidity import calculate_volume_liquidity
from .q7_relative_value import calculate_relative_value
from .q8_cross_asset import calculate_cross_asset
from .q9_factor import calculate_factor
from .q10_options_vol import FORMULA_VERSION as Q10_VERSION
from .q11_regime import calculate_regime
from .q12_event_session import calculate_event_session
from .v9_v1_contract import (
    DIRECTIONAL_BPS, HORIZONS, HORIZON_SECONDS, MAGNITUDE_BPS, QUANT_IDS,
    V1SlotObservation, build_v1_input, v1_input_hash,
)
from .v9_v2a_dataset import (
    MAGNITUDE_BPS as V2_MAGNITUDE_BPS, RawFamilyObservation, RawTarget,
    TargetIdentity,
)
from .v9_v3_synthesis import synthesize_v3
from .v9_v4a_evidence import canonical_sha256


H1_RUNNER_VERSION = "ATOM-TRUE-V9-H1-RUNNER-5"
_NANOSECONDS = 1_000_000_000
_REFRESH_NS = 3_600 * _NANOSECONDS
_COMPLETE_EDGE_NS = 5 * _NANOSECONDS
_COMPLETE_GAP_NS = 5 * _NANOSECONDS
_MAX_TARGET_RESOLUTION_DELAY_NS = round(
    MAX_TARGET_RESOLUTION_DELAY_SECONDS * _NANOSECONDS
)
_EASTERN = ZoneInfo("America/New_York")
_Q10 = "q10_options_vol"
_RESULT_NAMES = {
    "q1_momentum": "q1_momentum",
    "q2_mean_reversion": "q2_mean_reversion",
    "q3_volatility": "q3_volatility",
    "q4_stat_arb": "q4_stat_arb",
    "q5_microstructure": "q5_microstructure",
    "q6_volume_liquidity": "q6_volume_liquidity",
    "q7_relative_value": "q7_relative_value",
    "q8_cross_asset": "q8_cross_asset",
    "q9_factor": "q9_factor",
    "q11_regime": "q11_regime",
    "q12_event_session": "q12_event_session",
}
_FORMULA_VERSIONS = {**ALLOWED_FORMULA_VERSIONS, _Q10: Q10_VERSION}
_SYMBOL_ORDER = {"COIN": 0, "QQQ": 1}


@dataclass(frozen=True, slots=True)
class FamilyCoverage:
    quant_id: str
    horizon: str
    total: int
    available: int
    missing: int


@dataclass(frozen=True, slots=True)
class QuoteCoverage:
    symbol: str
    count: int
    first_quote_ns: int | None
    last_quote_ns: int | None
    first_quote_delay_ns: int | None
    last_quote_lead_ns: int | None
    p99_gap_ns: int | None
    max_gap_ns: int | None
    max_gap_start_ns: int | None
    max_gap_end_ns: int | None
    max_gap_start_utc: str | None
    max_gap_end_utc: str | None
    max_gap_previous_quote_ns: int | None
    max_gap_next_quote_ns: int | None
    max_gap_touches_rth_start: bool
    max_gap_touches_rth_end: bool
    configured_max_gap_ns: int
    over_limit_gap_count: int


@dataclass(frozen=True, slots=True)
class V3Coverage:
    horizon: str
    total: int
    mature: int
    provisional: int
    unavailable: int


@dataclass(frozen=True, slots=True)
class ResolutionCoverage:
    horizon: str
    forecasts: int
    session_eligible: int
    session_unavailable: int
    resolved: int
    unresolved: int
    p99_endpoint_delay_ns: int | None
    max_endpoint_delay_ns: int | None


@dataclass(frozen=True, slots=True)
class ResolutionSample:
    cycle_id: str
    horizon: str
    maturity_ns: int
    previous_observation_ns: int
    endpoint_observation_ns: int
    resolution_cutoff_ns: int
    endpoint_delay_ns: int
    actual_return_bps: float


@dataclass(frozen=True, slots=True)
class V2RefreshProof:
    anchor_ns: int
    capture_cutoff_ns: int
    state_as_of_ns: int
    resolved_target_count: int
    max_resolved_epoch: float | None
    candidate_status: str
    candidate_state_id: str
    published: bool
    published_state_id: str | None


@dataclass(frozen=True, slots=True)
class ReplayTimings:
    read_decode_seconds: float
    alignment_seconds: float
    quant_seconds: float
    family_seconds: dict[str, float]
    resolution_seconds: float
    v2_seconds: float
    v1_seconds: float
    v3_seconds: float
    persistence_seconds: float
    total_seconds: float


@dataclass(frozen=True, slots=True)
class H1ReplayReport:
    runner_version: str
    replay_run_id: str
    evidence_origin: str
    historical_session: str
    session_open_ns: int
    session_close_ns: int
    dataset_digest: str
    configuration_digest: str
    session_digest: str
    execution_stage: str
    data_status: str
    data_reason_codes: tuple[str, ...]
    quote_counts: tuple[tuple[str, int], ...]
    first_quote_ns: tuple[tuple[str, int | None], ...]
    last_quote_ns: tuple[tuple[str, int | None], ...]
    quote_coverage: tuple[QuoteCoverage, ...]
    retrieval_proof: HistoricalSipRetrievalProof | None
    frame_count: int
    rth_seconds: int
    frame_coverage: float
    qqq_attached_frame_count: int
    qqq_attached_frame_coverage: float
    qqq_fresh_frame_count: int
    qqq_fresh_frame_coverage: float
    family_coverage: tuple[FamilyCoverage, ...]
    v3_coverage: tuple[V3Coverage, ...]
    resolution_coverage: tuple[ResolutionCoverage, ...]
    resolution_samples: tuple[ResolutionSample, ...]
    v2_refreshes: tuple[V2RefreshProof, ...]
    q10_status: str
    persistence_writes: int
    timings: ReplayTimings
    replay_factor: float | None
    projected_seconds: tuple[tuple[str, float], ...]

    def to_dict(self) -> dict[str, object]:
        return asdict(self)


@dataclass(frozen=True, slots=True)
class _PendingFamily:
    record_id: int
    quant_id: str
    formula_version: str
    numerical_type: str
    value_bps: float
    source_as_of_epoch: float
    available_epoch: float


@dataclass(frozen=True, slots=True)
class _PendingTarget:
    record_id: int
    cycle_id: str
    horizon: str
    cutoff_ns: int
    maturity_ns: int
    cutoff_midpoint: float
    source_spec_version: str
    families: tuple[_PendingFamily, ...]
    v3_status: str
    v3_expected_return_bps: float | None


def _ns(value: datetime) -> int:
    if not isinstance(value, datetime) or value.tzinfo is None:
        raise ValueError("session boundaries must be timezone-aware")
    return round(value.astimezone(timezone.utc).timestamp() * _NANOSECONDS)


def _utc(epoch: float) -> datetime:
    return datetime.fromtimestamp(epoch, timezone.utc)


def _ns_utc(value: int | None) -> str | None:
    if value is None:
        return None
    seconds, nanoseconds = divmod(value, _NANOSECONDS)
    return (
        datetime.fromtimestamp(seconds, timezone.utc).strftime(
            "%Y-%m-%dT%H:%M:%S"
        ) + f".{nanoseconds:09d}Z"
    )


def _elapsed(clock: Callable[[], float], started: float) -> float:
    value = clock() - started
    if not math.isfinite(value) or value < 0:
        raise RuntimeError("H1_BENCHMARK_CLOCK_INVALID")
    return value


def _nearest_rank_p99(values: Iterable[int]) -> int | None:
    ordered = tuple(sorted(values))
    if not ordered:
        return None
    return ordered[max(0, math.ceil(0.99 * len(ordered)) - 1)]


def _quote_coverage(
    *, symbol: str, rows: tuple[HistoricalSipQuote, ...],
    open_ns: int, close_ns: int, maximum_gap_ns: int = _COMPLETE_GAP_NS,
) -> QuoteCoverage:
    gaps = tuple(
        (previous.provider_event_ns, current.provider_event_ns,
         current.provider_event_ns - previous.provider_event_ns)
        for previous, current in zip(rows, rows[1:])
    )
    maximum = max(gaps, key=lambda item: item[2], default=None)
    gap_start = None if maximum is None else maximum[0]
    gap_end = None if maximum is None else maximum[1]
    return QuoteCoverage(
        symbol,
        len(rows),
        None if not rows else rows[0].provider_event_ns,
        None if not rows else rows[-1].provider_event_ns,
        None if not rows else rows[0].provider_event_ns - open_ns,
        None if not rows else close_ns - rows[-1].provider_event_ns,
        _nearest_rank_p99(item[2] for item in gaps),
        None if maximum is None else maximum[2],
        gap_start,
        gap_end,
        _ns_utc(gap_start),
        _ns_utc(gap_end),
        gap_start,
        gap_end,
        gap_start == open_ns,
        gap_end == close_ns,
        maximum_gap_ns,
        sum(item[2] > maximum_gap_ns for item in gaps),
    )


def _validate_quote_sequence(
    quotes: tuple[HistoricalSipQuote, ...], *, open_ns: int, close_ns: int,
) -> None:
    keys = tuple(
        (row.provider_event_ns, _SYMBOL_ORDER[row.symbol]) for row in quotes
    )
    if any(current > following for current, following in zip(keys, keys[1:])):
        raise ValueError("historical quotes must be in canonical chronological order")
    if any(not open_ns <= row.provider_event_ns < close_ns for row in quotes):
        raise ValueError("historical quote is outside the replay session")
    last_by_symbol: dict[str, int] = {}
    for row in quotes:
        previous = last_by_symbol.get(row.symbol)
        if previous is not None and row.provider_event_ns <= previous:
            raise ValueError(
                "historical quote timestamps must be strictly increasing")
        last_by_symbol[row.symbol] = row.provider_event_ns


def _coverage_reason_codes(
    quote_coverage: tuple[QuoteCoverage, ...],
    *, maximum_gap_ns: int = _COMPLETE_GAP_NS,
) -> tuple[str, ...]:
    reasons = []
    for coverage in quote_coverage:
        if coverage.symbol != "COIN":
            continue
        if coverage.count < 2:
            reasons.append(f"{coverage.symbol}_INSUFFICIENT_QUOTES")
        if (coverage.first_quote_delay_ns is None or
                coverage.first_quote_delay_ns > _COMPLETE_EDGE_NS):
            reasons.append(f"{coverage.symbol}_OPEN_EDGE_GAP")
        if (coverage.last_quote_lead_ns is None or
                coverage.last_quote_lead_ns > _COMPLETE_EDGE_NS):
            reasons.append(f"{coverage.symbol}_CLOSE_EDGE_GAP")
        if (coverage.over_limit_gap_count > 0 or
                coverage.max_gap_ns is None or
                coverage.max_gap_ns > maximum_gap_ns):
            reasons.append(f"{coverage.symbol}_INTERQUOTE_GAP")
    return tuple(sorted(reasons))


def _proof_value(proof: object, name: str) -> object:
    if isinstance(proof, dict):
        return proof.get(name)
    return getattr(proof, name, None)


def _retrieval_proof_valid(
    proof: object, *, open_ns: int, close_ns: int, retained_count: int,
) -> bool:
    required = {
        "requested_symbols", "feed", "request_start_ns", "request_end_ns",
        "page_limit", "page_count", "page_raw_row_counts",
        "raw_row_count", "retained_row_count", "bucket_sampled_row_count",
        "rejected_row_count", "rejection_reason_counts",
        "terminal_next_page_token",
    }
    if isinstance(proof, dict) and not required.issubset(proof):
        return False
    if not isinstance(proof, (dict, HistoricalSipRetrievalProof)):
        return False
    page_limit = _proof_value(proof, "page_limit")
    page_count = _proof_value(proof, "page_count")
    page_rows = _proof_value(proof, "page_raw_row_counts")
    raw = _proof_value(proof, "raw_row_count")
    retained = _proof_value(proof, "retained_row_count")
    sampled = _proof_value(proof, "bucket_sampled_row_count")
    rejected = _proof_value(proof, "rejected_row_count")
    reasons = _proof_value(proof, "rejection_reason_counts")
    integers = (page_limit, page_count, raw, retained, sampled, rejected)
    if any(isinstance(value, bool) or not isinstance(value, int)
           for value in integers):
        return False
    if (tuple(_proof_value(proof, "requested_symbols") or ()) !=
            ("COIN", "QQQ") or _proof_value(proof, "feed") != "sip" or
            _proof_value(proof, "request_start_ns") != open_ns or
            _proof_value(proof, "request_end_ns") != close_ns or
            not 1 <= page_limit <= 10_000 or page_count <= 0 or
            not isinstance(page_rows, (list, tuple)) or
            len(page_rows) != page_count or
            any(isinstance(value, bool) or not isinstance(value, int) or
                value < 0 for value in page_rows) or
            raw != sum(page_rows) or retained != retained_count or
            min(raw, retained, sampled, rejected) < 0 or
            raw != retained + sampled + rejected or
            _proof_value(proof, "terminal_next_page_token") is not None or
            not isinstance(reasons, (list, tuple))):
        return False
    normalized_reasons = []
    for row in reasons:
        if (not isinstance(row, (list, tuple)) or len(row) != 2 or
                not isinstance(row[0], str) or not row[0] or
                isinstance(row[1], bool) or not isinstance(row[1], int) or
                row[1] <= 0):
            return False
        normalized_reasons.append((row[0], row[1]))
    return (
        normalized_reasons == sorted(set(normalized_reasons)) and
        rejected == sum(count for _reason, count in normalized_reasons)
    )


def _preflight_coin_times(
    rows: tuple[HistoricalSipQuote, ...], *, open_ns: int, close_ns: int,
) -> tuple[tuple[int, ...], tuple[int, ...]]:
    """Reproduce forecast and close-drain timestamps without replay work."""

    frame_times: list[int] = []
    index = 0
    latest_ns: int | None = None
    last_frame_ns: int | None = None
    cutoff_ns = open_ns
    while cutoff_ns < close_ns:
        while (index < len(rows) and
               rows[index].provider_event_ns <= cutoff_ns):
            latest_ns = rows[index].provider_event_ns
            index += 1
        if latest_ns is not None and latest_ns != last_frame_ns:
            frame_times.append(latest_ns)
            last_frame_ns = latest_ns
        cutoff_ns += _NANOSECONDS

    outcome_times = list(frame_times)
    if (rows and
            (not outcome_times or
             rows[-1].provider_event_ns > outcome_times[-1]) and
            rows[-1].provider_event_ns < close_ns):
        outcome_times.append(rows[-1].provider_event_ns)
    return tuple(frame_times), tuple(outcome_times)


def _endpoint_reason_codes(
    rows: tuple[HistoricalSipQuote, ...], *, open_ns: int, close_ns: int,
) -> tuple[str, ...]:
    frame_times, outcome_times = _preflight_coin_times(
        rows, open_ns=open_ns, close_ns=close_ns,
    )
    reasons = []
    for horizon in HORIZONS:
        horizon_ns = HORIZON_SECONDS[horizon] * _NANOSECONDS
        endpoint_index = 0
        for forecast_ns in frame_times:
            maturity_ns = forecast_ns + horizon_ns
            if maturity_ns >= close_ns:
                break
            while (endpoint_index < len(outcome_times) and
                   outcome_times[endpoint_index] < maturity_ns):
                endpoint_index += 1
            if endpoint_index >= len(outcome_times):
                reasons.append(f"{horizon}_ENDPOINT_GAP")
                break
    return tuple(sorted(reasons))


def _cycle_id(frame: ReplayFrame) -> str:
    cutoff_at = _utc(_forecast_epoch(frame))
    return (
        f"historical:{cutoff_at.astimezone(_EASTERN).date().isoformat()}:"
        f"{frame.coin_source_as_of_ns}"
    )


def _forecast_epoch(frame: ReplayFrame) -> float:
    return frame.coin_source_as_of_ns / _NANOSECONDS


def _calculate_provider_families(
    frame: ReplayFrame, family_seconds: dict[str, float],
) -> ReplayFamilyResults:
    """Run the deployed equations at the selected provider timestamp."""

    forecast_cutoff = _forecast_epoch(frame)
    latest = frame.coin_history.latest
    if latest is None:
        raise RuntimeError("REPLAY_CUTOFF_MIDPOINT_UNAVAILABLE")
    # Preserve the history module's one-ULP ordering correction when distinct
    # provider nanoseconds collapse to the same binary64 timestamp.
    calculation_cutoff = max(forecast_cutoff, latest.event_epoch)

    def stamp(result: object | None) -> object | None:
        return (None if result is None else
                replace(result, cutoff_epoch=forecast_cutoff))

    def timed(quant_id: str, call: Callable[[], object | None]) -> object | None:
        started = time.perf_counter()
        result = call()
        family_seconds[quant_id] += _elapsed(time.perf_counter, started)
        return result

    return ReplayFamilyResults(
        forecast_cutoff,
        stamp(timed("q1_momentum", lambda: calculate_momentum(
            frame.coin_history, cutoff_epoch=calculation_cutoff))),
        stamp(timed("q2_mean_reversion", lambda: calculate_mean_reversion(
            frame.coin_history, cutoff_epoch=calculation_cutoff))),
        stamp(timed("q3_volatility", lambda: calculate_volatility(
            frame.coin_history, cutoff_epoch=calculation_cutoff))),
        stamp(timed("q4_stat_arb", lambda: calculate_stat_arb(
            frame.coin_history, frame.qqq_history,
            cutoff_epoch=calculation_cutoff))),
        stamp(timed("q5_microstructure", lambda: calculate_microstructure(
            frame.coin_quote_history, cutoff_epoch=calculation_cutoff))),
        stamp(timed("q6_volume_liquidity", lambda: calculate_volume_liquidity(
            frame.coin_quote_history, cutoff_epoch=calculation_cutoff))),
        stamp(timed("q7_relative_value", lambda: calculate_relative_value(
            frame.coin_history, frame.qqq_history,
            cutoff_epoch=calculation_cutoff))),
        stamp(timed("q8_cross_asset", lambda: calculate_cross_asset(
            frame.coin_history, frame.qqq_history,
            cutoff_epoch=calculation_cutoff))),
        stamp(timed("q9_factor", lambda: calculate_factor(
            frame.coin_history, frame.qqq_history,
            cutoff_epoch=calculation_cutoff))),
        None,
        stamp(timed("q11_regime", lambda: calculate_regime(
            frame.coin_history, cutoff_epoch=calculation_cutoff))),
        stamp(timed("q12_event_session", lambda: calculate_event_session(
            frame.coin_history, cutoff_epoch=calculation_cutoff))),
    )


def _family_result_map(results: ReplayFamilyResults) -> dict[str, object | None]:
    return {
        quant_id: getattr(results, attribute)
        for quant_id, attribute in _RESULT_NAMES.items()
    } | {_Q10: None}


def _result_values(quant_id: str, result: object | None) -> tuple[object, ...] | None:
    if result is None:
        return None
    name = "volatility_bps" if quant_id == "q3_volatility" else "forecast_bps"
    values = getattr(result, name, None)
    if values is None:
        return None
    values = tuple(values)
    if len(values) != len(HORIZONS):
        raise RuntimeError("REPLAY_FAMILY_NOT_EXACT_SIX")
    return values


def _family_source_epoch(
    quant_id: str, result: object | None, frame: ReplayFrame,
) -> float:
    if quant_id == "q4_stat_arb" and result is not None:
        value = getattr(result, "source_as_of_epoch", None)
        if (isinstance(value, bool) or not isinstance(value, (int, float)) or
                not math.isfinite(value) or value > _forecast_epoch(frame)):
            raise RuntimeError("REPLAY_Q4_PROVIDER_TIMESTAMP_UNAVAILABLE")
        return float(value)
    return _forecast_epoch(frame)


def _build_v1(frame: ReplayFrame, results: ReplayFamilyResults, v2_state):
    cutoff_at = _utc(_forecast_epoch(frame))
    by_quant = _family_result_map(results)
    slots = []
    for quant_id in QUANT_IDS:
        result = by_quant[quant_id]
        values = _result_values(quant_id, result)
        source_at = _utc(_family_source_epoch(quant_id, result, frame))
        for index, horizon in enumerate(HORIZONS):
            value = None if values is None else values[index]
            reason = None
            if value is None:
                reason = ("REPLAY_Q10_DATA_UNAVAILABLE" if quant_id == _Q10
                          else "MISSING_VALUE")
            slots.append(V1SlotObservation(
                quant_id, _FORMULA_VERSIONS[quant_id], horizon,
                HORIZON_SECONDS[horizon],
                MAGNITUDE_BPS if quant_id == "q3_volatility" else DIRECTIONAL_BPS,
                value, cutoff_at, source_at, cutoff_at,
                frame.data_schema_version, frame.source_spec_version, reason,
            ))
    return build_v1_input(
        cycle_id=_cycle_id(frame), cutoff_at=cutoff_at,
        target_spec_id=TARGET_SPEC_ID,
        data_schema_version=frame.data_schema_version,
        source_spec_version=frame.source_spec_version, slots=slots,
        evidence_state_id=v2_state.state_id,
        evidence_state_version=v2_state.state_version,
        evidence_state_hash=v2_state.state_hash,
        evidence_state_as_of=_utc(v2_state.state_as_of),
        evidence_training_start=(None if v2_state.training_start is None else
                                 _utc(v2_state.training_start)),
        evidence_training_end=(None if v2_state.training_end is None else
                               _utc(v2_state.training_end)),
    )


def _pending_families(
    *, frame: ReplayFrame, results: ReplayFamilyResults, horizon_index: int,
    next_record_id: int,
) -> tuple[tuple[_PendingFamily, ...], int]:
    rows = []
    by_quant = _family_result_map(results)
    for quant_id in ALLOWED_FORMULA_VERSIONS:
        result = by_quant[quant_id]
        values = _result_values(quant_id, result)
        value = None if values is None else values[horizon_index]
        if value is None:
            continue
        if (isinstance(value, bool) or not isinstance(value, (int, float)) or
                not math.isfinite(value) or
                (quant_id == "q3_volatility" and value < 0)):
            raise RuntimeError("REPLAY_FAMILY_VALUE_INVALID")
        rows.append(_PendingFamily(
            next_record_id, quant_id, ALLOWED_FORMULA_VERSIONS[quant_id],
            V2_MAGNITUDE_BPS if quant_id == "q3_volatility" else DIRECTIONAL_BPS,
            float(value), _family_source_epoch(quant_id, result, frame),
            _forecast_epoch(frame),
        ))
        next_record_id += 1
    return tuple(rows), next_record_id


def _configuration_digest(
    *, session_open_ns: int, session_close_ns: int,
    maximum_gap_ns: int = _COMPLETE_GAP_NS,
) -> str:
    return canonical_sha256({
        "runner_version": H1_RUNNER_VERSION,
        "replay_method_version": REPLAY_METHOD_VERSION,
        "session_open_ns": session_open_ns,
        "session_close_ns": session_close_ns,
        "source": SOURCE,
        "data_schema_version": DATA_SCHEMA_VERSION,
        "target_spec_id": TARGET_SPEC_ID,
        "horizons": tuple((horizon, HORIZON_SECONDS[horizon])
                          for horizon in HORIZONS),
        "formula_versions": tuple(sorted(_FORMULA_VERSIONS.items())),
        "q10_status": "DATA_UNAVAILABLE",
        "v2_refresh_seconds": 3_600,
        "v2_refresh_anchor": "RTH_OPEN_FIRST_FRAME_AT_OR_AFTER",
        "v2_publication": "RETAIN_LAST_VALID_NON_UNAVAILABLE",
        "forecast_cutoff": "SELECTED_COIN_PROVIDER_EVENT_NS",
        "target_endpoint": "FIRST_ACCEPTED_REPLAY_COIN_QUOTE_AT_OR_AFTER",
        "session_target_rule": "MATURITY_STRICTLY_BEFORE_RTH_CLOSE",
        "close_rule": "RESOLUTION_ONLY_NO_FORECAST",
        "complete_edge_seconds": _COMPLETE_EDGE_NS / _NANOSECONDS,
        "maximum_interquote_gap_seconds": (
            maximum_gap_ns / _NANOSECONDS
        ),
        "preflight_target_endpoint_audit": "TIMESTAMP_ONLY_EXACT_SIX",
    })


def run_h1_session(
    *, reader: object, session_open: datetime, session_close: datetime,
    replay_run_id: str, monotonic_clock: Callable[[], float] = time.perf_counter,
    preflight_only: bool = False,
    maximum_interior_gap_seconds: int = 5,
    forecast_evidence: list | None = None,
) -> H1ReplayReport:
    """Run one complete RTH session without any external write."""

    if not isinstance(replay_run_id, str) or not 1 <= len(replay_run_id) <= 128:
        raise ValueError("replay_run_id must be 1-128 characters")
    if not callable(getattr(reader, "read_session", None)):
        raise TypeError("reader must provide read_session")
    if not isinstance(preflight_only, bool):
        raise TypeError("preflight_only must be bool")
    if maximum_interior_gap_seconds != 5:
        raise ValueError("maximum_interior_gap_seconds is frozen at 5")
    maximum_gap_ns = maximum_interior_gap_seconds * _NANOSECONDS
    open_ns, close_ns = _ns(session_open), _ns(session_close)
    local_open = session_open.astimezone(_EASTERN)
    local_close = session_close.astimezone(_EASTERN)
    if (local_open.date() != local_close.date() or
            local_open.timetz().replace(tzinfo=None) != datetime_time(9, 30) or
            local_close.timetz().replace(tzinfo=None) != datetime_time(16, 0)):
        raise ValueError("H1 requires one complete 09:30-16:00 ET session")

    total_started = monotonic_clock()
    started = monotonic_clock()
    try:
        quotes = tuple(reader.read_session(
            session_open=session_open, session_close=session_close,
        ))
    except RuntimeError as error:
        if error.args != ("REPLAY_DATA_UNAVAILABLE",):
            raise
        quotes = ()
    read_decode_seconds = _elapsed(monotonic_clock, started)
    retrieval_proof = getattr(reader, "last_retrieval_proof", None)
    if any(not isinstance(row, HistoricalSipQuote) for row in quotes):
        raise TypeError("reader returned a non-historical quote")
    _validate_quote_sequence(quotes, open_ns=open_ns, close_ns=close_ns)

    quote_counts = tuple(
        (symbol, sum(row.symbol == symbol for row in quotes))
        for symbol in ("COIN", "QQQ")
    )
    by_symbol = {
        symbol: tuple(row for row in quotes if row.symbol == symbol)
        for symbol in ("COIN", "QQQ")
    }
    quote_coverage = tuple(
        _quote_coverage(
            symbol=symbol, rows=rows, open_ns=open_ns, close_ns=close_ns,
            maximum_gap_ns=maximum_gap_ns,
        )
        for symbol, rows in by_symbol.items()
    )
    proof_reasons = (() if _retrieval_proof_valid(
        retrieval_proof, open_ns=open_ns, close_ns=close_ns,
        retained_count=len(quotes),
    ) else (("RETRIEVAL_PROOF_MISSING",) if retrieval_proof is None else
            ("RETRIEVAL_PROOF_INVALID",)))
    coverage_reasons = _coverage_reason_codes(
        quote_coverage, maximum_gap_ns=maximum_gap_ns,
    )
    endpoint_reasons = (() if (*proof_reasons, *coverage_reasons) else
                        _endpoint_reason_codes(
        by_symbol["COIN"], open_ns=open_ns, close_ns=close_ns,
    ))
    data_reason_codes = tuple(sorted(set(
        (*proof_reasons, *coverage_reasons, *endpoint_reasons)
    )))
    data_status = "CERTIFIED" if not data_reason_codes else "DATA_INCOMPLETE"
    dataset_digest = canonical_sha256(tuple(
        (row.symbol, row.provider_event_ns, row.bid, row.ask,
         row.bid_size, row.ask_size, row.source, row.data_schema_version,
         row.source_spec_version)
        for row in quotes
    ))
    config_digest = _configuration_digest(
        session_open_ns=open_ns, session_close_ns=close_ns,
        maximum_gap_ns=maximum_gap_ns,
    )
    first_quote_ns = tuple(
        (symbol, rows[0].provider_event_ns if rows else None)
        for symbol, rows in by_symbol.items()
    )
    last_quote_ns = tuple(
        (symbol, rows[-1].provider_event_ns if rows else None)
        for symbol, rows in by_symbol.items()
    )
    rth_seconds = (close_ns - open_ns) // _NANOSECONDS
    if data_status != "CERTIFIED" or preflight_only:
        execution_stage = (
            "PREFLIGHT_REJECTED" if data_status != "CERTIFIED"
            else "PREFLIGHT_ONLY"
        )
        report_data_status = (
            data_status if execution_stage == "PREFLIGHT_REJECTED"
            else "DATA_COMPLETE"
        )
        family_coverage = tuple(
            FamilyCoverage(quant_id, horizon, 0, 0, 0)
            for quant_id in QUANT_IDS for horizon in HORIZONS
        )
        v3_coverage = tuple(
            V3Coverage(horizon, 0, 0, 0, 0) for horizon in HORIZONS
        )
        resolution_coverage = tuple(
            ResolutionCoverage(horizon, 0, 0, 0, 0, 0, None, None)
            for horizon in HORIZONS
        )
        session_digest = canonical_sha256({
            "dataset_digest": dataset_digest,
            "configuration_digest": config_digest,
            "execution_stage": execution_stage,
            "data_status": report_data_status,
            "data_reason_codes": data_reason_codes,
            "quote_coverage": quote_coverage,
            "retrieval_proof": retrieval_proof,
        })
        total_seconds = _elapsed(monotonic_clock, total_started)
        timings = ReplayTimings(
            read_decode_seconds, 0.0, 0.0,
            {quant_id: 0.0 for quant_id in QUANT_IDS},
            0.0, 0.0, 0.0, 0.0, 0.0,
            total_seconds,
        )
        return H1ReplayReport(
            H1_RUNNER_VERSION, replay_run_id, EVIDENCE_ORIGIN,
            local_open.date().isoformat(), open_ns, close_ns,
            dataset_digest, config_digest, session_digest, execution_stage,
            report_data_status, data_reason_codes, quote_counts,
            first_quote_ns, last_quote_ns, quote_coverage, retrieval_proof,
            0, int(rth_seconds), 0.0, 0, 0.0, 0, 0.0,
            family_coverage, v3_coverage, resolution_coverage, (), (),
            "DATA_UNAVAILABLE", 0, timings, None, (),
        )

    coin_quotes = by_symbol["COIN"]
    coin_by_ns = {row.provider_event_ns: row for row in coin_quotes}
    accepted_coin_quotes: list[HistoricalSipQuote] = []
    accepted_coin_times: list[int] = []

    family_mutable = {
        (quant_id, horizon): [0, 0]
        for quant_id in QUANT_IDS for horizon in HORIZONS
    }
    v3_mutable = {
        horizon: {"MATURE": 0, "PROVISIONAL": 0, "UNAVAILABLE": 0}
        for horizon in HORIZONS
    }
    resolution_mutable = {horizon: [0, 0, 0] for horizon in HORIZONS}
    resolution_delays: dict[str, list[int]] = {
        horizon: [] for horizon in HORIZONS
    }
    pending: dict[str, deque[_PendingTarget]] = {
        horizon: deque() for horizon in HORIZONS
    }
    targets_by_horizon: dict[str, list[RawTarget]] = {
        horizon: [] for horizon in HORIZONS
    }
    observations_by_horizon: dict[str, list[RawFamilyObservation]] = {
        horizon: [] for horizon in HORIZONS
    }
    first_samples: dict[str, ResolutionSample] = {}
    refreshes: list[V2RefreshProof] = []
    stream_digest = hashlib.sha256()
    resolution_digest = hashlib.sha256()
    stream_digest.update(dataset_digest.encode("ascii"))
    stream_digest.update(config_digest.encode("ascii"))

    alignment_seconds = quant_seconds = resolution_seconds = 0.0
    family_seconds = {quant_id: 0.0 for quant_id in QUANT_IDS}
    v2_seconds = v1_seconds = v3_seconds = 0.0
    frame_count = qqq_attached_frames = qqq_fresh_frames = 0
    next_target_id = next_family_id = 1
    next_refresh_anchor = open_ns
    current_v2 = None
    pending_v2 = None

    def resolve_visible(visibility_ns: int) -> None:
        nonlocal resolution_seconds
        resolve_started = monotonic_clock()
        for horizon in HORIZONS:
            queue = pending[horizon]
            while queue:
                candidate = queue[0]
                maturity_ns = candidate.maturity_ns
                endpoint_index = bisect_left(accepted_coin_times, maturity_ns)
                if endpoint_index >= len(accepted_coin_quotes):
                    break
                endpoint = accepted_coin_quotes[endpoint_index]
                if (endpoint.provider_event_ns >= close_ns or
                        endpoint.provider_event_ns > visibility_ns):
                    break
                if endpoint_index == 0:
                    raise RuntimeError("REPLAY_TARGET_PREVIOUS_OBSERVATION_UNAVAILABLE")
                previous = accepted_coin_quotes[endpoint_index - 1]
                if not (previous.provider_event_ns < maturity_ns <=
                        endpoint.provider_event_ns <= visibility_ns):
                    raise RuntimeError("REPLAY_TARGET_TIMING_VIOLATION")
                queue.popleft()
                delay_ns = endpoint.provider_event_ns - maturity_ns
                if delay_ns > _MAX_TARGET_RESOLUTION_DELAY_NS:
                    continue
                target_bps = 10_000.0 * math.log(
                    endpoint.midpoint / candidate.cutoff_midpoint
                )
                target = RawTarget(
                    candidate.record_id, candidate.cycle_id, "COIN",
                    TARGET_SPEC_ID, DATA_SCHEMA_VERSION,
                    candidate.source_spec_version, horizon,
                    candidate.cutoff_ns / _NANOSECONDS,
                    candidate.maturity_ns / _NANOSECONDS,
                    endpoint.provider_event_ns / _NANOSECONDS, target_bps,
                )
                targets_by_horizon[horizon].append(target)
                identity = TargetIdentity(
                    candidate.cycle_id, candidate.cutoff_ns / _NANOSECONDS,
                    candidate.maturity_ns / _NANOSECONDS,
                )
                for family in candidate.families:
                    observations_by_horizon[horizon].append(
                        RawFamilyObservation(
                            family.record_id, identity, "COIN",
                            family.quant_id, family.formula_version,
                            DATA_SCHEMA_VERSION,
                            candidate.source_spec_version, horizon,
                            family.numerical_type, family.value_bps,
                            candidate.cutoff_ns / _NANOSECONDS,
                            family.source_as_of_epoch,
                            family.available_epoch, "FRESH",
                        )
                    )
                resolution_mutable[horizon][1] += 1
                resolution_delays[horizon].append(delay_ns)
                sample = ResolutionSample(
                    candidate.cycle_id, horizon, maturity_ns,
                    previous.provider_event_ns, endpoint.provider_event_ns,
                    visibility_ns, delay_ns, target_bps,
                )
                first_samples.setdefault(horizon, sample)
                resolution_digest.update(canonical_sha256({
                    "sample": sample,
                    "v3_status": candidate.v3_status,
                    "v3_expected_return_bps": candidate.v3_expected_return_bps,
                }).encode("ascii"))
        resolution_seconds += _elapsed(monotonic_clock, resolve_started)

    frame_iterator = iter(OneSessionReplayClock(
        quotes, session_open=session_open, session_close=session_close,
    ).frames())
    while True:
        started = monotonic_clock()
        try:
            frame = next(frame_iterator)
        except StopIteration:
            alignment_seconds += _elapsed(monotonic_clock, started)
            break
        alignment_seconds += _elapsed(monotonic_clock, started)
        frame_count += 1
        forecast_ns = frame.coin_source_as_of_ns
        accepted_quote = coin_by_ns[forecast_ns]
        accepted_coin_quotes.append(accepted_quote)
        accepted_coin_times.append(forecast_ns)
        if frame.qqq_source_as_of_ns is not None:
            qqq_attached_frames += 1
            if forecast_ns - frame.qqq_source_as_of_ns <= 5 * _NANOSECONDS:
                qqq_fresh_frames += 1

        resolve_visible(forecast_ns)
        due_anchors = []
        while next_refresh_anchor <= forecast_ns:
            due_anchors.append(next_refresh_anchor)
            next_refresh_anchor += _REFRESH_NS
        if due_anchors:
            started = monotonic_clock()
            envelope = build_replay_v2_as_of(
                frame=frame, replay_run_id=replay_run_id,
                targets_by_horizon=targets_by_horizon,
                observations_by_horizon=observations_by_horizon,
                family_versions=tuple(
                    (quant_id, formula, frame.data_schema_version,
                     frame.source_spec_version)
                    for quant_id, formula in ALLOWED_FORMULA_VERSIONS.items()
                ),
            )
            v2_seconds += _elapsed(monotonic_clock, started)
            candidate_v2 = envelope.v2_state
            published = (
                candidate_v2.creation_status == "VALID" and
                candidate_v2.top_level_status != "UNAVAILABLE"
            )
            if published:
                pending_v2 = candidate_v2
            all_targets = tuple(
                row for horizon in HORIZONS
                for row in targets_by_horizon[horizon]
            )
            maximum = max(
                (row.resolved_epoch for row in all_targets), default=None,
            )
            for anchor_ns in due_anchors:
                refreshes.append(V2RefreshProof(
                    anchor_ns, frame.cutoff_ns,
                    round(candidate_v2.state_as_of * _NANOSECONDS),
                    len(all_targets), maximum, candidate_v2.top_level_status,
                    candidate_v2.state_id, published,
                    None if pending_v2 is None else pending_v2.state_id,
                ))

        if (pending_v2 is not None and
                pending_v2.state_as_of <= _forecast_epoch(frame)):
            current_v2 = pending_v2

        started = monotonic_clock()
        results = _calculate_provider_families(frame, family_seconds)
        quant_seconds += _elapsed(monotonic_clock, started)
        result_map = _family_result_map(results)
        for quant_id in QUANT_IDS:
            values = _result_values(quant_id, result_map[quant_id])
            for index, horizon in enumerate(HORIZONS):
                family_mutable[(quant_id, horizon)][0] += 1
                if values is not None and values[index] is not None:
                    family_mutable[(quant_id, horizon)][1] += 1
        if forecast_evidence is not None:
            from .historical_evidence import HistoricalForecastEvidence
            cutoff_at = _utc(_forecast_epoch(frame))
            for quant_id in QUANT_IDS:
                family_result = result_map[quant_id]
                values = _result_values(quant_id, family_result)
                source_at = _utc(_family_source_epoch(
                    quant_id, family_result, frame,
                ))
                for index, horizon in enumerate(HORIZONS):
                    value = None if values is None else values[index]
                    reason = None if value is not None else (
                        "REPLAY_Q10_DATA_UNAVAILABLE" if quant_id == _Q10
                        else "MISSING_VALUE"
                    )
                    forecast_evidence.append(HistoricalForecastEvidence(
                        replay_run_id, cutoff_at, quant_id, horizon,
                        None if value is None else float(value),
                        "AVAILABLE" if value is not None else "UNAVAILABLE",
                        reason, _FORMULA_VERSIONS[quant_id],
                        MAGNITUDE_BPS if quant_id == "q3_volatility"
                        else DIRECTIONAL_BPS,
                        source_at, cutoff_at, frame.data_schema_version,
                        frame.source_spec_version,
                    ))

        v1 = v3 = None
        by_horizon = {}
        if current_v2 is not None:
            started = monotonic_clock()
            v1 = _build_v1(frame, results, current_v2)
            v1_seconds += _elapsed(monotonic_clock, started)
            started = monotonic_clock()
            v3 = synthesize_v3(v1, current_v2)
            v3_seconds += _elapsed(monotonic_clock, started)
            by_horizon = {row.horizon: row for row in v3.horizon_results}
            if tuple(by_horizon) != HORIZONS:
                raise RuntimeError("REPLAY_V3_NOT_EXACT_SIX")
        latest = frame.coin_history.latest
        if latest is None:
            raise RuntimeError("REPLAY_CUTOFF_MIDPOINT_UNAVAILABLE")
        for index, horizon in enumerate(HORIZONS):
            result = by_horizon.get(horizon)
            status = "UNAVAILABLE" if result is None else result.status
            expected_return = (None if result is None else
                               result.expected_return_bps)
            if status not in v3_mutable[horizon]:
                raise RuntimeError("REPLAY_V3_STATUS_INVALID")
            v3_mutable[horizon][status] += 1
            resolution_mutable[horizon][0] += 1
            maturity_ns = forecast_ns + HORIZON_SECONDS[horizon] * _NANOSECONDS
            session_eligible = maturity_ns < close_ns
            if session_eligible:
                resolution_mutable[horizon][2] += 1
            families = ()
            if session_eligible:
                families, next_family_id = _pending_families(
                    frame=frame, results=results, horizon_index=index,
                    next_record_id=next_family_id,
                )
            pending[horizon].append(_PendingTarget(
                next_target_id, _cycle_id(frame), horizon, forecast_ns,
                maturity_ns, latest.midpoint, frame.source_spec_version,
                families, status, expected_return,
            ))
            next_target_id += 1
        stream_digest.update(canonical_sha256({
            "frame": (
                frame.clock_ns, forecast_ns,
                frame.qqq_source_as_of_ns,
            ),
            "family_results": results,
            "v2_state_id": None if current_v2 is None else current_v2.state_id,
            "v2_state_hash": None if current_v2 is None else current_v2.state_hash,
            "v1_hash": None if v1 is None else v1_input_hash(v1),
            "v3": v3,
        }).encode("ascii"))

    # The 16:00 tick is outcome-only. It accepts the latest remaining quote
    # from the fractional final second but constructs no forecast frame.
    if ((not accepted_coin_times or
         coin_quotes[-1].provider_event_ns > accepted_coin_times[-1]) and
            coin_quotes[-1].provider_event_ns < close_ns):
        accepted_coin_quotes.append(coin_quotes[-1])
        accepted_coin_times.append(coin_quotes[-1].provider_event_ns)
    resolve_visible(close_ns)

    family_coverage = tuple(FamilyCoverage(
        quant_id, horizon, family_mutable[(quant_id, horizon)][0],
        family_mutable[(quant_id, horizon)][1],
        family_mutable[(quant_id, horizon)][0] -
        family_mutable[(quant_id, horizon)][1],
    ) for quant_id in QUANT_IDS for horizon in HORIZONS)
    v3_coverage = tuple(V3Coverage(
        horizon, sum(v3_mutable[horizon].values()),
        v3_mutable[horizon]["MATURE"],
        v3_mutable[horizon]["PROVISIONAL"],
        v3_mutable[horizon]["UNAVAILABLE"],
    ) for horizon in HORIZONS)
    resolution_coverage = tuple(ResolutionCoverage(
        horizon, resolution_mutable[horizon][0],
        resolution_mutable[horizon][2],
        resolution_mutable[horizon][0] - resolution_mutable[horizon][2],
        resolution_mutable[horizon][1],
        resolution_mutable[horizon][0] - resolution_mutable[horizon][1],
        _nearest_rank_p99(resolution_delays[horizon]),
        max(resolution_delays[horizon], default=None),
    ) for horizon in HORIZONS)
    endpoint_reasons = tuple(
        f"{row.horizon}_ENDPOINT_GAP"
        for row in resolution_coverage
        if row.resolved < row.session_eligible
    )
    data_reason_codes = tuple(sorted(set(
        (*data_reason_codes, *endpoint_reasons)
    )))
    data_status = "CERTIFIED" if not data_reason_codes else "DATA_INCOMPLETE"
    samples = tuple(first_samples[horizon] for horizon in HORIZONS
                    if horizon in first_samples)
    session_digest = canonical_sha256({
        "dataset_digest": dataset_digest,
        "configuration_digest": config_digest,
        "execution_stage": "REPLAY_COMPLETE",
        "stream_digest": stream_digest.hexdigest(),
        "resolution_digest": resolution_digest.hexdigest(),
        "data_status": data_status,
        "data_reason_codes": data_reason_codes,
        "quote_coverage": quote_coverage,
        "retrieval_proof": retrieval_proof,
        "qqq_attachment": (qqq_attached_frames, qqq_fresh_frames),
        "family_coverage": family_coverage,
        "v3_coverage": v3_coverage,
        "resolution_coverage": resolution_coverage,
        "v2_refreshes": tuple(refreshes),
    })
    total_seconds = _elapsed(monotonic_clock, total_started)
    timings = ReplayTimings(
        read_decode_seconds, alignment_seconds, quant_seconds,
        family_seconds,
        resolution_seconds, v2_seconds, v1_seconds, v3_seconds, 0.0,
        total_seconds,
    )
    rth_seconds = (close_ns - open_ns) // _NANOSECONDS
    factor = (None if data_status != "CERTIFIED" or total_seconds == 0 else
              rth_seconds / total_seconds)
    projections = (() if factor is None else tuple(
        (label, total_seconds * sessions)
        for label, sessions in (
            ("1_TRADING_WEEK", 5), ("1_TRADING_MONTH", 21),
            ("1_TRADING_YEAR", 252), ("2_TRADING_YEARS", 504),
            ("5_TRADING_YEARS", 1_260),
        )
    ))
    first_quote_ns = tuple(
        (symbol, rows[0].provider_event_ns if rows else None)
        for symbol, rows in by_symbol.items()
    )
    last_quote_ns = tuple(
        (symbol, rows[-1].provider_event_ns if rows else None)
        for symbol, rows in by_symbol.items()
    )
    return H1ReplayReport(
        H1_RUNNER_VERSION, replay_run_id, EVIDENCE_ORIGIN,
        local_open.date().isoformat(), open_ns, close_ns,
        dataset_digest, config_digest, session_digest, "REPLAY_COMPLETE",
        data_status, data_reason_codes, quote_counts,
        first_quote_ns, last_quote_ns, quote_coverage, retrieval_proof,
        frame_count, int(rth_seconds), frame_count / rth_seconds,
        qqq_attached_frames,
        0.0 if frame_count == 0 else qqq_attached_frames / frame_count,
        qqq_fresh_frames,
        0.0 if frame_count == 0 else qqq_fresh_frames / frame_count,
        family_coverage, v3_coverage, resolution_coverage, samples,
        tuple(refreshes), "DATA_UNAVAILABLE", 0, timings, factor,
        projections,
    )


def _session(day: date) -> tuple[datetime, datetime]:
    opened = datetime.combine(day, datetime_time(9, 30), tzinfo=_EASTERN)
    return opened, datetime.combine(day, datetime_time(16, 0), tzinfo=_EASTERN)


def _preflight_passed(report: H1ReplayReport) -> bool:
    return (
        report.execution_stage == "PREFLIGHT_ONLY" and
        report.data_status == "DATA_COMPLETE"
    )


def _batch_summary(report: H1ReplayReport, result_file: Path) -> dict[str, object]:
    rejected = tuple(
        coverage for coverage in report.quote_coverage
        if any(code.startswith(f"{coverage.symbol}_")
               for code in report.data_reason_codes)
    )
    return {
        "date": report.historical_session,
        "status": "QUALIFYING" if _preflight_passed(report) else "REJECTED",
        "reason_codes": report.data_reason_codes,
        "rejected_symbols": tuple({
            "symbol": row.symbol,
            "maximum_gap_ns": row.max_gap_ns,
            "previous_quote_utc": row.max_gap_start_utc,
            "next_quote_utc": row.max_gap_end_utc,
            "touches_rth_start": row.max_gap_touches_rth_start,
            "touches_rth_end": row.max_gap_touches_rth_end,
            "configured_maximum_gap_ns": row.configured_max_gap_ns,
        } for row in rejected),
        "result_file": str(result_file),
    }


def _qualifies_cached_result(
    result: object, *, day: date, maximum_gap_seconds: int,
) -> bool:
    """Fail-closed proof check over a saved full preflight result."""

    opened, closed = _session(day)
    open_ns, close_ns = _ns(opened), _ns(closed)
    if (not isinstance(result, dict) or maximum_gap_seconds != 5 or
            result.get("runner_version") != H1_RUNNER_VERSION or
            result.get("historical_session") != day.isoformat() or
            result.get("session_open_ns") != open_ns or
            result.get("session_close_ns") != close_ns or
            result.get("configuration_digest") != _configuration_digest(
                session_open_ns=open_ns, session_close_ns=close_ns,
            ) or result.get("execution_stage") != "PREFLIGHT_ONLY" or
            result.get("data_status") != "DATA_COMPLETE" or
            result.get("data_reason_codes") not in ([], ())):
        return False
    dataset_digest = result.get("dataset_digest")
    session_digest = result.get("session_digest")
    if (not isinstance(dataset_digest, str) or len(dataset_digest) != 64 or
            any(character not in "0123456789abcdef"
                for character in dataset_digest) or
            not isinstance(session_digest, str) or len(session_digest) != 64 or
            any(character not in "0123456789abcdef"
                for character in session_digest)):
        return False
    counts = result.get("quote_counts")
    if (not isinstance(counts, (list, tuple)) or
            tuple(row[0] for row in counts if isinstance(row, (list, tuple))
                  and len(row) == 2) != ("COIN", "QQQ") or
            any(not isinstance(row, (list, tuple)) or len(row) != 2 or
                isinstance(row[1], bool) or not isinstance(row[1], int) or
                row[1] < 0 for row in counts)):
        return False
    coverage = result.get("quote_coverage")
    if not isinstance(coverage, (list, tuple)):
        return False
    if (len(coverage) != 2 or
            tuple(row.get("symbol") for row in coverage
                  if isinstance(row, dict)) != ("COIN", "QQQ")):
        return False
    by_symbol = {row[0]: row[1] for row in counts}
    if any(row.get("count") != by_symbol[row["symbol"]]
           for row in coverage):
        return False
    coin = coverage[0]
    expected_session_digest = canonical_sha256({
        "dataset_digest": dataset_digest,
        "configuration_digest": result.get("configuration_digest"),
        "execution_stage": result.get("execution_stage"),
        "data_status": result.get("data_status"),
        "data_reason_codes": result.get("data_reason_codes"),
        "quote_coverage": coverage,
        "retrieval_proof": result.get("retrieval_proof"),
    })
    return (
        session_digest == expected_session_digest and
        coin.get("count", 0) >= 2 and
        coin.get("configured_max_gap_ns") == _COMPLETE_GAP_NS and
        coin.get("over_limit_gap_count") == 0 and
        isinstance(coin.get("max_gap_ns"), int) and
        not isinstance(coin.get("max_gap_ns"), bool) and
        0 <= coin["max_gap_ns"] <= _COMPLETE_GAP_NS and
        isinstance(coin.get("p99_gap_ns"), int) and
        not isinstance(coin.get("p99_gap_ns"), bool) and
        0 <= coin["p99_gap_ns"] <= _COMPLETE_GAP_NS and
        isinstance(coin.get("first_quote_delay_ns"), int) and
        not isinstance(coin.get("first_quote_delay_ns"), bool) and
        0 <= coin["first_quote_delay_ns"] <= _COMPLETE_EDGE_NS and
        isinstance(coin.get("last_quote_lead_ns"), int) and
        not isinstance(coin.get("last_quote_lead_ns"), bool) and
        0 <= coin["last_quote_lead_ns"] <= _COMPLETE_EDGE_NS and
        isinstance(coin.get("first_quote_ns"), int) and
        not isinstance(coin.get("first_quote_ns"), bool) and
        coin["first_quote_ns"] == open_ns + coin["first_quote_delay_ns"] and
        isinstance(coin.get("last_quote_ns"), int) and
        not isinstance(coin.get("last_quote_ns"), bool) and
        coin["last_quote_ns"] == close_ns - coin["last_quote_lead_ns"] and
        coin["count"] >= (
            math.ceil(max(
                0,
                close_ns - open_ns - coin["first_quote_delay_ns"]
                - coin["last_quote_lead_ns"],
            ) / max(1, coin["max_gap_ns"])) + 1
        ) and
        _retrieval_proof_valid(
            result.get("retrieval_proof"), open_ns=open_ns,
            close_ns=close_ns,
            retained_count=sum(row[1] for row in counts),
        )
    )


def _load_cached_result(path: Path, *, day: date) -> dict[str, object] | None:
    if not path.is_file():
        return None
    try:
        result = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError):
        return None
    if (not isinstance(result, dict) or
            result.get("historical_session") != day.isoformat()):
        return None
    return result


def _selection(day: date, threshold: int, *, cached: bool) -> dict[str, object]:
    return {
        "qualifying_date": day.isoformat(),
        "maximum_interior_gap_seconds": threshold,
        "result_source": "CACHE" if cached else "NEW_PREFLIGHT",
    }


def main(argv: Iterable[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Run one read-only ATOM TRUE V9 H1 historical SIP session",
    )
    parser.add_argument(
        "session", nargs="+", help="complete RTH session date(s) (YYYY-MM-DD)",
    )
    parser.add_argument("--run-id", help="replay run identity")
    parser.add_argument(
        "--preflight-only", action="store_true",
        help="validate retained quote coverage without running V9",
    )
    parser.add_argument(
        "--batch-preflight", action="store_true",
        help="scan dates in order, coverage-only, stopping at the first pass",
    )
    parser.add_argument(
        "--output-dir", default="h1-preflight-results",
        help="directory for full per-date JSON results in batch mode",
    )
    parser.add_argument(
        "--max-interior-gap-seconds", type=int, choices=(5,), default=5,
        help="frozen COIN RTH eligibility gap limit (5 seconds)",
    )
    parser.add_argument(
        "--persist-certified", action="store_true",
        help="atomically append a REPLAY_COMPLETE/CERTIFIED run",
    )
    parser.add_argument(
        "--git-commit", help="commit that produced the replay (defaults to HEAD)",
    )
    arguments = parser.parse_args(None if argv is None else tuple(argv))
    if len(arguments.session) > 1 and not arguments.batch_preflight:
        parser.error("multiple dates require --batch-preflight")
    if arguments.batch_preflight and arguments.run_id:
        parser.error("--run-id is only valid for a single session")
    if arguments.persist_certified and (arguments.batch_preflight or arguments.preflight_only):
        parser.error("--persist-certified requires a full single-session replay")
    try:
        days = tuple(date.fromisoformat(value) for value in arguments.session)
    except ValueError as error:
        parser.error(str(error))
    if arguments.batch_preflight:
        output_dir = Path(arguments.output_dir)
        output_dir.mkdir(parents=True, exist_ok=True)
        cached_results = {
            day: result for day in days
            if (result := _load_cached_result(
                output_dir / f"{day.isoformat()}.json", day=day,
            )) is not None
        }
        reader = None
        for day in days:
            result = cached_results.get(day)
            if result is not None:
                if _qualifies_cached_result(
                        result, day=day, maximum_gap_seconds=5):
                    print(json.dumps(
                        _selection(day, 5, cached=True),
                        sort_keys=True, separators=(",", ":"),
                    ))
                    return 0
                continue
            if reader is None:
                reader = AlpacaHistoricalSipReader.from_environment()
            opened, closed = _session(day)
            report = run_h1_session(
                reader=reader, session_open=opened, session_close=closed,
                replay_run_id=f"h1-preflight-{day.isoformat()}",
                preflight_only=True,
                maximum_interior_gap_seconds=5,
            )
            result_file = output_dir / f"{day.isoformat()}.json"
            result_file.write_text(
                json.dumps(report.to_dict(), sort_keys=True, separators=(",", ":"))
                + "\n", encoding="utf-8",
            )
            print(json.dumps(
                _batch_summary(report, result_file),
                sort_keys=True, separators=(",", ":"),
            ))
            if _preflight_passed(report):
                print(json.dumps(
                    _selection(day, 5, cached=False),
                    sort_keys=True, separators=(",", ":"),
                ))
                return 0
        print(json.dumps(
            {"qualifying_date": None,
             "maximum_interior_gap_seconds": None},
            sort_keys=True, separators=(",", ":"),
        ))
        return 2

    reader = AlpacaHistoricalSipReader.from_environment()
    day = days[0]
    opened, closed = _session(day)
    if arguments.persist_certified:
        from .historical_evidence import HistoricalEvidenceSpool
        evidence_context = HistoricalEvidenceSpool()
    else:
        from contextlib import nullcontext
        evidence_context = nullcontext(None)
    with evidence_context as evidence:
        report = run_h1_session(
            reader=reader, session_open=opened, session_close=closed,
            replay_run_id=arguments.run_id or f"h1-{day.isoformat()}",
            preflight_only=arguments.preflight_only,
            maximum_interior_gap_seconds=arguments.max_interior_gap_seconds,
            forecast_evidence=evidence,
        )
        if arguments.persist_certified:
            if report.execution_stage != "REPLAY_COMPLETE" or report.data_status != "CERTIFIED":
                print(json.dumps(report.to_dict(), sort_keys=True, separators=(",", ":")))
                return 2
            database_url = os.environ.get("HISTORICAL_EVIDENCE_DATABASE_URL")
            if not database_url:
                parser.error("HISTORICAL_EVIDENCE_DATABASE_URL is required to persist")
            import psycopg
            from .historical_evidence import HistoricalEvidenceWriter, build_manifest
            git_commit = arguments.git_commit or subprocess.run(
                ("git", "rev-parse", "HEAD"), check=True, capture_output=True,
                text=True,
            ).stdout.strip()
            manifest = build_manifest(report, evidence, git_commit=git_commit)
            with psycopg.connect(database_url) as connection:
                writes = HistoricalEvidenceWriter(connection).persist(
                    manifest, evidence,
                )
            report = replace(report, persistence_writes=writes)
    print(json.dumps(report.to_dict(), sort_keys=True, separators=(",", ":")))
    passed = (
        (report.execution_stage == "PREFLIGHT_ONLY" and
         report.data_status == "DATA_COMPLETE") or
        (report.execution_stage == "REPLAY_COMPLETE" and
         report.data_status == "CERTIFIED")
    )
    return 0 if passed else 2


if __name__ == "__main__":  # pragma: no cover - exercised through the CLI entry.
    raise SystemExit(main())


__all__ = [
    "FamilyCoverage", "H1ReplayReport", "H1_RUNNER_VERSION",
    "QuoteCoverage", "ReplayTimings", "ResolutionCoverage", "ResolutionSample",
    "V2RefreshProof", "V3Coverage", "main", "run_h1_session",
]
