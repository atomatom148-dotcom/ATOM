"""Frozen V4C predictive scale, range, probability, and gamma research state.

All builders in this module are offline pure functions.  ``final_numbers`` is
the bounded live transformation and never examines historical observations.
"""

from __future__ import annotations

from bisect import bisect_left, bisect_right
from dataclasses import asdict, dataclass, replace
from datetime import datetime
import hashlib
import json
import math
import sys
from typing import Callable, Iterable, Mapping, Sequence

from quant.v9_v1_contract import HORIZONS, HORIZON_SECONDS
from quant.v9_v3_synthesis import V3HorizonResult
from quant.v9_v4a_evidence import _canonical, canonical_sha256
from quant.v9_v4b_accuracy import effective_n, inverse_regularized_incomplete_beta

MODEL_VERSION = "ATOM_TRUE_V9_V4"
THRESHOLD_STATE_VERSION = "ATOM_TRUE_V9_V4C_THRESHOLD_1"
SCALE_STATE_VERSION = "ATOM_TRUE_V9_V4C_SCALE_1"
RANGE_STATE_VERSION = "ATOM_TRUE_V9_V4C_RANGE_1"
PROBABILITY_STATE_VERSION = "ATOM_TRUE_V9_V4C_PROBABILITY_1"
GAMMA_STATE_VERSION = "ATOM_TRUE_V9_V4C_GAMMA_CHALLENGER_1"
THRESHOLD_METHOD = "ATOM_TRUE_V9_V4_EMPIRICAL_NEAREST_RANK_1"
HAC_METHOD = "ATOM_TRUE_V9_V4_NW_BARTLETT_HAC_1"
HAC_LAG_METHOD = "ATOM_TRUE_V9_V4_NW_LAG_4N100_2_9_1"
NORMAL_CDF_METHOD = "ATOM_TRUE_V9_V4_NORMAL_CDF_ERFC_1"
NORMAL_PPF_METHOD = "ATOM_TRUE_V9_V4_NORMAL_PPF_BISECTION_ERFC_1"
HOLM_METHOD = "ATOM_TRUE_V9_V4_HOLM_6EVENT_005_1"
RELIABILITY_METHOD = "ATOM_TRUE_V9_V4_RELIABILITY_5BIN_EARLY_REMAINDER_TIE_MERGE_1"
GAMMA_METHOD = "ATOM_TRUE_V9_V4_GAMMA_ETA_GOLDEN_SECTION_1"
Q3_PARTITION_METHOD = "ATOM_TRUE_V9_V4_Q3_QUARTILE_EARLY_REMAINDER_TIE_MERGE_1"
Q3_HOLM_METHOD = "ATOM_TRUE_V9_V4_Q3_QUARTILE_HOLM_DEGRADATION_1"
EVENTS = ("POSITIVE", "NEGATIVE", "MEDIUM_POSITIVE", "MEDIUM_NEGATIVE",
          "LARGE_POSITIVE", "LARGE_NEGATIVE")
EPSILON = 2.0 ** -52


def nearest_rank(values: Sequence[float], p: float) -> float:
    xs = sorted(float(x) for x in values)
    if not xs or not math.isfinite(p) or not 0 < p <= 1 or any(not math.isfinite(x) for x in xs):
        raise ValueError("finite nonempty values and 0 < p <= 1 required")
    return xs[math.ceil(p * len(xs)) - 1]


def normal_cdf(z: float) -> float:
    if math.isnan(z): raise ValueError("NaN normal argument")
    value = .5 * math.erfc(-z / math.sqrt(2.0))
    tol = 64 * EPSILON * max(1.0, abs(value))
    if -tol <= value <= 1 + tol: return min(1.0, max(0.0, value))
    raise ArithmeticError("NORMAL_CDF_INVALID")


def normal_ppf(p: float, *, maximum_iterations: int = 256) -> float:
    if not math.isfinite(p) or not 0 <= p <= 1: raise ValueError("p must be in [0,1]")
    if p == 0: return -math.inf
    if p == 1: return math.inf
    lo, hi = -40.0, 40.0
    for _ in range(maximum_iterations):
        mid = lo + (hi-lo)/2
        q = normal_cdf(mid)
        if abs(q-p) <= 1e-12 or hi-lo <= 1.7763568394002505e-15: return mid
        if q < p: lo = mid
        else: hi = mid
    raise ArithmeticError("NORMAL_QUANTILE_DID_NOT_CONVERGE")


@dataclass(frozen=True, slots=True)
class HACResult:
    status: str; n: int; lag: int; mean: float | None; gamma0: float | None
    gammas: tuple[float, ...]; omega: float | None; se: float | None
    z: float | None; p_upper: float; reason_codes: tuple[str, ...]


def hac(values: Sequence[float]) -> HACResult:
    xs = tuple(float(x) for x in values); n = len(xs)
    if not n or any(not math.isfinite(x) for x in xs):
        return HACResult("UNAVAILABLE",n,0,None,None,(),None,None,None,1.0,("HAC_INPUT_UNAVAILABLE",))
    mean = math.fsum(xs)/n; centered = tuple(x-mean for x in xs)
    lag = min(max(math.floor(4*(n/100)**(2/9)),0),n-1)
    g0 = math.fsum(x*x for x in centered)/n
    gs = tuple(math.fsum(centered[k]*centered[k-l] for k in range(l,n))/n
               for l in range(1,lag+1))
    omega = g0 + 2*math.fsum((1-l/(lag+1))*gs[l-1] for l in range(1,lag+1))
    tolerance = 64*EPSILON*max(1.0,abs(g0),*(abs(x) for x in gs))
    if omega < -tolerance:
        return HACResult("UNAVAILABLE",n,lag,mean,g0,gs,None,None,None,1.0,("HAC_VARIANCE_INVALID",))
    omega=max(0.0,omega)
    if omega == 0:
        return HACResult("UNAVAILABLE",n,lag,mean,g0,gs,0.0,None,None,1.0,("HAC_VARIANCE_ZERO",))
    se=math.sqrt(omega/n); z=mean/se
    return HACResult("AVAILABLE",n,lag,mean,g0,gs,omega,se,z,1-normal_cdf(z),())


