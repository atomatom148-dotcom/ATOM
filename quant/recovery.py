"""Restart recovery from already-loaded Phase B evidence.

This module deliberately does not read, write, or define a persistence format.
Its only job is to rebuild the in-memory Phase B stores from evidence supplied
by the caller after a process restart.
"""

from __future__ import annotations

from dataclasses import dataclass
from itertools import groupby

from .ledger import Ledger, LedgerRecord
from .resolver import ResolvedOutcome, Resolver


@dataclass(frozen=True)
class RecoveredState:
    """Fresh Phase B stores rebuilt from caller-supplied evidence."""

    ledger: Ledger
    resolver: Resolver


def recover_state(
    records: list[LedgerRecord] | tuple[LedgerRecord, ...],
    outcomes: list[ResolvedOutcome] | tuple[ResolvedOutcome, ...],
) -> RecoveredState:
    """Rebuild fresh stores, rejecting inconsistent recovery evidence.

    Records and outcomes retain their supplied order.  Recovery is atomic from
    the caller's perspective: an invalid item raises before any state is
    returned, and the supplied evidence is never mutated.
    """

    ledger = Ledger()
    for record in records:
        ledger.commit(
            record.bundle,
            committed_at_epoch=record.committed_at_epoch,
        )

    resolver = Resolver()
    indexed_outcomes = list(enumerate(outcomes))
    indexed_outcomes.sort(key=lambda item: item[1].resolved_at_epoch)
    for resolved_at_epoch, group in groupby(
        indexed_outcomes, key=lambda item: item[1].resolved_at_epoch
    ):
        by_cycle: dict[str, dict[str, float]] = {}
        for _, outcome in group:
            record = ledger.get(outcome.cycle_id)
            if record is None:
                raise ValueError(
                    f"outcome references unknown cycle: {outcome.cycle_id}"
                )
            row = next(
                (
                    row
                    for row in record.bundle.rows
                    if row.horizon == outcome.horizon
                ),
                None,
            )
            if row is None or row.maturity_epoch != outcome.maturity_epoch:
                raise ValueError("outcome does not match committed horizon")
            cycle_prices = by_cycle.setdefault(outcome.cycle_id, {})
            if outcome.horizon in cycle_prices:
                raise ValueError("duplicate recovered horizon outcome")
            cycle_prices[outcome.horizon] = outcome.outcome_price

        for cycle_id, prices in by_cycle.items():
            record = ledger.get(cycle_id)
            assert record is not None
            resolver.resolve_due(
                record,
                now_epoch=resolved_at_epoch,
                prices_by_horizon=prices,
            )

    return RecoveredState(ledger=ledger, resolver=resolver)


__all__ = ["RecoveredState", "recover_state"]
