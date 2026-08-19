"""In-memory exact-six bundle ledger for Phase B1."""

from __future__ import annotations

from copy import deepcopy
from dataclasses import dataclass

from .models import ExactSixBundle, HORIZONS


@dataclass
class LedgerRecord:
    """One committed exact-six bundle."""

    bundle: ExactSixBundle


class Ledger:
    """An insertion-ordered, append-only ledger of exact-six bundles."""

    def __init__(self) -> None:
        self._records: dict[str, LedgerRecord] = {}

    def commit(self, bundle: ExactSixBundle) -> LedgerRecord:
        """Commit a defensive copy of a valid, previously unseen bundle."""

        if bundle.cycle_id in self._records:
            raise ValueError(f"cycle already committed: {bundle.cycle_id}")

        horizons = tuple(row.horizon for row in bundle.rows)
        if len(bundle.rows) != len(HORIZONS) or horizons != HORIZONS:
            raise ValueError("commit requires exactly six horizons in exact order")

        record = LedgerRecord(bundle=deepcopy(bundle))
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


__all__ = ["Ledger", "LedgerRecord"]
