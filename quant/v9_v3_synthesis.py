"""Deterministic live V9-V3 affine forecast synthesis.

This module is a pure boundary: it consumes one already captured V1 value and
one already captured V2D value.  It performs no I/O, retries, history reads, or
evidence reconstruction.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import timezone
from itertools import combinations
import math
import re
import sys

from quant.v9_v1_contract import (
    CONTRACT_VERSION, DIRECTIONAL_BPS, HORIZONS, HORIZON_SECONDS, V1Input,
)
from quant.v9_v2a_dataset import DIRECTIONAL_FAMILIES
from quant.v9_v2c_covariance import _jacobi
from quant.v9_v2d_evidence_state import (
    CALIBRATION_METHOD_VERSION, COVARIANCE_METHOD_VERSION,
    NUMERICAL_CANONICALIZATION_VERSION, STATE_SCHEMA_VERSION, STATE_VERSION,
    SYMBOL, V2A_METHOD_VERSION, V2B_METHOD_VERSION, V2C_METHOD_VERSION,
    V2EvidenceState, _digest,
)

MODEL_VERSION = "V9-V3-1"
OUTPUT_CONTRACT_VERSION = "V9-V3-1"
VARIANCE_SEMANTICS = "PRELIMINARY_SYNTHESIS_ERROR_VARIANCE_UNCALIBRATED"
RHO = math.sqrt(sys.float_info.epsilon)
_HASH = re.compile(r"^[0-9a-f]{64}$")


@dataclass(frozen=True, slots=True)
class V3HorizonResult:
    horizon: str
    horizon_seconds: int
    expected_return_bps: float | None
    synthesis_variance_bps2: float | None
    synthesis_scale_bps: float | None
    variance_semantics: str
    status: str
    reason_codes: tuple[str, ...]
    directional_input_count: int
    eligible_quant_ids: tuple[str, ...]
    used_quant_ids: tuple[str, ...]
    calibrated_family_values_bps: tuple[float, ...]
    calibration_uncertainties_bps2: tuple[float, ...]
    family_weights: tuple[float, ...]
    effective_family_count: float | None
    covariance_mode: str | None
    dependence_modeled: bool
    numerical_psd_correction_applied: bool
    solver_numerical_ridge_bps2: float
    maximum_kkt_residual: float | None
    evidence_state_id: str | None
    evidence_state_hash: str | None
    q3_used: bool
    q3_diagnostic_available: bool
    calibrated_q3_magnitude_bps: float | None
    q3_status: str
    q3_reason_codes: tuple[str, ...]
    gamma: float
    phi: float
    cross_horizon_transform: str


@dataclass(frozen=True, slots=True)
class V3Output:
    output_contract_version: str
    model_version: str
    cycle_id: str
    symbol: str
    cutoff_at: object
    evidence_state_id: str | None
    evidence_state_hash: str | None
    computation_status: str
    horizon_results: tuple[V3HorizonResult, ...]


def _finite(x: object) -> bool:
    return isinstance(x, (int, float)) and not isinstance(x, bool) and math.isfinite(x)


def _empty(h: str, reasons: tuple[str, ...], evidence: V2EvidenceState | None = None,
           *, count: int = 0, eligible: tuple[str, ...] = (),
           q3: tuple[bool, float | None, str, tuple[str, ...]] =
           (False, None, "UNAVAILABLE", ("Q3_UNAVAILABLE",))) -> V3HorizonResult:
    return V3HorizonResult(
        h, HORIZON_SECONDS[h], None, None, None, VARIANCE_SEMANTICS,
        "UNAVAILABLE", tuple(sorted(set(reasons))), count, eligible, (), (), (), (),
        None, None, False, False, 0.0, None,
        evidence.state_id if evidence else None, evidence.state_hash if evidence else None,
        False, *q3, 0.0, 1.0, "IDENTITY")


def _global_reasons(v1: V1Input, v2: V2EvidenceState | None) -> tuple[str, ...]:
    reasons = []
    if v1.contract_version != CONTRACT_VERSION:
        reasons.append("V1_CONTRACT_INCOMPATIBLE")
    if v2 is None:
        return tuple(reasons + ["EVIDENCE_STATE_MISSING"])
    if v2.creation_status != "VALID": reasons.append("EVIDENCE_CREATION_INVALID")
    if v2.state_schema_version != STATE_SCHEMA_VERSION or v2.state_version != STATE_VERSION:
        reasons.append("EVIDENCE_STATE_VERSION_INCOMPATIBLE")
    if (v2.calibration_method_version != CALIBRATION_METHOD_VERSION or
            v2.covariance_method_version != COVARIANCE_METHOD_VERSION or
            v2.v2a_method_version != V2A_METHOD_VERSION or
            v2.v2b_method_version != V2B_METHOD_VERSION or
            v2.v2c_method_version != V2C_METHOD_VERSION or
            v2.numerical_canonicalization_version != NUMERICAL_CANONICALIZATION_VERSION):
        reasons.append("EVIDENCE_METHOD_VERSION_INCOMPATIBLE")
    if v1.symbol != SYMBOL or v2.symbol != v1.symbol: reasons.append("SYMBOL_INCOMPATIBLE")
    if (v2.target_spec_id != v1.target_spec_id or
            v2.target_data_schema_version != v1.data_schema_version or
            v2.target_source_spec_version != v1.source_spec_version):
        reasons.append("TARGET_INCOMPATIBLE")
    cutoff = v1.cutoff_at.astimezone(timezone.utc).timestamp()
    if not _finite(v2.state_as_of) or v2.state_as_of > cutoff:
        reasons.append("EVIDENCE_FUTURE_DATED")
    expected = _digest(v2, excluded=frozenset(("state_hash", "state_id")))
    if (not isinstance(v2.state_hash, str) or not _HASH.fullmatch(v2.state_hash) or
            v2.state_hash != expected or v2.state_id != "v9v2:" + expected):
        reasons.append("EVIDENCE_STATE_HASH_INVALID")
    if (v1.evidence_state_id is not None and v1.evidence_state_id != v2.state_id) or (
            v1.evidence_state_hash is not None and v1.evidence_state_hash != v2.state_hash):
        reasons.append("CAPTURED_EVIDENCE_IDENTITY_MISMATCH")
    return tuple(sorted(set(reasons)))


def _psd2(matrix: object, f: float) -> tuple[float, float] | None:
    if not isinstance(matrix, tuple) or len(matrix) != 2 or any(
            not isinstance(row, tuple) or len(row) != 2 for row in matrix): return None
    if any(not _finite(x) for row in matrix for x in row): return None
    a, b, c, d = matrix[0][0], matrix[0][1], matrix[1][0], matrix[1][1]
    scale = max(abs(x) for row in matrix for x in row)
    tau = 2 * RHO * scale
    if abs(b-c) > tau: return None
    b = (b+c)/2
    vals, vecs = _jacobi([[a, b], [b, d]])
    if min(vals) < -tau: return None
    vals = [max(0.0, x) for x in vals]
    clean = [[math.fsum(vecs[i][k]*vals[k]*vecs[j][k] for k in range(2))
              for j in range(2)] for i in range(2)]
    u = clean[0][0] + 2*f*clean[0][1] + f*f*clean[1][1]
    su = abs(clean[0][0])+2*abs(f*clean[0][1])+abs(f*f*clean[1][1])
    if not math.isfinite(u) or u < -3*RHO*su: return None
    return max(0.0, u), max(abs(b-c), max(0.0, -min(vals)))


def _valid_principal(ids: tuple[str, ...], indices: tuple[int, ...], matrix: object,
                     diagonal: bool) -> bool:
    n = len(ids)
    if not isinstance(matrix, tuple) or len(matrix) != n or any(
            not isinstance(row, tuple) or len(row) != n for row in matrix): return False
    for i in indices:
        for j in indices:
            if not _finite(matrix[i][j]): return False
            if diagonal and i != j and matrix[i][j] != 0.0: return False
    return True


def _solve_linear_cholesky(m: list[list[float]]) -> list[float] | None:
    n=len(m); l=[[0.0]*n for _ in range(n)]
    for i in range(n):
        for j in range(i+1):
            s=math.fsum(l[i][k]*l[j][k] for k in range(j))
            if i == j:
                d=m[i][i]-s
                if d <= 0: return None
                l[i][j]=math.sqrt(d)
            else: l[i][j]=(m[i][j]-s)/l[j][j]
    y=[]
    for i in range(n): y.append((1-math.fsum(l[i][k]*y[k] for k in range(i)))/l[i][i])
    z=[0.0]*n
    for i in reversed(range(n)):
        z[i]=(y[i]-math.fsum(l[k][i]*z[k] for k in range(i+1,n)))/l[i][i]
    return z


def _support_weights(m: list[list[float]]) -> list[float] | None:
    n=len(m); vals, vecs=_jacobi(m); tau=n*RHO*max((abs(x) for x in vals), default=0.0)
    if min(vals) > tau:
        z=_solve_linear_cholesky(m)
        if z is None or abs(math.fsum(z)) <= tau: return None
        return [x/math.fsum(z) for x in z]
    if max((abs(x) for x in vals), default=0.0) <= tau: return [1/n]*n
    s=max(abs(x) for x in vals)
    k=[[2*m[i][j]/s for j in range(n)]+[1.0] for i in range(n)] + [[1.0]*n+[0.0]]
    d,r=_jacobi(k); tk=(n+1)*RHO*max(abs(x) for x in d)
    b=[0.0]*n+[1.0]
    sol=[math.fsum(r[i][j]*(math.fsum(r[k0][j]*b[k0] for k0 in range(n+1))/d[j]
                    if abs(d[j]) > tk else 0.0) for j in range(n+1)) for i in range(n+1)]
    residual=max(abs(math.fsum(k[i][j]*sol[j] for j in range(n+1))-b[i]) for i in range(n+1))
    if residual > 64*RHO*max(1.0, max(abs(x) for row in k for x in row)): return None
    return sol[:n]


def _optimize(o: list[list[float]]) -> tuple[list[float], float, float] | None:
    p=len(o); candidates=[]; scale=max(1.0,max(abs(x) for row in o for x in row)); tol=128*RHO*scale
    for size in range(1,p+1):
        for support in combinations(range(p),size):
            ws=_support_weights([[o[i][j] for j in support] for i in support])
            if ws is None: continue
            w=[0.0]*p
            for i,x in zip(support,ws): w[i]=x
            if any(not math.isfinite(x) or x < -tol for x in w) or abs(math.fsum(w)-1)>tol: continue
            w=[max(0.0,x) for x in w]; total=math.fsum(w); w=[x/total for x in w]
            g=[math.fsum(o[i][j]*w[j] for j in range(p)) for i in range(p)]
            q=math.fsum(w[i]*g[i] for i in range(p))
            residual=max([abs(g[i]-q) for i in support]+[max(0.0,q-g[i]) for i in range(p) if i not in support]+[abs(math.fsum(w)-1)])
            if residual <= tol: candidates.append((q,math.fsum(x*x for x in w),tuple(w),residual))
    if not candidates: return None
    q0=min(x[0] for x in candidates); tied=[x for x in candidates if x[0] <= q0+tol]
    norm=min(x[1] for x in tied); tied=[x for x in tied if x[1] <= norm+tol]
    best=min(tied,key=lambda x:x[2])
    return list(best[2]),best[0],best[3]


def synthesize_v3(v1: V1Input, evidence: V2EvidenceState | None) -> V3Output:
    """Synthesize all six horizons from the two immutable captured arguments."""
    global_reasons=_global_reasons(v1,evidence)
    if global_reasons:
        results=tuple(_empty(h,global_reasons,evidence) for h in HORIZONS)
        return V3Output(OUTPUT_CONTRACT_VERSION,MODEL_VERSION,v1.cycle_id,v1.symbol,
                        v1.cutoff_at,evidence.state_id if evidence else None,
                        evidence.state_hash if evidence else None,"UNAVAILABLE",results)
    assert evidence is not None
    hs={x.horizon:x for x in evidence.horizon_state_tuple}
    slots={(x.horizon,x.quant_id):x for x in v1.slots}
    results=[]
    for h in HORIZONS:
        ev=hs.get(h)
        if ev is None or ev.horizon_seconds != HORIZON_SECONDS[h]:
            results.append(_empty(h,("HORIZON_EVIDENCE_INCOMPATIBLE",),evidence)); continue
        q3slot=slots.get((h,"q3_volatility")); q3ok=False; q3value=None; q3reasons=[]
        if (q3slot is not None and q3slot.availability_state == "FRESH" and
                q3slot.numerical_type == "MAGNITUDE_BPS" and _finite(q3slot.value_bps) and
                ev.q3.status in ("MATURE","PROVISIONAL") and ev.q3.quant_id=="q3_volatility" and
                ev.q3.formula_version==q3slot.formula_version and _finite(ev.q3.calibration_alpha) and
                _finite(ev.q3.calibration_beta)):
            q3ok=True; q3value=ev.q3.calibration_alpha+ev.q3.calibration_beta*q3slot.value_bps
        else: q3reasons.append("Q3_INCOMPATIBLE_OR_UNAVAILABLE")
        q3=(q3ok,q3value,ev.q3.status,tuple(q3reasons or ev.q3.reason_codes))
        fresh=[]
        for q in DIRECTIONAL_FAMILIES:
            s=slots.get((h,q))
            if (s is not None and s.availability_state=="FRESH" and s.numerical_type==DIRECTIONAL_BPS
                    and s.horizon_seconds==HORIZON_SECONDS[h] and _finite(s.value_bps)
                    and s.forecast_cutoff_at==v1.cutoff_at and s.data_schema_version==v1.data_schema_version
                    and s.source_spec_version==v1.source_spec_version and
                    s.source_as_of_at<=v1.cutoff_at and s.available_at<=v1.cutoff_at): fresh.append((q,s))
        cmap={x.quant_id:x for x in ev.directional_calibrations}
        calibrated=[]
        for q,s in fresh:
            c=cmap.get(q)
            if c is None or c.formula_version!=s.formula_version or c.status not in ("MATURE","PROVISIONAL") or not _finite(c.calibration_intercept) or not _finite(c.calibration_slope): continue
            slope=c.calibration_slope; tau=RHO*max(1.0,abs(slope))
            if slope < -tau: continue
            slope=max(0.0,slope)
            uv=_psd2(c.calibration_parameter_covariance_2x2,float(s.value_bps))
            if uv is None: continue
            calibrated.append((q,c.calibration_intercept+slope*s.value_bps,uv[0],c))
        eligible=tuple(x[0] for x in calibrated)
        if not calibrated:
            results.append(_empty(h,("NO_CALIBRATION_VALID_DIRECTIONAL_FAMILY",),evidence,count=len(fresh),eligible=eligible,q3=q3)); continue
        ids=ev.ordered_directional_quant_ids; imap={q:i for i,q in enumerate(ids)}; matrix=ev.stabilized_covariance_matrix
        possible=tuple(i for i,x in enumerate(calibrated) if x[0] in imap)
        selected=None
        diagonal=not ev.dependence_modeled
        for size in range(len(possible),0,-1):
            for combo in combinations(possible,size):
                ix=tuple(imap[calibrated[i][0]] for i in combo)
                if _valid_principal(ids,ix,matrix,diagonal): selected=combo; break
            if selected is not None: break
        if selected is None:
            # A singleton is explicitly allowed to use its published residual variance.
            for i,x in enumerate(calibrated):
                if _finite(x[3].residual_variance) and x[3].residual_variance>=0: selected=(i,); break
        if selected is None:
            results.append(_empty(h,("COVARIANCE_SUBSET_UNAVAILABLE",),evidence,count=len(fresh),eligible=eligible,q3=q3)); continue
        a=[calibrated[i] for i in selected]; p=len(a)
        if p==1: sigma=[[a[0][3].residual_variance]]; mode="SINGLE_FAMILY"
        else:
            ix=[imap[x[0]] for x in a]; sigma=[[matrix[i][j] for j in ix] for i in ix]
            mode="DIAGONAL_PROVISIONAL" if diagonal else ("FULL_DEPENDENCE" if p==len(ids) else "PRINCIPAL_SUBSET")
        raw=[[sigma[i][j]+(a[i][2] if i==j else 0.0) for j in range(p)] for i in range(p)]
        scale=max(abs(x) for row in raw for x in row); tau=p*RHO*scale
        if max(abs(raw[i][j]-raw[j][i]) for i in range(p) for j in range(p))>tau:
            results.append(_empty(h,("OMEGA_INVALID",),evidence,count=len(fresh),eligible=eligible,q3=q3)); continue
        b=[[(raw[i][j]+raw[j][i])/2 for j in range(p)] for i in range(p)]; vals,vecs=_jacobi(b)
        if min(vals)<-tau:
            results.append(_empty(h,("OMEGA_INVALID",),evidence,count=len(fresh),eligible=eligible,q3=q3)); continue
        corrected=any(x<0 for x in vals); vals=[max(0.0,x) for x in vals]
        omega=[[math.fsum(vecs[i][k]*vals[k]*vecs[j][k] for k in range(p)) for j in range(p)] for i in range(p)]
        if p==1: w=[1.0]; q=omega[0][0]; kres=0.0
        else:
            solution=_optimize(omega)
            if solution is None:
                results.append(_empty(h,("NUMERICAL_FAILURE",),evidence,count=len(fresh),eligible=eligible,q3=q3)); continue
            w,q,kres=solution
        qt=p*RHO*max(1.0,scale)
        if q < -qt:
            results.append(_empty(h,("NUMERICAL_FAILURE",),evidence,count=len(fresh),eligible=eligible,q3=q3)); continue
        q=max(0.0,q); mu=math.fsum(w[i]*a[i][1] for i in range(p)); provisional=(mode=="DIAGONAL_PROVISIONAL" or any(x[3].status=="PROVISIONAL" for x in a))
        results.append(V3HorizonResult(h,HORIZON_SECONDS[h],mu,q,math.sqrt(q),VARIANCE_SEMANTICS,
            "PROVISIONAL" if provisional else "AVAILABLE",(),len(fresh),eligible,tuple(x[0] for x in a),
            tuple(x[1] for x in a),tuple(x[2] for x in a),tuple(w),1/math.fsum(x*x for x in w),mode,
            ev.dependence_modeled and p>1,corrected,0.0,kres,evidence.state_id,evidence.state_hash,
            False,*q3,0.0,1.0,"IDENTITY"))
    status="AVAILABLE" if all(x.status=="AVAILABLE" for x in results) else ("UNAVAILABLE" if all(x.status=="UNAVAILABLE" for x in results) else "PROVISIONAL")
    return V3Output(OUTPUT_CONTRACT_VERSION,MODEL_VERSION,v1.cycle_id,v1.symbol,v1.cutoff_at,
                    evidence.state_id,evidence.state_hash,status,tuple(results))


build_v3_output = synthesize_v3

__all__ = ["MODEL_VERSION", "OUTPUT_CONTRACT_VERSION", "VARIANCE_SEMANTICS",
           "V3HorizonResult", "V3Output", "build_v3_output", "synthesize_v3"]
