from pathlib import Path


ROOT = Path(__file__).parents[1]
MIGRATION = ROOT / "migrations" / "019_fix_forecast_commit_proof_conflict.sql"
SQL = " ".join(MIGRATION.read_text().upper().split())


def test_conflict_target_uses_the_proof_table_primary_key_constraint():
    assert (
        "ON CONFLICT ON CONSTRAINT FORECAST_COMMIT_PROOFS_PKEY DO NOTHING"
        in SQL
    )
    assert "ON CONFLICT (FORECAST_RECORD_ID) DO NOTHING" not in SQL


def test_replacement_preserves_the_security_contract():
    assert (
        "CREATE OR REPLACE FUNCTION "
        "ATOM_V9_INTERNAL.RECORD_FORECAST_COMMIT_PROOF(P_ID TEXT)" in SQL
    )
    assert "LANGUAGE PLPGSQL SECURITY DEFINER SET SEARCH_PATH = PG_CATALOG" in SQL
    assert SQL.count("GRANT ATOM_V9_PROOF_OWNER TO POSTGRES") == 1
    assert SQL.count("REVOKE ATOM_V9_PROOF_OWNER FROM POSTGRES") == 1


def test_replacement_does_not_backfill_or_mutate_evidence():
    assert "CREATE TABLE" not in SQL
    assert "ALTER TABLE" not in SQL
    assert "UPDATE PUBLIC.ATOM_V9_V4_FORECASTS" not in SQL
    assert "DELETE FROM PUBLIC.ATOM_V9_V4_FORECASTS" not in SQL
    assert "INSERT INTO PUBLIC.ATOM_V9_V4_FORECASTS" not in SQL
    assert "UPDATE PUBLIC.ATOM_V9_V4_OUTCOMES" not in SQL
    assert "DELETE FROM PUBLIC.ATOM_V9_V4_OUTCOMES" not in SQL
    assert "INSERT INTO PUBLIC.ATOM_V9_V4_OUTCOMES" not in SQL
