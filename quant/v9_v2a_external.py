"""Offline-only, SQLite-backed V2A parity path for q1_momentum / 30S.

This module is intentionally not imported by production orchestration.  It is
the freeze-amended Phase 1B adapter: the legacy :class:`V2ADataset` and its
public builders remain untouched.
"""

from __future__ import annotations

from dataclasses import dataclass, replace
import hashlib
import json
import math
import os
from pathlib import Path
import shutil
import sqlite3
import tempfile
import uuid
from typing import Iterable

from quant.v9_v2a_dataset import (
    DATASET_SCHEMA_VERSION, DIRECTIONAL_BPS, METHOD_VERSION, ExclusionCount,
    FamilyLineage, RawFamilyObservation, RawTarget, TargetIdentity,
)
from quant.v9_v2b_calibration import (
    ALPHA_BIAS, FORMULA_VERSION as V2B_VERSION, BiasDiagnostic,
    DirectionalCalibration, EffectiveN, V2BCalibration, v2b_component_hash,
)
from quant.v9_v2c_covariance import METHOD_VERSION as V2C_VERSION, V2CCovariance
from quant.v9_v2d_evidence_state import (
    CALIBRATION_METHOD_VERSION, COVARIANCE_METHOD_VERSION,
    EFFECTIVE_N_METHOD_VERSION, MODEL_FAMILY,
    NUMERICAL_CANONICALIZATION_VERSION, STATE_SCHEMA_VERSION, STATE_VERSION,
    ComponentHash, DirectionalCalibrationState, HorizonEvidenceState,
    Q3MagnitudeState, V2EvidenceState, _digest, _missing,
    serialize_v2_evidence_state, v2d_state_hash,
)

_OWNER = "ATOM-V9-V2A-EXTERNAL-1"
_Q = "q1_momentum"
_H = "30S"


def _finite(value: object) -> bool:
    return not isinstance(value, bool) and isinstance(value, (int, float)) and math.isfinite(value)


def _ft(value: float) -> dict[str, str]:
    return {"$float64": (0.0 if value == 0.0 else float(value)).hex()}


@dataclass(slots=True)
class ExternalV2AView:
    workspace: Path
    connection: sqlite3.Connection
    state_as_of: float
    target_spec_id: str
    target_data_schema_version: str
    target_source_spec_version: str
    formula_version: str
    family_data_schema_version: str
    family_source_spec_version: str
    raw_resolved_count: int
    skeleton_count: int
    observation_count: int
    training_start: float | None
    training_end: float | None
    exclusions: tuple[ExclusionCount, ...]
    dataset_hash: str
    peak_disk_bytes: int

    @property
    def family_lineage(self) -> tuple[FamilyLineage, ...]:
        return (FamilyLineage(_Q, self.formula_version,
                              self.family_data_schema_version,
                              self.family_source_spec_version),)

    def close(self) -> None:
        self.connection.close()

    def disk_bytes(self) -> int:
        return sum(p.stat().st_size for p in self.workspace.iterdir() if p.is_file())


def _owned_workspace(root: Path | None) -> Path:
    path = Path(tempfile.mkdtemp(prefix="atom-v2a-external-", dir=root)).resolve()
    os.chmod(path, 0o700)
    (path / "owner.json").write_text(json.dumps({"owner": _OWNER, "path": str(path),
                                                  "uid": os.getuid()}), encoding="ascii")
    return path


def cleanup_owned_workspace(path: Path, *, root: Path | None = None) -> None:
    path = path.resolve()
    if root is not None and path.parent != root.resolve():
        raise ValueError("workspace is outside the configured root")
    if not path.name.startswith("atom-v2a-external-") or path.is_symlink():
        raise ValueError("refusing to clean an unowned workspace")
    marker = path / "owner.json"
    try:
        data = json.loads(marker.read_text(encoding="ascii"))
    except (OSError, ValueError) as error:
        raise ValueError("refusing to clean an unowned workspace") from error
    if data != {"owner": _OWNER, "path": str(path), "uid": os.getuid()}:
        raise ValueError("refusing to clean an unowned workspace")
    shutil.rmtree(path)


def _row_object(keys, values):
    return {key: (_ft(value) if isinstance(value, float) else value)
            for key, value in zip(keys, values)}


