"""In-memory exact-six bundle ledger for Phase B1."""

from __future__ import annotations

from copy import deepcopy
from dataclasses import dataclass
import math

from .models import ExactSixBundle, HORIZONS


@dataclass
class LedgerRecord:
    """One committed exact-six bundle."""

    bundle: ExactSixBundle
    committed_at_epoch: float


class Ledger:
    """An insertion-ordered, append-only ledger of exact-six bundles."""

    def __init__(self) -> None:
        self._records: dict[str, LedgerRecord] = {}

    def commit(
        self, bundle: ExactSixBundle, *, committed_at_epoch: float
    ) -> LedgerRecord:
        """Commit a defensive copy of a valid, previously unseen bundle."""

        if bundle.cycle_id in self._records:
            raise ValueError(f"cycle already committed: {bundle.cycle_id}")

        validate_bundle_integrity(bundle)
        if not math.isfinite(committed_at_epoch):
            raise ValueError("commit timestamp must be finite")
        if committed_at_epoch < bundle.cutoff_epoch:
            raise ValueError("commit timestamp cannot precede the bundle cutoff")
        first_maturity = min(row.maturity_epoch for row in bundle.rows)
        if committed_at_epoch >= first_maturity:
            raise ValueError("commit must occur before first horizon maturity")

        record = LedgerRecord(
            bundle=deepcopy(bundle), committed_at_epoch=committed_at_epoch
        )
        self._records[bundle.cycle_id] = record
        return deepcopy(record)

    def latest(self) -> LedgerRecord | None:
        """Return a copy of the most recently committed record, if one exists."""

        if not self._records:
            return None
        return deepcopy(next(reversed(self._records.values())))

    def get(self, cycle_id: str) -> LedgerRecord | None:
        """Return a copy of a record by cycle ID, or ``None`` when missing."""

        record = self._records.get(cycle_id)
        return deepcopy(record) if record is not None else None

    def count(self) -> int:
        """Return the number of committed records."""

        return len(self._records)


def validate_bundle_integrity(bundle: ExactSixBundle) -> None:
    """Reject rows that cannot truthfully belong to the claimed commit."""

    horizons = tuple(row.horizon for row in bundle.rows)
    if len(bundle.rows) != len(HORIZONS) or horizons != HORIZONS:
        raise ValueError("commit requires exactly six horizons in exact order")
    if not math.isfinite(bundle.cutoff_epoch):
        raise ValueError("commit cutoff must be finite")
    if any(row.cutoff_epoch != bundle.cutoff_epoch for row in bundle.rows):
        raise ValueError("every row cutoff must match the bundle cutoff")
    if any(
        not math.isfinite(row.maturity_epoch)
        or row.maturity_epoch <= bundle.cutoff_epoch
        for row in bundle.rows
    ):
        raise ValueError("every horizon must mature after the commit cutoff")


__all__ = ["Ledger", "LedgerRecord"]
