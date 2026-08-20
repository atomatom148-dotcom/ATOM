"""Deterministic evidence-usability combination for Phase D3."""

from __future__ import annotations

from dataclasses import dataclass

from .staleness import StalenessEvidence
from .structure import StructureEvidence
from .vol_friction import VolFrictionEvidence


@dataclass(frozen=True)
class BlockingEvidence:
    blocked: bool
    reason_codes: tuple[str, ...]


def assess_blocking(
    *,
    staleness: StalenessEvidence,
    vol_friction: VolFrictionEvidence,
    structure: StructureEvidence,
) -> BlockingEvidence:
    """Combine the three authoritative evidence-usability results."""

    reasons: list[str] = []
    sources = (
        ("STALENESS", staleness),
        ("VOL_FRICTION", vol_friction),
        ("STRUCTURE", structure),
    )
    for prefix, evidence in sources:
        if evidence.usable:
            continue
        if evidence.reason_codes:
            reasons.extend(
                f"{prefix}:{reason}" for reason in evidence.reason_codes
            )
        else:
            reasons.append(f"{prefix}:UNUSABLE_WITHOUT_REASON")

    return BlockingEvidence(blocked=bool(reasons), reason_codes=tuple(reasons))


__all__ = ["BlockingEvidence", "assess_blocking"]