@dataclass(frozen=True, slots=True)
class HolmResult:
    index: int; rank: int; threshold: float; passed: bool


def holm(p_values: Sequence[float], *, alpha: float=.05) -> tuple[HolmResult,...]:
    m=len(p_values); ordered=sorted(range(m),key=lambda i:(p_values[i],i)); passing=True; out=[]
    for rank,index in enumerate(ordered,1):
        threshold=alpha/(m-rank+1); passed=passing and p_values[index] <= threshold
        if not passed: passing=False
        out.append(HolmResult(index,rank,threshold,passed))
    return tuple(sorted(out,key=lambda x:x.index))


@dataclass(frozen=True, slots=True)
class ProbabilityCalibration:
    status: str; brier_score: float | None; climatology_brier_score: float | None
    mean_brier_improvement: float | None; hac_result: HACResult
    p: float; brier_gate_passed: bool; reason_codes: tuple[str,...]


def calibrate_probability_event(predictions: Sequence[float], outcomes: Sequence[int],
                                p_climatology: float) -> ProbabilityCalibration:
    """Evaluate one event; unavailable HAC can never become a Brier pass."""
    ps=tuple(float(x) for x in predictions); os=tuple(outcomes)
    if (not ps or len(ps)!=len(os) or not math.isfinite(p_climatology) or
            not 0<=p_climatology<=1 or any(not math.isfinite(p) or not 0<=p<=1 for p in ps) or
            any(o not in (0,1) for o in os)):
        unavailable=hac(())
        return ProbabilityCalibration("UNAVAILABLE",None,None,None,unavailable,1.0,False,
                                      ("PROBABILITY_INPUT_UNAVAILABLE",))
    model=tuple((p-o)**2 for p,o in zip(ps,os))
    climate=tuple((p_climatology-o)**2 for o in os)
    improvements=tuple(c-m for c,m in zip(climate,model)); result=hac(improvements)
    bs=math.fsum(model)/len(model); cbs=math.fsum(climate)/len(climate)
    mean=math.fsum(improvements)/len(improvements)
    if result.status=="UNAVAILABLE":
        return ProbabilityCalibration("UNAVAILABLE",bs,cbs,mean,result,1.0,False,
                                      result.reason_codes)
    passed=result.p_upper<.05 and mean>0
    return ProbabilityCalibration("PROVISIONAL",bs,cbs,mean,result,result.p_upper,passed,())


@dataclass(frozen=True, slots=True)
class ProbabilityObservation:
    cutoff: datetime; target_resolved_at: datetime; forecast_record_id: str
    prediction: float; outcome: int


@dataclass(frozen=True, slots=True)
class ProbabilityEventInput:
    event: str; observations: tuple[ProbabilityObservation,...]
    calibration_end: datetime; holdout_end: datetime


@dataclass(frozen=True, slots=True)
class ProbabilityEventState:
    event: str; status: str; calibration: ProbabilityCalibration
    holm_rank: int; holm_threshold: float; holm_passed: bool
    holm_gate_lower_bound: float | None; reason_codes: tuple[str,...]


