"""Deterministic stale-evidence protection for Phase D2."""

from __future__ import annotations

from dataclasses import dataclass

from .models import Snapshot


# D2 deliberately uses one explicit operational limit.  It is not learned,
# inferred, or adjusted from market activity.
MAX_SNAPSHOT_AGE_SECONDS = 60.0


@dataclass(frozen=True)
class StalenessStatus:
    age_seconds: float
    stale: bool
    usable: bool
    reason_codes: tuple[str, ...]


def assess_staleness(
    snapshot: Snapshot,
    *,
    now_epoch: float,
) -> StalenessStatus:
    """Assess snapshot age without changing the snapshot or pipeline state.

    Existing intake evidence remains authoritative: a snapshot already marked
    non-fresh stays unusable.  D2 adds the missing wall-clock protection so a
    previously fresh snapshot cannot be treated as usable forever.
    """

    age_seconds = now_epoch - snapshot.asof_epoch
    reasons: list[str] = []

    if age_seconds < 0:
        reasons.append("SNAPSHOT_FROM_FUTURE")
    elif age_seconds > MAX_SNAPSHOT_AGE_SECONDS:
        reasons.append("STALE_SNAPSHOT")

    if not snapshot.fresh:
        reasons.extend(snapshot.reason_codes or ["SNAPSHOT_NOT_FRESH"])

    return StalenessStatus(
        age_seconds=age_seconds,
        stale="STALE_SNAPSHOT" in reasons,
        usable=snapshot.is_usable() and not reasons,
        reason_codes=tuple(reasons),
    )


__all__ = [
    "MAX_SNAPSHOT_AGE_SECONDS",
    "StalenessStatus",
    "assess_staleness",
]
