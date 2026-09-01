from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def test_volatility_publication_cycle_lookup_has_targeted_read_index():
    sql = (
        ROOT
        / "migrations"
        / "028_index_volatility_evidence_publication_cycles.sql"
    ).read_text()
    normalized = " ".join(sql.split())

    assert (
        "CREATE INDEX IF NOT EXISTS "
        "volatility_forecasts_cycle_id_forecast_id_idx"
    ) in normalized
    assert (
        "ON public.volatility_forecasts (cycle_id, forecast_id)"
    ) in normalized
    assert "lock_timeout" in sql
    assert "statement_timeout" in sql
    assert "INSERT INTO" not in sql
    assert "UPDATE " not in sql
    assert "DELETE FROM" not in sql
    assert "TRUNCATE " not in sql
