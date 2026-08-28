"""Fresh-process laboratory for the frozen V2 state-schema feasibility gate.

This is deliberately test/spike code: it neither connects to a database nor
publishes a state.  ``measure`` writes an intermediate canonical state so each
subsequent operation can be measured in a new interpreter.
"""

from __future__ import annotations

import argparse
from dataclasses import asdict
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import resource
import subprocess
import sys
import time

# Permit direct execution from the repository root, matching the other spikes.
REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
if str(REPOSITORY_ROOT) not in sys.path:
    sys.path.insert(0, str(REPOSITORY_ROOT))

from quant.v9_production import ImmutableV2StateProvider
from quant.v9_v2_build_receipt import (
    RECEIPT_SCHEMA_VERSION, V2BuildReceipt, seal_receipt,
    serialize_v2_build_receipt,
)
from quant.v9_v2a_dataset import (
    DIRECTIONAL_BPS, HORIZON_SECONDS, RawFamilyObservation, RawTarget,
    TargetIdentity, build_v2a_dataset,
)
from quant.v9_v2b_calibration import calibrate_v2b
from quant.v9_v2c_covariance import build_v2c_covariance
from quant.v9_v2d_evidence_state import (
    build_v2d_evidence_state, deserialize_v2_evidence_state,
    serialize_v2_evidence_state,
)

CARDINALITIES = (1_000, 10_000, 65_535, 65_536, 65_537, 200_000)
STATE_AS_OF = 2_000_000_000.0


def _rss_bytes() -> int:
    # Linux ru_maxrss is KiB. All gate measurements run on Linux CI/operator hosts.
    return int(resource.getrusage(resource.RUSAGE_SELF).ru_maxrss * 1024)


def build_legacy(rows: int):
    """Construct a production-code V2A/B/C/D chain with exactly ``rows`` evidence rows."""
    horizon = "30S"
    seconds = HORIZON_SECONDS[horizon]
    targets, observations = [], []
    for index in range(rows):
        cutoff = float(index * seconds)
        identity = TargetIdentity(f"gate-{index:06d}", cutoff, cutoff + seconds)
        # A constant zero residual takes V2B's frozen O(n) degenerate-series path;
        # the object cardinality and codecs remain completely representative.
        targets.append(RawTarget(index, identity.cycle_id, "COIN", "gate-target",
                                 "gate-schema", "gate-source", horizon, cutoff,
                                 cutoff + seconds, cutoff + seconds, 1.0))
        observations.append(RawFamilyObservation(
            index, identity, "COIN", "q1_momentum", "gate-q1", "gate-schema",
            "gate-source", horizon, DIRECTIONAL_BPS, 1.0, cutoff, cutoff,
            cutoff, "FRESH",
        ))
    dataset = build_v2a_dataset(
        state_as_of=STATE_AS_OF, horizon=horizon, target_spec_id="gate-target",
        target_data_schema_version="gate-schema",
        target_source_spec_version="gate-source",
        family_versions=(("q1_momentum", "gate-q1", "gate-schema", "gate-source"),),
        targets=targets, observations=observations,
    )
    calibration = calibrate_v2b((dataset,))
    covariance = build_v2c_covariance(dataset, calibration)
    return dataset, calibration, covariance, build_v2d_evidence_state(
        state_as_of=STATE_AS_OF, datasets=(dataset,), calibrations=(calibration,),
        covariances=(covariance,),
    )


def canonical_receipt(state, rows: int) -> str:
    receipt = seal_receipt(V2BuildReceipt(
        RECEIPT_SCHEMA_VERSION, state.state_id, state.state_as_of,
        rows, rows, rows, rows, rows, 0, (rows + 4095) // 4096, 4096,
        "directional:30S:0x0.0p+0:gate-000000",
        f"directional:30S:{float((rows - 1) * 30).hex()}:gate-{rows - 1:06d}",
        (("30S", rows),), (("30S", "q1_momentum", rows),),
        (("30S", "q1_momentum", float(rows)),), 0.0, 0,
        state.evidence_manifest_hash, "",
    ))
    return serialize_v2_build_receipt(receipt)


def _result(phase: str, rows: int, baseline: int, started: float, **values):
    return {"phase": phase, "rows": rows, "baseline_rss_bytes": baseline,
            "peak_rss_bytes": _rss_bytes(),
            "elapsed_seconds": time.perf_counter() - started, **values}


