"""Atomic, process-local storage for exact-six forecast bundles.

Phase B1 deliberately defines only the ledger boundary.  Persistence and
forecast resolution belong to later phases.
"""

from __future__ import annotations

from copy import deepcopy
from dataclasses import dataclass

from .models import ExactSixBundle, HORIZONS


class LedgerCommitError(ValueError):
    """Raised when a bundle cannot be committed without breaking ledger law."""


@dataclass(frozen=True)
class LedgerCommit:
    """An immutable receipt plus a private snapshot of the committed bundle."""

    cycle_id: str
    committed_at_epoch: float
    _bundle: ExactSixBundle

    @property
    def bundle(self) -> ExactSixBundle:
        """Return a copy so callers cannot rewrite committed history."""

        return deepcopy(self._bundle)


class ExactSixLedger:
    """Minimal in-memory, append-only exact-six ledger."""

    def __init__(self) -> None:
        self._commits: dict[str, LedgerCommit] = {}

    def commit(
        self, bundle: ExactSixBundle, *, committed_at_epoch: float
    ) -> LedgerCommit:
        """Atomically commit one bundle before any of its rows mature.

        Validation happens before the ledger is modified.  A cycle identifier
        is idempotency ownership, not an update key: committed cycles cannot be
        overwritten, even with an otherwise identical bundle.
        """

        if bundle.cycle_id in self._commits:
            raise LedgerCommitError(f"cycle already committed: {bundle.cycle_id}")

        got = tuple(row.horizon for row in bundle.rows)
        if len(bundle.rows) != len(HORIZONS) or got != HORIZONS:
            raise LedgerCommitError("commit requires exactly six ordered horizons")

        if any(row.cutoff_epoch != bundle.cutoff_epoch for row in bundle.rows):
            raise LedgerCommitError("row cutoff must match bundle cutoff")

        if any(row.maturity_epoch <= committed_at_epoch for row in bundle.rows):
            raise LedgerCommitError("bundle must be committed before horizon maturity")

        stored = deepcopy(bundle)
        receipt = LedgerCommit(
            cycle_id=bundle.cycle_id,
            committed_at_epoch=committed_at_epoch,
            _bundle=stored,
        )
        self._commits[bundle.cycle_id] = receipt
        return self.get(bundle.cycle_id)

    def get(self, cycle_id: str) -> LedgerCommit:
        """Return a defensive copy of a cycle's commit receipt."""

        receipt = self._commits[cycle_id]
        return LedgerCommit(
            cycle_id=receipt.cycle_id,
            committed_at_epoch=receipt.committed_at_epoch,
            _bundle=deepcopy(receipt._bundle),
        )

    def __len__(self) -> int:
        return len(self._commits)


# The shorter name keeps the phase boundary pleasant to consume while the
# descriptive name documents its exact-six invariant.
Ledger = ExactSixLedger


__all__ = ["ExactSixLedger", "Ledger", "LedgerCommit", "LedgerCommitError"]
