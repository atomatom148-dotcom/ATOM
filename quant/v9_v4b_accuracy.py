"""Frozen V4B accuracy state and pure Final Numbers transformation."""

from __future__ import annotations

from dataclasses import asdict, dataclass, replace
from datetime import datetime
import json
import math
import sys
from typing import Iterable, Mapping, Sequence

from quant.v9_v1_contract import HORIZONS, HORIZON_SECONDS
from quant.v9_v3_synthesis import V3HorizonResult
from quant.v9_v4a_evidence import (CONTRACT_VERSION, EVIDENCE_VERSION,
    ForecastRecord, OutcomeRecord, OVERLAP_METHOD_VERSION, canonical_sha256,
    select_non_overlapping, _canonical, _decanonical, _close_if_supported,
    _commit_if_supported, _rollback_if_supported)

STATE_VERSION = "ATOM_TRUE_V9_V4B_ACCURACY_1"
MODEL_VERSION = "ATOM_TRUE_V9_V4"
JEFFREYS_METHOD = "EFFECTIVE_N_ADJUSTED_JEFFREYS"
BETA_PROBABILITY_TOLERANCE = 1e-12
BETA_X_TOLERANCE = 1.7763568394002505e-15
BETA_BISECTION_MAX_ITERATIONS = 128
BETA_CF_TOLERANCE = 1e-14
BETA_CF_MAX_ITERATIONS = 256


def _beta_fraction(a: float, b: float, x: float) -> float:
    """Modified Lentz continued fraction for the incomplete beta."""
    tiny = sys.float_info.min
    qab, qap, qam = a + b, a + 1.0, a - 1.0
    c = 1.0
    d = 1.0 - qab * x / qap
    if abs(d) < tiny: d = tiny
    d = 1.0 / d
    result = d
    for m in range(1, BETA_CF_MAX_ITERATIONS + 1):
        m2 = 2 * m
        aa = m * (b - m) * x / ((qam + m2) * (a + m2))
        d = 1.0 + aa * d
        if abs(d) < tiny: d = tiny
        c = 1.0 + aa / c
        if abs(c) < tiny: c = tiny
        d = 1.0 / d; result *= d * c
        aa = -(a + m) * (qab + m) * x / ((a + m2) * (qap + m2))
        d = 1.0 + aa * d
        if abs(d) < tiny: d = tiny
        c = 1.0 + aa / c
        if abs(c) < tiny: c = tiny
        d = 1.0 / d
        delta = d * c; result *= delta
        if abs(delta - 1.0) <= BETA_CF_TOLERANCE:
            return result
    raise ArithmeticError("BETA_CONTINUED_FRACTION_DID_NOT_CONVERGE")


def regularized_incomplete_beta(a: float, b: float, x: float) -> float:
    if not (math.isfinite(a) and math.isfinite(b) and a > 0 and b > 0 and
            math.isfinite(x) and 0 <= x <= 1):
        raise ValueError("beta arguments must be finite, a/b positive, and x in [0,1]")
    if x == 0: return 0.0
    if x == 1: return 1.0
    factor = math.exp(math.lgamma(a+b)-math.lgamma(a)-math.lgamma(b) +
                      a*math.log(x) + b*math.log1p(-x))
    if x < (a + 1.0) / (a + b + 2.0):
        value = factor * _beta_fraction(a, b, x) / a
    else:
        value = 1.0 - factor * _beta_fraction(b, a, 1.0-x) / b
    return min(1.0, max(0.0, value))


def inverse_regularized_incomplete_beta(a: float, b: float, probability: float) -> float:
    if not math.isfinite(probability) or not 0 <= probability <= 1:
        raise ValueError("probability must be finite and in [0,1]")
    if probability == 0: return 0.0
    if probability == 1: return 1.0
    lo, hi = 0.0, 1.0
    for _ in range(BETA_BISECTION_MAX_ITERATIONS):
        mid = lo + (hi-lo)/2.0
        delta = regularized_incomplete_beta(a, b, mid) - probability
        if abs(delta) <= BETA_PROBABILITY_TOLERANCE or hi-lo <= BETA_X_TOLERANCE:
            return mid
        if delta < 0: lo = mid
        else: hi = mid
    return lo + (hi-lo)/2.0


