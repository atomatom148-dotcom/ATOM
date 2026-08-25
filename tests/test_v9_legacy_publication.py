from pathlib import Path
from types import SimpleNamespace

from quant.evidence import records_for_results


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


def test_q5_q9_cannot_fall_back_to_cutoff_as_source_time():
    for quant_id in (
        "q5_microstructure", "q6_volume_liquidity", "q7_relative_value",
        "q8_cross_asset", "q9_factor",
    ):
        result = SimpleNamespace(
            quant_id=quant_id, formula_version="test-v1",
            forecast_bps=(1.0,) * 6,
        )
        assert records_for_results(
            results=(result,), cycle_id="COIN:100", symbol="COIN",
            cutoff_epoch=100.0, cutoff_midpoint=50.0, created_epoch=101.0,
        ) == ()
