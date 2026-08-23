"""Frozen V4C predictive scale, range, probability, and gamma research state.

All builders in this module are offline pure functions.  ``final_numbers`` is
the bounded live transformation and never examines historical observations.
"""

from __future__ import annotations

from bisect import bisect_left, bisect_right
from dataclasses import asdict, dataclass, replace
from datetime import datetime, timezone
import json
import math
from typing import Mapping, Sequence

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
STATE_VERSIONS = (THRESHOLD_STATE_VERSION, SCALE_STATE_VERSION, RANGE_STATE_VERSION,
                  PROBABILITY_STATE_VERSION, GAMMA_STATE_VERSION)
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


def _finite(value: object) -> bool:
    return isinstance(value, (int, float)) and not isinstance(value, bool) and math.isfinite(value)


def _reasons(*groups: Sequence[str]) -> tuple[str, ...]:
    return tuple(sorted({reason for group in groups for reason in group}))


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
class ProbabilityHoldoutObservation:
    cutoff: datetime; forecast_record_id: str; actual_bps: float; mean_bps: float
    predictive_scale_bps: float


@dataclass(frozen=True, slots=True)
class ProbabilityEventState:
    event: str; status: str; calibration_n: int; calibration_effective_n: float
    holdout_effective_n: float; effective_events: float; effective_non_events: float
    brier_score: float | None; climatology_brier_score: float | None
    mean_paired_brier_improvement: float | None; hac_result: HACResult
    unadjusted_p: float; holm_rank: int; holm_threshold: float
    holm_gate_lower_bound: float | None; reliability_result: ReliabilityResult | None
    reason_codes: tuple[str, ...]


def _event_outcome(event: str, actual: float, medium: float | None, large: float | None) -> int:
    if event == "POSITIVE": return int(actual > 0)
    if event == "NEGATIVE": return int(actual < 0)
    if event == "MEDIUM_POSITIVE": return int(medium is not None and actual >= medium)
    if event == "MEDIUM_NEGATIVE": return int(medium is not None and actual <= -medium)
    if event == "LARGE_POSITIVE": return int(large is not None and actual >= large)
    if event == "LARGE_NEGATIVE": return int(large is not None and actual <= -large)
    raise ValueError("unknown probability event")


def event_probabilities(sorted_z: Sequence[float], mean_bps: float, scale_bps: float,
                        medium_bps: float | None, large_bps: float | None) -> tuple[float, ...]:
    if not _finite(mean_bps) or not _finite(scale_bps) or scale_bps <= 0: raise ValueError("invalid live probability input")
    right,left=empirical_cdfs(sorted_z,-mean_bps/scale_bps)
    values=[1-right,left]
    for threshold in (medium_bps,large_bps):
        if threshold is None: values.extend((math.nan,math.nan)); continue
        values.extend((1-empirical_cdfs(sorted_z,(threshold-mean_bps)/scale_bps)[1],
                       empirical_cdfs(sorted_z,(-threshold-mean_bps)/scale_bps)[0]))
    return tuple(values)


