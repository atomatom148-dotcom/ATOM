import hashlib
import json
from pathlib import Path

from quant.v9_v2d_evidence_state import deserialize_v2_evidence_state, serialize_v2_evidence_state
from spikes.v2_frozen_schema_feasibility import (
    build_legacy, canonical_receipt, measure, write_golden,
)


FIXTURE = Path(__file__).parent / "fixtures" / "v2_frozen_schema_golden.json"


def test_frozen_golden_bytes_and_identities_are_deterministic(tmp_path):
    expected = json.loads(FIXTURE.read_text(encoding="ascii"))
    retry = tmp_path / "retry.json"
    write_golden(retry, expected["rows"])
    assert json.loads(retry.read_text(encoding="ascii")) == expected
    state = deserialize_v2_evidence_state(expected["state_bytes"])
    assert serialize_v2_evidence_state(state) == expected["state_bytes"]
    assert hashlib.sha256(expected["state_bytes"].encode()).hexdigest() == expected["state_bytes_sha256"]
    assert (state.state_hash, state.state_id) == (expected["state_hash"], expected["state_id"])
    assert json.loads(expected["receipt_bytes"])["receipt_sha256"] == expected["receipt_hash"]


def test_source_identity_change_changes_frozen_hashes():
    first = build_legacy(16)
    second = build_legacy(17)
    assert first[0].dataset_hash != second[0].dataset_hash
    assert first[3].evidence_manifest_hash != second[3].evidence_manifest_hash
    assert first[3].state_hash != second[3].state_hash
    first_receipt = json.loads(canonical_receipt(first[3], 16))
    second_receipt = json.loads(canonical_receipt(second[3], 17))
    assert first_receipt["last_source_identity"] != second_receipt["last_source_identity"]
    assert first_receipt["receipt_sha256"] != second_receipt["receipt_sha256"]


def test_boundary_measurements_use_fresh_processes_and_do_not_retain_rss(tmp_path):
    report = measure(tmp_path / "report.json", tmp_path / "work", (15, 16, 17))
    assert report["fresh_process_per_phase"] is True
    assert [(x["rows"], x["phase"]) for x in report["measurements"]] == [
        (rows, phase) for rows in (15, 16, 17)
        for phase in ("construction", "serialization", "deserialization", "live_restore")
    ]
    assert all(x["peak_rss_bytes"] >= x["baseline_rss_bytes"]
               for x in report["measurements"])
