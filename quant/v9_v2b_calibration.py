"""Deterministic V9 V2-B calibration over immutable V2-A datasets.

This module is intentionally an offline, pure mathematical boundary.  It does
not read evidence, publish state, or construct forecasts.  Every observation
used below is already admitted by :mod:`quant.v9_v2a_dataset`.
"""

from __future__ import annotations

from dataclasses import dataclass
import math
import sys
from typing import Iterable, Sequence

from quant.v9_v2a_dataset import Q3, V2ADataset


FORMULA_VERSION = "V9-V2B-1"
ALPHA_BIAS = 0.05
_EPS = sys.float_info.epsilon


@dataclass(frozen=True, slots=True)
class EffectiveN:
    observation_count: int
    kish_n: float
    serial_dependence_factor: float
    effective_n: float
    retained_lags: int
    reasons: tuple[str, ...] = ()


@dataclass(frozen=True, slots=True)
class BiasDiagnostic:
    residual_bias: float
    standard_error: float | None
    z_statistic: float | None
    two_sided_p_value: float | None
    alpha: float
    result: str


@dataclass(frozen=True, slots=True)
class DirectionalCalibration:
    quant_id: str
    formula_version: str
    horizon: str
    raw_resolved_count: int
    canonical_skeleton_count: int
    family_observation_count: int
    kish_n: float
    serial_dependence_factor: float
    effective_n: float
    tau_a_squared: float
    tau_c_squared: float
    lambda_a: float | None
    lambda_c: float | None
    calibration_intercept: float
    calibration_slope: float
    slope_boundary_flag: bool
    slope_identifiable_flag: bool
    calibration_parameter_covariance_2x2: tuple[tuple[float, float], tuple[float, float]]
    effective_model_degrees_of_freedom: float
    raw_bias_bps: float
    calibrated_bias_bps: float
    calibrated_rmse_bps: float
    calibrated_mae_bps: float
    residual_variance: float
    residual_standard_deviation: float
    coverage: float
    bias_diagnostic: BiasDiagnostic
    status: str
    reason_codes: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class Q3MagnitudeCalibration:
    quant_id: str
    formula_version: str
    horizon: str
    magnitude_target_specification: str
    family_observation_count: int
    kish_n: float
    serial_dependence_factor: float
    effective_n: float
    calibration_alpha: float
    calibration_beta: float
    alpha_boundary_flag: bool
    beta_boundary_flag: bool
    tau_alpha_squared: float
    tau_beta_squared: float
    lambda_alpha: float | None
    lambda_beta: float | None
    parameter_covariance_2x2: tuple[tuple[float, float], tuple[float, float]]
    raw_magnitude_bias: float
    calibrated_magnitude_bias: float
    magnitude_mae: float
    magnitude_rmse: float
    magnitude_residual_variance: float
    historical_calibrated_magnitude_second_moment: float
    coverage: float
    effective_model_degrees_of_freedom: float
    status: str
    reason_codes: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class V2BCalibration:
    formula_version: str
    directional: tuple[DirectionalCalibration, ...]
    q3_magnitude: tuple[Q3MagnitudeCalibration, ...]
    gamma: float
    gamma_state: str


def _zero(x: float) -> float:
    if not math.isfinite(x):
        raise ArithmeticError("non-finite V2-B result")
    return 0.0 if x == 0.0 else x


def _small(x: float, scale: float) -> bool:
    return abs(x) <= 64.0 * _EPS * max(1.0, scale)


def effective_n(scores: Sequence[float]) -> EffectiveN:
    """Apply equal-weight Kish N and the frozen paired IPS adjustment."""
    values = tuple(float(x) for x in scores)
    if any(not math.isfinite(x) for x in values):
        raise ValueError("scores must be finite")
    n = len(values)
    if not n:
        return EffectiveN(0, 0.0, 1.0, 0.0, 0)
    mean = math.fsum(values) / n
    centered = tuple(x - mean for x in values)
    denominator = math.fsum(x * x for x in centered)
    scale = math.fsum(x * x for x in values) + n * mean * mean
    if _small(denominator, scale):
        return EffectiveN(n, float(n), 1.0, float(n), 0,
                          ("SERIAL_DEPENDENCE_UNIDENTIFIABLE",))
    rhos = [1.0]
    for lag in range(1, n):
        rhos.append(math.fsum(centered[k] * centered[k + lag]
                              for k in range(n - lag)) / denominator)
    retained = 0
    if n >= 4:
        j = 1
        while 2 * j < n and rhos[2 * j - 1] + rhos[2 * j] > 0.0:
            retained = 2 * j
            j += 1
    tau = max(1.0, 1.0 + 2.0 * math.fsum(
        (1.0 - lag / n) * rhos[lag] for lag in range(1, retained + 1)))
    neff = min(float(n), max(1.0, n / tau))
    return EffectiveN(n, float(n), _zero(tau), _zero(neff), retained)


