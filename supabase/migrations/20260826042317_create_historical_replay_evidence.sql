-- H2-A: append-only historical replay evidence, isolated from live evidence.
SET LOCAL lock_timeout = '2s';
SET LOCAL statement_timeout = '30s';

DO $$
BEGIN
    IF EXISTS (SELECT 1 FROM pg_catalog.pg_roles
               WHERE rolname = 'atom_historical_replay_writer') THEN
        RAISE duplicate_object USING MESSAGE =
            'role "atom_historical_replay_writer" already exists; refusing to adopt it';
    END IF;
    CREATE ROLE atom_historical_replay_writer WITH
        LOGIN NOINHERIT NOSUPERUSER NOCREATEDB NOCREATEROLE
        NOREPLICATION NOBYPASSRLS;
END
$$;

GRANT USAGE ON SCHEMA public TO atom_historical_replay_writer;

CREATE TABLE public.atom_historical_replay_runs (
    replay_run_id text PRIMARY KEY CHECK (length(replay_run_id) BETWEEN 1 AND 128),
    historical_session date NOT NULL,
    execution_stage text NOT NULL CHECK (execution_stage = 'REPLAY_COMPLETE'),
    certification_status text NOT NULL CHECK (certification_status = 'CERTIFIED'),
    git_commit text NOT NULL CHECK (git_commit ~ '^[0-9a-f]{7,64}$'),
    configuration_digest text NOT NULL CHECK (configuration_digest ~ '^[0-9a-f]{64}$'),
    dataset_digest text NOT NULL CHECK (dataset_digest ~ '^[0-9a-f]{64}$'),
    session_digest text NOT NULL CHECK (session_digest ~ '^[0-9a-f]{64}$'),
    artifact_sha256 text NOT NULL CHECK (artifact_sha256 ~ '^[0-9a-f]{64}$'),
    frame_count bigint NOT NULL CHECK (frame_count > 0),
    quote_counts jsonb NOT NULL CHECK (jsonb_typeof(quote_counts) = 'object'),
    available_observation_count bigint NOT NULL CHECK (available_observation_count >= 0),
    unavailable_observation_count bigint NOT NULL CHECK (unavailable_observation_count >= 0),
    stage_timings jsonb NOT NULL CHECK (jsonb_typeof(stage_timings) = 'object'),
    family_timings jsonb NOT NULL CHECK (jsonb_typeof(family_timings) = 'object'),
    data_schema_version text NOT NULL,
    source_schema_version text NOT NULL,
    created_at timestamptz NOT NULL,
    content_sha256 text NOT NULL CHECK (content_sha256 ~ '^[0-9a-f]{64}$'),
    CHECK (available_observation_count + unavailable_observation_count = frame_count * 72)
);

CREATE TABLE public.atom_historical_replay_forecasts (
    replay_run_id text NOT NULL REFERENCES public.atom_historical_replay_runs(replay_run_id),
    cutoff_at timestamptz NOT NULL,
    quant_id text NOT NULL CHECK (quant_id IN (
        'q1_momentum','q2_mean_reversion','q3_volatility','q4_stat_arb',
        'q5_microstructure','q6_volume_liquidity','q7_relative_value',
        'q8_cross_asset','q9_factor','q10_options_vol','q11_regime',
        'q12_event_session'
    )),
    horizon text NOT NULL CHECK (horizon IN ('30S','1M','5M','15M','30M','1H')),
    expected_return_bps double precision,
    availability_status text NOT NULL CHECK (availability_status IN ('AVAILABLE','UNAVAILABLE')),
    unavailable_reason text,
    formula_version text NOT NULL,
    numerical_type text NOT NULL CHECK (numerical_type IN ('DIRECTIONAL_BPS','MAGNITUDE_BPS')),
    source_as_of timestamptz NOT NULL,
    available_at timestamptz NOT NULL,
    data_schema_version text NOT NULL,
    source_schema_version text NOT NULL,
    content_sha256 text NOT NULL CHECK (content_sha256 ~ '^[0-9a-f]{64}$'),
    PRIMARY KEY (replay_run_id, cutoff_at, quant_id, horizon),
    CHECK ((availability_status = 'AVAILABLE' AND expected_return_bps IS NOT NULL
            AND unavailable_reason IS NULL)
        OR (availability_status = 'UNAVAILABLE' AND expected_return_bps IS NULL
            AND unavailable_reason IS NOT NULL)),
    CHECK (expected_return_bps IS NULL OR expected_return_bps NOT IN ('Infinity'::float8, '-Infinity'::float8)),
    CHECK (source_as_of <= cutoff_at AND available_at <= cutoff_at)
);

CREATE FUNCTION public.atom_historical_replay_reject_mutation()
RETURNS trigger LANGUAGE plpgsql SECURITY INVOKER SET search_path = pg_catalog AS $$
BEGIN
    RAISE EXCEPTION 'historical replay evidence is append-only' USING ERRCODE = '55000';
END
$$;

CREATE TRIGGER atom_historical_replay_runs_reject_update_delete
BEFORE UPDATE OR DELETE ON public.atom_historical_replay_runs
FOR EACH ROW EXECUTE FUNCTION public.atom_historical_replay_reject_mutation();
CREATE TRIGGER atom_historical_replay_runs_reject_truncate
BEFORE TRUNCATE ON public.atom_historical_replay_runs
FOR EACH STATEMENT EXECUTE FUNCTION public.atom_historical_replay_reject_mutation();
CREATE TRIGGER atom_historical_replay_forecasts_reject_update_delete
BEFORE UPDATE OR DELETE ON public.atom_historical_replay_forecasts
FOR EACH ROW EXECUTE FUNCTION public.atom_historical_replay_reject_mutation();
CREATE TRIGGER atom_historical_replay_forecasts_reject_truncate
BEFORE TRUNCATE ON public.atom_historical_replay_forecasts
FOR EACH STATEMENT EXECUTE FUNCTION public.atom_historical_replay_reject_mutation();

ALTER TABLE public.atom_historical_replay_runs ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.atom_historical_replay_runs FORCE ROW LEVEL SECURITY;
ALTER TABLE public.atom_historical_replay_forecasts ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.atom_historical_replay_forecasts FORCE ROW LEVEL SECURITY;

REVOKE ALL ON TABLE public.atom_historical_replay_runs,
    public.atom_historical_replay_forecasts
FROM PUBLIC, anon, authenticated, service_role, atom_historical_replay_writer;
GRANT SELECT, INSERT ON TABLE public.atom_historical_replay_runs,
    public.atom_historical_replay_forecasts TO atom_historical_replay_writer;

CREATE POLICY atom_historical_replay_runs_writer_select
ON public.atom_historical_replay_runs FOR SELECT
TO atom_historical_replay_writer USING (true);
CREATE POLICY atom_historical_replay_runs_writer_insert
ON public.atom_historical_replay_runs FOR INSERT
TO atom_historical_replay_writer WITH CHECK (
    execution_stage = 'REPLAY_COMPLETE' AND certification_status = 'CERTIFIED'
);
CREATE POLICY atom_historical_replay_forecasts_writer_select
ON public.atom_historical_replay_forecasts FOR SELECT
TO atom_historical_replay_writer USING (true);
CREATE POLICY atom_historical_replay_forecasts_writer_insert
ON public.atom_historical_replay_forecasts FOR INSERT
TO atom_historical_replay_writer WITH CHECK (true);

REVOKE ALL ON FUNCTION public.atom_historical_replay_reject_mutation()
FROM PUBLIC, anon, authenticated, service_role, atom_historical_replay_writer;