def _stream_hash(view: ExternalV2AView) -> str:
    h = hashlib.sha256()
    def put(value: str) -> None: h.update(value.encode("ascii"))
    def scalar(value: object) -> str:
        return json.dumps(_ft(value) if isinstance(value, float) else value,
                          sort_keys=True, separators=(",", ":"), ensure_ascii=True)
    put("{")
    fields = [
        ("complete_case_target_identities", "ids"),
        ("dataset_schema_version", DATASET_SCHEMA_VERSION),
        ("directional_subsets", "subsets"),
        ("exclusions", "exclusions"),
        ("family_lineage", "lineage"), ("horizon", _H),
        ("method_version", METHOD_VERSION), ("pair_support", "[]"),
        ("q3_subset", None), ("raw_resolved_count", view.raw_resolved_count),
        ("skeleton", "skeleton"), ("state_as_of", view.state_as_of),
        ("symbol", "COIN"), ("target_data_schema_version", view.target_data_schema_version),
        ("target_source_spec_version", view.target_source_spec_version),
        ("target_spec_id", view.target_spec_id), ("training_end", view.training_end),
        ("training_start", view.training_start),
    ]
    for fi, (name, value) in enumerate(fields):
        if fi: put(",")
        put(json.dumps(name) + ":")
        if value == "ids":
            put("[")
            for i, row in enumerate(view.connection.execute(
                    "SELECT cycle,cutoff,maturity FROM admitted ORDER BY ordinal")):
                if i: put(",")
                put(json.dumps(_row_object(("cutoff_epoch","cycle_id","maturity_epoch"),
                                           (row[1],row[0],row[2])), sort_keys=True,
                               separators=(",", ":"), ensure_ascii=True))
            put("]")
        elif value == "subsets":
            put('[{"formula_version":' + scalar(view.formula_version) + ',"observations":[')
            keys=("available_epoch","data_schema_version","forecast_cutoff_epoch",
                  "formula_version","numerical_type","quant_id","record_id",
                  "source_as_of_epoch","source_spec_version","target_identity","value_bps")
            for i,row in enumerate(view.connection.execute(
                "SELECT available,family_schema,forecast,formula,numerical,quant,record_id,source_as_of,family_source,cycle,cutoff,maturity,value FROM admitted ORDER BY ordinal")):
                if i: put(",")
                identity=_row_object(("cutoff_epoch","cycle_id","maturity_epoch"),(row[10],row[9],row[11]))
                values=(*row[:9],identity,row[12])
                put(json.dumps(_row_object(keys,values),sort_keys=True,separators=(",",":"),ensure_ascii=True))
            put('],"quant_id":"q1_momentum"}]')
        elif value == "exclusions":
            put(json.dumps([{"count":x.count,"reason_code":x.reason_code} for x in view.exclusions],
                           sort_keys=True,separators=(",",":")))
        elif value == "lineage":
            put(json.dumps([{"data_schema_version":view.family_data_schema_version,
                             "formula_version":view.formula_version,"quant_id":_Q,
                             "source_spec_version":view.family_source_spec_version}],
                           sort_keys=True,separators=(",",":")))
        elif value == "skeleton":
            put("[")
            keys=("cutoff_epoch","identity","record_id","resolved_epoch","target_bps")
            for i,row in enumerate(view.connection.execute(
                    "SELECT cutoff,cycle,maturity,target_record,resolved,target FROM admitted ORDER BY ordinal")):
                if i: put(",")
                identity=_row_object(("cutoff_epoch","cycle_id","maturity_epoch"),(row[0],row[1],row[2]))
                put(json.dumps(_row_object(keys,(row[0],identity,row[3],row[4],row[5])),
                               sort_keys=True,separators=(",",":"),ensure_ascii=True))
            put("]")
        elif value == "[]": put("[]")
        else: put(scalar(value))
    put("}")
    return h.hexdigest()


