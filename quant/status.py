"""Minimal truthful quant status for Phase B4."""

from __future__ import annotations

from dataclasses import dataclass

from .ledger import Ledger
from .resolver import Resolver


@dataclass(frozen=True)
class QuantStatus:
    ledger_active: bool
    ledger_count: int
    latest_cycle_id: str | None
    resolved_count: int
    resolver_active: bool


def build_status(
    ledger: Ledger,
    resolver: Resolver,
) -> QuantStatus:
    """Build status only from committed and resolved evidence."""

    ledger_count = ledger.count()
    latest = ledger.latest()
    resolved_count = resolver.count()
    return QuantStatus(
        ledger_active=ledger_count > 0,
        ledger_count=ledger_count,
        latest_cycle_id=(
            latest.bundle.cycle_id if latest is not None else None
        ),
        resolved_count=resolved_count,
        resolver_active=resolved_count > 0,
    )


__all__ = ["QuantStatus", "build_status"]
