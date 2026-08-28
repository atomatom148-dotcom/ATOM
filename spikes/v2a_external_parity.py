#!/usr/bin/env python3
"""Fresh-process Phase 1B resource/parity measurement (offline fixtures only)."""
from __future__ import annotations
import argparse, hashlib, json, resource, sys, time
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path: sys.path.insert(0,str(ROOT))
from quant.v9_v2a_dataset import DIRECTIONAL_BPS, RawFamilyObservation, RawTarget, TargetIdentity
from quant.v9_v2a_external import (build_external_v2a, build_external_v2b,
    build_external_v2c, build_external_v2d, cleanup_owned_workspace)
from quant.v9_v2_build_receipt import (RECEIPT_SCHEMA_VERSION, V2BuildReceipt,
    seal_receipt, serialize_v2_build_receipt)
from quant.v9_v2d_evidence_state import serialize_v2_evidence_state

STATE_AS_OF=2_000_000_000.0
def targets(n):
    for i in range(n):
        c=float(i*30); yield RawTarget(i,f"gate-{i:06d}","COIN","gate-target","gate-schema","gate-source","30S",c,c+30,c+30,1.0)
def observations(n):
    for i in range(n):
        c=float(i*30); identity=TargetIdentity(f"gate-{i:06d}",c,c+30)
        yield RawFamilyObservation(i,identity,"COIN","q1_momentum","gate-q1","gate-schema","gate-source","30S",DIRECTIONAL_BPS,1.0,c,c,c,"FRESH")
def run(n,root):
    started=time.perf_counter(); baseline=resource.getrusage(resource.RUSAGE_SELF).ru_maxrss*1024
    view=build_external_v2a(state_as_of=STATE_AS_OF,target_spec_id="gate-target",
        target_data_schema_version="gate-schema",target_source_spec_version="gate-source",
        formula_version="gate-q1",family_data_schema_version="gate-schema",
        family_source_spec_version="gate-source",targets=targets(n),observations=observations(n),root=root)
    v2a_peak=resource.getrusage(resource.RUSAGE_SELF).ru_maxrss*1024
    disk=view.disk_bytes(); peak_disk=view.peak_disk_bytes
    calibration=build_external_v2b(view); covariance=build_external_v2c(view,calibration)
    state=build_external_v2d(view,calibration,covariance); state_bytes=serialize_v2_evidence_state(state)
    receipt=seal_receipt(V2BuildReceipt(RECEIPT_SCHEMA_VERSION,state.state_id,STATE_AS_OF,n,n,n,n,n,0,
        (n+4095)//4096,4096,"directional:30S:0x0.0p+0:gate-000000",
        f"directional:30S:{float((n-1)*30).hex()}:gate-{n-1:06d}",(("30S",n),),
        (("30S","q1_momentum",n),),(("30S","q1_momentum",float(n)),),0.0,0,
        state.evidence_manifest_hash,"")); receipt_bytes=serialize_v2_build_receipt(receipt)
    workspace=view.workspace; view.close(); cleanup_owned_workspace(workspace,root=root)
    return {"rows":n,"baseline_rss_bytes":baseline,"external_v2a_peak_rss_bytes":v2a_peak,
        "temporary_disk_bytes":disk,"peak_temporary_disk_bytes":peak_disk,
        "elapsed_seconds":time.perf_counter()-started,"dataset_hash":state.component_hash_tuple[0].digest,
        "v2b_hash":state.component_hash_tuple[1].digest,"v2c_hash":state.component_hash_tuple[2].digest,
        "state_hash":state.state_hash,"state_id":state.state_id,"state_bytes_sha256":hashlib.sha256(state_bytes.encode()).hexdigest(),
        "receipt_sha256":hashlib.sha256(receipt_bytes.encode()).hexdigest(),"receipt_hash":receipt.receipt_sha256,
        "workspace_removed":not workspace.exists()}
if __name__=="__main__":
    p=argparse.ArgumentParser(); p.add_argument("rows",type=int); p.add_argument("--root",type=Path,required=True)
    a=p.parse_args(); print(json.dumps(run(a.rows,a.root),sort_keys=True))
