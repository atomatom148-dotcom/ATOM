"""Phase C2 structure evidence derived from one snapshot."""

from __future__ import annotations

from dataclasses import dataclass
import math

from .models import Snapshot


@dataclass(frozen=True)
class StructureEvidence:
    usable: bool
    distance_from_close_pct: float | None
    midpoint: float | None
    distance_from_mid_pct: float | None
    location_in_quote: float | None
    reason_codes: tuple[str, ...]


def evaluate_structure(snapshot: Snapshot) -> StructureEvidence:
    """Return descriptive price structure without making a decision."""

    reasons: list[str] = []
    if not snapshot.fresh:
        reasons.append("STALE_SNAPSHOT")
    _require_positive_finite(snapshot.last, "LAST", reasons)
    _require_positive_finite(snapshot.bid, "BID", reasons)
    _require_positive_finite(snapshot.ask, "ASK", reasons)
    if (
        _is_positive_finite(snapshot.bid)
        and _is_positive_finite(snapshot.ask)
        and snapshot.ask < snapshot.bid
    ):
        reasons.append("ASK_BELOW_BID")

    if reasons:
        return StructureEvidence(False, None, None, None, None, tuple(reasons))

    assert snapshot.last is not None
    assert snapshot.bid is not None
    assert snapshot.ask is not None
    midpoint = (snapshot.bid + snapshot.ask) / 2
    distance_from_mid_pct = (snapshot.last - midpoint) / snapshot.last

    if snapshot.ask == snapshot.bid:
        location_in_quote = None
        reasons.append("ZERO_QUOTE_WIDTH")
    else:
        location_in_quote = (snapshot.last - snapshot.bid) / (
            snapshot.ask - snapshot.bid
        )

    if _is_positive_finite(snapshot.bar_close):
        distance_from_close_pct = (
            snapshot.last - snapshot.bar_close
        ) / snapshot.last
    else:
        distance_from_close_pct = None
        reasons.append("CLOSE_UNAVAILABLE")

    return StructureEvidence(
        usable=True,
        distance_from_close_pct=distance_from_close_pct,
        midpoint=midpoint,
        distance_from_mid_pct=distance_from_mid_pct,
        location_in_quote=location_in_quote,
        reason_codes=tuple(reasons),
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
