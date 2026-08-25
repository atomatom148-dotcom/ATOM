from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
MIGRATION = ROOT / "migrations" / "015_add_legacy_evidence_publications.sql"


def test_legacy_publication_migration_is_post_commit_append_only_and_no_backfill():
    sql = MIGRATION.read_text()
    assert "POST_COMMIT_DB_OBSERVATION_V1" in sql
    assert "v_xid = pg_catalog.pg_current_xact_id()" in sql
    assert "v_xid <= v_not_before_xid" in sql
    assert "commit_observed_at" in sql
    assert "reject_commit_proof_mutation" in sql
    assert "UPDATE public.forecasts" not in sql
    assert "UPDATE public.forecast_outcomes" not in sql
    assert "track_commit_timestamp" not in sql
    assert "ALTER SYSTEM" not in sql
    assert "GRANT SELECT ON public.forecasts" in sql
    assert "forecasts_proof_owner_select" in sql
    assert "forecast_outcomes_proof_owner_select" in sql
    assert "volatility_forecasts_proof_owner_select" in sql
    assert "volatility_outcomes_proof_owner_select" in sql



def test_publication_proof_recorder_suppresses_only_unapplied_schema_errors():
    from quant.evidence import PostgresEvidenceStore

    class MissingProofSchema(Exception):
        sqlstate = "42883"

    store = object.__new__(PostgresEvidenceStore)
    store._database_url = "postgresql://unused"
    store._connect = lambda _url: (_ for _ in ()).throw(MissingProofSchema())
    store._record_publication_proofs(
        (), observation_epoch=1.0, resolution_symbol="COIN",
        volatility_forecasts=(), resolution_enabled=False,
    )

    store._connect = lambda _url: (_ for _ in ()).throw(
        RuntimeError("transient connection failure")
    )
    import pytest
    with pytest.raises(RuntimeError, match="transient connection failure"):
        store._record_publication_proofs(
            (), observation_epoch=1.0, resolution_symbol="COIN",
            volatility_forecasts=(), resolution_enabled=False,
        )
