"""Deterministic stale-evidence assessment for Phase D2."""

from __future__ import annotations

from dataclasses import dataclass
import math

from .models import Snapshot


@dataclass(frozen=True)
class StalenessEvidence:
    usable: bool
    age_seconds: float | None
    reason_codes: tuple[str, ...]


def assess_staleness(
    snapshot: Snapshot,
    *,
    now_epoch: float,
    max_age_seconds: float,
) -> StalenessEvidence:
    """Return age-based evidence without mutating the snapshot."""

    if not _is_finite_number(now_epoch):
        return StalenessEvidence(False, None, ("INVALID_NOW_EPOCH",))
    if not _is_finite_number(max_age_seconds) or max_age_seconds < 0:
        return StalenessEvidence(False, None, ("INVALID_MAX_AGE_SECONDS",))
    if not _is_finite_number(snapshot.asof_epoch):
        return StalenessEvidence(False, None, ("INVALID_ASOF_EPOCH",))

    age_seconds = now_epoch - snapshot.asof_epoch
    if not snapshot.fresh:
        return StalenessEvidence(
            False, age_seconds, ("SNAPSHOT_MARKED_STALE",)
        )
    if age_seconds < 0:
        return StalenessEvidence(
            False, age_seconds, ("SNAPSHOT_FROM_FUTURE",)
        )
    if age_seconds > max_age_seconds:
        return StalenessEvidence(False, age_seconds, ("SNAPSHOT_TOO_OLD",))
    return StalenessEvidence(True, age_seconds, ())


def _is_finite_number(value: object) -> bool:
    return (
        isinstance(value, (int, float))
        and not isinstance(value, bool)
        and math.isfinite(value)
    )


__all__ = ["StalenessEvidence", "assess_staleness"]