@dataclass(frozen=True, slots=True)
class _Series:
    dataset: V2ADataset
    quant_id: str
    formula: str
    x: tuple[float, ...]
    y: tuple[float, ...]
    en: EffectiveN


@dataclass(frozen=True, slots=True)
class _Preliminary:
    intercept: float
    slope: float
    residual_scale: float
    covariance: tuple[tuple[float, float], tuple[float, float]]


def _series(dataset: V2ADataset, quant_id: str, formula: str,
            observations: Iterable[object], magnitude: bool = False) -> _Series:
    targets = {row.identity: row.target_bps for row in dataset.skeleton}
    pairs = tuple((float(row.value_bps), abs(targets[row.target_identity]) if magnitude
                   else targets[row.target_identity]) for row in observations)
    x = tuple(pair[0] for pair in pairs)
    y = tuple(pair[1] for pair in pairs)
    score = tuple((abs(b) - a) if magnitude else (b - a) for a, b in pairs)
    return _Series(dataset, quant_id, formula, x, y, effective_n(score))


def _moments(s: _Series) -> tuple[float, float, float, float, float]:
    w = s.en.effective_n / len(s.x)
    return (s.en.effective_n, w * math.fsum(s.x),
            w * math.fsum(x * x for x in s.x), w * math.fsum(s.y),
            w * math.fsum(x * y for x, y in zip(s.x, s.y)))


def _inv2(a: float, b: float, d: float) -> tuple[float, float, float] | None:
    det = a * d - b * b
    if det <= 64.0 * _EPS * max(1.0, abs(a * d), b * b):
        return None
    return d / det, -b / det, a / det


def _preliminary(s: _Series) -> _Preliminary | None:
    if len(s.x) < 2 or s.en.effective_n <= 2.0:
        return None
    s0, sx, sxx, sy, sxy = _moments(s)
    inv = _inv2(s0, sx, sxx)
    if inv is None:
        return None
    i00, i01, i11 = inv
    a = i00 * sy + i01 * sxy
    c = i01 * sy + i11 * sxy
    w = s.en.effective_n / len(s.x)
    scale = w * math.fsum((y - a - c * x) ** 2
                          for x, y in zip(s.x, s.y)) / s.en.effective_n
    if not all(math.isfinite(v) for v in (a, c, scale)) or scale < 0.0:
        return None
    cov = ((scale * i00, scale * i01), (scale * i01, scale * i11))
    if any(not math.isfinite(v) for row in cov for v in row):
        return None
    return _Preliminary(_zero(a), _zero(c), _zero(scale), cov)


