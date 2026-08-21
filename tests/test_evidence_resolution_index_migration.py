import re
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
MIGRATION = ROOT / "migrations" / "005_index_evidence_resolution.sql"


class EvidenceResolutionIndexMigrationTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.sql = " ".join(MIGRATION.read_text(encoding="utf-8").upper().split())

    def test_indexes_only_resolution_timestamps(self):
        self.assertIn(
            "CREATE INDEX IF NOT EXISTS FORECASTS_MATURITY_EPOCH_IDX "
            "ON PUBLIC.FORECASTS (MATURITY_EPOCH);",
            self.sql,
        )
        self.assertIn(
            "CREATE INDEX IF NOT EXISTS FORECAST_OUTCOMES_RESOLVED_EPOCH_IDX "
            "ON PUBLIC.FORECAST_OUTCOMES (RESOLVED_EPOCH DESC);",
            self.sql,
        )

    def test_migration_does_not_mutate_or_delete_evidence(self):
        for statement in ("INSERT", "UPDATE", "DELETE", "TRUNCATE", "DROP"):
            with self.subTest(statement=statement):
                self.assertIsNone(re.search(rf"\b{statement}\b", self.sql))


if __name__ == "__main__":
    unittest.main()