def build_external_v2a(*, state_as_of: float, target_spec_id: str,
                       target_data_schema_version: str, target_source_spec_version: str,
                       formula_version: str, family_data_schema_version: str,
                       family_source_spec_version: str, targets: Iterable[RawTarget],
                       observations: Iterable[RawFamilyObservation], root: Path | None = None,
                       interrupt: str | None = None) -> ExternalV2AView:
    """Stage and seal the scoped view. Inputs are offline iterables only."""
    workspace = _owned_workspace(root)
    con = None
    peak_disk = 0
    def sample_disk() -> None:
        nonlocal peak_disk
        peak_disk=max(peak_disk,sum(p.stat().st_size for p in workspace.iterdir() if p.is_file()))
    try:
        con=sqlite3.connect(workspace / "v2a.sqlite3")
        con.execute("PRAGMA journal_mode=DELETE"); con.execute("PRAGMA synchronous=FULL")
        con.executescript("""
        CREATE TABLE targets(cycle TEXT,cutoff REAL,maturity REAL,record_id INTEGER,resolved REAL,target REAL,PRIMARY KEY(cycle,cutoff,maturity,record_id));
        CREATE TABLE observations(cycle TEXT,cutoff REAL,maturity REAL,record_id INTEGER,value REAL,forecast REAL,source_as_of REAL,available REAL,payload BLOB,payload_hash TEXT,PRIMARY KEY(cycle,cutoff,maturity,record_id));
        CREATE TABLE admitted(ordinal INTEGER PRIMARY KEY,cycle TEXT,cutoff REAL,maturity REAL,target_record INTEGER,resolved REAL,target REAL,record_id INTEGER,value REAL,forecast REAL,source_as_of REAL,available REAL,formula TEXT,family_schema TEXT,family_source TEXT,numerical TEXT,quant TEXT);
        """)
        raw=0
        for i,t in enumerate(targets):
            if interrupt == "ingestion" and i == 1: raise InterruptedError("interrupted during ingestion")
            if not all(_finite(x) for x in (t.cutoff_epoch,t.maturity_epoch,t.resolved_epoch,t.target_bps)):
                raise ValueError("malformed target")
            if (t.symbol,t.horizon,t.target_spec_id,t.data_schema_version,t.source_spec_version)!=("COIN",_H,target_spec_id,target_data_schema_version,target_source_spec_version):
                raise ValueError("wrong target schema/source version")
            if t.maturity_epoch != t.cutoff_epoch+30 or t.resolved_epoch<t.maturity_epoch or t.resolved_epoch>state_as_of:
                raise ValueError("missing or invalid target")
            raw += 1
            con.execute("INSERT INTO targets VALUES(?,?,?,?,?,?)",(t.cycle_id,t.cutoff_epoch,t.maturity_epoch,t.record_id,t.resolved_epoch,t.target_bps))
            if (i+1)%4096==0: sample_disk(); con.commit(); sample_disk()
        for i,o in enumerate(observations):
            if (o.quant_id,o.symbol,o.horizon,o.formula_version,o.data_schema_version,o.source_spec_version,o.numerical_type)!=(
                    _Q,"COIN",_H,formula_version,family_data_schema_version,family_source_spec_version,DIRECTIONAL_BPS):
                raise ValueError("wrong formula or schema/source version")
            if not (o.source_as_of_epoch<=o.forecast_cutoff_epoch<=o.available_epoch<o.target_identity.maturity_epoch) or o.availability_state!="FRESH":
                raise ValueError("non-causal observation")
            payload=repr(o).encode(); digest=hashlib.sha256(payload).hexdigest()
            con.execute("INSERT INTO observations VALUES(?,?,?,?,?,?,?,?,?,?)",(o.target_identity.cycle_id,o.target_identity.cutoff_epoch,o.target_identity.maturity_epoch,o.record_id,o.value_bps,o.forecast_cutoff_epoch,o.source_as_of_epoch,o.available_epoch,payload,digest))
            if (i+1)%4096==0: sample_disk(); con.commit(); sample_disk()
        sample_disk(); con.commit(); sample_disk()
        query="""SELECT t.cycle,t.cutoff,t.maturity,min(t.record_id),min(t.resolved),min(t.target),min(o.record_id),min(o.value),min(o.forecast),min(o.source_as_of),min(o.available)
        FROM targets t LEFT JOIN observations o USING(cycle,cutoff,maturity) GROUP BY t.cycle,t.cutoff,t.maturity ORDER BY t.cutoff,t.cycle,t.maturity,min(t.record_id)"""
        previous=None; ordinal=0
        for row in con.execute(query):
            if interrupt == "ordered_pass" and ordinal == 1: raise InterruptedError("interrupted during ordered pass")
            if row[6] is None: raise ValueError("missing target observation")
            if previous is not None and row[1] < previous+30: continue
            previous=row[1]
            con.execute("INSERT INTO admitted VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
                        (ordinal,*row[:11],formula_version,family_data_schema_version,family_source_spec_version,DIRECTIONAL_BPS,_Q))
            ordinal+=1
            if ordinal%4096==0: sample_disk()
        if ordinal != con.execute("SELECT count(DISTINCT cycle||char(0)||hex(cutoff)||char(0)||hex(maturity)) FROM observations").fetchone()[0]:
            raise ValueError("page-boundary duplicate or omission")
        sample_disk(); con.commit(); sample_disk()
        bounds=con.execute("SELECT min(cutoff),max(cutoff) FROM targets").fetchone()
        view=ExternalV2AView(workspace,con,state_as_of,target_spec_id,target_data_schema_version,
            target_source_spec_version,formula_version,family_data_schema_version,
            family_source_spec_version,raw,ordinal,ordinal,bounds[0],bounds[1],(),"",0)
        view.dataset_hash=_stream_hash(view); sample_disk(); view.peak_disk_bytes=peak_disk
        return view
    except BaseException:
        if con is not None: con.close()
        cleanup_owned_workspace(workspace,root=root)
        raise