def _covariance(s: _Series, a: float, c: float, la: float, lc: float,
                free_a: bool, free_c: bool, boundary: bool,
                prior: tuple[float, float]) -> tuple[tuple[tuple[float, float], tuple[float, float]], float, bool]:
    s0, sx, sxx, _, _ = _moments(s)
    if free_a and free_c:
        inv = _inv2(s0 + la, sx, sxx + lc)
        if inv is None:
            return ((prior[0], 0.0), (0.0, prior[1])), 2.0, False
        i00, i01, i11 = inv
        d = i00 * s0 + 2.0 * i01 * sx + i11 * sxx
        if s.en.effective_n <= d:
            return ((prior[0], 0.0), (0.0, prior[1])), d, False
        factor = s.en.effective_n / (s.en.effective_n - d)
        w = s.en.effective_n / len(s.x)
        b00 = factor * w * math.fsum((y-a-c*x)**2 for x,y in zip(s.x,s.y))
        b01 = factor * w * math.fsum((y-a-c*x)**2*x for x,y in zip(s.x,s.y))
        b11 = factor * w * math.fsum((y-a-c*x)**2*x*x for x,y in zip(s.x,s.y))
        v00 = i00*i00*b00 + 2*i00*i01*b01 + i01*i01*b11
        v01 = i00*i01*b00 + (i00*i11+i01*i01)*b01 + i01*i11*b11
        v11 = i01*i01*b00 + 2*i01*i11*b01 + i11*i11*b11
        # Roundoff-only PSD projection for a symmetric 2x2 matrix.
        if v00 < 0 and _small(v00, abs(v00)+abs(v11)): v00 = 0.0
        if v11 < 0 and _small(v11, abs(v00)+abs(v11)): v11 = 0.0
        if v00 < 0 or v11 < 0 or v00*v11 + 64*_EPS*max(1.0,v00*v11) < v01*v01:
            return ((prior[0], 0.0), (0.0, prior[1])), d, False
        if boundary:
            return ((_zero(2*v00), 0.0), (0.0, _zero(2*v11))), d, True
        return ((_zero(v00), _zero(v01)), (_zero(v01), _zero(v11))), d, True
    # Exact one-dimensional sandwich for the sole free coefficient.
    q = tuple(1.0 if free_a else x for x in s.x)
    data_h = s0 if free_a else sxx
    penalty = la if free_a else lc
    d = data_h / (data_h + penalty) if data_h + penalty > 0 else 0.0
    if s.en.effective_n <= d or data_h + penalty <= 0:
        variance = prior[0] if free_a else prior[1]
        ok = False
    else:
        w = s.en.effective_n / len(s.x)
        meat = s.en.effective_n/(s.en.effective_n-d) * w * math.fsum(
            (y-a-c*x)**2*z*z for x,y,z in zip(s.x,s.y,q))
        variance = meat/(data_h+penalty)**2
        ok = math.isfinite(variance) and variance >= 0
        if not ok: variance = prior[0] if free_a else prior[1]
        elif boundary: variance *= 2.0
    return (((_zero(variance) if free_a else 0.0), 0.0),
            (0.0, (_zero(variance) if free_c else 0.0))), d, ok


def _bias(residuals: tuple[float, ...], neff: float) -> BiasDiagnostic:
    n = len(residuals)
    mean = math.fsum(residuals) / n
    if n < 2 or neff <= 0:
        return BiasDiagnostic(_zero(mean), None, None, None, ALPHA_BIAS, "UNDETERMINED")
    variance = math.fsum((r - mean) ** 2 for r in residuals) / (n - 1)
    se = math.sqrt(max(0.0, variance) / neff)
    if _small(se, math.sqrt(max(0.0, variance))):
        if _small(mean, math.sqrt(max(0.0, variance))):
            return BiasDiagnostic(_zero(mean), 0.0, None, None, ALPHA_BIAS, "PASS")
        return BiasDiagnostic(_zero(mean), 0.0, None, None, ALPHA_BIAS, "FAIL")
    z = mean / se
    p = math.erfc(abs(z) / math.sqrt(2.0))
    return BiasDiagnostic(_zero(mean), _zero(se), _zero(z), _zero(p), ALPHA_BIAS,
                          "PASS" if abs(z) <= 1.959963984540054 else "FAIL")