def effective_n(values: Sequence[float]) -> tuple[float, tuple[str, ...]]:
    n = len(values)
    if n < 3: return float(n), ()
    mean = math.fsum(values) / n
    centered = [value-mean for value in values]
    denominator = math.fsum(value*value for value in centered)
    if denominator <= math.ulp(max(1.0, max(map(abs, values), default=1.0))) ** 2:
        return float(n), ("SERIAL_DEPENDENCE_UNIDENTIFIABLE",)
    rho = [math.fsum(centered[k]*centered[k+lag] for k in range(n-lag))/denominator
           for lag in range(1, n)]
    included: list[int] = []
    for first in range(1, n-1, 2):
        if rho[first-1] + rho[first] <= 0: break
        included.extend((first, first+1))
    tau = max(1.0, 1.0 + 2.0*math.fsum((1-lag/n)*rho[lag-1] for lag in included))
    result = n/tau
    if result > n and result-n <= 16*math.ulp(float(n)): result = float(n)
    return min(float(n), max(1.0, result)), ()


@dataclass(frozen=True, slots=True)
class HorizonAccuracyState:
    horizon: str; horizon_seconds: int; cohort_id: str; cohort_hash: str
    state_as_of: datetime; raw_resolved_n: int; non_overlapping_n: int
    first_cutoff: datetime | None; last_cutoff: datetime | None
    selected_forecast_digest: str; overlap_method_version: str
    bias_bps: float | None; bias_effective_n: float
    mae_bps: float | None; mae_effective_n: float
    rmse_bps: float | None; rmse_effective_n: float
    directional_wins: int; directional_losses: int; zero_realized_return_count: int
    directional_accuracy: float | None; directional_effective_n: float
    effective_wins: float | None; effective_losses: float | None
    jeffreys_posterior_mean: float | None; jeffreys_lower: float | None
    jeffreys_upper: float | None; jeffreys_interval_width: float | None
    jeffreys_method: str; status: str; reason_codes: tuple[str, ...]

    @property
    def effective_n(self) -> float: return self.directional_effective_n


@dataclass(frozen=True, slots=True)
class AccuracyState:
    state_id: str; state_hash: str; state_version: str; model_version: str
    symbol: str; cohort_id: str; state_as_of: datetime
    horizon_states: tuple[HorizonAccuracyState, ...]


