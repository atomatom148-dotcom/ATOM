-- SIM-2's isolated, immutable paper-simulation intent evidence.
DO $$
BEGIN
    IF EXISTS (SELECT 1 FROM pg_catalog.pg_roles WHERE rolname = 'atom_v9_sim_runtime') THEN
        RAISE duplicate_object USING
            MESSAGE = 'role "atom_v9_sim_runtime" already exists; refusing to adopt it';
    END IF;

    CREATE ROLE atom_v9_sim_runtime WITH
        LOGIN NOINHERIT NOSUPERUSER NOCREATEDB NOCREATEROLE NOREPLICATION NOBYPASSRLS;
END
$$;

GRANT USAGE ON SCHEMA public TO atom_v9_sim_runtime;

CREATE TABLE public.atom_v9_sim_intents (
    intent_id text PRIMARY KEY CHECK (intent_id ~ '^v9simintent:[0-9a-f]{64}$'),
    intent_hash text UNIQUE NOT NULL CHECK (intent_hash ~ '^[0-9a-f]{64}$'),
    contract_version text NOT NULL CHECK (contract_version = 'ATOM_TRUE_V9_SIM1_INTENT_1'),
    canonicalization_version text NOT NULL CHECK (canonicalization_version = 'ATOM_TRUE_V9_SIM_CANONICAL_V4A_1'),
    simulator_version text NOT NULL CHECK (simulator_version = 'ATOM_TRUE_V9_SIM_1'),
    symbol text NOT NULL CHECK (symbol = 'COIN'),
    horizon text NOT NULL,
    horizon_seconds integer NOT NULL,
    cutoff_at timestamptz NOT NULL,
    eligible_at timestamptz NOT NULL,
    source_v3_status text NOT NULL CHECK (source_v3_status IN ('AVAILABLE', 'PROVISIONAL', 'UNAVAILABLE')),
    decision text NOT NULL CHECK (decision IN ('LONG', 'SHORT', 'NO_TRADE')),
    status text NOT NULL CHECK (status IN ('ACTIONABLE', 'NO_TRADE', 'UNAVAILABLE')),
    record_json jsonb NOT NULL CHECK (jsonb_typeof(record_json) = 'object'),
    created_at timestamptz NOT NULL DEFAULT CURRENT_TIMESTAMP,
    CHECK ((horizon, horizon_seconds) IN
        (('30S', 30), ('1M', 60), ('5M', 300), ('15M', 900),
         ('30M', 1800), ('1H', 3600))),
    CHECK (eligible_at >= cutoff_at)
);

CREATE INDEX atom_v9_sim_intents_lookup_idx
ON public.atom_v9_sim_intents (symbol, horizon, eligible_at, intent_id);

CREATE FUNCTION public.atom_v9_sim_reject_mutation() RETURNS trigger
LANGUAGE plpgsql
SECURITY INVOKER
SET search_path = pg_catalog
AS $$
BEGIN
    RAISE EXCEPTION 'SIM evidence is append-only';
END
$$;

CREATE TRIGGER atom_v9_sim_intents_reject_update_delete
BEFORE UPDATE OR DELETE ON public.atom_v9_sim_intents
FOR EACH ROW EXECUTE FUNCTION public.atom_v9_sim_reject_mutation();
CREATE TRIGGER atom_v9_sim_intents_reject_truncate
BEFORE TRUNCATE ON public.atom_v9_sim_intents
FOR EACH STATEMENT EXECUTE FUNCTION public.atom_v9_sim_reject_mutation();

ALTER TABLE public.atom_v9_sim_intents ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.atom_v9_sim_intents FORCE ROW LEVEL SECURITY;

REVOKE ALL PRIVILEGES ON TABLE public.atom_v9_sim_intents
FROM PUBLIC, anon, authenticated, service_role, atom_v9_v4_runtime, atom_v9_sim_runtime;
GRANT SELECT, INSERT ON TABLE public.atom_v9_sim_intents TO atom_v9_sim_runtime;

CREATE POLICY atom_v9_sim_intents_runtime_select ON public.atom_v9_sim_intents
FOR SELECT TO atom_v9_sim_runtime USING (true);
CREATE POLICY atom_v9_sim_intents_runtime_insert ON public.atom_v9_sim_intents
FOR INSERT TO atom_v9_sim_runtime WITH CHECK (true);

REVOKE ALL PRIVILEGES ON TABLE public.atom_v9_v4_forecasts,
    public.atom_v9_v4_outcomes, public.atom_v9_v4_states, public.forecasts,
    public.forecast_outcomes, public.volatility_forecasts,
    public.volatility_forecast_outcomes
FROM atom_v9_sim_runtime;

REVOKE ALL PRIVILEGES ON FUNCTION public.atom_v9_sim_reject_mutation()
FROM PUBLIC, anon, authenticated, service_role, atom_v9_v4_runtime, atom_v9_sim_runtime;
