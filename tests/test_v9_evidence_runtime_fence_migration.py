from pathlib import Path


SQL = (Path(__file__).parents[1] /
       "migrations/013_fence_evidence_runtime_writer.sql").read_text()


def test_runtime_fence_uses_the_exact_application_advisory_lock():
    assert "pg_try_advisory_lock(4707474704086680908::bigint)" in SQL
    assert "pg_try_advisory_xact_lock" not in SQL
    assert "l.pid = pg_catalog.pg_backend_pid()" in SQL
    assert "l.classid = 1096044365::oid" in SQL
    assert "l.objid = 1446593868::oid" in SQL
    assert "l.objsubid = 1" in SQL
    assert "ERRCODE = '55P03'" in SQL
    assert "SECURITY INVOKER" in SQL
    assert "SET search_path = pg_catalog" in SQL


def test_runtime_fence_bounds_ddl_waits_during_online_installation():
    assert "SET LOCAL lock_timeout = '2s'" in SQL
    assert "SET LOCAL statement_timeout = '15s'" in SQL


def test_every_official_evidence_insert_is_fenced_but_states_and_sim_are_not():
    tables = (
        "forecasts", "forecast_outcomes", "volatility_forecasts",
        "volatility_forecast_outcomes", "atom_v9_v4_forecasts",
        "atom_v9_v4_outcomes",
    )
    for table in tables:
        assert f"BEFORE INSERT ON public.{table}" in SQL
    assert "BEFORE INSERT ON public.atom_v9_v4_states" not in SQL
    assert "BEFORE INSERT ON public.atom_v9_sim_intents" not in SQL
    assert SQL.count("FOR EACH STATEMENT EXECUTE FUNCTION") == len(tables)


def test_runtime_fence_changes_no_historical_evidence_rows():
    upper = SQL.upper()
    assert " UPDATE " not in upper
    assert " DELETE " not in upper
    assert " TRUNCATE " not in upper
    assert "ALTER TABLE" not in upper