def _scores(view):
    for target,value in view.connection.execute("SELECT target,value FROM admitted ORDER BY ordinal"):
        yield target-value


def validate_external_v2a(view: ExternalV2AView) -> None:
    """Fail closed if the sealed owned workspace or staged bytes changed."""
    marker=json.loads((view.workspace/"owner.json").read_text(encoding="ascii"))
    if marker != {"owner":_OWNER,"path":str(view.workspace),"uid":os.getuid()}:
        raise ValueError("workspace ownership validation failed")
    for payload,digest in view.connection.execute("SELECT payload,payload_hash FROM observations"):
        if hashlib.sha256(payload).hexdigest()!=digest:
            raise ValueError("corrupt staged payload")
    if _stream_hash(view)!=view.dataset_hash:
        raise ValueError("external V2A parity mismatch")


def _effective_n(view: ExternalV2AView) -> EffectiveN:
    n=view.observation_count
    if not n: return EffectiveN(0,0.0,1.0,0.0,0)
    mean=math.fsum(_scores(view))/n
    denominator=math.fsum((x-mean)**2 for x in _scores(view))
    scale=math.fsum(x*x for x in _scores(view))+n*mean*mean
    if abs(denominator)<=64*math.ulp(1.0)*max(1.0,scale):
        return EffectiveN(n,float(n),1.0,float(n),0,("SERIAL_DEPENDENCE_UNIDENTIFIABLE",))
    rhos=[1.0]; retained=0
    for lag in range(1,n):
        products=(a[0]*a[1] for a in view.connection.execute(
            "SELECT (a.target-a.value-?),(b.target-b.value-?) FROM admitted a JOIN admitted b ON b.ordinal=a.ordinal+? ORDER BY a.ordinal",(mean,mean,lag)))
        rhos.append(math.fsum(products)/denominator)
        if lag%2==0 and rhos[lag-1]+rhos[lag]>0: retained=lag
        elif lag%2==0: break
    tau=max(1.0,1.0+2.0*math.fsum((1.0-lag/n)*rhos[lag] for lag in range(1,retained+1)))
    return EffectiveN(n,float(n),tau,min(float(n),max(1.0,n/tau)),retained)