def calibrate_six_events(inputs: Mapping[str, ProbabilityEventInput]) -> tuple[ProbabilityEventState,...]:
    """Apply the frozen, horizon-local six-event probability family."""
    if tuple(inputs) != EVENTS or any(inputs[event].event != event for event in EVENTS):
        raise ValueError("exact canonical six-event family required")
    prepared=[]
    for event in EVENTS:
        item=inputs[event]
        if (item.calibration_end.tzinfo is None or item.holdout_end.tzinfo is None or
                item.calibration_end>=item.holdout_end):
            raise ValueError("ordered timezone-aware probability boundaries required")
        ordered=tuple(sorted(item.observations,key=lambda x:(x.cutoff,x.forecast_record_id)))
        valid=tuple(x for x in ordered if x.cutoff.tzinfo is not None and
                    x.target_resolved_at.tzinfo is not None and math.isfinite(x.prediction) and
                    0<=x.prediction<=1 and x.outcome in (0,1))
        calibration=tuple(x for x in valid if x.cutoff<=item.calibration_end and
                          x.target_resolved_at<=item.calibration_end)
        holdout=tuple(x for x in valid if item.calibration_end<x.cutoff<=item.holdout_end and
                      x.target_resolved_at<=item.holdout_end)
        calibration_sequence=tuple(x.outcome for x in calibration)
        calibration_neff,_=effective_n(calibration_sequence)
        holdout_sequence=tuple(x.outcome for x in holdout); holdout_neff,_=effective_n(holdout_sequence)
        events=sum(holdout_sequence); effective_events=holdout_neff*events/len(holdout) if holdout else 0.0
        climatology=(sum(calibration_sequence)+.5)/(len(calibration_sequence)+1) if calibration else math.nan
        reliability_result=reliability(tuple(ReliabilityObservation(
            x.prediction,x.outcome,x.cutoff,x.forecast_record_id) for x in holdout))
        calibration_result=calibrate_probability_event(
            tuple(x.prediction for x in holdout),holdout_sequence,climatology)
        prepared.append((calibration_result,len(calibration),calibration_neff,holdout_neff,
                         effective_events,holdout_neff-effective_events,reliability_result))
    calibrations=tuple(x[0] for x in prepared)
    adjusted=holm(tuple(x.p if x.hac_result.status=="AVAILABLE" else 1.0 for x in calibrations))
    states=[]
    for event,details,cal,correction in zip(EVENTS,prepared,calibrations,adjusted):
        _,calibration_n,calibration_neff,holdout_neff,effective_events,effective_non_events,reliability_result=details
        reasons=list(cal.reason_codes)
        evidence=(calibration_n>=500 and calibration_neff>=400 and holdout_neff>=400 and
                  effective_events>=30 and effective_non_events>=30)
        if not evidence:reasons.append("PROBABILITY_EVIDENCE_INSUFFICIENT")
        reliable=reliability_result.status=="PASS"
        if not reliable:reasons.append("RELIABILITY_GATE_FAILED")
        lower=None
        if correction.passed and cal.hac_result.status=="AVAILABLE":
            lower=cal.mean_brier_improvement-normal_ppf(1-correction.threshold)*cal.hac_result.se
        mature=(evidence and reliable and cal.hac_result.status=="AVAILABLE" and cal.brier_gate_passed and
                correction.passed and lower is not None and math.isfinite(lower) and lower>0)
        status="MATURE" if mature else ("UNAVAILABLE" if cal.hac_result.status=="UNAVAILABLE" else "PROVISIONAL")
        states.append(ProbabilityEventState(event,status,cal,correction.rank,correction.threshold,
                                            correction.passed,lower,tuple(sorted(set(reasons)))))
    return tuple(states)


@dataclass(frozen=True, slots=True)
class Q3QuartileObservation:
    forecast_record_id: str; cutoff: datetime; magnitude: float; d_gamma: float


@dataclass(frozen=True, slots=True)
class Q3QuartileState:
    quartile_index: int; status: str; raw_n: int; effective_n: float
    minimum_magnitude: float | None; maximum_magnitude: float | None
    mean_d_gamma: float | None
    hac_result: HACResult; p_degradation: float; evidence_digest: str
    holm_rank: int | None; holm_threshold: float | None
    significant_degradation: bool
    reason_codes: tuple[str,...]


def build_q3_quartile_state(observations: Sequence[Q3QuartileObservation], *, quartile_index: int=0) -> Q3QuartileState:
    ordered=tuple(sorted(observations,key=lambda x:(x.cutoff,x.forecast_record_id)))
    valid=all(x.cutoff.tzinfo is not None and math.isfinite(x.magnitude) and x.magnitude>=0 and
              math.isfinite(x.d_gamma) for x in ordered)
    digest=canonical_sha256(tuple((x.forecast_record_id,x.cutoff,x.magnitude,x.d_gamma)
                                  for x in ordered))
    if not ordered or not valid:
        result=hac(())
        return Q3QuartileState(quartile_index,"UNAVAILABLE",len(ordered),0.0,None,None,None,
                              result,1.0,digest,None,None,False,("Q3_QUARTILE_INPUT_UNAVAILABLE",))
    sequence=tuple(x.d_gamma for x in ordered); neff,_=effective_n(sequence); result=hac(sequence)
    if result.status=="UNAVAILABLE":
        return Q3QuartileState(quartile_index,"UNAVAILABLE",len(ordered),neff,
                              min(x.magnitude for x in ordered),max(x.magnitude for x in ordered),
                              result.mean,result,1.0,digest,None,None,False,result.reason_codes)
    return Q3QuartileState(quartile_index,"AVAILABLE",len(ordered),neff,
                          min(x.magnitude for x in ordered),max(x.magnitude for x in ordered),
                          result.mean,result,normal_cdf(result.z),digest,None,None,False,())


@dataclass(frozen=True, slots=True)
class Q3QuartileGate:
    status: str; q: int; r: int; initial_sizes: tuple[int,...]
    removed_boundaries: tuple[int,...]; quartiles: tuple[Q3QuartileState,...]
    significant_degradation: tuple[bool,...]; evidence_digest: str
    reason_codes: tuple[str,...]


