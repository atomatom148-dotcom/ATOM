"""Phase C1 volatility/friction evidence derived from one snapshot."""

from __future__ import annotations

from dataclasses import dataclass
import math

from .models import Snapshot


@dataclass(frozen=True)
class VolFrictionEvidence:
    usable: bool
    range_pct: float | None
    spread_pct: float | None
    net_range_pct: float | None
    reason_codes: tuple[str, ...]


def evaluate_vol_friction(snapshot: Snapshot) -> VolFrictionEvidence:
    """Return descriptive volatility/friction evidence without prediction."""

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
        return VolFrictionEvidence(
            usable=False,
            range_pct=None,
            spread_pct=None,
            net_range_pct=None,
            reason_codes=tuple(reasons),
        )

    # Required evidence has been validated above.
    assert snapshot.last is not None
    assert snapshot.bid is not None
    assert snapshot.ask is not None
    spread_pct = (snapshot.ask - snapshot.bid) / snapshot.last

    if not _is_positive_finite(snapshot.bar_close):
        return VolFrictionEvidence(
            usable=True,
            range_pct=None,
            spread_pct=spread_pct,
            net_range_pct=None,
            reason_codes=("RANGE_UNAVAILABLE",),
        )

    range_pct = abs(snapshot.last - snapshot.bar_close) / snapshot.last
    return VolFrictionEvidence(
        usable=True,
        range_pct=range_pct,
        spread_pct=spread_pct,
        net_range_pct=max(range_pct - spread_pct, 0.0),
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


__all__ = ["VolFrictionEvidence", "evaluate_vol_friction"]
