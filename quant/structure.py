"""Phase C2 structure evidence derived from one snapshot."""

from __future__ import annotations

from dataclasses import dataclass
import math

from .models import Snapshot


@dataclass(frozen=True)
class StructureEvidence:
    """A descriptive comparison of the last price with the bar close."""

    usable: bool
    displacement_pct: float | None
    relation: str | None
    reason_codes: tuple[str, ...]


def evaluate_structure(snapshot: Snapshot) -> StructureEvidence:
    """Describe price location without producing a forecast or setup decision."""

    reasons: list[str] = []
    if not snapshot.fresh:
        reasons.append("STALE_SNAPSHOT")
    _require_positive_finite(snapshot.last, "LAST", reasons)
    _require_positive_finite(snapshot.bar_close, "BAR_CLOSE", reasons)

    if reasons:
        return StructureEvidence(
            usable=False,
            displacement_pct=None,
            relation=None,
            reason_codes=tuple(reasons),
        )

    # Both observations were validated above.
    assert snapshot.last is not None
    assert snapshot.bar_close is not None
    displacement_pct = (snapshot.last - snapshot.bar_close) / snapshot.bar_close
    if snapshot.last > snapshot.bar_close:
        relation = "ABOVE_BAR_CLOSE"
    elif snapshot.last < snapshot.bar_close:
        relation = "BELOW_BAR_CLOSE"
    else:
        relation = "AT_BAR_CLOSE"

    return StructureEvidence(
        usable=True,
        displacement_pct=displacement_pct,
        relation=relation,
        reason_codes=(),
    )


def _require_positive_finite(
    value: object, name: str, reasons: list[str]
) -> None:
    if value is None:
        reasons.append(f"MISSING_{name}")
    elif not _is_positive_finite(value):
        reasons.append(f"INVALID_{name}")


def _is_positive_finite(value: object) -> bool:
    return (
        isinstance(value, (int, float))
        and not isinstance(value, bool)
        and math.isfinite(value)
        and value > 0
    )


__all__ = ["StructureEvidence", "evaluate_structure"]