def build_q3_quartile_gate(observations: Sequence[Q3QuartileObservation]) -> Q3QuartileGate:
    canonical=tuple(sorted(observations,key=lambda x:(x.magnitude,x.cutoff,x.forecast_record_id)))
    digest=canonical_sha256(tuple((x.forecast_record_id,x.cutoff,x.magnitude,x.d_gamma)
                                  for x in canonical))
    n=len(canonical); q,r=divmod(n,4)
    if n<4:
        return Q3QuartileGate("UNAVAILABLE",q,r,(),(),(),(),digest,("Q3_QUARTILE_COUNT_INSUFFICIENT",))
    if any(x.cutoff.tzinfo is None or not math.isfinite(x.magnitude) or x.magnitude<0 or
           not math.isfinite(x.d_gamma) for x in canonical):
        return Q3QuartileGate("UNAVAILABLE",q,r,(),(),(),(),digest,("Q3_QUARTILE_INPUT_UNAVAILABLE",))
    sizes=tuple(q+(index<r) for index in range(4)); boundaries=[]; total=0
    for size in sizes[:-1]:total+=size;boundaries.append(total)
    removed=tuple(index for index,boundary in enumerate(boundaries,1)
                  if canonical[boundary-1].magnitude==canonical[boundary].magnitude)
    surviving=[boundary for index,boundary in enumerate(boundaries,1) if index not in removed]
    if len(surviving)!=3:
        return Q3QuartileGate("UNAVAILABLE",q,r,sizes,removed,(),(),digest,("Q3_QUARTILE_TIE_COLLAPSE",))
    groups=[];start=0
    for end in surviving+[n]:groups.append(canonical[start:end]);start=end
    quartiles=tuple(build_q3_quartile_state(group,quartile_index=index)
                    for index,group in enumerate(groups,1))
    reasons=tuple(reason for quartile in quartiles for reason in quartile.reason_codes)
    if any(quartile.status!="AVAILABLE" or quartile.effective_n<50 for quartile in quartiles):
        extra=("Q3_QUARTILE_EFFECTIVE_N_INSUFFICIENT",) if any(x.effective_n<50 for x in quartiles) else ()
        return Q3QuartileGate("UNAVAILABLE",q,r,sizes,removed,quartiles,(),digest,
                             tuple(sorted(set(reasons+extra))))
    corrections=holm(tuple(x.p_degradation for x in quartiles))
    quartiles=tuple(replace(quartile,holm_rank=correction.rank,
                            holm_threshold=correction.threshold,
                            significant_degradation=correction.passed)
                    for quartile,correction in zip(quartiles,corrections))
    degraded=tuple(x.significant_degradation for x in quartiles)
    status="FAIL" if any(degraded) else "PASS"
    final_reasons=("Q3_QUARTILE_SIGNIFICANT_DEGRADATION",) if status=="FAIL" else ()
    return Q3QuartileGate(status,q,r,sizes,removed,quartiles,degraded,digest,final_reasons)


def empirical_cdfs(sorted_z: Sequence[float], z: float) -> tuple[float,float]:
    n=len(sorted_z)
    if not n or not math.isfinite(z): raise ValueError("finite z and nonempty CDF required")
    return ((bisect_right(sorted_z,z)+.5)/(n+1),
            (bisect_left(sorted_z,z)+.5)/(n+1))


@dataclass(frozen=True, slots=True)
class ReliabilityObservation:
    probability: float; outcome: int; cutoff: datetime; forecast_record_id: str

@dataclass(frozen=True, slots=True)
class ReliabilityBin:
    raw_n: int; effective_n: float; minimum_probability: float; maximum_probability: float
    mean_probability: float; events: int; non_events: int; effective_events: float
    effective_non_events: float; jeffreys_lower: float; jeffreys_upper: float; passed: bool

@dataclass(frozen=True, slots=True)
class ReliabilityResult:
    status: str; q: int; r: int; initial_sizes: tuple[int,...]
    removed_boundaries: tuple[int,...]; bins: tuple[ReliabilityBin,...]; reason_codes: tuple[str,...]