def calibrate_probability_events(calibration: Sequence[ProbabilityHoldoutObservation],
                                 holdout: Sequence[ProbabilityHoldoutObservation], *,
                                 medium_bps: float | None, large_bps: float | None
                                 ) -> tuple[tuple[float, ...], tuple[ProbabilityEventState, ...]]:
    cal=tuple(x for x in calibration if all(_finite(v) for v in
        (x.actual_bps,x.mean_bps,x.predictive_scale_bps)) and x.predictive_scale_bps>0)
    residuals=tuple(sorted((x.actual_bps-x.mean_bps)/x.predictive_scale_bps for x in cal))
    cal_neff,_=effective_n(tuple((x.actual_bps-x.mean_bps)/x.predictive_scale_bps for x in cal))
    provisional=[]
    for event in EVENTS:
        threshold_ok=(not event.startswith("MEDIUM") or medium_bps is not None) and (not event.startswith("LARGE") or large_bps is not None)
        cal_outcomes=[_event_outcome(event,x.actual_bps,medium_bps,large_bps) for x in cal] if threshold_ok else []
        climatology=(sum(cal_outcomes)+.5)/(len(cal_outcomes)+1) if cal_outcomes else None
        records=[]
        for x in sorted(holdout,key=lambda item:(item.cutoff,item.forecast_record_id)):
            if not residuals or not threshold_ok or not all(_finite(v) for v in (x.actual_bps,x.mean_bps,x.predictive_scale_bps)) or x.predictive_scale_bps<=0: continue
            probability=event_probabilities(residuals,x.mean_bps,x.predictive_scale_bps,medium_bps,large_bps)[EVENTS.index(event)]
            outcome=_event_outcome(event,x.actual_bps,medium_bps,large_bps)
            records.append((x,probability,outcome))
        outcomes=[x[2] for x in records]; hold_neff,_=effective_n(outcomes)
        events=sum(outcomes); ee=hold_neff*events/len(outcomes) if outcomes else 0.; en=hold_neff-ee
        diffs=[(climatology-o)**2-(p-o)**2 for _,p,o in records] if climatology is not None else []
        hs=hac(diffs); bs=math.fsum((p-o)**2 for _,p,o in records)/len(records) if records else None
        cb=math.fsum((climatology-o)**2 for o in outcomes)/len(outcomes) if outcomes else None
        rel=reliability([ReliabilityObservation(p,o,x.cutoff,x.forecast_record_id) for x,p,o in records]) if records else None
        provisional.append((event,cal_neff,hold_neff,ee,en,bs,cb,hs,rel,len(records)))
    corrections=holm([x[7].p_upper for x in provisional])
    states=[]
    for item,correction in zip(provisional,corrections):
        event,cneff,hneff,ee,en,bs,cb,hs,rel,n=item
        lower=(hs.mean-normal_ppf(1-correction.threshold)*hs.se) if correction.passed and hs.se is not None else None
        evidence_ok=len(cal)>=500 and cneff>=400 and hneff>=400 and ee>=30 and en>=30
        mature=evidence_ok and correction.passed and lower is not None and lower>0 and rel is not None and rel.status=="PASS"
        diagnostics=bool(residuals and n)
        status="MATURE" if mature else "PROVISIONAL" if diagnostics else "UNAVAILABLE"
        reasons=[]
        if not evidence_ok: reasons.append("PROBABILITY_EVIDENCE_INSUFFICIENT")
        if not correction.passed or lower is None or lower<=0: reasons.append("BRIER_HOLM_GATE_FAILED")
        if rel is None or rel.status!="PASS": reasons.append("RELIABILITY_GATE_FAILED")
        states.append(ProbabilityEventState(event,status,len(cal),cneff,hneff,ee,en,bs,cb,hs.mean,
            hs,hs.p_upper,correction.rank,correction.threshold,lower,rel,_reasons(reasons,hs.reason_codes)))
    return residuals,tuple(states)


@dataclass(frozen=True, slots=True)
class CalibrationObservation:
    cutoff: datetime; forecast_record_id: str; actual_bps: float; mean_bps: float
    q0_bps2: float; session_id: str
    proof_eligible: bool = True; target_timing_status: str = "VERIFIED"
    cohort_id: str = ""; cohort_hash: str = ""; target_resolved_at: datetime | None = None
    horizon_seconds: int = 0


@dataclass(frozen=True, slots=True)
class EvidenceBlocks:
    threshold: tuple[CalibrationObservation, ...]
    calibration: tuple[CalibrationObservation, ...]
    validation: tuple[CalibrationObservation, ...]
    threshold_boundaries: tuple[datetime | None, datetime | None]
    calibration_boundaries: tuple[datetime | None, datetime | None]
    validation_boundaries: tuple[datetime | None, datetime | None]
    status: str; reason_codes: tuple[str, ...]


