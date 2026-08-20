"""Honest restart-loss assessment for Phase D1."""

from __future__ import annotations

from dataclasses import dataclass

from .ledger import Ledger
from .resolver import Resolver


@dataclass(frozen=True)
class RecoveryStatus:
    ledger_records: int
    resolved_outcomes: int
    recoverable: bool
    reason_codes: tuple[str, ...]


def assess_recovery(ledger: Ledger, resolver: Resolver) -> RecoveryStatus:
    """Report whether the in-memory stores contain volatile evidence."""

    ledger_records = ledger.count()
    resolved_outcomes = resolver.count()
    reasons: list[str] = []
    if ledger_records > 0:
        reasons.append("VOLATILE_LEDGER_NOT_DURABLE")
    if resolved_outcomes > 0:
        reasons.append("VOLATILE_RESOLVER_NOT_DURABLE")

    return RecoveryStatus(
        ledger_records=ledger_records,
        resolved_outcomes=resolved_outcomes,
        recoverable=ledger_records == 0 and resolved_outcomes == 0,
        reason_codes=tuple(reasons),
    )


__all__ = ["RecoveryStatus", "assess_recovery"]
