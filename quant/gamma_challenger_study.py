"""G-1 offline, read-only Gamma Challenger falsification study.

This module deliberately composes the frozen V4C Gamma implementation with
the frozen E-1 window selector and bootstrap.  It has no production consumer
and no database write surface.
"""

from __future__ import annotations

import hashlib
import json
import math
import os
import random
import sys
from dataclasses import asdict, dataclass
from datetime import date, datetime, timezone
from pathlib import Path
from typing import Mapping, Sequence

from quant.evidence_scorecard import (
    BOOTSTRAP_RESAMPLES,
    BOOTSTRAP_SEED,
    CellSelector,
    EVIDENCE_TABLES,
    GUARD_SQL,
    INTERVAL_NARROW,
    INTERVAL_WIDE,
    Row,
    percentile_interval,
    session_bootstrap,
    session_of,
    V9_PROOF_SQL,
)
from quant.v9_v4b_accuracy import effective_n
from quant.v9_v4c_predictive import (
    GammaInput,
    Q3QuartileObservation,
    build_q3_quartile_gate,
    optimize_gamma,
)
from quant.v9_v4a_evidence import (
    V4AWriter,
    deserialize_forecast_record,
    deserialize_outcome_record,
)

CONTRACT = "docs/g-1-v4c-gamma-challenger-research-freeze.md"
CODE_VERSION = "ATOM-G1-GAMMA-STUDY-1"
READONLY_URL_ENV = "ATOM_E1_SCORECARD_READONLY_DATABASE_URL"
READONLY_ROLE = "atom_e1_scorecard_reader"
HORIZONS = ("30S", "1M", "5M", "15M", "30M", "1H")
MIN_CALIBRATION_WINDOWS = 250
MIN_CALIBRATION_EFFECTIVE_N = 200.0
MIN_HOLDOUT_SESSIONS = 20
MIN_HOLDOUT_WINDOWS = 500
NORMAL_90_Z = 1.6448536269514722
ADOPTION_SESSION = date(2026, 9, 4)


@dataclass(frozen=True, slots=True)
class StudyRow:
    forecast_record_id: str
    cohort_id: str
    horizon: str
    cutoff_epoch: float
    expected_return_bps: float | None
    predictive_variance_bps2: float | None
    q3_diagnostic_magnitude_bps: float | None
    actual_return_bps: float | None
    admissible: bool
    outcome_eligible: bool


@dataclass(frozen=True, slots=True)
class PreparedRows:
    rows: tuple[StudyRow, ...]
    n_input: int
    n_null_excluded: int
    n_inadmissible: int
    n_non_rth: int
    n_overlap_excluded: int


@dataclass(frozen=True, slots=True)
class FittedParameters:
    eta_hat: float
    gamma: float
    m2: float
    baseline_kappa_squared: float
    challenger_kappa_squared: float
    in_sample_optimizer_improvement: float
    convergence_status: str


def _finite_number(value: object, *, positive: bool = False) -> float | None:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return None
    result = float(value)
    if not math.isfinite(result) or (positive and result <= 0.0):
        return None
    return result


def select_windows(rows: Sequence[StudyRow], horizon: str) -> PreparedRows:
    """Apply E-1 selection unchanged, then exclude and count G-1 nulls."""

    selector = CellSelector("V9", ("G-1", horizon), horizon)
    ordered = sorted(rows, key=lambda row: (session_of(row.cutoff_epoch),
                                             row.cutoff_epoch,
                                             row.forecast_record_id))
    by_id: dict[str, StudyRow] = {}
    for row in ordered:
        if row.horizon != horizon or row.forecast_record_id in by_id:
            raise ValueError("G-1 rows require one unique, matching horizon identity")
        by_id[row.forecast_record_id] = row
        selector.feed(Row("V9", ("G-1", horizon), horizon, row.cutoff_epoch,
                          row.expected_return_bps, row.actual_return_bps,
                          row.forecast_record_id, row.admissible,
                          row.outcome_eligible))
    selected = tuple(by_id[row.record_key] for row in selector.windows)
    valid = tuple(row for row in selected if
                  _finite_number(row.expected_return_bps) is not None and
                  _finite_number(row.predictive_variance_bps2, positive=True) is not None and
                  _finite_number(row.q3_diagnostic_magnitude_bps) is not None and
                  float(row.q3_diagnostic_magnitude_bps) >= 0.0 and
                  _finite_number(row.actual_return_bps) is not None and
                  row.outcome_eligible)
    counts = selector.counts()
    return PreparedRows(valid, len(rows), len(selected) - len(valid),
                        counts.n_inadmissible, counts.n_non_rth,
                        counts.n_overlap_excluded)