def _horizon_state(horizon: str, cohort_id: str, cohort_hash: str, as_of: datetime,
                   pairs: Sequence[tuple[ForecastRecord, OutcomeRecord]]) -> HorizonAccuracyState:
    valid = [(f,o) for f,o in pairs if f.horizon == horizon and f.cohort_id == cohort_id and
             f.cohort_hash == cohort_hash and f.contract_version == CONTRACT_VERSION and
             f.evidence_version == EVIDENCE_VERSION and o.contract_version == CONTRACT_VERSION and
             o.evidence_version == EVIDENCE_VERSION and o.proof_eligible and
             o.target_timing_status != "UNVERIFIED" and f.cutoff_at <= as_of and
             o.forecast_record_id == f.forecast_record_id and
             isinstance(f.expected_return_bps, (int,float)) and
             isinstance(o.actual_return_bps, (int,float)) and
             not isinstance(f.expected_return_bps, bool) and
             not isinstance(o.actual_return_bps, bool) and
             math.isfinite(f.expected_return_bps) and math.isfinite(o.actual_return_bps)]
    selection = select_non_overlapping(valid)
    ids = set(selection.selected_ids)
    selected = sorted(((f,o) for f,o in valid if f.forecast_record_id in ids),
                      key=lambda pair:(pair[0].cutoff_at,pair[0].forecast_record_id))
    signed = [f.expected_return_bps-o.actual_return_bps for f,o in selected]
    absolute = [abs(x) for x in signed]; squared = [x*x for x in signed]
    directional = [
        0.0 if f.expected_return_bps == 0 else
        float((f.expected_return_bps > 0 and o.actual_return_bps > 0) or
              (f.expected_return_bps < 0 and o.actual_return_bps < 0))
        for f, o in selected if o.actual_return_bps != 0
    ]
    zeros = sum(o.actual_return_bps == 0 for _,o in selected)
    wins = sum(directional); losses = len(directional)-wins
    bn, br = effective_n(signed); mn, mr = effective_n(absolute)
    rn, rr = effective_n(squared); dn, dr = effective_n(directional)
    n = len(signed); d = len(directional)
    bias = math.fsum(signed)/n if n else None
    mae = math.fsum(absolute)/n if n else None
    rmse = math.sqrt(math.fsum(squared)/n) if n else None
    accuracy = wins/d if d else None
    ew = dn*wins/d if d else None; el = dn*losses/d if d else None
    if d:
        a, b = ew+.5, el+.5
        lower = inverse_regularized_incomplete_beta(a,b,.025)
        upper = inverse_regularized_incomplete_beta(a,b,.975)
        posterior = a/(a+b); width = upper-lower
        status = "MATURE" if dn >= 385 and width <= .10 else "PROVISIONAL"
    else:
        lower=upper=posterior=width=None; status="UNAVAILABLE"
    reasons = tuple(sorted(set(br+mr+rr+dr + (() if d else ("NO_SCOREABLE_DIRECTIONAL_EVIDENCE",)))))
    return HorizonAccuracyState(horizon,HORIZON_SECONDS[horizon],cohort_id,cohort_hash,as_of,
        selection.raw_resolved_n,selection.non_overlapping_n,selection.first_cutoff,
        selection.last_cutoff,selection.selected_digest,OVERLAP_METHOD_VERSION,bias,bn,mae,mn,
        rmse,rn,int(wins),int(losses),zeros,accuracy,dn,ew,el,posterior,lower,upper,width,
        JEFFREYS_METHOD,status,reasons)


def build_accuracy_state(*, symbol: str, state_as_of: datetime,
                         cohorts: Mapping[str, tuple[str,str]],
                         evidence: Iterable[tuple[ForecastRecord,OutcomeRecord]]) -> AccuracyState:
    if tuple(cohorts) != HORIZONS:
        raise ValueError("cohorts must contain exactly six canonical horizons in order")
    pairs = tuple(evidence)
    horizons = tuple(_horizon_state(h,*cohorts[h],state_as_of,pairs) for h in HORIZONS)
    cohort_id = "v9v4statecohort:" + canonical_sha256(tuple(cohorts[h] for h in HORIZONS))
    shell = AccuracyState("","",STATE_VERSION,MODEL_VERSION,symbol,cohort_id,state_as_of,horizons)
    payload = {k:v for k,v in asdict(shell).items() if k not in ("state_id","state_hash")}
    digest = canonical_sha256(payload)
    return replace(shell,state_id="v9v4state:"+digest,state_hash=digest)


@dataclass(frozen=True, slots=True)
class FinalNumbers:
    horizon: str; horizon_seconds: int; final_bps: float | None
    move_percent: float | None; direction: str; status: str
    accuracy: HorizonAccuracyState | None; reason_codes: tuple[str,...]


