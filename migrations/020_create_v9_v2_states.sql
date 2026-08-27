-- Durable V2D states are content-addressed, append-only recovery evidence.
SET LOCAL lock_timeout = '2s';
SET LOCAL statement_timeout = '15s';

-- Reuse the existing production runtime without adopting an unsafe role.
DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1
        FROM pg_catalog.pg_roles
        WHERE rolname = 'atom_v9_v4_runtime'
          AND rolcanlogin
          AND NOT rolinherit
          AND NOT rolsuper
          AND NOT rolcreatedb
          AND NOT rolcreaterole
          AND NOT rolreplication
          AND NOT rolbypassrls
          AND NOT EXISTS (
              SELECT 1
              FROM pg_catalog.pg_auth_members AS membership
              WHERE membership.member = pg_roles.oid
          )
    ) THEN
        RAISE EXCEPTION
            'atom_v9_v4_runtime is missing or has unsafe attributes'
            USING ERRCODE = '55000';
    END IF;
END
$$;

CREATE TABLE public.atom_v9_v2_states (
    state_id text PRIMARY KEY
        CHECK (state_id ~ '^v9v2:[0-9a-f]{64}$'),
    state_hash text UNIQUE NOT NULL
        CHECK (state_hash ~ '^[0-9a-f]{64}$'),
    state_schema_version text NOT NULL
        CHECK (state_schema_version = 'V9-V2D-STATE-3'),
    state_version text NOT NULL
        CHECK (state_version = 'V9-V2D-3'),
    model_family text NOT NULL
        CHECK (model_family = 'V9-V2'),
    symbol text NOT NULL
        CHECK (symbol = 'COIN'),
    target_spec_id text NOT NULL
        CHECK (target_spec_id = 'COIN_MIDPOINT_LOG_RETURN_BPS_1'),
    target_data_schema_version text NOT NULL
        CHECK (target_data_schema_version = 'atom-market-input-v1'),
    target_source_spec_version text NOT NULL
        CHECK (target_source_spec_version = 'alpaca-market-data-v1'),
    state_as_of double precision NOT NULL
        CHECK (state_as_of NOT IN (
            'NaN'::double precision,
            'Infinity'::double precision,
            '-Infinity'::double precision
        )),
    top_level_status text NOT NULL
        CHECK (top_level_status IN ('MATURE', 'PROVISIONAL')),
    creation_status text NOT NULL
        CHECK (creation_status = 'VALID'),
    state_json jsonb NOT NULL
        CHECK (jsonb_typeof(state_json) = 'object'),
    created_at timestamptz NOT NULL DEFAULT CURRENT_TIMESTAMP,
    CHECK (state_id = 'v9v2:' || state_hash)
);

CREATE INDEX atom_v9_v2_states_restore_idx
ON public.atom_v9_v2_states
    (state_schema_version, state_version, model_family, symbol,
     target_spec_id, target_data_schema_version, target_source_spec_version,
     state_as_of DESC, state_id DESC);

CREATE FUNCTION public.atom_v9_v2_reject_mutation()
RETURNS trigger
LANGUAGE plpgsql
SECURITY INVOKER
SET search_path = pg_catalog
AS $$
BEGIN
    RAISE EXCEPTION 'V2 states are append-only'
        USING ERRCODE = '55000';
END
$$;

CREATE TRIGGER atom_v9_v2_states_reject_update_delete
BEFORE UPDATE OR DELETE ON public.atom_v9_v2_states
FOR EACH ROW EXECUTE FUNCTION public.atom_v9_v2_reject_mutation();
CREATE TRIGGER atom_v9_v2_states_reject_truncate
BEFORE TRUNCATE ON public.atom_v9_v2_states
FOR EACH STATEMENT EXECUTE FUNCTION public.atom_v9_v2_reject_mutation();

ALTER TABLE public.atom_v9_v2_states ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.atom_v9_v2_states FORCE ROW LEVEL SECURITY;

REVOKE ALL PRIVILEGES ON TABLE public.atom_v9_v2_states
FROM PUBLIC, anon, authenticated, service_role, atom_v9_sim_runtime,
    atom_v9_proof_owner, atom_v9_v4_runtime;
GRANT SELECT, INSERT ON TABLE public.atom_v9_v2_states
TO atom_v9_v4_runtime;

CREATE POLICY atom_v9_v2_states_runtime_select
ON public.atom_v9_v2_states
FOR SELECT TO atom_v9_v4_runtime USING (true);
CREATE POLICY atom_v9_v2_states_runtime_insert
ON public.atom_v9_v2_states
FOR INSERT TO atom_v9_v4_runtime WITH CHECK (true);

REVOKE ALL PRIVILEGES ON FUNCTION public.atom_v9_v2_reject_mutation()
FROM PUBLIC, anon, authenticated, service_role, atom_v9_sim_runtime,
    atom_v9_proof_owner, atom_v9_v4_runtime;
