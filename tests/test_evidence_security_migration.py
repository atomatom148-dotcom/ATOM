import re
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
MIGRATION = ROOT / "migrations" / "004_secure_evidence_rls.sql"


class EvidenceSecurityMigrationTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.sql = MIGRATION.read_text(encoding="utf-8")
        cls.normalized = " ".join(cls.sql.upper().split())

    def test_enables_rls_on_both_evidence_tables(self):
        for table in ("FORECASTS", "FORECAST_OUTCOMES"):
            with self.subTest(table=table):
                self.assertIn(
                    f"ALTER TABLE PUBLIC.{table} ENABLE ROW LEVEL SECURITY;",
                    self.normalized,
                )

    def test_revokes_all_table_privileges_from_data_api_roles(self):
        self.assertRegex(
            self.normalized,
            r"REVOKE ALL PRIVILEGES ON TABLE "
            r"PUBLIC\.FORECASTS, PUBLIC\.FORECAST_OUTCOMES "
            r"FROM PUBLIC, ANON, AUTHENTICATED, SERVICE_ROLE;",
        )

    def test_revokes_forecast_identity_sequence(self):
        self.assertRegex(
            self.normalized,
            r"REVOKE ALL PRIVILEGES ON SEQUENCE "
            r"PUBLIC\.FORECASTS_FORECAST_ID_SEQ "
            r"FROM PUBLIC, ANON, AUTHENTICATED, SERVICE_ROLE;",
        )

    def test_does_not_create_public_access_policies_or_mutate_evidence(self):
        self.assertNotIn("CREATE POLICY", self.normalized)
        for statement in ("INSERT", "UPDATE", "DELETE", "TRUNCATE", "DROP"):
            with self.subTest(statement=statement):
                self.assertIsNone(re.search(rf"\b{statement}\b", self.normalized))


if __name__ == "__main__":
    unittest.main()