def frozen_session_split(rows: Sequence[StudyRow], adoption_session: date
                         ) -> tuple[tuple[date, ...], tuple[date, ...]]:
    """Return all pre-adoption sessions and the first 20 post-adoption sessions."""
    sessions = sorted({session_of(row.cutoff_epoch) for row in rows})
    pilot = tuple(session for session in sessions if session < adoption_session)
    confirmatory = tuple(session for session in sessions
                         if session >= adoption_session)[:MIN_HOLDOUT_SESSIONS]
    return pilot, confirmatory


def fit_calibration(rows: Sequence[StudyRow]) -> FittedParameters | None:
    """Fit every parameter on calibration data only using frozen V4C math."""

    inputs = tuple(GammaInput(float(row.actual_return_bps) - float(row.expected_return_bps),
                              float(row.predictive_variance_bps2),
                              float(row.q3_diagnostic_magnitude_bps)) for row in rows)
    neff, _ = effective_n(tuple(item.error for item in inputs))
    if len(inputs) < MIN_CALIBRATION_WINDOWS or neff < MIN_CALIBRATION_EFFECTIVE_N:
        return None
    fit = optimize_gamma(inputs)
    if fit.convergence_status != "CONVERGED" or fit.eta is None or fit.gamma is None or fit.m2 is None:
        return None
    phi = tuple((1.0 - fit.eta) + fit.eta * item.magnitude ** 2 / fit.m2
                for item in inputs)
    baseline_k2 = math.fsum(item.error ** 2 / item.q0 for item in inputs) / len(inputs)
    challenger_k2 = math.fsum(item.error ** 2 / (item.q0 * scale)
                              for item, scale in zip(inputs, phi)) / len(inputs)
    if not all(math.isfinite(value) and value > 0.0
               for value in (baseline_k2, challenger_k2)):
        return None
    return FittedParameters(fit.eta, fit.gamma, fit.m2, baseline_k2,
                            challenger_k2, float(fit.objective_improvement),
                            fit.convergence_status)


def _loss(error: float, variance: float) -> float:
    return math.log(variance) + error * error / variance


def score_holdout(rows: Sequence[StudyRow], fitted: FittedParameters, *,
                  resamples: int = BOOTSTRAP_RESAMPLES) -> dict[str, object]:
    """Score a sealed holdout without fitting or mutating any parameter."""

    gains: list[float] = []
    baseline_covered = 0
    challenger_covered = 0
    sums: dict[date, float] = {}
    counts: dict[date, int] = {}
    quartile_rows = []
    for row in rows:
        error = float(row.actual_return_bps) - float(row.expected_return_bps)
        q0 = float(row.predictive_variance_bps2)
        magnitude = float(row.q3_diagnostic_magnitude_bps)
        phi = (1.0 - fitted.eta_hat) + fitted.eta_hat * magnitude * magnitude / fitted.m2
        baseline_variance = fitted.baseline_kappa_squared * q0
        challenger_variance = fitted.challenger_kappa_squared * q0 * phi
        gain = _loss(error, baseline_variance) - _loss(error, challenger_variance)
        gains.append(gain)
        session = session_of(row.cutoff_epoch)
        sums[session] = sums.get(session, 0.0) + gain
        counts[session] = counts.get(session, 0) + 1
        baseline_covered += abs(error) <= NORMAL_90_Z * math.sqrt(baseline_variance)
        challenger_covered += abs(error) <= NORMAL_90_Z * math.sqrt(challenger_variance)
        quartile_rows.append(Q3QuartileObservation(
            row.forecast_record_id,
            datetime.fromtimestamp(row.cutoff_epoch, timezone.utc), magnitude, gain))
    boot = session_bootstrap(sums, counts, random.Random(BOOTSTRAP_SEED),
                             resamples=resamples)
    gate = build_q3_quartile_gate(quartile_rows)
    n = len(rows)
    return {
        "delta_h": math.fsum(gains) / n,
        "interval_999": list(percentile_interval(boot, INTERVAL_WIDE)),
        "interval_95": list(percentile_interval(boot, INTERVAL_NARROW)),
        "quartile_verdict": gate.status,
        "quartile_reason_codes": list(gate.reason_codes),
        "baseline_coverage_90": baseline_covered / n,
        "challenger_coverage_90": challenger_covered / n,
        "n_sessions": len(counts),
        "n_windows": n,
    }