def run_phase(phase: str, rows: int, state_path: Path) -> dict[str, object]:
    baseline, started = _rss_bytes(), time.perf_counter()
    if phase == "construction":
        dataset, calibration, covariance, state = build_legacy(rows)
        payload = serialize_v2_evidence_state(state)
        state_path.write_text(payload, encoding="ascii")
        return _result(phase, rows, baseline, started, state_size_bytes=len(payload),
                       state_hash=state.state_hash, state_id=state.state_id,
                       dataset_hash=dataset.dataset_hash,
                       component_hashes=[asdict(item) for item in state.component_hash_tuple],
                       v2a_skeleton_rows=len(dataset.skeleton),
                       v2a_observation_rows=sum(len(x.observations)
                                                for x in dataset.directional_subsets),
                       v2b_directional_records=len(calibration.directional),
                       v2c_matrix_dimension=len(covariance.ordered_quant_ids))
    source = state_path.read_text(encoding="ascii")
    if phase == "serialization":
        state = deserialize_v2_evidence_state(source)
        payload = serialize_v2_evidence_state(state)
        assert payload == source
    elif phase == "deserialization":
        state = deserialize_v2_evidence_state(source)
        payload = serialize_v2_evidence_state(state)
        assert payload == source
    elif phase == "live_restore":
        state = deserialize_v2_evidence_state(source)
        class Store:
            def latest(self, *, requested_cutoff):
                return state, "FOUND"
        provider = ImmutableV2StateProvider(None, store=Store())
        snapshot = provider.restore(datetime.fromtimestamp(STATE_AS_OF + 1, timezone.utc))
        assert snapshot.status == "AVAILABLE"
        assert provider.capture(datetime.fromtimestamp(STATE_AS_OF + 1, timezone.utc)) is state
        payload = source
    else:
        raise ValueError(f"unknown phase: {phase}")
    return _result(phase, rows, baseline, started, state_size_bytes=len(payload))


def measure(output: Path, workspace: Path, cardinalities=CARDINALITIES) -> dict[str, object]:
    workspace.mkdir(parents=True, exist_ok=True)
    results = []
    for rows in cardinalities:
        state_path = workspace / f"state-{rows}.json"
        for phase in ("construction", "serialization", "deserialization", "live_restore"):
            command = [sys.executable, str(Path(__file__).resolve()), "phase", phase,
                       str(rows), str(state_path)]
            completed = subprocess.run(command, check=True, capture_output=True, text=True)
            results.append(json.loads(completed.stdout))
    report = {"schema": "ATOM-V9-V2-FROZEN-SCHEMA-FEASIBILITY-1",
              "fresh_process_per_phase": True, "measurements": results}
    output.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="ascii")
    return report


def write_golden(path: Path, rows: int = 16) -> None:
    dataset, _calibration, _covariance, state = build_legacy(rows)
    state_bytes = serialize_v2_evidence_state(state)
    receipt_bytes = canonical_receipt(state, rows)
    fixture = {
        "fixture_schema": "ATOM-V9-V2-FROZEN-GOLDEN-1", "rows": rows,
        "state_bytes": state_bytes,
        "state_bytes_sha256": hashlib.sha256(state_bytes.encode("ascii")).hexdigest(),
        "state_hash": state.state_hash, "state_id": state.state_id,
        "evidence_manifest_hash": state.evidence_manifest_hash,
        "dataset_hash": dataset.dataset_hash,
        "component_hashes": [asdict(item) for item in state.component_hash_tuple],
        "receipt_bytes": receipt_bytes,
        "receipt_bytes_sha256": hashlib.sha256(receipt_bytes.encode("ascii")).hexdigest(),
        "receipt_hash": json.loads(receipt_bytes)["receipt_sha256"],
    }
    path.write_text(json.dumps(fixture, indent=2, sort_keys=True) + "\n", encoding="ascii")


def main() -> None:
    parser = argparse.ArgumentParser()
    sub = parser.add_subparsers(dest="command", required=True)
    phase = sub.add_parser("phase")
    phase.add_argument("phase", choices=("construction", "serialization", "deserialization", "live_restore"))
    phase.add_argument("rows", type=int)
    phase.add_argument("state_path", type=Path)
    measurement = sub.add_parser("measure")
    measurement.add_argument("output", type=Path)
    measurement.add_argument("workspace", type=Path)
    golden = sub.add_parser("golden")
    golden.add_argument("output", type=Path)
    args = parser.parse_args()
    if args.command == "phase":
        print(json.dumps(run_phase(args.phase, args.rows, args.state_path), sort_keys=True))
    elif args.command == "measure":
        measure(args.output, args.workspace)
    else:
        write_golden(args.output)


if __name__ == "__main__":
    main()
