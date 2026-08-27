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



def test_bounded_publication_reader_is_indexed_capped_and_read_only():
    sql = (
        ROOT / "migrations" /
        "017_bound_legacy_evidence_publication_reads.sql"
    ).read_text()
    assert "read_legacy_evidence_publications" in sql
    assert "read_legacy_evidence_publications_for_records" in sql
    assert "legacy_evidence_publications_kind_observed_id_idx" in sql
    assert "p.commit_observed_at<=p_as_of" in sql
    assert "LEAST(GREATEST(p_limit, 0), 65536)" in sql
    assert "window_truncated boolean" in sql
    assert "LIMIT COALESCE(LEAST(GREATEST(p_limit, 0), 65536), 0) + 1" in sql
    assert "cardinality(p_record_ids), 0) <= 65536" in sql
    assert "p.record_id=ANY" in sql
    assert "ROWS 65536" in sql
    assert "SECURITY DEFINER" in sql
    assert "SET search_path=pg_catalog" in sql
    assert "OWNER TO atom_v9_proof_owner" in sql
    assert "TO atom_v9_v4_runtime" in sql
    assert "INSERT INTO atom_v9_internal.legacy_evidence_publications" not in sql
    assert "UPDATE atom_v9_internal.legacy_evidence_publications" not in sql
    assert "DELETE FROM atom_v9_internal.legacy_evidence_publications" not in sql


def test_publication_cycle_lookup_has_one_targeted_read_index():
    sql = (
        ROOT / "migrations" /
        "018_index_legacy_evidence_publication_cycles.sql"
    ).read_text()
    normalized = " ".join(sql.split())
    assert "CREATE INDEX IF NOT EXISTS forecasts_cycle_id_forecast_id_idx" in normalized
    assert "ON public.forecasts (cycle_id, forecast_id)" in normalized
    assert "lock_timeout" in sql
    assert "INSERT INTO" not in sql
    assert "UPDATE " not in sql
    assert "DELETE FROM" not in sql
    assert "TRUNCATE " not in sql



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


def test_effective_observation_reader_is_sparse_exact_and_read_only():
    sql = (
        ROOT / "migrations" /
        "021_add_cohort_effective_observation_reader.sql"
    ).read_text()
    normalized = " ".join(sql.split())
    assert "read_legacy_effective_observations" in sql
    assert "WITH RECURSIVE requested AS MATERIALIZED" in sql
    assert "jsonb_array_length" in sql
    assert "> 256" in sql
    assert "LEAST(GREATEST(p_per_cohort_limit, 0), 64)" in sql
    assert "f.cutoff_epoch>=s.cutoff_epoch+s.horizon_seconds" in normalized
    assert "fp.commit_observed_at<to_timestamp(f.maturity_epoch)" in normalized
    assert "op.commit_observed_at<=p_as_of" in normalized
    assert "o.resolved_epoch<=f.maturity_epoch+5.0" in normalized
    assert "o.resolved_epoch<=extract(epoch FROM p_as_of)" in normalized
    assert "SECURITY DEFINER" in sql
    assert "SET search_path=pg_catalog" in sql
    assert "OWNER TO atom_v9_proof_owner" in sql
    assert "TO atom_v9_v4_runtime" in sql
    assert "CREATE INDEX IF NOT EXISTS forecasts_phase_e_cohort_cutoff_idx" in normalized
    assert "CREATE INDEX IF NOT EXISTS volatility_forecasts_phase_e_cohort_cutoff_idx" in normalized
    assert "INSERT INTO atom_v9_internal.legacy_evidence_publications" not in sql
    assert "UPDATE atom_v9_internal.legacy_evidence_publications" not in sql
    assert "DELETE FROM atom_v9_internal.legacy_evidence_publications" not in sql