def build_external_v2b(view: ExternalV2AView) -> V2BCalibration:
    validate_external_v2a(view)
    en=_effective_n(view); n=view.observation_count
    sx=math.fsum(row[0] for row in view.connection.execute("SELECT value FROM admitted ORDER BY ordinal"))
    sxx=math.fsum(row[0]*row[0] for row in view.connection.execute("SELECT value FROM admitted ORDER BY ordinal"))
    identifiable=not (abs(sxx-sx*sx/en.effective_n)<=64*math.ulp(1.0)*max(1.0,abs(sxx)+abs(sx*sx/en.effective_n)))
    reasons=list(en.reasons)+["HYPERPRIOR_UNIDENTIFIABLE"]
    if not identifiable: reasons.append("SLOPE_UNIDENTIFIABLE")
    residual_mean=math.fsum(_scores(view))/n
    variance=math.fsum((x-residual_mean)**2 for x in _scores(view))/(n-1) if n>1 else 0.0
    if abs(math.sqrt(variance))<=64*math.ulp(1.0)*max(1.0,math.sqrt(variance)):
        bias=BiasDiagnostic(residual_mean,0.0,None,None,ALPHA_BIAS,"PASS" if abs(residual_mean)<=64*math.ulp(1.0)*max(1.0,math.sqrt(variance)) else "FAIL")
    else:
        se=math.sqrt(variance/en.effective_n); z=residual_mean/se
        bias=BiasDiagnostic(residual_mean,se,z,math.erfc(abs(z)/math.sqrt(2)),ALPHA_BIAS,"PASS" if abs(z)<=1.959963984540054 else "FAIL")
    raw=math.fsum(row[0]-row[1] for row in view.connection.execute("SELECT value,target FROM admitted ORDER BY ordinal"))/n
    mse=math.fsum(x*x for x in _scores(view))/n; mae=math.fsum(abs(x) for x in _scores(view))/n
    item=DirectionalCalibration(_Q,view.formula_version,_H,view.family_data_schema_version,
        view.family_source_spec_version,view.dataset_hash,view.raw_resolved_count,view.skeleton_count,n,
        en.kish_n,en.serial_dependence_factor,en.effective_n,0.0,0.0,None,None,0.0,1.0,False,identifiable,
        ((0.0,0.0),(0.0,0.0)),0.0,raw,-residual_mean,math.sqrt(mse),mae,variance,math.sqrt(variance),
        n/view.skeleton_count,bias,"PROVISIONAL",tuple(dict.fromkeys(reasons)))
    return V2BCalibration(V2B_VERSION,((_H,view.dataset_hash),),(item,),(),0.0,
        "SCALE_CONDITIONING_UNAVAILABLE_PENDING_CAUSAL_V3_REPLAY")


def build_external_v2c(view: ExternalV2AView, calibration: V2BCalibration) -> V2CCovariance:
    cal=calibration.directional[0]; n=view.observation_count
    mean=math.fsum(_scores(view))/n
    scores=((x-mean)**2 for x in _scores(view)); en=_effective_n_squared(view,mean)
    supported=n>=2 and en>1.0
    covariance=math.fsum(scores)/(n-1) if supported else 0.0
    reasons={"V2B_CALIBRATION_PROVISIONAL"}
    if not supported: reasons.add("PAIR_COVARIANCE_UNSUPPORTED")
    # For p=1 OAS is the population residual variance.
    empirical=math.fsum((x-mean)**2 for x in _scores(view))/n if n>=2 else 0.0
    if n>=2:
        candidate=empirical
        if candidate > 0.0:
            ridge=max(float.fromhex("0x0.0000000000001p-1022"),math.sqrt(math.ulp(1.0))*candidate)
            stable=candidate+ridge; status="PROVISIONAL"; dependence=True
        else:
            ridge=None; stable=0.0; status="UNAVAILABLE"; dependence=False
            reasons.add("SUPPORTED_POSITIVE_SCALE_UNAVAILABLE")
        matrices=(((empirical,),),((candidate,),),((stable,),))
    else:
        reasons.update(("COMPLETE_CASE_DEPENDENCE_UNAVAILABLE","SUPPORTED_POSITIVE_SCALE_UNAVAILABLE")); status="UNAVAILABLE"; dependence=False; ridge=None; stable=0.0
        matrices=(((0.0,),),((0.0,),),((0.0,),))
    return V2CCovariance(V2C_VERSION,_H,view.dataset_hash,v2b_component_hash(calibration,_H),(_Q,),(view.formula_version,),view.family_lineage,
        ((float(n),),),((en,),),((supported,),),((covariance,),),(_Q,),n,(),matrices[0],
        "STANDARD_COMPLETE_CASE_OAS" if n>=2 else None,1.0 if n>=2 else None,empirical if n>=2 else None,
        matrices[1],matrices[2],candidate if n>=2 else None,candidate if n>=2 else None,0,0.0,0.0,ridge,1.0 if ridge is not None else None,
        dependence,status,tuple(sorted(reasons)))


