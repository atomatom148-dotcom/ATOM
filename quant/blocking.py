"""Deterministic blocked-evidence assessment for Phase D3."""

from __future__ import annotations

from dataclasses import dataclass

from .ledger import validate_bundle_integrity
from .models import ExactSixBundle, SetupState


@dataclass(frozen=True)
class BlockedEvidence:
    blocked: bool
    blocked_horizons: tuple[str, ...]
    reason_codes: tuple[str, ...]


def assess_blocked(bundle: ExactSixBundle) -> BlockedEvidence:
    """Report explicit ``BLOCKED`` rows without interpreting their evidence.

    The committed setup state and reason codes are authoritative.  This
    assessment does not infer a block from other states or evidence and does
    not alter the bundle.
    """

    validate_bundle_integrity(bundle)
    blocked_rows = tuple(
        row for row in bundle.rows if row.setup_state is SetupState.BLOCKED
    )
    return BlockedEvidence(
        blocked=bool(blocked_rows),
        blocked_horizons=tuple(row.horizon for row in blocked_rows),
        reason_codes=tuple(
            reason
            for row in blocked_rows
            for reason in row.reason_codes
        ),
    )


__all__ = ["BlockedEvidence", "assess_blocked"]
