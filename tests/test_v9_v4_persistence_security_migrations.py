import re
from pathlib import Path


ROOT = Path(__file__).parents[1]
V4A_SQL = (ROOT / "migrations/008_create_v9_v4a_evidence.sql").read_text()
V4B_SQL = (ROOT / "migrations/009_create_v9_v4_states.sql").read_text()
NORMALIZED_V4A = " ".join(V4A_SQL.split())
NORMALIZED_ALL = " ".join((V4A_SQL + "\n" + V4B_SQL).split())
V4_TABLES = (
    "atom_v9_v4_forecasts",
    "atom_v9_v4_outcomes",
    "atom_v9_v4_states",
)
LEGACY_TABLES = (
    "forecasts",
    "forecast_outcomes",
    "volatility_forecasts",
    "volatility_forecast_outcomes",
)


def test_runtime_role_creation_refuses_preexisting_role_and_has_fixed_attributes():
    assert "IF EXISTS (SELECT 1 FROM pg_catalog.pg_roles" in V4A_SQL
    assert "RAISE duplicate_object" in V4A_SQL
    assert V4A_SQL.index("RAISE duplicate_object") < V4A_SQL.index("CREATE ROLE")
    assert re.search(
        r"CREATE ROLE atom_v9_v4_runtime WITH\s+LOGIN NOINHERIT NOSUPERUSER "
        r"NOCREATEDB NOCREATEROLE NOREPLICATION NOBYPASSRLS;",
        V4A_SQL,
    )
    assert "ALTER ROLE" not in V4A_SQL
    assert "PASSWORD" not in V4A_SQL.upper()
    assert "GRANT USAGE ON SCHEMA public TO atom_v9_v4_runtime" in V4A_SQL


def test_v4_tables_have_rls_narrow_grants_and_role_specific_policies():
    for table in V4_TABLES:
        assert f"ALTER TABLE public.{table} ENABLE ROW LEVEL SECURITY" in NORMALIZED_ALL
        assert f"CREATE POLICY {table}_runtime_select ON public.{table} " \
               f"FOR SELECT TO atom_v9_v4_runtime USING (true)" in NORMALIZED_ALL
        assert f"CREATE POLICY {table}_runtime_insert ON public.{table} " \
               f"FOR INSERT TO atom_v9_v4_runtime WITH CHECK (true)" in NORMALIZED_ALL
    assert NORMALIZED_ALL.count("FROM PUBLIC, anon, authenticated, service_role, atom_v9_v4_runtime") == 5
    assert "GRANT UPDATE" not in NORMALIZED_ALL
    assert "GRANT DELETE" not in NORMALIZED_ALL
    assert "GRANT TRUNCATE" not in NORMALIZED_ALL


def test_legacy_tables_get_only_runtime_read_append_access_and_rls_policies():
    for table in LEGACY_TABLES:
        assert f"ALTER TABLE public.{table} ENABLE ROW LEVEL SECURITY" in NORMALIZED_V4A
        assert f"CREATE POLICY {table}_runtime_select ON public.{table} " \
               f"FOR SELECT TO atom_v9_v4_runtime USING (true)" in NORMALIZED_V4A
        assert f"CREATE POLICY {table}_runtime_insert ON public.{table} " \
               f"FOR INSERT TO atom_v9_v4_runtime WITH CHECK (true)" in NORMALIZED_V4A
    assert "GRANT USAGE, SELECT ON SEQUENCE public.forecasts_forecast_id_seq, " \
           "public.volatility_forecasts_forecast_id_seq TO atom_v9_v4_runtime" in NORMALIZED_V4A


def test_append_only_enforcement_uses_row_and_statement_triggers():
    for table in V4_TABLES:
        assert f"BEFORE UPDATE OR DELETE ON public.{table} FOR EACH ROW" in NORMALIZED_ALL
        assert f"BEFORE TRUNCATE ON public.{table} FOR EACH STATEMENT" in NORMALIZED_ALL
    function = re.search(
        r"CREATE FUNCTION public\.atom_v9_v4_reject_mutation\(\) RETURNS trigger(.*?)\$\$;",
        V4A_SQL,
        re.DOTALL,
    ).group(1)
    assert "SECURITY INVOKER" in function
    assert "SET search_path = pg_catalog" in function
    assert "SECURITY DEFINER" not in function
    assert "REVOKE ALL PRIVILEGES ON FUNCTION public.atom_v9_v4_reject_mutation() " \
           "FROM PUBLIC, anon, authenticated, service_role, atom_v9_v4_runtime" in NORMALIZED_V4A


def test_migrations_contain_no_evidence_data_mutation():
    for sql in (V4A_SQL, V4B_SQL):
        for operation in ("UPDATE", "DELETE FROM", "TRUNCATE TABLE", "INSERT INTO"):
            assert not re.search(rf"^\s*{operation}\b", sql, re.IGNORECASE | re.MULTILINE)
