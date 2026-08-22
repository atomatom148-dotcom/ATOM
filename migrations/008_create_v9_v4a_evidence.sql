-- V4A's only durable state: immutable forecast and outcome evidence.
CREATE TABLE public.atom_v9_v4_forecasts (
    forecast_record_id text PRIMARY KEY,
    forecast_record_hash text NOT NULL UNIQUE CHECK (forecast_record_hash ~ '^[0-9a-f]{64}$'),
    symbol text NOT NULL,
    cutoff_at timestamptz NOT NULL,
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
CREATE INDEX atom_v9_v4_outcomes_logical_key_idx
ON public.atom_v9_v4_outcomes (forecast_record_id, target_identity);

CREATE FUNCTION public.atom_v9_v4_reject_mutation() RETURNS trigger
LANGUAGE plpgsql AS $$ BEGIN RAISE EXCEPTION 'V4A evidence is append-only'; END $$;

CREATE TRIGGER atom_v9_v4_forecasts_immutable BEFORE UPDATE OR DELETE OR TRUNCATE
ON public.atom_v9_v4_forecasts FOR EACH STATEMENT EXECUTE FUNCTION public.atom_v9_v4_reject_mutation();
CREATE TRIGGER atom_v9_v4_outcomes_immutable BEFORE UPDATE OR DELETE OR TRUNCATE
ON public.atom_v9_v4_outcomes FOR EACH STATEMENT EXECUTE FUNCTION public.atom_v9_v4_reject_mutation();

REVOKE ALL PRIVILEGES ON TABLE public.atom_v9_v4_forecasts, public.atom_v9_v4_outcomes FROM PUBLIC;
REVOKE ALL PRIVILEGES ON FUNCTION public.atom_v9_v4_reject_mutation() FROM PUBLIC;
DO $$ BEGIN
    IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'atom_v9_v4_runtime') THEN
        REVOKE ALL PRIVILEGES ON TABLE public.atom_v9_v4_forecasts, public.atom_v9_v4_outcomes FROM atom_v9_v4_runtime;
        GRANT SELECT, INSERT ON TABLE public.atom_v9_v4_forecasts, public.atom_v9_v4_outcomes TO atom_v9_v4_runtime;
    END IF;
END $$;
