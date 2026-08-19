"""Minimal due-horizon resolution for Phase B3."""

from __future__ import annotations

from dataclasses import dataclass
import math

from .ledger import LedgerRecord


@dataclass(frozen=True)
class ResolvedOutcome:
    """Observed price attached to one matured forecast horizon."""

    cycle_id: str
    horizon: str
    maturity_epoch: float
    resolved_at_epoch: float
    outcome_price: float


def resolve_due(
    record: LedgerRecord,
    *,
    now_epoch: float,
    outcome_price: float,
) -> list[ResolvedOutcome]:
    """Return outcomes for horizons matured by ``now_epoch`` in frozen order."""

    if not math.isfinite(outcome_price) or outcome_price <= 0:
        raise ValueError("outcome_price must be positive and finite")

    return [
        ResolvedOutcome(
            cycle_id=record.bundle.cycle_id,
            horizon=row.horizon,
            maturity_epoch=row.maturity_epoch,
            resolved_at_epoch=now_epoch,
            outcome_price=outcome_price,
        )
        for row in record.bundle.rows
        if row.maturity_epoch <= now_epoch
    ]


__all__ = ["ResolvedOutcome", "resolve_due"]
