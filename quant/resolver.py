"""Minimal due-horizon resolution for Phase B3."""

from __future__ import annotations

from dataclasses import dataclass
from copy import deepcopy
import math

from .ledger import LedgerRecord, validate_bundle_integrity


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
    if not math.isfinite(now_epoch):
        raise ValueError("now_epoch must be finite")
    validate_bundle_integrity(record.bundle)
    if not math.isfinite(record.committed_at_epoch):
        raise ValueError("commit timestamp must be finite")
    if any(
        record.committed_at_epoch >= row.maturity_epoch
        for row in record.bundle.rows
    ):
        raise ValueError("commit must occur before every horizon maturity")

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


class Resolver:
    """Append-only store of outcomes produced from committed, due rows."""

    def __init__(self) -> None:
        self._outcomes: dict[tuple[str, str], ResolvedOutcome] = {}

    def resolve_due(
        self,
        record: LedgerRecord,
        *,
        now_epoch: float,
        outcome_price: float,
    ) -> list[ResolvedOutcome]:
        """Append and return only outcomes not resolved by an earlier call."""

        resolved = resolve_due(
            record, now_epoch=now_epoch, outcome_price=outcome_price
        )
        appended = []
        for outcome in resolved:
            key = (outcome.cycle_id, outcome.horizon)
            if key not in self._outcomes:
                self._outcomes[key] = outcome
                appended.append(outcome)
        return deepcopy(appended)

    def outcomes(self) -> list[ResolvedOutcome]:
        """Return defensive copies of all outcomes in append order."""

        return deepcopy(list(self._outcomes.values()))

    def count(self) -> int:
        return len(self._outcomes)


__all__ = ["ResolvedOutcome", "Resolver", "resolve_due"]