def evaluate_horizon(calibration: PreparedRows, holdout: PreparedRows, horizon: str,
                     *, resamples: int = BOOTSTRAP_RESAMPLES) -> dict[str, object]:
    calibration_errors = tuple(float(r.actual_return_bps) - float(r.expected_return_bps)
                               for r in calibration.rows)
    calibration_neff, _ = effective_n(calibration_errors)
    holdout_sessions = len({session_of(row.cutoff_epoch) for row in holdout.rows})
    counts = {
        "calibration_input": calibration.n_input,
        "calibration_windows": len(calibration.rows),
        "calibration_effective_n": calibration_neff,
        "calibration_null_excluded": calibration.n_null_excluded,
        "calibration_inadmissible": calibration.n_inadmissible,
        "calibration_non_rth": calibration.n_non_rth,
        "calibration_overlap_excluded": calibration.n_overlap_excluded,
        "holdout_input": holdout.n_input,
        "holdout_windows": len(holdout.rows),
        "holdout_sessions": holdout_sessions,
        "holdout_null_excluded": holdout.n_null_excluded,
        "holdout_inadmissible": holdout.n_inadmissible,
        "holdout_non_rth": holdout.n_non_rth,
        "holdout_overlap_excluded": holdout.n_overlap_excluded,
    }
    if (len(calibration.rows) < MIN_CALIBRATION_WINDOWS or
            calibration_neff < MIN_CALIBRATION_EFFECTIVE_N or
            holdout_sessions < MIN_HOLDOUT_SESSIONS or
            len(holdout.rows) < MIN_HOLDOUT_WINDOWS):
        return {"horizon": horizon, "counts": counts, "final_verdict": "INSUFFICIENT"}
    fitted = fit_calibration(calibration.rows)
    if fitted is None:
        return {"horizon": horizon, "counts": counts, "final_verdict": "INVALID",
                "protocol_reason": "NON_CONVERGED_OR_BOUNDARY_FIT"}
    score = score_holdout(holdout.rows, fitted, resamples=resamples)
    coverage_met = abs(score["challenger_coverage_90"] - .9) <= abs(
        score["baseline_coverage_90"] - .9)
    passed = (fitted.eta_hat > 0.0 and score["interval_999"][0] > 0.0 and
              score["quartile_verdict"] == "PASS" and coverage_met)
    return {"horizon": horizon, "counts": counts, **asdict(fitted), **score,
            "coverage_condition_met": coverage_met,
            "final_verdict": "PASS" if passed else "FAIL"}


def canonical_json(payload: object) -> str:
    return json.dumps(payload, sort_keys=True, separators=(",", ":"), allow_nan=False)


def build_receipt(*, verified_main_sha: str, horizon: str, cohort_identity: str,
                  calibration_sessions: Sequence[date], holdout_sessions: Sequence[date],
                  result: Mapping[str, object], current_user: str) -> dict[str, object]:
    verify_reader_identity(current_user)
    body = {
        "contract": CONTRACT, "code_version": CODE_VERSION,
        "verified_main_sha": verified_main_sha, "reader_identity": current_user,
        "horizon": horizon, "cohort_identity": cohort_identity,
        "calibration_sessions": [value.isoformat() for value in calibration_sessions],
        "holdout_sessions": [value.isoformat() for value in holdout_sessions],
        "bootstrap": {"resamples": BOOTSTRAP_RESAMPLES, "seed": BOOTSTRAP_SEED,
                      "intervals": [INTERVAL_WIDE, INTERVAL_NARROW]},
        "result": dict(result), "read_only": True,
        "forecast_writes": 0, "outcome_writes": 0, "evidence_writes": 0,
        "protocol_disclosure": (
            "G-1 variance/calibration falsification only; no forbidden E-2 statistic "
            "was computed or inspected; holdout parameters remained sealed."),
    }
    return {**body, "sha256": hashlib.sha256(canonical_json(body).encode()).hexdigest()}


