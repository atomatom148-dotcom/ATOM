import re
import unittest
from pathlib import Path


MIGRATION = (
    Path(__file__).resolve().parents[1]
    / "migrations"
    / "007_add_q3_volatility_evidence.sql"
)


class Q3VolatilityEvidenceMigrationTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.sql = MIGRATION.read_text(encoding="utf-8")
        cls.normalized = " ".join(cls.sql.split())

    def test_q3_is_isolated_from_directional_forecasts(self):
        self.assertIn("CREATE TABLE public.volatility_forecasts", self.normalized)
        self.assertIn("quant_id = 'q3_volatility'", self.normalized)
        self.assertNotRegex(self.sql, r"(?i)ALTER\s+TABLE\s+(?:public\.)?forecasts")

    def test_outcome_is_non_directional_realized_move(self):
        self.assertIn("realized_move_bps double precision NOT NULL", self.normalized)
        self.assertNotIn("outcome_bps", self.sql)

    def test_both_tables_are_append_only_indexed_and_backend_only(self):
        for table in ("volatility_forecasts", "volatility_forecast_outcomes"):
            self.assertIn(f"BEFORE UPDATE OR DELETE ON public.{table}", self.normalized)
            self.assertIn(f"ALTER TABLE public.{table} ENABLE ROW LEVEL SECURITY", self.normalized)
        self.assertIn("volatility_forecasts_maturity_epoch_idx", self.sql)
        self.assertIn("volatility_forecast_outcomes_resolved_epoch_idx", self.sql)
        self.assertIn("FROM PUBLIC, anon, authenticated, service_role", self.normalized)

    def test_versions_are_required_and_no_existing_evidence_is_changed(self):
        self.assertIn("data_schema_version text NOT NULL", self.normalized)
        self.assertIn("source_spec_version text NOT NULL", self.normalized)
        for forbidden in (
            r"\bDROP\b", r"\bTRUNCATE\b", r"\bDELETE\s+FROM\b",
            r"\bUPDATE\s+(?:public\.)?(?:forecasts|forecast_outcomes)\b",
        ):
            self.assertIsNone(re.search(forbidden, self.sql, re.IGNORECASE))


if __name__ == "__main__":
    unittest.main()
