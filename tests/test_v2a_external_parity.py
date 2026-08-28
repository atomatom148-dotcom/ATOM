from dataclasses import replace
import hashlib
from pathlib import Path
import pytest
from spikes.v2_frozen_schema_feasibility import build_legacy, canonical_receipt
from spikes.v2a_external_parity import observations, targets
from quant.v9_v2a_external import (build_external_v2a,build_external_v2b,
    build_external_v2c,build_external_v2d,cleanup_owned_workspace,validate_external_v2a)
from quant.v9_v2b_calibration import v2b_component_hash
from quant.v9_v2d_evidence_state import serialize_v2_evidence_state

KW=dict(state_as_of=2e9,target_spec_id="gate-target",target_data_schema_version="gate-schema",
    target_source_spec_version="gate-source",formula_version="gate-q1",
    family_data_schema_version="gate-schema",family_source_spec_version="gate-source")
def build(tmp_path,n=16,**extra): return build_external_v2a(**KW,targets=targets(n),observations=observations(n),root=tmp_path,**extra)
def close(view,root):
    path=view.workspace; view.close(); cleanup_owned_workspace(path,root=root); assert not path.exists()

def test_exact_frozen_chain_and_receipt_parity(tmp_path):
    view=build(tmp_path); legacy=build_legacy(16)
    b=build_external_v2b(view); c=build_external_v2c(view,b); state=build_external_v2d(view,b,c)
    assert view.dataset_hash==legacy[0].dataset_hash
    assert v2b_component_hash(b,"30S")==v2b_component_hash(legacy[1],"30S")
    assert c==legacy[2]
    assert serialize_v2_evidence_state(state)==serialize_v2_evidence_state(legacy[3])
    assert state.state_id==legacy[3].state_id
    assert canonical_receipt(state,16)==canonical_receipt(legacy[3],16)
    close(view,tmp_path)

@pytest.mark.parametrize("field,value,message",[("formula_version","wrong","formula"),
    ("data_schema_version","wrong","schema"),("source_spec_version","wrong","schema")])
def test_wrong_observation_lineage_fails_and_cleans(tmp_path,field,value,message):
    rows=list(observations(2)); rows[0]=replace(rows[0],**{field:value})
    with pytest.raises(ValueError,match=message): build_external_v2a(**KW,targets=targets(2),observations=rows,root=tmp_path)
    assert not list(tmp_path.iterdir())

def test_missing_target_duplicate_noncausal_and_boundaries_fail_closed(tmp_path):
    with pytest.raises(ValueError,match="missing"): build_external_v2a(**KW,targets=targets(2),observations=observations(1),root=tmp_path)
    duplicate=list(targets(2)); duplicate.append(duplicate[0])
    with pytest.raises(Exception): build_external_v2a(**KW,targets=duplicate,observations=observations(2),root=tmp_path)
    noncausal=list(observations(2)); noncausal[0]=replace(noncausal[0],available_epoch=31.0)
    with pytest.raises(ValueError,match="non-causal"): build_external_v2a(**KW,targets=targets(2),observations=noncausal,root=tmp_path)
    omitted=list(observations(4097)); del omitted[4096]
    with pytest.raises(ValueError): build_external_v2a(**KW,targets=targets(4097),observations=omitted,root=tmp_path)
    duplicated=list(observations(4097)); duplicated.insert(4096,duplicated[4095])
    with pytest.raises(Exception): build_external_v2a(**KW,targets=targets(4097),observations=duplicated,root=tmp_path)
    assert not list(tmp_path.iterdir())

def test_corruption_interruption_disk_full_mismatch_and_cleanup_guard(tmp_path,monkeypatch):
    view=build(tmp_path,2); view.connection.execute("UPDATE observations SET payload_hash=? WHERE record_id=1",("0"*64,)); view.connection.commit()
    with pytest.raises(ValueError,match="corrupt"): validate_external_v2a(view)
    close(view,tmp_path)
    view=build(tmp_path,2); view.dataset_hash="0"*64
    with pytest.raises(ValueError,match="parity mismatch"): build_external_v2b(view)
    close(view,tmp_path)
    for phase in ("ingestion","ordered_pass"):
        with pytest.raises(InterruptedError): build(tmp_path,2,interrupt=phase)
        assert not list(tmp_path.iterdir())
    import quant.v9_v2a_external as module
    monkeypatch.setattr(module.sqlite3,"connect",lambda *_: (_ for _ in ()).throw(module.sqlite3.OperationalError("database or disk is full")))
    with pytest.raises(module.sqlite3.OperationalError,match="disk is full"): build(tmp_path,2)
    assert not list(tmp_path.iterdir())
    unowned=tmp_path/"not-owned"; unowned.mkdir()
    with pytest.raises(ValueError,match="unowned"): cleanup_owned_workspace(unowned,root=tmp_path)