def construct_evidence_blocks(observations: Sequence[CalibrationObservation], *,
                              cohort_id: str, cohort_hash: str,
                              threshold_end: datetime, calibration_end: datetime,
                              validation_end: datetime) -> EvidenceBlocks:
    """Freeze caller-selected chronological boundaries without inspecting results."""
    if not threshold_end < calibration_end < validation_end:
        raise ValueError("chronological block boundaries must be strictly increasing")
    eligible = tuple(sorted((x for x in observations if x.proof_eligible and
        x.target_timing_status == "VERIFIED" and x.cohort_id == cohort_id and
        x.cohort_hash == cohort_hash and x.target_resolved_at is not None and
        x.target_resolved_at <= validation_end and all(_finite(v) for v in
        (x.actual_bps, x.mean_bps, x.q0_bps2))), key=lambda x:(x.cutoff,x.forecast_record_id)))
    # Exact record-id duplicates or same cutoff/id incompatible values contaminate the key.
    grouped: dict[tuple[datetime,str], list[CalibrationObservation]] = {}
    for item in eligible: grouped.setdefault((item.cutoff,item.forecast_record_id),[]).append(item)
    canonical = tuple(items[0] for _,items in sorted(grouped.items()) if len(set(items)) == 1)
    selected=[]
    for item in canonical:
        if not selected or item.cutoff.timestamp() >= selected[-1].cutoff.timestamp()+selected[-1].horizon_seconds:
            selected.append(item)
    clean=tuple(selected)
    threshold=tuple(x for x in clean if x.cutoff < threshold_end)
    calibration=tuple(x for x in clean if threshold_end <= x.cutoff < calibration_end)
    validation=tuple(x for x in clean if calibration_end <= x.cutoff < validation_end)
    bounds=lambda xs:(xs[0].cutoff,xs[-1].cutoff) if xs else (None,None)
    status="AVAILABLE" if threshold and calibration and validation else "UNAVAILABLE"
    return EvidenceBlocks(threshold,calibration,validation,bounds(threshold),bounds(calibration),
                          bounds(validation),status,() if status=="AVAILABLE" else ("EVIDENCE_BLOCK_UNAVAILABLE",))

@dataclass(frozen=True, slots=True)
class ScaleResult:
    status: str; raw_n: int; effective_n: float; kappa_squared: float | None
    kappa: float | None; reason_codes: tuple[str,...]

def calibrate_scale(observations: Sequence[CalibrationObservation]) -> ScaleResult:
    valid=tuple(x for x in observations if x.proof_eligible and x.target_timing_status=="VERIFIED" and
        all(_finite(v) for v in (x.actual_bps,x.mean_bps,x.q0_bps2)) and x.q0_bps2>0)
    scores=tuple((x.actual_bps-x.mean_bps)**2/x.q0_bps2 for x in valid)
    neff,reasons=effective_n(scores)
    k2=math.fsum(scores)/len(scores) if scores else None
    k=math.sqrt(k2) if k2 is not None and math.isfinite(k2) and k2>0 else None
    status="MATURE" if len(valid)>=250 and neff>=200 and k is not None else ("PROVISIONAL" if k is not None else "UNAVAILABLE")
    return ScaleResult(status,len(valid),neff,k2 if k is not None else None,k,tuple(reasons))

@dataclass(frozen=True, slots=True)
class ThresholdResult:
    status: str; raw_n: int; effective_n: float; sessions: int
    medium_bps: float | None; large_bps: float | None; reason_codes: tuple[str,...]

def build_thresholds(observations: Sequence[CalibrationObservation]) -> ThresholdResult:
    valid=tuple(x for x in observations if x.proof_eligible and x.target_timing_status=="VERIFIED" and
                _finite(x.actual_bps))
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

def _jeffreys(binary: Sequence[int]) -> tuple[float,tuple[float,float]] | None:
    if not binary:return None
    neff,_=effective_n(binary); wins=sum(binary); ew=neff*wins/len(binary); el=neff-ew
    return neff,(inverse_regularized_incomplete_beta(ew+.5,el+.5,.025),
                 inverse_regularized_incomplete_beta(ew+.5,el+.5,.975))