def _effective_n_squared(view,mean):
    # Frozen effective_n over pair covariance scores; constant scores take the
    # common bounded pass used by the acceptance fixture.
    values=lambda: ((x-mean)**2 for x in _scores(view))
    n=view.observation_count; m=math.fsum(values())/n
    den=math.fsum((x-m)**2 for x in values()); scale=math.fsum(x*x for x in values())+n*m*m
    if abs(den)<=64*math.ulp(1.0)*max(1.0,scale): return float(n)
    # Exact fallback delegates to a temporary scalar table without RAM growth.
    view.connection.execute("DROP TABLE IF EXISTS covariance_scores")
    view.connection.execute("CREATE TEMP TABLE covariance_scores(i INTEGER PRIMARY KEY,v REAL)")
    view.connection.executemany("INSERT INTO covariance_scores VALUES(?,?)",enumerate(values()))
    retained=0; rhos=[1.0]
    for lag in range(1,n):
        rho=math.fsum(r[0] for r in view.connection.execute("SELECT (a.v-?)*(b.v-?) FROM covariance_scores a JOIN covariance_scores b ON b.i=a.i+? ORDER BY a.i",(m,m,lag)))/den
        rhos.append(rho)
        if lag%2==0 and rhos[-2]+rho>0: retained=lag
        elif lag%2==0: break
    tau=max(1.0,1+2*math.fsum((1-i/n)*rhos[i] for i in range(1,retained+1)))
    return min(float(n),max(1.0,n/tau))


def build_external_v2d(view, calibration, covariance) -> V2EvidenceState:
    cal=calibration.directional[0]
    directional=DirectionalCalibrationState(cal.quant_id,cal.formula_version,cal.data_schema_version,
        cal.source_spec_version,cal.dataset_hash,cal.calibration_intercept,cal.calibration_slope,
        cal.calibration_parameter_covariance_2x2,cal.effective_n,cal.residual_variance,
        cal.residual_standard_deviation,cal.status,tuple(sorted(cal.reason_codes)))
    hs_reasons=tuple(sorted(set(cal.reason_codes)|set(covariance.reason_codes)|{"Q3_EVIDENCE_UNAVAILABLE"}|
                            ({"COVARIANCE_UNAVAILABLE"} if covariance.status=="UNAVAILABLE" else set())))
    horizon=HorizonEvidenceState(_H,30,"UNAVAILABLE" if covariance.status=="UNAVAILABLE" else "PROVISIONAL",
        hs_reasons,(directional,),view.family_lineage,(_Q,),covariance.pair_support_boolean_matrix,
        covariance.stabilized_covariance_matrix if covariance.status!="UNAVAILABLE" else None,
        covariance.dependence_modeled,covariance.status,covariance.reason_codes,
        Q3MagnitudeState("UNAVAILABLE",("Q3_EVIDENCE_UNAVAILABLE",)))
    components=tuple(sorted((ComponentHash(_H,"V2A",view.dataset_hash),
        ComponentHash(_H,"V2B",v2b_component_hash(calibration,_H)),
        ComponentHash(_H,"V2C",_digest(covariance)))))
    manifest=_digest(tuple((x.horizon,x.layer,x.digest) for x in components))
    horizons=(horizon,*(_missing(h) for h in ("1M","5M","15M","30M","1H")))
    reasons=tuple(sorted({r for h in horizons for r in h.reason_codes}))
    state=V2EvidenceState(STATE_SCHEMA_VERSION,STATE_VERSION,MODEL_FAMILY,"COIN",view.state_as_of,
        view.training_start,view.training_end,view.target_spec_id,view.target_data_schema_version,
        view.target_source_spec_version,METHOD_VERSION,V2B_VERSION,V2C_VERSION,EFFECTIVE_N_METHOD_VERSION,
        CALIBRATION_METHOD_VERSION,COVARIANCE_METHOD_VERSION,NUMERICAL_CANONICALIZATION_VERSION,
        manifest,components,horizons,tuple((x.reason_code,x.count) for x in view.exclusions),
        "UNAVAILABLE","VALID",reasons,"","")
    digest=v2d_state_hash(state); state=replace(state,state_hash=digest,state_id="v9v2:"+digest)
    serialize_v2_evidence_state(state)
    return state
