"""Deterministic operational consistency certification for Phase D5."""

from __future__ import annotations

from dataclasses import dataclass

from .blocking import BlockingEvidence
from .hydration import HydratedState
from .recovery import RecoveryStatus
from .staleness import StalenessEvidence


@dataclass(frozen=True)
class OperationalCertification:
    certified: bool
    ledger_records: int
    resolved_outcomes: int
    reason_codes: tuple[str, ...]


def certify_operations(
    *,
    recovery: RecoveryStatus,
    staleness: StalenessEvidence,
    blocking: BlockingEvidence,
    hydrated: HydratedState,
) -> OperationalCertification:
    """Check consistency of authoritative D1-D4 operational evidence."""

    reasons: list[str] = []

    if not staleness.usable:
        if staleness.reason_codes:
            reasons.extend(
                f"STALENESS:{reason}" for reason in staleness.reason_codes
            )
        else:
            reasons.append("STALENESS:UNUSABLE_WITHOUT_REASON")

    if blocking.blocked:
        if blocking.reason_codes:
            reasons.extend(
                f"BLOCKING:{reason}" for reason in blocking.reason_codes
            )
        else:
            reasons.append("BLOCKING:BLOCKED_WITHOUT_REASON")

    if hydrated.ledger_records != hydrated.ledger.count():
        reasons.append("HYDRATION:LEDGER_COUNT_MISMATCH")
    if hydrated.resolved_outcomes != hydrated.resolver.count():
        reasons.append("HYDRATION:RESOLVER_COUNT_MISMATCH")

    if not recovery.recoverable:
        if recovery.ledger_records > hydrated.ledger_records:
            reasons.append("RECOVERY:LEDGER_EVIDENCE_NOT_RESTORED")
        if recovery.resolved_outcomes > hydrated.resolved_outcomes:
            reasons.append("RECOVERY:RESOLVED_EVIDENCE_NOT_RESTORED")

    return OperationalCertification(
        certified=not reasons,
        ledger_records=hydrated.ledger_records,
        resolved_outcomes=hydrated.resolved_outcomes,
        reason_codes=tuple(reasons),
    )


__all__ = ["OperationalCertification", "certify_operations"]
