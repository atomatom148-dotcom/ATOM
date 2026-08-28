from pathlib import Path


SQL = Path(
    "migrations/023_index_v2_external_rebuild_pagination.sql"
).read_text(encoding="utf-8")
SQL_CODE = "\n".join(
    line for line in SQL.splitlines() if not line.lstrip().startswith("--")
)
NORMALIZED = " ".join(SQL_CODE.upper().split())


def test_external_rebuild_migration_adds_bounded_keyset_indexes():
    columns = (
        "DATA_SCHEMA_VERSION, SOURCE_SPEC_VERSION, HORIZON, "
        "CUTOFF_EPOCH, FORECAST_ID"
    )
    assert (
        "CREATE INDEX CONCURRENTLY "
        "FORECASTS_V2_EXTERNAL_PAGE_IDX ON PUBLIC.FORECASTS ( " + columns
    ) in NORMALIZED
    assert (
        "CREATE INDEX CONCURRENTLY "
        "VOLATILITY_FORECASTS_V2_EXTERNAL_PAGE_IDX "
        "ON PUBLIC.VOLATILITY_FORECASTS ( " + columns
    ) in NORMALIZED
    assert "BEGIN" not in NORMALIZED
    assert "COMMIT" not in NORMALIZED
    assert "IF NOT EXISTS" not in NORMALIZED