def _directional_result(s: _Series, prior: tuple[float, float], donors: int,
                        pool: float | None) -> DirectionalCalibration:
    reasons = list(s.en.reasons)
    n, neff = len(s.x), s.en.effective_n
    tau_a, tau_c = prior
    if not n:
        return DirectionalCalibration(s.quant_id, s.formula, s.dataset.horizon,
            s.dataset.raw_resolved_count, len(s.dataset.skeleton), 0, 0.0, 1.0, 0.0,
            tau_a, tau_c, None, None, 0.0, 1.0, False, False,
            ((0.0,0.0),(0.0,0.0)), 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0,
            0.0, _bias((0.0,), 0.0), "UNAVAILABLE", ("NO_EVIDENCE",))
    if donors < 2:
        reasons.append("HYPERPRIOR_UNIDENTIFIABLE")
        _, sx, sxx, _, _ = _moments(s)
        identifiable = not _small(sxx - sx * sx / neff,
                                  abs(sxx) + abs(sx * sx / neff))
        if not identifiable:
            reasons.append("SLOPE_UNIDENTIFIABLE")
        a, c, la, lc, d = 0.0, 1.0, None, None, 0.0
        cov = ((0.0,0.0),(0.0,0.0))
    else:
        s0,sx,sxx,sy,sxy = _moments(s)
        forecast_var = sxx - sx*sx/s0
        identifiable = not _small(forecast_var, abs(sxx)+abs(sx*sx/s0))
        prelim = _preliminary(s)
        scale = prelim.residual_scale if prelim is not None else 0.0
        if _small(scale, math.fsum(y*y for y in s.y)/n):
            if pool is not None and pool > 0:
                scale = pool; reasons.append("RESIDUAL_SCALE_FALLBACK")
            else:
                reasons.append("RESIDUAL_SCALE_UNAVAILABLE")
                a,c,la,lc,d,cov = 0.0,1.0,None,None,0.0,((tau_a,0.0),(0.0,tau_c))
                identifiable = identifiable
                return _finish_directional(s,a,c,cov,d,False,identifiable,tau_a,tau_c,la,lc,reasons)
        la = scale/tau_a if tau_a > 0 else None
        lc = scale/tau_c if tau_c > 0 else None
        if not identifiable:
            reasons.append("SLOPE_UNIDENTIFIABLE")
            c = 1.0
            a = (sy-sx)/(s0+(la or 0.0)) if tau_a > 0 else 0.0
            cov,d,ok = _covariance(s,a,c,la or 0.0,0.0,tau_a>0,False,False,prior)
            if not ok: reasons.append("TINY_EFFECTIVE_N")
            return _finish_directional(s,a,c,cov,d,False,False,tau_a,tau_c,la,lc,reasons)
        free_a, free_c = tau_a > 0, tau_c > 0
        if free_a and free_c:
            inv = _inv2(s0+la, sx, sxx+lc)
            if inv is None:
                reasons.append("NUMERICAL_SINGULARITY")
                return _finish_directional(s,0,1,((tau_a,0.0),(0.0,tau_c)),0,False,True,tau_a,tau_c,la,lc,reasons)
            i00,i01,i11=inv; a=i00*sy+i01*(sxy+lc); c=i01*sy+i11*(sxy+lc)
        elif free_a:
            c=1.0; a=(sy-sx)/(s0+la)
        elif free_c:
            a=0.0; c=(sxy+lc)/(sxx+lc)
        else: a,c=0.0,1.0
        boundary = c < 0.0
        if boundary:
            c=0.0; a=sy/(s0+(la or 0.0)) if free_a else 0.0
            reasons.append("SLOPE_BOUNDARY")
        cov,d,ok = _covariance(s,a,c,la or 0.0,lc or 0.0,free_a,free_c,boundary,prior)
        if not ok: reasons.append("TINY_EFFECTIVE_N")
        return _finish_directional(s,a,c,cov,d,boundary,True,tau_a,tau_c,la,lc,reasons)
    return _finish_directional(s,a,c,cov,d,False,identifiable,tau_a,tau_c,la,lc,reasons)


def _finish_directional(s: _Series, a: float, c: float, cov, d: float,
                        boundary: bool, identifiable: bool, ta: float, tc: float,
                        la: float | None, lc: float | None, reasons: list[str]):
    residuals = tuple(y-a-c*x for x,y in zip(s.x,s.y)); n=len(residuals)
    raw = math.fsum(x-y for x,y in zip(s.x,s.y))/n
    calibrated = -math.fsum(residuals)/n
    mse = math.fsum(r*r for r in residuals)/n
    mean_r = math.fsum(residuals)/n
    variance = math.fsum((r-mean_r)**2 for r in residuals)/(n-1) if n>1 else 0.0
    mature = (identifiable and len(s.x)>0 and s.en.effective_n>2 and
              "HYPERPRIOR_UNIDENTIFIABLE" not in reasons and
              "SERIAL_DEPENDENCE_UNIDENTIFIABLE" not in reasons and
              "RESIDUAL_SCALE_UNAVAILABLE" not in reasons and
              "RESIDUAL_SCALE_FALLBACK" not in reasons and not boundary and
              "TINY_EFFECTIVE_N" not in reasons)
    return DirectionalCalibration(s.quant_id,s.formula,s.dataset.horizon,
        s.dataset.raw_resolved_count,len(s.dataset.skeleton),n,s.en.kish_n,
        s.en.serial_dependence_factor,s.en.effective_n,ta,tc,la,lc,_zero(a),_zero(c),
        boundary,identifiable,cov,_zero(d),_zero(raw),_zero(calibrated),
        _zero(math.sqrt(mse)),_zero(math.fsum(abs(r) for r in residuals)/n),
        _zero(variance),_zero(math.sqrt(variance)),_zero(n/len(s.dataset.skeleton)) if s.dataset.skeleton else 0.0,
        _bias(residuals,s.en.effective_n),"MATURE" if mature else "PROVISIONAL",
        tuple(dict.fromkeys(reasons)))


