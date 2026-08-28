from dataclasses import fields
from pathlib import Path

from quant.v9_v2a_dataset import V2ADataset


REPORT = Path(__file__).parents[1] / "docs" / "v2a-phase-1b-interface-blocker.md"


def test_frozen_v2a_row_collections_are_concrete_tuples():
    annotations = {field.name: field.type for field in fields(V2ADataset)}
    assert annotations["skeleton"] == "tuple[TargetOrigin, ...]"
    assert annotations["directional_subsets"] == "tuple[FamilySubset, ...]"
    assert annotations["pair_support"] == "tuple[PairSupport, ...]"
    assert annotations["complete_case_target_identities"] == (
        "tuple[TargetIdentity, ...]"
    )


def test_phase_1b_report_fails_closed_without_parity_claims():
    report = REPORT.read_text(encoding="utf-8")
    assert "BLOCKED_BY_FROZEN_V2A_INTERFACE" in report
    assert "No parity or resource result is claimed" in report
    assert "not a prototype or a parity claim" in report