def verify_reader_identity(current_user: object) -> None:
    if str(current_user) != READONLY_ROLE:
        raise SystemExit(f"G-1 reader refused: {current_user!r} is not {READONLY_ROLE!r}")


STREAM_SQL = """
SELECT f.forecast_record_id, f.forecast_record_hash, f.record_json,
       o.outcome_record_hash, o.record_json
FROM public.atom_v9_v4_forecasts AS f
LEFT JOIN LATERAL (
 SELECT x.outcome_record_hash, x.record_json FROM public.atom_v9_v4_outcomes AS x
 WHERE x.forecast_record_id = f.forecast_record_id
   AND x.record_json->>'target_timing_status' = 'VERIFIED'
 ORDER BY x.created_at, x.outcome_record_id LIMIT 1
) AS o ON true
WHERE f.record_json->>'evidence_origin' = 'PRODUCTION'
  AND f.horizon = %(horizon)s
  AND f.cutoff_at >= %(lo)s AND f.cutoff_at < %(hi)s
ORDER BY f.cutoff_at, f.forecast_record_id
"""


def open_readonly_connection(database_url: str):
    """Open only the explicit E-1 credential; callers own selection/proof reads."""
    import psycopg
    connection = psycopg.connect(database_url, connect_timeout=10)
    connection.read_only = True
    connection.isolation_level = psycopg.IsolationLevel.REPEATABLE_READ
    with connection.cursor() as cursor:
        cursor.execute(GUARD_SQL, {"tables": list(EVIDENCE_TABLES)})
        current_user, can_write, _, _ = cursor.fetchone()
        verify_reader_identity(current_user)
        if can_write:
            connection.close()
            raise SystemExit("G-1 reader refused: reader holds evidence write privilege")
    return connection


def read_rows(connection, *, horizon: str, lo: datetime,
              hi: datetime) -> tuple[StudyRow, ...]:
    """Read one horizon through the existing V9 proof seam, without writes."""
    if horizon not in HORIZONS or lo.tzinfo is None or hi.tzinfo is None or lo >= hi:
        raise ValueError("canonical horizon and ordered aware bounds required")
    with connection.transaction():
        with connection.cursor() as cursor:
            cursor.execute(GUARD_SQL, {"tables": list(EVIDENCE_TABLES)})
            current_user, can_write, _, _ = cursor.fetchone()
            verify_reader_identity(current_user)
            if can_write:
                raise SystemExit("G-1 reader refused: reader holds evidence write privilege")
            cursor.execute(STREAM_SQL, {"horizon": horizon, "lo": lo, "hi": hi})
            raw = cursor.fetchall()
            cursor.execute(V9_PROOF_SQL, {"ids": [str(row[0]) for row in raw]})
            proofs = {str(key): None if proof_id is None else
                      (proof_id, proof_hash, observed, endpoint, eligible, method)
                      for key, proof_id, proof_hash, observed, endpoint, eligible, method
                      in cursor.fetchall()}
    result = []
    for record_id, forecast_hash, forecast_json, outcome_hash, outcome_json in raw:
        forecast = deserialize_forecast_record(forecast_json,
                                               expected_hash=str(forecast_hash))
        proof = proofs.get(str(record_id))
        forecast = V4AWriter._apply_commit_proof(forecast, proof)
        outcome = (None if outcome_json is None else
                   deserialize_outcome_record(outcome_json,
                                              expected_hash=str(outcome_hash)))
        result.append(StudyRow(
            str(record_id), forecast.cohort_id, forecast.horizon,
            forecast.cutoff_at.timestamp(), forecast.expected_return_bps,
            forecast.predictive_variance_bps2,
            forecast.q3_diagnostic_magnitude_bps,
            None if outcome is None else outcome.actual_return_bps,
            forecast.persistence_proof_eligible is True,
            outcome is not None and outcome.target_timing_status == "VERIFIED" and
            outcome.proof_eligible is True))
    return tuple(result)


