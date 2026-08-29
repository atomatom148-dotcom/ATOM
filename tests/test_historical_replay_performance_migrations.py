import re
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
STATS_MIGRATION = ROOT / "supabase" / "migrations" / (
    "20260829125932_tune_historical_replay_statistics.sql"
)
INDEX_MIGRATION = ROOT / "migrations" / (
    "025_index_historical_replay_scoring.sql"
)


def _normalized(path: Path) -> str:
    sql = "\n".join(
        line for line in path.read_text(encoding="utf-8").splitlines()
        if not line.lstrip().startswith("--")
    )
    return " ".join(sql.upper().split())


class HistoricalReplayPerformanceMigrationTests(unittest.TestCase):
    def test_statistics_migration_sets_frozen_thresholds_and_refreshes_stats(self):
        sql = _normalized(STATS_MIGRATION)
        self.assertIn(
            "ALTER TABLE PUBLIC.ATOM_HISTORICAL_REPLAY_FORECASTS SET ( "
            "AUTOVACUUM_ANALYZE_SCALE_FACTOR = 0.0, "
            "AUTOVACUUM_ANALYZE_THRESHOLD = 100000 );",
            sql,
        )
        self.assertIn(
            "ALTER TABLE PUBLIC.ATOM_HISTORICAL_REPLAY_OUTCOMES SET ( "
            "AUTOVACUUM_ANALYZE_SCALE_FACTOR = 0.0, "
            "AUTOVACUUM_ANALYZE_THRESHOLD = 10000 );",
            sql,
        )
        for table in (
            "ATOM_HISTORICAL_REPLAY_RUNS",
            "ATOM_HISTORICAL_REPLAY_FORECASTS",
            "ATOM_HISTORICAL_REPLAY_OUTCOMES",
        ):
            with self.subTest(table=table):
                self.assertIn(f"ANALYZE PUBLIC.{table};", sql)

    def test_scoring_index_matches_the_frozen_query_shape(self):
        sql = _normalized(INDEX_MIGRATION)
        self.assertIn("SET STATEMENT_TIMEOUT = '0';", sql)
        self.assertIn("SET LOCK_TIMEOUT = '5S';", sql)
        self.assertIn(
            "CREATE INDEX CONCURRENTLY "
            "ATOM_HISTORICAL_REPLAY_FORECASTS_SCORING_IDX "
            "ON PUBLIC.ATOM_HISTORICAL_REPLAY_FORECASTS "
            "(REPLAY_RUN_ID, QUANT_ID, HORIZON, CUTOFF_AT);",
            sql,
        )
        self.assertEqual(sql.count("CREATE INDEX CONCURRENTLY"), 1)
        self.assertIn("RESET LOCK_TIMEOUT;", sql)
        self.assertIn("RESET STATEMENT_TIMEOUT;", sql)
        self.assertLess(
            sql.index("SET STATEMENT_TIMEOUT = '0';"),
            sql.index("CREATE INDEX CONCURRENTLY"),
        )
        self.assertLess(
            sql.index("CREATE INDEX CONCURRENTLY"),
            sql.index("RESET STATEMENT_TIMEOUT;"),
        )
        for forbidden in ("IF NOT EXISTS", "BEGIN", "COMMIT"):
            with self.subTest(forbidden=forbidden):
                self.assertNotIn(forbidden, sql)

    def test_performance_migrations_cannot_mutate_evidence_or_change_math_schema(self):
        sql = _normalized(STATS_MIGRATION) + " " + _normalized(INDEX_MIGRATION)
        for statement in (
            "INSERT",
            "UPDATE",
            "DELETE",
            "TRUNCATE",
            "DROP",
            "CREATE TABLE",
            "ADD COLUMN",
            "ALTER COLUMN",
            "CREATE TRIGGER",
            "CREATE POLICY",
            "GRANT",
            "REVOKE",
        ):
            with self.subTest(statement=statement):
                self.assertIsNone(re.search(rf"\b{statement}\b", sql))


if __name__ == "__main__":
    unittest.main()
