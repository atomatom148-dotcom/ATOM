from pathlib import Path
import re


SQL = (Path(__file__).parents[1] /
       "migrations/012_index_v4_outcome_recovery.sql").read_text()


def test_recovery_migration_only_adds_the_commit_order_index():
    assert re.search(
        r"CREATE\s+INDEX\s+IF\s+NOT\s+EXISTS\s+"
        r"atom_v9_v4_outcomes_recovery_idx",
        SQL, re.IGNORECASE,
    )
    assert re.search(
        r"ON\s+public\.atom_v9_v4_outcomes\s*"
        r"\(created_at\s+DESC,\s*outcome_record_id\s+DESC\)",
        SQL, re.IGNORECASE,
    )
    assert not re.search(r"\b(UPDATE|DELETE|TRUNCATE|INSERT)\b", SQL,
                         re.IGNORECASE)
    assert "CONCURRENTLY" not in SQL.upper()
