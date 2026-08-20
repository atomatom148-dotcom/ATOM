import re
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
BASELINE = ROOT / "migrations" / "001_live_q1_q2_evidence.sql"
PREVIOUS_MIGRATION = ROOT / "migrations" / "002_expand_directional_quant_id_check.sql"
MIGRATION = ROOT / "migrations" / "003_enable_q10_directional_evidence.sql"
APPROVED_QUANT_IDS = {
    "q1_momentum",
    "q2_mean_reversion",
    "q4_stat_arb",
    "q5_microstructure",
    "q6_volume_liquidity",
    "q7_relative_value",
    "q8_cross_asset",
    "q9_factor",
    "q10_options_vol",
    "q11_regime",
    "q12_event_session",
}


class DirectionalQuantConstraintMigrationTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.baseline = BASELINE.read_text(encoding="utf-8")
        cls.previous_migration = PREVIOUS_MIGRATION.read_text(encoding="utf-8")
        cls.migration = MIGRATION.read_text(encoding="utf-8")
        cls.allowed_quant_ids = cls._allowed_quant_ids(cls.migration)
        cls.previous_allowed_quant_ids = cls._allowed_quant_ids(
            cls.previous_migration
        )

    @staticmethod
    def _allowed_quant_ids(sql):
        match = re.search(
            r"ADD\s+CONSTRAINT\s+forecasts_quant_id_check\s+CHECK\s*\("
            r"\s*quant_id\s+IN\s*\((.*?)\)\s*\)",
            sql,
            flags=re.IGNORECASE | re.DOTALL,
        )
        if match is None:
            raise AssertionError("explicit forecasts quant_id CHECK was not found")
        return set(re.findall(r"'([^']+)'", match.group(1)))

    def test_check_permits_exactly_the_approved_directional_families(self):
        self.assertEqual(self.allowed_quant_ids, APPROVED_QUANT_IDS)

    def test_check_explicitly_permits_q10(self):
        self.assertIn("q10_options_vol", self.allowed_quant_ids)

    def test_only_q10_is_added_to_the_previous_whitelist(self):
        self.assertEqual(
            self.allowed_quant_ids - self.previous_allowed_quant_ids,
            {"q10_options_vol"},
        )
        self.assertEqual(
            self.previous_allowed_quant_ids - self.allowed_quant_ids,
            set(),
        )

    def test_check_rejects_q3_and_unknown_families(self):
        for quant_id in ("q3_volatility", "unknown_quant"):
            with self.subTest(quant_id=quant_id):
                self.assertNotIn(quant_id, self.allowed_quant_ids)

    def test_replaces_only_the_existing_named_constraint(self):
        self.assertRegex(
            self.migration,
            r"(?i)ALTER\s+TABLE\s+forecasts\s+DROP\s+CONSTRAINT\s+"
            r"forecasts_quant_id_check\s*,\s*ADD\s+CONSTRAINT\s+"
            r"forecasts_quant_id_check",
        )
        self.assertEqual(
            len(re.findall(r"(?i)\bALTER\s+TABLE\b", self.migration)), 1
        )

    def test_migration_has_no_data_mutation_or_table_recreation(self):
        for forbidden in ("UPDATE", "DELETE", "INSERT", "CREATE TABLE"):
            with self.subTest(statement=forbidden):
                self.assertIsNone(
                    re.search(rf"(?i)\b{forbidden.replace(' ', r'\s+')}\b", self.migration)
                )

    def test_forecast_identity_and_outcomes_are_unchanged(self):
        self.assertIn(
            "CONSTRAINT forecasts_identity UNIQUE "
            "(quant_id, formula_version, cycle_id, symbol, horizon)",
            self.baseline,
        )
        self.assertIn("CREATE TABLE forecast_outcomes", self.baseline)
        self.assertNotIn("forecasts_identity", self.migration)
        self.assertNotIn("forecast_outcomes", self.migration)

    def test_existing_forecast_columns_are_unchanged(self):
        self.assertIn("quant_id text NOT NULL CHECK", self.baseline)
        self.assertIsNone(
            re.search(r"(?i)\b(?:ADD|ALTER|DROP)\s+COLUMN\b", self.migration)
        )


if __name__ == "__main__":
    unittest.main()
