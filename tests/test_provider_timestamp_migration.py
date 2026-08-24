import re
from pathlib import Path


SQL = (Path(__file__).parents[1] / "migrations" /
       "011_add_forecast_source_as_of.sql").read_text()


def test_migration_adds_nullable_causal_provider_timestamp_only():
    assert re.search(
        r"(?is)ALTER\s+TABLE\s+public\.forecasts\s+ADD\s+COLUMN\s+IF\s+NOT\s+EXISTS"
        r"\s+source_as_of_epoch\s+double\s+precision",
        SQL,
    )
    assert "source_as_of_epoch <= cutoff_epoch" in SQL
    assert "source_as_of_epoch IS NULL" in SQL
    assert not re.search(r"(?i)source_as_of_epoch\s+double\s+precision\s+NOT\s+NULL", SQL)


def test_migration_never_rewrites_existing_evidence():
    for forbidden in ("UPDATE", "DELETE", "INSERT", "TRUNCATE"):
        assert not re.search(rf"(?i)\b{forbidden}\b", SQL)
