"""Exact restoration of existing numerical evidence for Phase D4."""

from __future__ import annotations

from copy import deepcopy
from dataclasses import dataclass

from .ledger import Ledger, LedgerRecord
from .resolver import ResolvedOutcome, Resolver


@dataclass(frozen=True)
class HydratedState:
    ledger: Ledger
    resolver: Resolver
    ledger_records: int
    resolved_outcomes: int


def hydrate_exact_six(
    *,
    records: tuple[LedgerRecord, ...],
    outcomes: tuple[ResolvedOutcome, ...],
) -> HydratedState:
    """Restore supplied records and outcomes through their existing stores."""

    ledger = Ledger()
    resolver = Resolver()
    committed: dict[str, LedgerRecord] = {}

    for supplied in records:
        restored = ledger.commit(
            deepcopy(supplied.bundle),
            committed_at_epoch=supplied.committed_at_epoch,
        )
        committed[restored.bundle.cycle_id] = restored

    matched: list[tuple[int, ResolvedOutcome, LedgerRecord]] = []
    for position, outcome in enumerate(outcomes):
        record = committed.get(outcome.cycle_id)
        if record is None:
            raise ValueError(
                f"outcome references unknown cycle: {outcome.cycle_id}"
            )
        row = next(
            (
                row
                for row in record.bundle.rows
                if row.horizon == outcome.horizon
                and row.maturity_epoch == outcome.maturity_epoch
            ),
            None,
        )
        if row is None:
            raise ValueError("outcome horizon and maturity must match a committed row")
        matched.append((position, outcome, record))

    for _, outcome, record in sorted(
        matched,
        key=lambda item: (item[1].resolved_at_epoch, item[0]),
    ):
        resolver.resolve_due(
            record,
            now_epoch=outcome.resolved_at_epoch,
            prices_by_horizon={outcome.horizon: outcome.outcome_price},
        )

    return HydratedState(
        ledger=ledger,
        resolver=resolver,
        ledger_records=ledger.count(),
        resolved_outcomes=resolver.count(),
    )


__all__ = ["HydratedState", "hydrate_exact_six"]