def _q3_result(s: _Series, prior: tuple[float,float], donors: int, pool: float | None,
               target_spec: str) -> Q3MagnitudeCalibration:
    reasons=list(s.en.reasons); n=len(s.x); ta,tb=prior
    if not n:
        return Q3MagnitudeCalibration(Q3,s.formula,s.dataset.horizon,target_spec,0,0,1,0,
            0,1,False,False,ta,tb,None,None,((0.,0.),(0.,0.)),0,0,0,0,0,0,0,0,
            "UNAVAILABLE",("NO_EVIDENCE",))
    if donors<2:
        reasons.append("HYPERPRIOR_UNIDENTIFIABLE"); a,b,la,lb,cov,d=0.,1.,None,None,((0.,0.),(0.,0.)),0.
    else:
        s0,sx,sxx,sy,sxy=_moments(s); prelim=_preliminary(s); scale=prelim.residual_scale if prelim else 0.
        if _small(scale,math.fsum(y*y for y in s.y)/n):
            if pool is not None and pool>0: scale=pool; reasons.append("RESIDUAL_SCALE_FALLBACK")
            else: reasons.append("RESIDUAL_SCALE_UNAVAILABLE"); a,b,la,lb,cov,d=0.,1.,None,None,((ta,0.),(0.,tb)),0.; return _finish_q3(s,a,b,cov,d,ta,tb,la,lb,reasons,target_spec)
        la=scale/ta if ta>0 else None; lb=scale/tb if tb>0 else None
        # Enumerate the four exact active sets and use the frozen tie-break.
        candidates=[]
        inv=_inv2(s0+(la or 0),sx,sxx+(lb or 0)) if ta>0 and tb>0 else None
        if ta>0 and tb>0 and inv:
            i00,i01,i11=inv; aa=i00*sy+i01*(sxy+lb); bb=i01*sy+i11*(sxy+lb)
            if aa>=0 and bb>=0: candidates.append((aa,bb,0))
        if tb>0: candidates.append((0.,max(0.,(sxy+lb)/(sxx+lb)),1))
        if ta>0: candidates.append((max(0.,sy/(s0+la)),0.,1))
        candidates.append((0.,0.,2))
        if ta==0 and tb>0: candidates.append((0.,max(0.,(sxy+lb)/(sxx+lb)),1))
        if tb==0 and ta>0: candidates.append((max(0.,(sy-sx)/(s0+la)),1.,0))
        if ta==0 and tb==0: candidates.append((0.,1.,0))
        w=s.en.effective_n/n
        def key(z):
            aa,bb,bounds=z; obj=w*math.fsum((y-aa-bb*x)**2 for x,y in zip(s.x,s.y))
            if ta>0: obj+=aa*aa/(ta/scale)
            elif aa!=0: obj=math.inf
            if tb>0: obj+=(bb-1)**2/(tb/scale)
            elif bb!=1: obj=math.inf
            return (round(obj,14),aa*aa+(bb-1)**2,bounds,aa,bb)
        a,b,_=min(candidates,key=key); boundary=a==0 or b==0
        if a==0: reasons.append("ALPHA_BOUNDARY")
        if b==0: reasons.append("BETA_BOUNDARY")
        cov,d,ok=_covariance(s,a,b,la or 0,lb or 0,ta>0,tb>0,boundary,prior)
        if not ok: reasons.append("TINY_EFFECTIVE_N")
        return _finish_q3(s,a,b,cov,d,ta,tb,la,lb,reasons,target_spec)
    return _finish_q3(s,a,b,cov,d,ta,tb,la,lb,reasons,target_spec)


def _finish_q3(s,a,b,cov,d,ta,tb,la,lb,reasons,target_spec):
    residuals=tuple(y-a-b*x for x,y in zip(s.x,s.y)); n=len(s.x); mean=math.fsum(residuals)/n
    mse=math.fsum(r*r for r in residuals)/n; var=math.fsum((r-mean)**2 for r in residuals)/(n-1) if n>1 else 0.
    calibrated=tuple(a+b*x for x in s.x)
    mature=(s.en.effective_n>2 and "HYPERPRIOR_UNIDENTIFIABLE" not in reasons and
            "SERIAL_DEPENDENCE_UNIDENTIFIABLE" not in reasons and
            "RESIDUAL_SCALE_UNAVAILABLE" not in reasons and "RESIDUAL_SCALE_FALLBACK" not in reasons and
            "TINY_EFFECTIVE_N" not in reasons and "BETA_BOUNDARY" not in reasons and "ALPHA_BOUNDARY" not in reasons)
    return Q3MagnitudeCalibration(Q3,s.formula,s.dataset.horizon,target_spec,n,s.en.kish_n,
        s.en.serial_dependence_factor,s.en.effective_n,_zero(a),_zero(b),a==0,b==0,ta,tb,la,lb,cov,
        _zero(math.fsum(x-y for x,y in zip(s.x,s.y))/n),_zero(-mean),
        _zero(math.fsum(abs(r) for r in residuals)/n),_zero(math.sqrt(mse)),_zero(var),
        _zero(math.fsum(x*x for x in calibrated)/n),_zero(n/len(s.dataset.skeleton)) if s.dataset.skeleton else 0.,
        _zero(d),"MATURE" if mature else "PROVISIONAL",tuple(dict.fromkeys(reasons)))