def reliability(observations: Sequence[ReliabilityObservation]) -> ReliabilityResult:
    n=len(observations)
    if n < 5: return ReliabilityResult("UNAVAILABLE",n//5,n%5,(),(),(),("RELIABILITY_BIN_COUNT_INSUFFICIENT",))
    ordered=sorted(observations,key=lambda x:(x.probability,x.cutoff,x.forecast_record_id))
    if any(not math.isfinite(x.probability) or not 0<=x.probability<=1 or x.outcome not in (0,1) for x in ordered):
        return ReliabilityResult("UNAVAILABLE",n//5,n%5,(),(),(),("RELIABILITY_INPUT_INVALID",))
    q,r=divmod(n,5); sizes=tuple(q+(j<r) for j in range(5)); bounds=[]; total=0
    for size in sizes[:-1]: total+=size; bounds.append(total)
    removed=tuple(j+1 for j,b in enumerate(bounds) if ordered[b-1].probability == ordered[b].probability)
    surviving=[b for j,b in enumerate(bounds,1) if j not in removed]
    groups=[]; start=0
    for end in surviving+[n]: groups.append(ordered[start:end]); start=end
    level=1-.05/len(groups); tail=(1-level)/2; result=[]
    for group in groups:
        chrono=sorted(group,key=lambda x:(x.cutoff,x.forecast_record_id)); seq=[x.outcome for x in chrono]
        neff,_=effective_n(seq); events=sum(seq); ee=neff*events/len(seq); en=neff-ee
        lo=inverse_regularized_incomplete_beta(ee+.5,en+.5,tail)
        hi=inverse_regularized_incomplete_beta(ee+.5,en+.5,1-tail)
        meanp=math.fsum(x.probability for x in group)/len(group)
        result.append(ReliabilityBin(len(group),neff,group[0].probability,group[-1].probability,
            meanp,events,len(group)-events,ee,en,lo,hi,neff>=30 and lo<=meanp<=hi))
    passed=all(x.passed for x in result)
    return ReliabilityResult("PASS" if passed else "FAIL",q,r,sizes,removed,tuple(result),())


@dataclass(frozen=True, slots=True)
class CalibrationObservation:
    cutoff: datetime; forecast_record_id: str; actual_bps: float; mean_bps: float
    q0_bps2: float; session_id: str; target_resolved_at: datetime

@dataclass(frozen=True, slots=True)
class ScaleResult:
    status: str; raw_n: int; effective_n: float; kappa_squared: float | None
    kappa: float | None; reason_codes: tuple[str,...]

def _resolved_by(x: CalibrationObservation, boundary: datetime) -> bool:
    return (boundary.tzinfo is not None and x.cutoff.tzinfo is not None and
            x.target_resolved_at.tzinfo is not None and
            x.cutoff <= boundary and x.target_resolved_at <= boundary)

def calibrate_scale(observations: Sequence[CalibrationObservation], *, calibration_end: datetime) -> ScaleResult:
    valid=tuple(x for x in observations if _resolved_by(x,calibration_end) and all(math.isfinite(v) for v in
        (x.actual_bps,x.mean_bps,x.q0_bps2)) and x.q0_bps2>0)
    scores_list=[]
    for x in valid:
        error=x.actual_bps-x.mean_bps
        try:score=error*error/x.q0_bps2
        except OverflowError:continue
        if math.isfinite(error) and math.isfinite(score):scores_list.append(score)
    scores=tuple(scores_list)
    neff,reasons=effective_n(scores)
    k2=math.fsum(scores)/len(scores) if scores else None
    k=math.sqrt(k2) if k2 is not None and math.isfinite(k2) and k2>0 else None
    status="MATURE" if len(scores)>=250 and neff>=200 and k is not None else ("PROVISIONAL" if k is not None else "UNAVAILABLE")
    return ScaleResult(status,len(scores),neff,k2 if k is not None else None,k,tuple(reasons))

@dataclass(frozen=True, slots=True)
class ThresholdResult:
    status: str; raw_n: int; effective_n: float; sessions: int
    medium_bps: float | None; large_bps: float | None; reason_codes: tuple[str,...]

def build_thresholds(observations: Sequence[CalibrationObservation], *, reference_end: datetime) -> ThresholdResult:
    valid=tuple(x for x in observations if _resolved_by(x,reference_end) and math.isfinite(x.actual_bps))
    magnitudes=tuple(abs(x.actual_bps) for x in valid); neff,reasons=effective_n(magnitudes)
    sessions=len({x.session_id for x in valid})
    mature=bool(magnitudes) and sessions>=20 and neff>=500
    return ThresholdResult("MATURE" if mature else "UNAVAILABLE",len(valid),neff,sessions,
        nearest_rank(magnitudes,.75) if mature else None,nearest_rank(magnitudes,.9) if mature else None,
        tuple(reasons))

@dataclass(frozen=True, slots=True)
class RangeResult:
    status: str; quantile: float | None; calibration_n: int; calibration_effective_n: float
    validation_n: int; validation_effective_n: float; coverage: float | None
    coverage_interval: tuple[float,float] | None; effective_misses: float
    miss_share_interval: tuple[float,float] | None; rolling_effective_n: float
    rolling_interval: tuple[float,float] | None; mean_width: float | None
    reason_codes: tuple[str,...]

@dataclass(frozen=True, slots=True)
class RangeValidationObservation:
    cutoff: datetime; target_resolved_at: datetime; actual_bps: float
    lower_bps: float; upper_bps: float; session_id: str

def _jeffreys(binary: Sequence[int]) -> tuple[float,tuple[float,float]] | None:
    if not binary:return None
    neff,_=effective_n(binary); wins=sum(binary); ew=neff*wins/len(binary); el=neff-ew
    return neff,(inverse_regularized_incomplete_beta(ew+.5,el+.5,.025),
                 inverse_regularized_incomplete_beta(ew+.5,el+.5,.975))

def calibrate_range(calibration_scores: Sequence[float], validation: Sequence[RangeValidationObservation],
                    rolling_session_ids: Sequence[str], *, validation_end: datetime) -> RangeResult:
    scores=tuple(float(x) for x in calibration_scores if math.isfinite(x) and x>=0)
    score_neff,score_reasons=effective_n(scores); j=math.ceil((len(scores)+1)*.9)
    quantile=sorted(scores)[j-1] if scores and j<=len(scores) else None
    valid=tuple(x for x in validation if validation_end.tzinfo is not None and x.cutoff.tzinfo is not None and
        x.target_resolved_at.tzinfo is not None and x.cutoff<=validation_end and
        x.target_resolved_at<=validation_end and all(math.isfinite(v) for v in
        (x.actual_bps,x.lower_bps,x.upper_bps)) and x.lower_bps<=x.upper_bps and
        math.isfinite(x.upper_bps-x.lower_bps))
    covered=[int(x.lower_bps<=x.actual_bps<=x.upper_bps) for x in valid]; cov=_jeffreys(covered)
    lower_miss=[int(x.actual_bps<x.lower_bps) for x in valid
                if not x.lower_bps<=x.actual_bps<=x.upper_bps]; miss=_jeffreys(lower_miss)
    rolling_set=set(rolling_session_ids[-20:]); rolling=[flag for flag,x in zip(covered,valid) if x.session_id in rolling_set]
    roll=_jeffreys(rolling); coverage=math.fsum(covered)/len(covered) if covered else None
    effmiss=(cov[0]*(1-coverage)) if cov and coverage is not None else 0.0
    width=math.fsum(x.upper_bps-x.lower_bps for x in valid)/len(valid) if valid else None
    mature=(quantile is not None and len(scores)>=250 and score_neff>=200 and len(valid)>=250 and
            cov is not None and cov[0]>=200 and cov[1][0]<=.9<=cov[1][1] and
            (cov[1][1]-cov[1][0])/2<=.05 and effmiss>=20 and miss is not None and
            miss[1][0]<=.5<=miss[1][1] and roll is not None and roll[0]>=100 and
            roll[1][0]<=.9<=roll[1][1] and width is not None and math.isfinite(width))
    status="MATURE" if mature else ("PROVISIONAL" if quantile is not None else "UNAVAILABLE")
    return RangeResult(status,quantile,len(scores),score_neff,len(valid),cov[0] if cov else 0.0,
        coverage,cov[1] if cov else None,effmiss,miss[1] if miss else None,roll[0] if roll else 0.0,
        roll[1] if roll else None,width,tuple(score_reasons))


@dataclass(frozen=True, slots=True)
class GammaInput:
    error: float; q0: float; magnitude: float

@dataclass(frozen=True, slots=True)
class GammaOptimizerResult:
    status: str; eta: float | None; gamma: float | None; objective: float | None
    m2: float | None; iterations: int; interval: tuple[float,float] | None
    evaluations: tuple[tuple[float,float],...]; reason_codes: tuple[str,...]
    baseline_objective: float | None=None; challenger_objective: float | None=None
    objective_improvement: float | None=None; convergence_status: str="UNAVAILABLE"


def gamma_objective(inputs: Sequence[GammaInput], eta: float, m2: float) -> float:
    if not 0<=eta<1: return math.inf
    terms=[]; q=[]
    for x in inputs:
        phi=(1-eta)+eta*x.magnitude*x.magnitude/m2; value=x.q0*phi
        if not math.isfinite(value) or value<=0: return math.inf
        q.append(value); terms.append(x.error*x.error/value)
    k2=math.fsum(terms)/len(terms) if terms else math.nan
    if not math.isfinite(k2) or k2<=0: return math.inf
    losses=[math.log(k2*v)+x.error*x.error/(k2*v) for x,v in zip(inputs,q)]
    result=math.fsum(losses)
    return result if math.isfinite(result) else math.inf


def _objective_preferred(a: tuple[float,float], b: tuple[float,float]) -> bool:
    ea,la=a; eb,lb=b
    if math.isfinite(la) != math.isfinite(lb): return math.isfinite(la)
    if not math.isfinite(la): return ea < eb
    tol=64*EPSILON*max(1.0,abs(la),abs(lb))
    if la < lb-tol:return True
    if lb < la-tol:return False
    return ea < eb


def optimize_gamma(inputs: Sequence[GammaInput], *, maximum_iterations: int=256) -> GammaOptimizerResult:
    xs=tuple(inputs)
    if not xs or any(not all(math.isfinite(v) for v in (x.error,x.q0,x.magnitude)) or x.q0<=0 or x.magnitude<0 for x in xs):
        return GammaOptimizerResult("UNAVAILABLE",None,None,None,None,0,None,(),("GAMMA_OBJECTIVE_UNAVAILABLE",))
    m2=math.fsum(x.magnitude*x.magnitude for x in xs)/len(xs)
    if not math.isfinite(m2) or m2<=0:
        return GammaOptimizerResult("UNAVAILABLE",None,None,None,m2,0,None,(),("GAMMA_OBJECTIVE_UNAVAILABLE",))
    cache:dict[float,float]={}
    def ev(eta):
        if eta not in cache: cache[eta]=gamma_objective(xs,eta,m2)
        return cache[eta]
    if not math.isfinite(ev(0.0)):
        return GammaOptimizerResult("UNAVAILABLE",None,None,None,m2,0,None,tuple(sorted(cache.items())),("GAMMA_OBJECTIVE_UNAVAILABLE",))
    a,b=0.0,1.0; g=(math.sqrt(5)-1)/2; c=b-g*(b-a); d=a+g*(b-a); lc,ld=ev(c),ev(d)
    iterations=0
    while b-a>1e-12 and iterations<maximum_iterations:
        iterations+=1
        if _objective_preferred((c,lc),(d,ld)):
            oldc,oldlc=c,lc; b=d; d,ld=oldc,oldlc; c=b-g*(b-a); lc=ev(c)
        else:
            oldd,oldld=d,ld; a=c; c,lc=oldd,oldld; d=a+g*(b-a); ld=ev(d)
    if b-a>1e-12:
        return GammaOptimizerResult("UNAVAILABLE",None,None,None,m2,iterations,(a,b),tuple(sorted(cache.items())),("GAMMA_OPTIMIZER_DID_NOT_CONVERGE",),ev(0.0),None,None,"DID_NOT_CONVERGE")
    candidates=(0.0,a,b,(a+b)/2,c,d)
    canonical=tuple(sorted(set(eta for eta in candidates if 0<=eta<1)))
    evaluated=[(eta,ev(eta)) for eta in canonical if math.isfinite(ev(eta))]
    if not evaluated:
        return GammaOptimizerResult("UNAVAILABLE",None,None,None,m2,iterations,(a,b),tuple(sorted(cache.items())),("GAMMA_OBJECTIVE_UNAVAILABLE",))
    minimum=min(objective for _,objective in evaluated)
    equivalent=[item for item in evaluated if
        abs(item[1]-minimum) <= 64*EPSILON*max(1.0,abs(item[1]),abs(minimum))]
    best=min(equivalent,key=lambda item:item[0])
    greatest=max(cache.items(),key=lambda x:x[0])[0]
    if b==1 and best[0]>0 and best[0]==greatest:
        return GammaOptimizerResult("UNAVAILABLE",None,None,None,m2,iterations,(a,b),tuple(sorted(cache.items())),("GAMMA_FINITE_OPTIMUM_UNAVAILABLE",))
    eta,obj=best; denominator=m2*(1-eta); gamma=0.0 if eta==0 else eta/denominator
    if not math.isfinite(denominator) or denominator<=0 or not math.isfinite(gamma) or gamma<0:
        return GammaOptimizerResult("UNAVAILABLE",None,None,None,m2,iterations,(a,b),tuple(sorted(cache.items())),("GAMMA_FINITE_OPTIMUM_UNAVAILABLE",))
    baseline=ev(0.0)
    return GammaOptimizerResult("INACTIVE",eta,gamma,obj,m2,iterations,(a,b),tuple(sorted(cache.items())),(),
                                baseline,obj,baseline-obj,"CONVERGED")


@dataclass(frozen=True, slots=True)
class CompactHorizonState:
    horizon: str; threshold_status: str; medium_threshold_bps: float | None
    large_threshold_bps: float | None; scale_status: str; kappa_squared: float | None
    kappa: float | None; range_status: str; range_quantile: float | None
    sorted_residuals: tuple[float,...]; event_statuses: tuple[str,...]
    reason_codes: tuple[str,...]=()

    def __post_init__(self):
        object.__setattr__(self,"sorted_residuals",tuple(self.sorted_residuals))
        object.__setattr__(self,"event_statuses",tuple(self.event_statuses))
        object.__setattr__(self,"reason_codes",tuple(self.reason_codes))
        if self.horizon not in HORIZONS or len(self.event_statuses)!=6:
            raise ValueError("canonical horizon and six event statuses required")
        if tuple(sorted(self.sorted_residuals)) != self.sorted_residuals or any(not math.isfinite(x) for x in self.sorted_residuals):
            raise ValueError("signed residuals must be a finite sorted tuple")
        numerical=(self.medium_threshold_bps,self.large_threshold_bps,self.kappa_squared,
                   self.kappa,self.range_quantile)
        if any(value is not None and not math.isfinite(value) for value in numerical):
            raise ValueError("compact state numerical fields must be finite or null")

@dataclass(frozen=True, slots=True)
class V4CState:
    state_id: str; state_hash: str; state_version: str; model_version: str; symbol: str; cohort_id: str
    state_as_of: datetime; evidence_first_cutoff: datetime | None
    evidence_last_cutoff: datetime | None
    horizons: tuple[CompactHorizonState,...]
    gamma: float=0.0; phi: float=1.0; gamma_status: str="INACTIVE"

    def __post_init__(self):
        object.__setattr__(self,"horizons",tuple(self.horizons))
        if self.gamma != 0 or self.phi != 1 or self.gamma_status != "INACTIVE":
            raise ValueError("V4C production gamma is frozen inactive")
        boundaries=(self.evidence_first_cutoff,self.evidence_last_cutoff)
        if (boundaries[0] is None)!=(boundaries[1] is None):
            raise ValueError("evidence boundaries must both be null or non-null")
        if boundaries[0] is not None and not boundaries[0]<=boundaries[1]<=self.state_as_of:
            raise ValueError("evidence boundaries must satisfy first <= last <= state_as_of")

def build_v4c_state(*,symbol:str,cohort_id:str,state_as_of:datetime,
                    evidence_first_cutoff:datetime|None,
                    evidence_last_cutoff:datetime|None,
                    horizons:Sequence[CompactHorizonState])->V4CState:
    values=tuple(horizons)
    if tuple(x.horizon for x in values)!=HORIZONS:
        raise ValueError("six canonical horizon states required")
    shell=V4CState("","",PROBABILITY_STATE_VERSION,MODEL_VERSION,symbol,cohort_id,state_as_of,
                   evidence_first_cutoff,evidence_last_cutoff,values)
    payload={k:v for k,v in asdict(shell).items() if k not in ("state_id","state_hash")}
    digest=canonical_sha256(payload)
    return replace(shell,state_id="v9v4state:"+digest,state_hash=digest)

@dataclass(frozen=True, slots=True)
class FinalNumbers:
    horizon: str; horizon_seconds: int; final_bps: float | None; move_percent: float | None
    direction: str; predictive_scale_bps: float | None; range_lower_bps: float | None
    range_upper_bps: float | None; range_lower_percent: float | None
    range_upper_percent: float | None; range_status: str
    probability_positive: float | None; probability_negative: float | None
    probability_zero: float | None; probability_medium_positive: float | None
    probability_medium_negative: float | None; probability_large_positive: float | None
    probability_large_negative: float | None; probability_status: tuple[str,...]
    medium_threshold_bps: float | None; large_threshold_bps: float | None
    gamma: float; phi: float; gamma_status: str; reason_codes: tuple[str,...]


def final_numbers(result: V3HorizonResult, state: CompactHorizonState | None) -> FinalNumbers:
    reasons=list(result.reason_codes)
    if (result.status=="UNAVAILABLE" or result.expected_return_bps is None or
            not math.isfinite(result.expected_return_bps)):
        reasons.extend(("V3_UNAVAILABLE","FINAL_BPS_UNAVAILABLE")); mu=None
    else: mu=result.expected_return_bps
    move=None
    if mu is not None:
        try: move=100*math.expm1(mu/10000)
        except OverflowError: reasons.append("MOVE_PERCENT_NUMERICAL_FAILURE")
        if move is not None and not math.isfinite(move):
            move=None; reasons.append("MOVE_PERCENT_NUMERICAL_FAILURE")
    direction="UNAVAILABLE" if mu is None else "EXPECTED_UP" if mu>0 else "EXPECTED_DOWN" if mu<0 else "EXPECTED_FLAT"
    scale=None
    if state and state.scale_status=="MATURE" and state.kappa and result.predictive_variance_bps2 and result.predictive_variance_bps2>0:
        scale=state.kappa*math.sqrt(result.predictive_variance_bps2)
        if not math.isfinite(scale) or scale<=0:scale=None
    lower=upper=lowerp=upperp=None; range_status=state.range_status if state else "UNAVAILABLE"
    if state and state.range_status=="MATURE" and mu is not None and scale and state.range_quantile is not None:
        lower=mu-state.range_quantile*scale; upper=mu+state.range_quantile*scale
        for name,value in (("lower",lower),("upper",upper)):
            try:p=100*math.expm1(value/10000)
            except OverflowError:p=None
            if name=="lower":lowerp=p
            else:upperp=p
    if range_status=="MATURE" and (lower is None or upper is None or not math.isfinite(lower) or
                                  not math.isfinite(upper) or upper < lower):
        range_status="UNAVAILABLE"; lower=upper=lowerp=upperp=None
    probs=[None]*7; statuses=list(state.event_statuses if state else ("UNAVAILABLE",)*6)
    if state and mu is not None and scale and state.sorted_residuals:
        fr,fl=empirical_cdfs(state.sorted_residuals,-mu/scale)
        if statuses[0]=="MATURE": probs[0]=1-fr; probs[2]=fr-fl
        if statuses[1]=="MATURE": probs[1]=fl
        thresholds=(state.medium_threshold_bps,state.medium_threshold_bps,state.large_threshold_bps,state.large_threshold_bps)
        for i,t in enumerate(thresholds,2):
            if statuses[i]!="MATURE" or t is None:continue
            if i%2==0: probs[i+1]=1-empirical_cdfs(state.sorted_residuals,(t-mu)/scale)[1]
            else: probs[i+1]=empirical_cdfs(state.sorted_residuals,(-t-mu)/scale)[0]
    output_for_event=(probs[0],probs[1],probs[3],probs[4],probs[5],probs[6])
    statuses=tuple("UNAVAILABLE" if status=="MATURE" and
                   (value is None or not math.isfinite(value) or not 0<=value<=1) else status
                   for status,value in zip(statuses,output_for_event))
    if statuses[0]!="MATURE" or statuses[1]!="MATURE": probs[2]=None
    return FinalNumbers(result.horizon,result.horizon_seconds,mu,move,direction,scale,lower,upper,
        lowerp,upperp,range_status,*probs,statuses,
        state.medium_threshold_bps if state else None,state.large_threshold_bps if state else None,
        0.0,1.0,"INACTIVE",tuple(sorted(set(reasons+(list(state.reason_codes) if state else [])))))


class V4CStateStore:
    def __init__(self,connection):self.connection=connection
    def insert(self,state:V4CState,created_at:datetime)->str:
        payload={k:v for k,v in asdict(state).items() if k not in ("state_id","state_hash")}
        digest=canonical_sha256(payload)
        if state.state_hash!=digest or state.state_id!="v9v4state:"+digest:
            return "STATE_HASH_MISMATCH"
        if ((state.evidence_first_cutoff is None)!=(state.evidence_last_cutoff is None) or
                state.evidence_first_cutoff is not None and
                not state.evidence_first_cutoff<=state.evidence_last_cutoff<=state.state_as_of):
            return "STATE_TIME_INVALID"
        cursor=self.connection.cursor(); cursor.execute("SELECT state_hash FROM atom_v9_v4_states WHERE state_id=%s",(state.state_id,)); rows=cursor.fetchall()
        if rows:return "IDEMPOTENT" if rows[0][0]==state.state_hash else "STATE_CONFLICT"
        cursor.execute("INSERT INTO atom_v9_v4_states (state_id,state_hash,state_version,model_version,symbol,cohort_id,state_as_of,evidence_first_cutoff,evidence_last_cutoff,state_json,created_at) VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)",
            (state.state_id,state.state_hash,state.state_version,state.model_version,state.symbol,state.cohort_id,state.state_as_of,state.evidence_first_cutoff,state.evidence_last_cutoff,json.dumps(_canonical(asdict(state)),sort_keys=True),created_at))
        return "INSERT"

    def latest_json(self,*,symbol:str,cohort_id:str,requested_cutoff:datetime):
        cursor=self.connection.cursor()
        cursor.execute("SELECT state_hash,state_json,state_as_of,evidence_first_cutoff,evidence_last_cutoff FROM atom_v9_v4_states WHERE state_version=%s AND model_version=%s AND symbol=%s AND cohort_id=%s AND state_as_of<=%s ORDER BY state_as_of DESC, state_id DESC LIMIT 2",
            (PROBABILITY_STATE_VERSION,MODEL_VERSION,symbol,cohort_id,requested_cutoff))
        rows=cursor.fetchall()
        if not rows:return None,"UNAVAILABLE"
        greatest=rows[0][2]
        if len(rows)>1 and rows[1][2]==greatest and rows[1][0]!=rows[0][0]:
            return None,"STATE_CONFLICT"
        state_hash,state_json,state_as_of,first,last=rows[0]
        if ((first is None)!=(last is None) or first is not None and not first<=last<=state_as_of):
            return None,"STATE_TIME_INVALID"
        value=json.loads(state_json) if isinstance(state_json,str) else state_json
        if not isinstance(value,dict) or value.get("state_hash")!=state_hash:return None,"STATE_HASH_MISMATCH"
        payload={k:v for k,v in value.items() if k not in ("state_id","state_hash")}
        encoded=json.dumps(payload,sort_keys=True,separators=(",",":"),ensure_ascii=True).encode("ascii")
        if hashlib.sha256(encoded).hexdigest()!=state_hash:return None,"STATE_HASH_MISMATCH"
        return value,"AVAILABLE"