def configured_database_url() -> str:
    value = os.environ.get(READONLY_URL_ENV)
    if not value:
        raise SystemExit(f"G-1 reader refused: {READONLY_URL_ENV} is not set")
    return value


def _write_receipt(path: Path, receipt: Mapping[str, object]) -> None:
    """Create one immutable receipt; never replace prior evidence."""
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("x", encoding="utf-8") as stream:
        stream.write(json.dumps(receipt, sort_keys=True, indent=2, allow_nan=False))
        stream.write("\n")


def run_once(*, verified_main_sha: str, receipts_dir: Path = Path("docs"),
             now: datetime | None = None) -> dict[str, str]:
    """Run the frozen G-1 pilot/confirmatory study once across all horizons."""
    upper_bound = now or datetime.now(timezone.utc)
    if upper_bound.tzinfo is None:
        raise ValueError("G-1 upper bound must be timezone-aware")
    connection = open_readonly_connection(configured_database_url())
    verdicts: dict[str, str] = {}
    try:
        for horizon in HORIZONS:
            rows = read_rows(connection, horizon=horizon,
                             lo=datetime(1970, 1, 1, tzinfo=timezone.utc),
                             hi=upper_bound)
            pilot_sessions, holdout_sessions = frozen_session_split(rows, ADOPTION_SESSION)
            pilot_set, holdout_set = set(pilot_sessions), set(holdout_sessions)
            calibration = select_windows(
                tuple(row for row in rows if session_of(row.cutoff_epoch) in pilot_set),
                horizon)
            holdout = select_windows(
                tuple(row for row in rows if session_of(row.cutoff_epoch) in holdout_set),
                horizon)
            fitted = fit_calibration(calibration.rows)
            pilot_result: dict[str, object] = {
                "counts": {
                    "calibration_input": calibration.n_input,
                    "calibration_windows": len(calibration.rows),
                    "calibration_null_excluded": calibration.n_null_excluded,
                    "calibration_inadmissible": calibration.n_inadmissible,
                    "calibration_non_rth": calibration.n_non_rth,
                    "calibration_overlap_excluded": calibration.n_overlap_excluded,
                },
                "fit": None if fitted is None else asdict(fitted),
                "final_verdict": "INSUFFICIENT" if fitted is None else "PILOT_ONLY",
            }
            result = evaluate_horizon(calibration, holdout, horizon)
            cohort_identity = ",".join(sorted({row.cohort_id for row in
                                                calibration.rows + holdout.rows}))
            pilot_receipt = build_receipt(
                verified_main_sha=verified_main_sha, horizon=horizon,
                cohort_identity=cohort_identity,
                calibration_sessions=pilot_sessions, holdout_sessions=(),
                result=pilot_result, current_user=READONLY_ROLE)
            confirmatory_receipt = build_receipt(
                verified_main_sha=verified_main_sha, horizon=horizon,
                cohort_identity=cohort_identity,
                calibration_sessions=pilot_sessions,
                holdout_sessions=holdout_sessions, result=result,
                current_user=READONLY_ROLE)
            stem = horizon.lower()
            pilot_path = receipts_dir / f"g-1-pilot-{stem}-{pilot_receipt['sha256']}.json"
            confirmatory_path = receipts_dir / (
                f"g-1-confirmatory-{stem}-{confirmatory_receipt['sha256']}.json")
            if pilot_path.exists() or confirmatory_path.exists():
                raise SystemExit(f"G-1 refused to overwrite existing receipt for {horizon}")
            _write_receipt(pilot_path, pilot_receipt)
            _write_receipt(confirmatory_path, confirmatory_receipt)
            verdicts[horizon] = str(result["final_verdict"])
    finally:
        connection.close()
    return verdicts


def main(argv: Sequence[str] | None = None) -> int:
    if argv is None:
        argv = sys.argv[1:]
    if len(argv) != 2 or argv[0] != "--verified-main-sha" or not argv[1]:
        raise SystemExit(
            "usage: python -m quant.gamma_challenger_study --verified-main-sha SHA")
    for horizon, verdict in run_once(verified_main_sha=argv[1]).items():
        print(f"{horizon}: {verdict}")
    return 0


if __name__ == "__main__":  # pragma: no cover - exercised through main tests.
    raise SystemExit(main())