def calibrate_v2b(datasets: Iterable[V2ADataset]) -> V2BCalibration:
    """Calibrate compatible families per horizon and Q3 across horizons."""
    data=tuple(datasets)
    if len({(d.horizon,d.dataset_hash) for d in data}) != len(data):
        raise ValueError("duplicate V2-A dataset")
    directional=[]
    for d in data:
        directional.extend(_series(d,s.quant_id,s.formula_version,s.observations)
                           for s in d.directional_subsets)
    prelim={id(s):_preliminary(s) for s in directional}
    def cohort(s):
        d=s.dataset
        return (d.horizon,d.symbol,d.target_spec_id,d.target_data_schema_version,
                d.target_source_spec_version)
    priors={}; pools={}
    for key in {cohort(s) for s in directional}:
        members=[s for s in directional if cohort(s)==key]
        donors=[prelim[id(s)] for s in members if prelim[id(s)] is not None]
        priors[key]=(max(0.,math.fsum(p.intercept**2-p.covariance[0][0] for p in donors)/len(donors)),
                         max(0.,math.fsum((p.slope-1)**2-p.covariance[1][1] for p in donors)/len(donors))) if len(donors)>=2 else (0.,0.)
        valid=[(s,prelim[id(s)]) for s in members if prelim[id(s)] is not None]
        numerator=math.fsum(s.en.effective_n*p.residual_scale for s,p in valid)
        pools[key]=(numerator/math.fsum(s.en.effective_n for s,p in valid)) if valid and numerator>0 else None
    dresults=tuple(_directional_result(s,priors[cohort(s)],
                   sum(prelim[id(x)] is not None for x in directional if cohort(x)==cohort(s)),
                   pools[cohort(s)]) for s in directional)
    qseries=[_series(d,Q3,d.q3_subset.formula_version,d.q3_subset.observations,True)
             for d in data if d.q3_subset is not None]
    qpre={id(s):_preliminary(s) for s in qseries}
    def qcohort(s):
        d=s.dataset
        return (d.symbol,d.target_spec_id,d.target_data_schema_version,d.target_source_spec_version,
                s.formula)
    qhyper={}
    for key in {qcohort(s) for s in qseries}:
        members=[s for s in qseries if qcohort(s)==key]
        donors=[(s,qpre[id(s)],math.sqrt(math.fsum(y*y for y in s.y)/len(s.y)))
                for s in members if qpre[id(s)] is not None and s.y and math.fsum(y*y for y in s.y)>0]
        if len(donors)>=2:
            tsa=max(0.,math.fsum((p.intercept/d)**2-p.covariance[0][0]/(d*d) for s,p,d in donors)/len(donors))
            tb=max(0.,math.fsum((p.slope-1)**2-p.covariance[1][1] for s,p,d in donors)/len(donors))
        else: tsa=tb=0.
        numerator=math.fsum(s.en.effective_n*p.residual_scale for s,p,d in donors)
        pool=numerator/math.fsum(s.en.effective_n for s,p,d in donors) if donors and numerator>0 else None
        qhyper[key]=(tsa,tb,len(donors),pool)
    qresults=[]
    for s in qseries:
        tsa,tb,count,pool=qhyper[qcohort(s)]
        qresults.append(_q3_result(s,((math.fsum(y*y for y in s.y)/len(s.y))*tsa if s.y else 0.,tb),count,pool,
                                    "ABSOLUTE_DIRECTIONAL_TARGET_BPS"))
    return V2BCalibration(FORMULA_VERSION,dresults,tuple(qresults),0.0,
                          "SCALE_CONDITIONING_UNAVAILABLE_PENDING_CAUSAL_V3_REPLAY")


# Public construction spelling mirrors ``build_v2a_dataset``.
build_v2b_calibration = calibrate_v2b
