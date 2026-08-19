"""Minimal due-horizon selection for Phase B3."""

from __future__ import annotations

from .ledger import LedgerRecord


def due_horizons(record: LedgerRecord, now_epoch: float) -> list[str]:
    """Return committed horizon names that have matured by ``now_epoch``.

    This resolver only identifies work that is due. It does not mutate the
    append-only ledger, score forecasts, or invent resolution evidence.
    """

    return [
        row.horizon
        for row in record.bundle.rows
        if row.maturity_epoch <= now_epoch
    ]


__all__ = ["due_horizons"]
