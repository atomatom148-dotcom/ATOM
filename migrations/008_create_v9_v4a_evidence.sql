-- V4A's only durable state: immutable forecast and outcome evidence.
DO $$
BEGIN
    IF EXISTS (SELECT 1 FROM pg_catalog.pg_roles WHERE rolname = 'atom_v9_v4_runtime') THEN
        RAISE duplicate_object USING
            MESSAGE = 'role "atom_v9_v4_runtime" already exists; refusing to adopt it';
    END IF;

    CREATE ROLE atom_v9_v4_runtime WITH
        LOGIN NOINHERIT NOSUPERUSER NOCREATEDB NOCREATEROLE NOREPLICATION NOBYPASSRLS;
END
$$;

GRANT USAGE ON SCHEMA public TO atom_v9_v4_runtime;

CREATE TABLE public.atom_v9_v4_forecasts (
    forecast_record_id text PRIMARY KEY,
    forecast_record_hash text NOT NULL UNIQUE CHECK (forecast_record_hash ~ '^[0-9a-f]{64}$'),
    symbol text NOT NULL,
    cutoff_at timestamptz NOT NULL,
    target_endpoint timestamptz NOT NULL,
    horizon text NOT NULL,
    cycle_id text NOT NULL,
    v3_model_version text NOT NULL,
    record_json jsonb NOT NULL,
    persisted_at timestamptz NOT NULL
);

CREATE TABLE public.atom_v9_v4_outcomes (
    outcome_record_id text PRIMARY KEY,
    outcome_record_hash text NOT NULL UNIQUE CHECK (outcome_record_hash ~ '^[0-9a-f]{64}$'),
    forecast_record_id text NOT NULL REFERENCES public.atom_v9_v4_forecasts(forecast_record_id),
    target_identity text NOT NULL,
    record_json jsonb NOT NULL,
    created_at timestamptz NOT NULL
);

CREATE INDEX atom_v9_v4_forecasts_logical_key_idx
ON public.atom_v9_v4_forecasts (symbol, cutoff_at, horizon, cycle_id, v3_model_version);
CREATE INDEX atom_v9_v4_forecasts_due_idx
ON public.atom_v9_v4_forecasts (target_endpoint, forecast_record_id);
CREATE INDEX atom_v9_v4_outcomes_logical_key_idx
ON public.atom_v9_v4_outcomes (forecast_record_id, target_identity);

CREATE FUNCTION public.atom_v9_v4_reject_mutation() RETURNS trigger
LANGUAGE plpgsql
SECURITY INVOKER
SET search_path = pg_catalog
AS $$
BEGIN
    RAISE EXCEPTION 'V4 evidence is append-only';
END
$$;

CREATE TRIGGER atom_v9_v4_forecasts_reject_update_delete
BEFORE UPDATE OR DELETE ON public.atom_v9_v4_forecasts
FOR EACH ROW EXECUTE FUNCTION public.atom_v9_v4_reject_mutation();
CREATE TRIGGER atom_v9_v4_forecasts_reject_truncate
BEFORE TRUNCATE ON public.atom_v9_v4_forecasts
FOR EACH STATEMENT EXECUTE FUNCTION public.atom_v9_v4_reject_mutation();
CREATE TRIGGER atom_v9_v4_outcomes_reject_update_delete
BEFORE UPDATE OR DELETE ON public.atom_v9_v4_outcomes
FOR EACH ROW EXECUTE FUNCTION public.atom_v9_v4_reject_mutation();
CREATE TRIGGER atom_v9_v4_outcomes_reject_truncate
BEFORE TRUNCATE ON public.atom_v9_v4_outcomes
FOR EACH STATEMENT EXECUTE FUNCTION public.atom_v9_v4_reject_mutation();

ALTER TABLE public.atom_v9_v4_forecasts ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.atom_v9_v4_outcomes ENABLE ROW LEVEL SECURITY;

REVOKE ALL PRIVILEGES ON TABLE public.atom_v9_v4_forecasts, public.atom_v9_v4_outcomes
FROM PUBLIC, anon, authenticated, service_role, atom_v9_v4_runtime;
GRANT SELECT, INSERT ON TABLE public.atom_v9_v4_forecasts, public.atom_v9_v4_outcomes
TO atom_v9_v4_runtime;

CREATE POLICY atom_v9_v4_forecasts_runtime_select ON public.atom_v9_v4_forecasts
FOR SELECT TO atom_v9_v4_runtime USING (true);
CREATE POLICY atom_v9_v4_forecasts_runtime_insert ON public.atom_v9_v4_forecasts
FOR INSERT TO atom_v9_v4_runtime WITH CHECK (true);
CREATE POLICY atom_v9_v4_outcomes_runtime_select ON public.atom_v9_v4_outcomes
FOR SELECT TO atom_v9_v4_runtime USING (true);
CREATE POLICY atom_v9_v4_outcomes_runtime_insert ON public.atom_v9_v4_outcomes
FOR INSERT TO atom_v9_v4_runtime WITH CHECK (true);

ALTER TABLE public.forecasts ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.forecast_outcomes ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.volatility_forecasts ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.volatility_forecast_outcomes ENABLE ROW LEVEL SECURITY;

REVOKE ALL PRIVILEGES ON TABLE public.forecasts, public.forecast_outcomes,
    public.volatility_forecasts, public.volatility_forecast_outcomes
FROM PUBLIC, anon, authenticated, service_role, atom_v9_v4_runtime;
GRANT SELECT, INSERT ON TABLE public.forecasts, public.forecast_outcomes,
    public.volatility_forecasts, public.volatility_forecast_outcomes
TO atom_v9_v4_runtime;

CREATE POLICY forecasts_runtime_select ON public.forecasts
FOR SELECT TO atom_v9_v4_runtime USING (true);
CREATE POLICY forecasts_runtime_insert ON public.forecasts
FOR INSERT TO atom_v9_v4_runtime WITH CHECK (true);
CREATE POLICY forecast_outcomes_runtime_select ON public.forecast_outcomes
FOR SELECT TO atom_v9_v4_runtime USING (true);
CREATE POLICY forecast_outcomes_runtime_insert ON public.forecast_outcomes
FOR INSERT TO atom_v9_v4_runtime WITH CHECK (true);
CREATE POLICY volatility_forecasts_runtime_select ON public.volatility_forecasts
FOR SELECT TO atom_v9_v4_runtime USING (true);
CREATE POLICY volatility_forecasts_runtime_insert ON public.volatility_forecasts
FOR INSERT TO atom_v9_v4_runtime WITH CHECK (true);
CREATE POLICY volatility_forecast_outcomes_runtime_select ON public.volatility_forecast_outcomes
FOR SELECT TO atom_v9_v4_runtime USING (true);
CREATE POLICY volatility_forecast_outcomes_runtime_insert ON public.volatility_forecast_outcomes
FOR INSERT TO atom_v9_v4_runtime WITH CHECK (true);

REVOKE ALL PRIVILEGES ON SEQUENCE public.forecasts_forecast_id_seq,
    public.volatility_forecasts_forecast_id_seq
FROM PUBLIC, anon, authenticated, service_role, atom_v9_v4_runtime;
GRANT USAGE, SELECT ON SEQUENCE public.forecasts_forecast_id_seq,
    public.volatility_forecasts_forecast_id_seq
TO atom_v9_v4_runtime;

REVOKE ALL PRIVILEGES ON FUNCTION public.atom_v9_v4_reject_mutation()
FROM PUBLIC, anon, authenticated, service_role, atom_v9_v4_runtime;