def calibrate_range(calibration_scores: Sequence[float], validation: Sequence[tuple[float,float,float,str]],
                    rolling_session_ids: Sequence[str]) -> RangeResult:
    scores=tuple(float(x) for x in calibration_scores if math.isfinite(x) and x>=0)
    score_neff,score_reasons=effective_n(scores); j=math.ceil((len(scores)+1)*.9)
    quantile=sorted(scores)[j-1] if scores and j<=len(scores) else None
    valid=tuple(x for x in validation if all(math.isfinite(v) for v in x[:3]) and x[1]<=x[2])
    covered=[int(lo<=y<=hi) for y,lo,hi,_ in valid]; cov=_jeffreys(covered)
    lower_miss=[int(y<lo) for y,lo,hi,_ in valid if not lo<=y<=hi]; miss=_jeffreys(lower_miss)
    rolling_set=set(rolling_session_ids[-20:]); rolling=[flag for flag,x in zip(covered,valid) if x[3] in rolling_set]
    roll=_jeffreys(rolling); coverage=math.fsum(covered)/len(covered) if covered else None
    effmiss=(cov[0]*(1-coverage)) if cov and coverage is not None else 0.0
    width=math.fsum(hi-lo for _,lo,hi,_ in valid)/len(valid) if valid else None
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
    cutoff: datetime = datetime(1970,1,1,tzinfo=timezone.utc)
    forecast_record_id: str = ""

@dataclass(frozen=True, slots=True)
class GammaOptimizerResult:
    status: str; eta: float | None; gamma: float | None; objective: float | None
    m2: float | None; iterations: int; interval: tuple[float,float] | None
    evaluations: tuple[tuple[float,float],...]; reason_codes: tuple[str,...]


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
    ev(0.0); a,b=0.0,1.0; g=(math.sqrt(5)-1)/2; c=b-g*(b-a); d=a+g*(b-a); lc,ld=ev(c),ev(d)
    iterations=0
    while b-a>1e-12 and iterations<maximum_iterations:
        iterations+=1
        if _objective_preferred((c,lc),(d,ld)):
            oldc,oldlc=c,lc; b=d; d,ld=oldc,oldlc; c=b-g*(b-a); lc=ev(c)
        else:
            oldd,oldld=d,ld; a=c; c,lc=oldd,oldld; d=a+g*(b-a); ld=ev(d)
    if b-a>1e-12:
        return GammaOptimizerResult("UNAVAILABLE",None,None,None,m2,iterations,(a,b),tuple(sorted(cache.items())),("GAMMA_OPTIMIZER_DID_NOT_CONVERGE",))
    candidates={0.0,a,c,d,(a+b)/2};
    if b<1:candidates.add(b)
    evaluated=[(eta,ev(eta)) for eta in candidates if 0<=eta<1 and math.isfinite(ev(eta))]
    if not evaluated:
        return GammaOptimizerResult("UNAVAILABLE",None,None,None,m2,iterations,(a,b),tuple(sorted(cache.items())),("GAMMA_OBJECTIVE_UNAVAILABLE",))
    best=evaluated[0]
    for item in evaluated[1:]:
        if _objective_preferred(item,best):best=item
    greatest=max(cache.items(),key=lambda x:x[0])[0]
    if b==1 and best[0]>0 and best[0]==greatest:
        return GammaOptimizerResult("UNAVAILABLE",None,None,None,m2,iterations,(a,b),tuple(sorted(cache.items())),("GAMMA_FINITE_OPTIMUM_UNAVAILABLE",))
    eta,obj=best; denominator=m2*(1-eta); gamma=0.0 if eta==0 else eta/denominator
    if not math.isfinite(denominator) or denominator<=0 or not math.isfinite(gamma) or gamma<0:
        return GammaOptimizerResult("UNAVAILABLE",None,None,None,m2,iterations,(a,b),tuple(sorted(cache.items())),("GAMMA_FINITE_OPTIMUM_UNAVAILABLE",))
    return GammaOptimizerResult("INACTIVE",eta,gamma,obj,m2,iterations,(a,b),tuple(sorted(cache.items())),())


