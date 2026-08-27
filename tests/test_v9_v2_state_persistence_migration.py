"""Static contract checks for the append-only V2 state migration."""

from pathlib import Path
import re


ROOT = Path(__file__).resolve().parents[1]
MIGRATION = ROOT / "migrations/020_create_v9_v2_states.sql"
SQL = MIGRATION.read_text(encoding="utf-8")
NORMAL_SQL = " ".join(SQL.split())


def test_v2_state_table_has_strict_content_addressed_schema_and_restore_index():
    assert SQL.count("CREATE TABLE") == 1
    assert "CREATE TABLE public.atom_v9_v2_states" in SQL

    required_columns = (
        "state_id text PRIMARY KEY",
        "state_hash text UNIQUE NOT NULL",
        "state_schema_version text NOT NULL",
        "state_version text NOT NULL",
        "model_family text NOT NULL",
        "symbol text NOT NULL",
        "target_spec_id text NOT NULL",
        "target_data_schema_version text NOT NULL",
        "target_source_spec_version text NOT NULL",
        "state_as_of double precision NOT NULL",
        "top_level_status text NOT NULL",
        "creation_status text NOT NULL",
        "state_json jsonb NOT NULL",
        "created_at timestamptz NOT NULL DEFAULT CURRENT_TIMESTAMP",
    )
    for declaration in required_columns:
        assert declaration in SQL

    required_constraints = (
        "state_id ~ '^v9v2:[0-9a-f]{64}$'",
        "state_hash ~ '^[0-9a-f]{64}$'",
        "state_id = 'v9v2:' || state_hash",
        "state_schema_version = 'V9-V2D-STATE-3'",
        "state_version = 'V9-V2D-3'",
        "model_family = 'V9-V2'",
        "symbol = 'COIN'",
        "target_spec_id = 'COIN_MIDPOINT_LOG_RETURN_BPS_1'",
        "target_data_schema_version = 'atom-market-input-v1'",
        "target_source_spec_version = 'alpaca-market-data-v1'",
        "top_level_status IN ('MATURE', 'PROVISIONAL')",
        "creation_status = 'VALID'",
        "jsonb_typeof(state_json) = 'object'",
        "'NaN'::double precision",
        "'Infinity'::double precision",
        "'-Infinity'::double precision",
    )
    for constraint in required_constraints:
        assert constraint in NORMAL_SQL

    indexes = re.findall(
        r"CREATE\s+(UNIQUE\s+)?INDEX\s+(\w+)\s+ON\s+([^;]+);",
        SQL,
        re.IGNORECASE | re.DOTALL,
    )
    assert indexes == [(
        "",
        "atom_v9_v2_states_restore_idx",
        "public.atom_v9_v2_states\n    (state_schema_version, state_version, model_family, symbol,\n"
        "     target_spec_id, target_data_schema_version, target_source_spec_version,\n"
        "     state_as_of DESC, state_id DESC)",
    )]


def test_v2_state_runtime_access_is_forced_rls_and_select_insert_only():
    assert "CREATE ROLE" not in SQL
    role_check = re.search(
        r"IF NOT EXISTS \((.*?)\) THEN",
        SQL,
        re.DOTALL,
    )
    assert role_check is not None
    for predicate in (
        "rolname = 'atom_v9_v4_runtime'",
        "rolcanlogin",
        "NOT rolinherit",
        "NOT rolsuper",
        "NOT rolcreatedb",
        "NOT rolcreaterole",
        "NOT rolreplication",
        "NOT rolbypassrls",
        "FROM pg_catalog.pg_auth_members AS membership",
        "membership.member = pg_roles.oid",
    ):
        assert predicate in role_check.group(1)

    assert (
        "ALTER TABLE public.atom_v9_v2_states ENABLE ROW LEVEL SECURITY;"
        in NORMAL_SQL
    )
    assert (
        "ALTER TABLE public.atom_v9_v2_states FORCE ROW LEVEL SECURITY;"
        in NORMAL_SQL
    )
    assert (
        "REVOKE ALL PRIVILEGES ON TABLE public.atom_v9_v2_states FROM PUBLIC, "
        "anon, authenticated, service_role, atom_v9_sim_runtime, "
        "atom_v9_proof_owner, atom_v9_v4_runtime;"
        in NORMAL_SQL
    )

    grants = re.findall(r"\bGRANT\s+(.+?);", NORMAL_SQL, re.IGNORECASE)
    assert grants == [
        "SELECT, INSERT ON TABLE public.atom_v9_v2_states TO atom_v9_v4_runtime"
    ]
    assert "OWNER TO atom_v9_v4_runtime" not in NORMAL_SQL

    policies = re.findall(
        r"CREATE POLICY (\w+) ON public\.atom_v9_v2_states (.*?);",
        NORMAL_SQL,
    )
    assert policies == [
        (
            "atom_v9_v2_states_runtime_select",
            "FOR SELECT TO atom_v9_v4_runtime USING (true)",
        ),
        (
            "atom_v9_v2_states_runtime_insert",
            "FOR INSERT TO atom_v9_v4_runtime WITH CHECK (true)",
        ),
    ]

    for forbidden in ("UPDATE", "DELETE", "TRUNCATE", "REFERENCES", "TRIGGER"):
        assert not re.search(
            rf"GRANT\s+[^;]*\b{forbidden}\b",
            NORMAL_SQL,
            re.IGNORECASE,
        )


def test_v2_state_append_only_triggers_use_a_safe_unprivileged_function():
    function = re.search(
        r"CREATE FUNCTION public\.atom_v9_v2_reject_mutation\(\)\s*"
        r"RETURNS trigger(.*?)\$\$;",
        SQL,
        re.DOTALL,
    )
    assert function is not None
    body = function.group(1)
    assert "LANGUAGE plpgsql" in body
    assert "SECURITY INVOKER" in body
    assert "SET search_path = pg_catalog" in body
    assert "SECURITY DEFINER" not in body
    assert "RAISE EXCEPTION 'V2 states are append-only'" in body
    assert "ERRCODE = '55000'" in body

    assert (
        "CREATE TRIGGER atom_v9_v2_states_reject_update_delete BEFORE UPDATE OR "
        "DELETE ON public.atom_v9_v2_states FOR EACH ROW EXECUTE FUNCTION "
        "public.atom_v9_v2_reject_mutation();"
        in NORMAL_SQL
    )
    assert (
        "CREATE TRIGGER atom_v9_v2_states_reject_truncate BEFORE TRUNCATE ON "
        "public.atom_v9_v2_states FOR EACH STATEMENT EXECUTE FUNCTION "
        "public.atom_v9_v2_reject_mutation();"
        in NORMAL_SQL
    )
    assert (
        "REVOKE ALL PRIVILEGES ON FUNCTION public.atom_v9_v2_reject_mutation() "
        "FROM PUBLIC, anon, authenticated, service_role, atom_v9_sim_runtime, "
        "atom_v9_proof_owner, atom_v9_v4_runtime;"
        in NORMAL_SQL
    )


def test_v2_state_migration_has_bounded_ddl_and_no_data_backfill():
    assert "SET LOCAL lock_timeout = '2s';" in SQL
    assert "SET LOCAL statement_timeout = '15s';" in SQL
    for operation in ("UPDATE", "DELETE FROM", "TRUNCATE TABLE", "INSERT INTO"):
        assert not re.search(
            rf"^\s*{operation}\b",
            SQL,
            re.IGNORECASE | re.MULTILINE,
        )
    assert "ON CONFLICT" not in SQL.upper()
