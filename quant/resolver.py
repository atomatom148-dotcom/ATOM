"""Append-only due-horizon resolution for Phase B."""

from __future__ import annotations

from copy import deepcopy
from dataclasses import dataclass
import math

from .ledger import LedgerRecord, validate_bundle_integrity


@dataclass(frozen=True)
class ResolvedOutcome:
    """Observed maturity price attached to one forecast horizon."""

    cycle_id: str
    horizon: str
    maturity_epoch: float
    resolved_at_epoch: float
    outcome_price: float


class Resolver:
    """Append-only store of validated horizon outcomes."""

    def __init__(self) -> None:
        self._outcomes: dict[tuple[str, str, float], ResolvedOutcome] = {}

    def resolve_due(
        self,
        record: LedgerRecord,
        *,
        now_epoch: float,
        prices_by_horizon: dict[str, float],
    ) -> list[ResolvedOutcome]:
        """Atomically append supplied prices for their exact due horizons."""

        validate_bundle_integrity(record.bundle)
        if not math.isfinite(record.committed_at_epoch):
            raise ValueError("commit timestamp must be finite")
        if record.committed_at_epoch < record.bundle.cutoff_epoch:
            raise ValueError("commit timestamp cannot precede the bundle cutoff")
        first_maturity = min(row.maturity_epoch for row in record.bundle.rows)
        if record.committed_at_epoch >= first_maturity:
            raise ValueError("commit must occur before first horizon maturity")
        if not math.isfinite(now_epoch):
            raise ValueError("now_epoch must be finite")

        rows_by_horizon = {
            row.horizon: row for row in record.bundle.rows
        }
        pending: list[tuple[tuple[str, str, float], ResolvedOutcome]] = []
        for horizon, price in prices_by_horizon.items():
            row = rows_by_horizon.get(horizon)
            if row is None:
                raise ValueError(f"unknown horizon: {horizon}")
            if not math.isfinite(price) or price <= 0:
                raise ValueError("outcome prices must be positive and finite")
            if row.maturity_epoch > now_epoch:
                raise ValueError(f"horizon is not due: {horizon}")
            identity = (
                record.bundle.cycle_id,
                horizon,
                row.maturity_epoch,
            )
            if identity in self._outcomes:
                raise ValueError(f"horizon already resolved: {horizon}")
            pending.append(
                (
                    identity,
                    ResolvedOutcome(
                        cycle_id=record.bundle.cycle_id,
                        horizon=horizon,
                        maturity_epoch=row.maturity_epoch,
                        resolved_at_epoch=now_epoch,
                        outcome_price=price,
                    ),
                )
            )

        for identity, outcome in pending:
            self._outcomes[identity] = outcome
        return deepcopy([outcome for _, outcome in pending])

    def count(self) -> int:
        return len(self._outcomes)

    def get(self, cycle_id: str, horizon: str) -> ResolvedOutcome | None:
        for identity, outcome in self._outcomes.items():
            if identity[:2] == (cycle_id, horizon):
                return deepcopy(outcome)
        return None

    def all(self) -> list[ResolvedOutcome]:
        return deepcopy(list(self._outcomes.values()))


__all__ = ["ResolvedOutcome", "Resolver"]
