"""Phase B4 proofs for the minimal truthful status projection."""

from __future__ import annotations

from pathlib import Path
import sys
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from quant.ledger import Ledger
from quant.snapshot import missing_example
from quant.unified_quant import write_cycle
import status.api as status_api
from status.api import get_status


CUTOFF = 1_700_000_100.0


class PhaseB4StatusTests(unittest.TestCase):
    def test_empty_ledger_reports_only_empty_facts(self) -> None:
        self.assertEqual(
            get_status(Ledger()),
            {"ledger_count": 0, "latest_cycle": None},
        )

    def test_status_reports_the_actual_latest_committed_cycle(self) -> None:
        ledger = Ledger()
        write_cycle(
            missing_example(),
            ledger,
            cycle_id="cycle-1",
            cutoff_epoch=CUTOFF,
        )
        latest = write_cycle(
            missing_example(),
            ledger,
            cycle_id="cycle-2",
            cutoff_epoch=CUTOFF + 1,
        )

        self.assertEqual(
            get_status(ledger),
            {"ledger_count": 2, "latest_cycle": latest.bundle.to_dict()},
        )

    def test_missing_values_and_unavailable_reasons_are_not_invented(self) -> None:
        ledger = Ledger()
        record = write_cycle(
            missing_example(),
            ledger,
            cycle_id="cycle-1",
            cutoff_epoch=CUTOFF,
        )

        payload = get_status(ledger)

        self.assertEqual(payload["latest_cycle"], record.bundle.to_dict())
        for row in payload["latest_cycle"]["rows"]:
            self.assertEqual(row["setup_state"], "UNAVAILABLE")
            self.assertEqual(row["reason_codes"], ["MISSING_LAST"])
            self.assertIsNone(row["direction"])
            self.assertIsNone(row["probability"])

    def test_forbidden_status_surfaces_are_absent(self) -> None:
        payload = get_status(Ledger())

        for name in (
            "ready",
            "probability",
            "resolved_count",
            "eligible_count",
            "cold_start",
            "chart",
            "broker",
            "order",
            "execute",
            "execution",
        ):
            self.assertNotIn(name, payload)
            self.assertFalse(hasattr(status_api, name), name)


if __name__ == "__main__":
    unittest.main()
