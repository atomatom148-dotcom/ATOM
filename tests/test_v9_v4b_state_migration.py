from pathlib import Path


SQL = (Path(__file__).parents[1] / "migrations/009_create_v9_v4_states.sql").read_text()


def test_v4b_creates_exactly_one_append_only_state_table():
    assert SQL.count("CREATE TABLE") == 1
    assert "CREATE TABLE public.atom_v9_v4_states" in SQL
    assert "BEFORE UPDATE OR DELETE ON public.atom_v9_v4_states" in SQL
    assert "FOR EACH ROW" in SQL
    assert "BEFORE TRUNCATE ON public.atom_v9_v4_states" in SQL
    assert "FOR EACH STATEMENT" in SQL
    assert "GRANT SELECT, INSERT ON TABLE public.atom_v9_v4_states" in SQL
    assert "UPSERT" not in SQL and "ON CONFLICT" not in SQL


def test_v4b_state_schema_and_minimal_lookup_index():
    for field in ("state_id text PRIMARY KEY", "state_hash text UNIQUE NOT NULL",
                  "state_version text NOT NULL", "model_version text NOT NULL",
                  "symbol text NOT NULL", "cohort_id text NOT NULL",
                  "state_as_of timestamptz NOT NULL", "state_json jsonb NOT NULL",
                  "created_at timestamptz NOT NULL"):
        assert field in SQL
    assert SQL.count("CREATE INDEX") == 1
    assert "(state_version, model_version, symbol, cohort_id, state_as_of DESC)" in SQL
    assert SQL.count("ALTER TABLE") == 1
    assert "ALTER TABLE public.atom_v9_v4_states ENABLE ROW LEVEL SECURITY" in SQL