@dataclass(frozen=True, slots=True)
class Q3Quartile:
    index: int; raw_n: int; effective_n: float; minimum_magnitude: float
    maximum_magnitude: float; mean_d_gamma: float; hac_result: HACResult
    p_degradation: float; holm_rank: int; holm_threshold: float
    significant_degradation: bool; status: str; reason_codes: tuple[str,...]


@dataclass(frozen=True, slots=True)
class Q3QuartileResult:
    status: str; raw_n: int; q: int; r: int; initial_sizes: tuple[int,...]
    removed_boundaries: tuple[int,...]; quartiles: tuple[Q3Quartile,...]
    evidence_digest: str; reason_codes: tuple[str,...]


def q3_quartile_diagnostics(inputs: Sequence[GammaInput], eta: float, m2: float) -> Q3QuartileResult:
    valid=tuple(x for x in inputs if all(_finite(v) for v in (x.error,x.q0,x.magnitude)) and x.q0>0 and x.magnitude>=0)
    n=len(valid)
    if n<4:return Q3QuartileResult("UNAVAILABLE",n,n//4,n%4,(),(),(),canonical_sha256(()),("Q3_QUARTILE_COUNT_INSUFFICIENT",))
    ordered=sorted(valid,key=lambda x:(x.magnitude,x.cutoff,x.forecast_record_id)); q,r=divmod(n,4)
    sizes=tuple(q+(j<r) for j in range(4)); bounds=[]; total=0
    for size in sizes[:-1]:total+=size;bounds.append(total)
    removed=tuple(j+1 for j,b in enumerate(bounds) if ordered[b-1].magnitude==ordered[b].magnitude)
    surviving=[b for j,b in enumerate(bounds,1) if j not in removed]; groups=[];start=0
    for end in surviving+[n]:groups.append(ordered[start:end]);start=end
    digest=canonical_sha256(tuple((x.forecast_record_id,x.cutoff) for x in ordered))
    if len(groups)!=4:return Q3QuartileResult("UNAVAILABLE",n,q,r,sizes,removed,(),digest,("Q3_QUARTILE_TIE_COLLAPSE",))
    def loss_differential(x):
        phi=(1-eta)+eta*x.magnitude*x.magnitude/m2; qe=x.q0*phi
        # The comparison uses separately calibrated kappas over the identical sample.
        return x,qe
    q0k=math.fsum(x.error*x.error/x.q0 for x in ordered)/n
    qek=math.fsum(x.error*x.error/loss_differential(x)[1] for x in ordered)/n
    preliminary=[]
    for group in groups:
        chronological=sorted(group,key=lambda x:(x.cutoff,x.forecast_record_id))
        ds=[math.log(q0k*x.q0)+x.error*x.error/(q0k*x.q0)-
            math.log(qek*loss_differential(x)[1])-x.error*x.error/(qek*loss_differential(x)[1]) for x in chronological]
        neff,_=effective_n(ds); hs=hac(ds); p=normal_cdf(hs.z) if hs.z is not None else 1.0
        preliminary.append((group,ds,neff,hs,p))
    corrections=holm([x[4] for x in preliminary])
    quartiles=[]
    for index,(item,correction) in enumerate(zip(preliminary,corrections),1):
        group,ds,neff,hs,p=item; available=neff>=50 and hs.status=="AVAILABLE"
        significant=available and correction.passed
        quartiles.append(Q3Quartile(index,len(group),neff,group[0].magnitude,group[-1].magnitude,
            math.fsum(ds)/len(ds),hs,p,correction.rank,correction.threshold,significant,
            "AVAILABLE" if available else "UNAVAILABLE",() if available else ("Q3_QUARTILE_EVIDENCE_UNAVAILABLE",)))
    if any(x.status=="UNAVAILABLE" for x in quartiles):status="UNAVAILABLE";reasons=("Q3_QUARTILE_TEST_UNAVAILABLE",)
    elif any(x.significant_degradation for x in quartiles):status="FAIL";reasons=("Q3_QUARTILE_SIGNIFICANT_DEGRADATION",)
    else:status="PASS";reasons=()
    return Q3QuartileResult(status,n,q,r,sizes,removed,tuple(quartiles),digest,reasons)


@dataclass(frozen=True, slots=True)
class CompactHorizonState:
    horizon: str; threshold_status: str; medium_threshold_bps: float | None
    large_threshold_bps: float | None; scale_status: str; kappa_squared: float | None
    kappa: float | None; range_status: str; range_quantile: float | None
    sorted_residuals: tuple[float,...]; event_statuses: tuple[str,...]
    reason_codes: tuple[str,...]=()
    probability_events: tuple[ProbabilityEventState,...]=()
    threshold_diagnostics: ThresholdResult | None=None
    scale_diagnostics: ScaleResult | None=None
    range_diagnostics: RangeResult | None=None
    gamma_optimizer: GammaOptimizerResult | None=None
    q3_quartiles: Q3QuartileResult | None=None

    def __post_init__(self):
        object.__setattr__(self,"sorted_residuals",tuple(self.sorted_residuals))
        object.__setattr__(self,"event_statuses",tuple(self.event_statuses))
        object.__setattr__(self,"reason_codes",tuple(self.reason_codes))
        object.__setattr__(self,"probability_events",tuple(self.probability_events))
        if self.horizon not in HORIZONS or len(self.event_statuses)!=6:
            raise ValueError("canonical horizon and six event statuses required")
        if tuple(sorted(self.sorted_residuals)) != self.sorted_residuals or any(not math.isfinite(x) for x in self.sorted_residuals):
            raise ValueError("signed residuals must be a finite sorted tuple")

@dataclass(frozen=True, slots=True)
class V4CState:
    state_id: str; state_hash: str; model_version: str; symbol: str; cohort_id: str
    state_as_of: datetime; horizons: tuple[CompactHorizonState,...]
    gamma: float=0.0; phi: float=1.0; gamma_status: str="INACTIVE"
    state_version: str=PROBABILITY_STATE_VERSION
    evidence_first_cutoff: datetime | None=None
    evidence_last_cutoff: datetime | None=None

    def __post_init__(self):
        object.__setattr__(self,"horizons",tuple(self.horizons))
        if self.gamma != 0 or self.phi != 1 or self.gamma_status != "INACTIVE":
            raise ValueError("V4C production gamma is frozen inactive")

def build_v4c_state(*,symbol:str,cohort_id:str,state_as_of:datetime,
                    horizons:Sequence[CompactHorizonState],
                    state_version:str=PROBABILITY_STATE_VERSION,
                    evidence_first_cutoff:datetime|None=None,
                    evidence_last_cutoff:datetime|None=None)->V4CState:
    values=tuple(horizons)
    if tuple(x.horizon for x in values)!=HORIZONS:
        raise ValueError("six canonical horizon states required")
    if state_version not in STATE_VERSIONS: raise ValueError("unknown V4C state version")
    if ((evidence_first_cutoff is None) != (evidence_last_cutoff is None) or
        evidence_first_cutoff is not None and evidence_first_cutoff>evidence_last_cutoff):
        raise ValueError("invalid evidence boundaries")
    shell=V4CState("","",MODEL_VERSION,symbol,cohort_id,state_as_of,values,
        state_version=state_version,evidence_first_cutoff=evidence_first_cutoff,
        evidence_last_cutoff=evidence_last_cutoff)
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
    mu=result.expected_return_bps; reasons=list(result.reason_codes)
    if mu is not None and not _finite(mu): mu=None; reasons.append("FINAL_BPS_NUMERICAL_FAILURE")
    move=None
    if mu is not None:
        try: move=100*math.expm1(mu/10000)
        except OverflowError: reasons.append("MOVE_PERCENT_NUMERICAL_FAILURE")
    direction="UNAVAILABLE" if mu is None else "UP" if mu>0 else "DOWN" if mu<0 else "FLAT"
    scale=None
    q0=result.predictive_variance_bps2
    if state and state.scale_status=="MATURE" and _finite(state.kappa) and state.kappa>0 and _finite(q0) and q0>0:
        scale=state.kappa*math.sqrt(result.predictive_variance_bps2)
    lower=upper=lowerp=upperp=None
    if state and state.range_status=="MATURE" and mu is not None and scale and state.range_quantile is not None:
        lower=mu-state.range_quantile*scale; upper=mu+state.range_quantile*scale
        for name,value in (("lower",lower),("upper",upper)):
            try:p=100*math.expm1(value/10000)
            except OverflowError:p=None
            if name=="lower":lowerp=p
            else:upperp=p
    probs=[None]*7; statuses=state.event_statuses if state else ("UNAVAILABLE",)*6
    if state and mu is not None and scale and state.sorted_residuals:
        fr,fl=empirical_cdfs(state.sorted_residuals,-mu/scale)
        if statuses[0]=="MATURE": probs[0]=1-fr
        if statuses[1]=="MATURE": probs[1]=fl
        if statuses[0]==statuses[1]=="MATURE": probs[2]=fr-fl
        thresholds=(state.medium_threshold_bps,state.medium_threshold_bps,state.large_threshold_bps,state.large_threshold_bps)
        for i,t in enumerate(thresholds,2):
            if statuses[i]!="MATURE" or t is None:continue
            if i%2==0: probs[i+1]=1-empirical_cdfs(state.sorted_residuals,(t-mu)/scale)[1]
            else: probs[i+1]=empirical_cdfs(state.sorted_residuals,(-t-mu)/scale)[0]
    return FinalNumbers(result.horizon,result.horizon_seconds,mu,move,direction,scale,lower,upper,
        lowerp,upperp,state.range_status if state else "UNAVAILABLE",*probs,statuses,
        state.medium_threshold_bps if state else None,state.large_threshold_bps if state else None,
        0.0,1.0,"INACTIVE",tuple(sorted(set(reasons+(list(state.reason_codes) if state else [])))))


class V4CStateStore:
    def __init__(self,connection):self.connection=connection
    def insert(self,state:V4CState,created_at:datetime)->str:
        cursor=self.connection.cursor(); cursor.execute("SELECT state_hash FROM atom_v9_v4_states WHERE state_id=%s",(state.state_id,)); rows=cursor.fetchall()
        if rows:return "IDEMPOTENT" if rows[0][0]==state.state_hash else "STATE_CONFLICT"
        cursor.execute("SELECT state_hash FROM atom_v9_v4_states WHERE state_version=%s AND model_version=%s AND symbol=%s AND cohort_id=%s AND state_as_of=%s",
            (state.state_version,state.model_version,state.symbol,state.cohort_id,state.state_as_of))
        same_time=cursor.fetchall()
        if same_time and any(row[0]!=state.state_hash for row in same_time):return "STATE_CONFLICT"
        cursor.execute("INSERT INTO atom_v9_v4_states (state_id,state_hash,state_version,model_version,symbol,cohort_id,state_as_of,evidence_first_cutoff,evidence_last_cutoff,state_json,created_at) VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)",
            (state.state_id,state.state_hash,state.state_version,state.model_version,state.symbol,state.cohort_id,state.state_as_of,state.evidence_first_cutoff,state.evidence_last_cutoff,json.dumps(_canonical(asdict(state)),sort_keys=True),created_at))
        return "INSERT"

    def latest_json(self, *, symbol:str, cohort_id:str, requested_cutoff:datetime,
                    state_version:str=PROBABILITY_STATE_VERSION):
        cursor=self.connection.cursor()
        cursor.execute("SELECT state_hash,state_json,state_as_of FROM atom_v9_v4_states WHERE state_version=%s AND model_version=%s AND symbol=%s AND cohort_id=%s AND state_as_of<=%s ORDER BY state_as_of DESC,state_hash ASC",
            (state_version,MODEL_VERSION,symbol,cohort_id,requested_cutoff))
        rows=cursor.fetchall()
        if not rows:return None,"UNAVAILABLE"
        greatest=rows[0][2]; tied=[row for row in rows if row[2]==greatest]
        if len({row[0] for row in tied})!=1:return None,"STATE_CONFLICT"
        return tied[0][1],"AVAILABLE"
