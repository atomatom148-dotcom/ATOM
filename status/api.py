"""Minimal truthful status JSON for Phase B4."""

from __future__ import annotations

from typing import Any

from quant.ledger import Ledger


def get_status(ledger: Ledger) -> dict[str, Any]:
    """Return only facts currently present in the ledger.

    An empty ledger has no latest cycle.  Once a cycle has been committed, its
    stored exact-six bundle is returned without deriving readiness, counts, or
    forecast evidence that the ledger does not contain.
    """

    latest = ledger.latest()
    return {
        "ledger_count": ledger.count(),
        "latest_cycle": latest.bundle.to_dict() if latest is not None else None,
    }


__all__ = ["get_status"]