def final_numbers(result: V3HorizonResult,
                  accuracy: HorizonAccuracyState | None = None) -> FinalNumbers:
    value = result.expected_return_bps
    if value is None:
        return FinalNumbers(result.horizon,result.horizon_seconds,None,None,"UNAVAILABLE",
                            result.status,accuracy,result.reason_codes)
    reasons = list(result.reason_codes)
    try: move = 100.0*math.expm1(value/10000.0)
    except OverflowError: move = None
    if move is not None and not math.isfinite(move): move = None
    if move is None: reasons.append("MOVE_PERCENT_NUMERICAL_FAILURE")
    direction = "EXPECTED_UP" if value > 0 else "EXPECTED_DOWN" if value < 0 else "EXPECTED_FLAT"
    return FinalNumbers(result.horizon,result.horizon_seconds,value,move,direction,result.status,
                        accuracy,tuple(sorted(set(reasons))))


class AccuracyStateStore:
    def __init__(self, connection): self.connection = connection

    def insert(self, state: AccuracyState, created_at: datetime) -> str:
        cursor=self.connection.cursor()
        try:
            cursor.execute("SELECT state_hash FROM atom_v9_v4_states WHERE state_id=%s",(state.state_id,))
            rows=cursor.fetchall()
            if rows:
                status="IDEMPOTENT" if rows[0][0] == state.state_hash else "STATE_CONFLICT"
                _commit_if_supported(self.connection)
                return status
            cutoffs=[x for h in state.horizon_states for x in (h.first_cutoff,h.last_cutoff) if x]
            cursor.execute("INSERT INTO atom_v9_v4_states (state_id,state_hash,state_version,model_version,symbol,cohort_id,state_as_of,evidence_first_cutoff,evidence_last_cutoff,state_json,created_at) VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)",
                (state.state_id,state.state_hash,state.state_version,state.model_version,state.symbol,
                 state.cohort_id,state.state_as_of,min(cutoffs) if cutoffs else None,
                 max(cutoffs) if cutoffs else None,json.dumps(_canonical(asdict(state)),sort_keys=True),created_at))
            _commit_if_supported(self.connection)
            return "INSERT"
        except Exception:
            _rollback_if_supported(self.connection)
            raise
        finally:
            _close_if_supported(cursor)

    def latest_json(self, *, symbol: str, cohort_id: str, requested_cutoff: datetime):
        cursor=self.connection.cursor()
        try:
            cursor.execute("SELECT state_hash,state_json,state_as_of FROM atom_v9_v4_states WHERE state_version=%s AND model_version=%s AND symbol=%s AND cohort_id=%s AND state_as_of<=%s ORDER BY state_as_of DESC, state_id DESC LIMIT 2",
                (STATE_VERSION,MODEL_VERSION,symbol,cohort_id,requested_cutoff))
            rows=cursor.fetchall()
            _commit_if_supported(self.connection)
        except Exception:
            _rollback_if_supported(self.connection)
            raise
        finally:
            _close_if_supported(cursor)
        if not rows: return None, "UNAVAILABLE"
        greatest = rows[0][2]
        tied=[row for row in rows if row[2] == greatest]
        if len({row[0] for row in tied}) != 1: return None,"STATE_CONFLICT"
        state_hash, raw, _ = tied[0]
        try:
            canonical = json.loads(raw) if isinstance(raw, str) else raw
            if not isinstance(canonical, dict) or canonical.get("state_hash") != state_hash:
                return None, "STATE_HASH_MISMATCH"
            value = _decanonical(canonical)
            payload = {key: item for key, item in value.items()
                       if key not in ("state_id", "state_hash")}
            if canonical_sha256(payload) != state_hash:
                return None, "STATE_HASH_MISMATCH"
            horizons = tuple(HorizonAccuracyState(
                **{**item, "reason_codes": tuple(item["reason_codes"])}
            ) for item in value["horizon_states"])
            state = AccuracyState(
                value["state_id"], value["state_hash"], value["state_version"],
                value["model_version"], value["symbol"], value["cohort_id"],
                value["state_as_of"], horizons,
            )
        except (KeyError, TypeError, ValueError):
            return None, "STATE_DESERIALIZATION_INVALID"
        return state,"AVAILABLE"
