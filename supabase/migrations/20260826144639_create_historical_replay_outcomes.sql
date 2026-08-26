-- H2-C: append-only outcomes shared by every family at a cutoff and horizon.
SET LOCAL lock_timeout = '2s';
SET LOCAL statement_timeout = '30s';

DO $$
BEGIN
  IF EXISTS (SELECT 1 FROM pg_catalog.pg_roles WHERE rolname IN
      ('atom_historical_outcome_resolver','atom_historical_score_reader')) THEN
    RAISE duplicate_object USING MESSAGE = 'H2-C role already exists; refusing to adopt it';
  END IF;
  CREATE ROLE atom_historical_outcome_resolver WITH LOGIN NOINHERIT NOSUPERUSER
    NOCREATEDB NOCREATEROLE NOREPLICATION NOBYPASSRLS;
  CREATE ROLE atom_historical_score_reader WITH LOGIN NOINHERIT NOSUPERUSER
    NOCREATEDB NOCREATEROLE NOREPLICATION NOBYPASSRLS;
END $$;
GRANT USAGE ON SCHEMA public TO atom_historical_outcome_resolver, atom_historical_score_reader;

CREATE TABLE public.atom_historical_replay_outcomes (
  replay_run_id text NOT NULL REFERENCES public.atom_historical_replay_runs(replay_run_id),
  cutoff_at timestamptz NOT NULL,
  horizon text NOT NULL CHECK (horizon IN ('30S','1M','5M','15M','30M','1H')),
  actual_return_bps double precision,
  availability_status text NOT NULL CHECK (availability_status IN ('AVAILABLE','UNAVAILABLE')),
  unavailable_reason text,
  cutoff_midpoint_at timestamptz,
  cutoff_midpoint double precision,
  target_midpoint_at timestamptz,
  target_midpoint double precision,
  data_schema_version text NOT NULL,
  source_schema_version text NOT NULL,
  content_sha256 text NOT NULL CHECK (content_sha256 ~ '^[0-9a-f]{64}$'),
  resolved_at timestamptz NOT NULL,
  PRIMARY KEY (replay_run_id, cutoff_at, horizon),
  CHECK ((availability_status = 'AVAILABLE' AND actual_return_bps IS NOT NULL
          AND unavailable_reason IS NULL AND cutoff_midpoint_at IS NOT NULL
          AND cutoff_midpoint > 0 AND target_midpoint_at IS NOT NULL
          AND target_midpoint > 0)
      OR (availability_status = 'UNAVAILABLE' AND actual_return_bps IS NULL
          AND unavailable_reason IS NOT NULL)),
  CHECK (actual_return_bps IS NULL OR actual_return_bps NOT IN
         ('Infinity'::float8, '-Infinity'::float8)),
  CHECK (cutoff_midpoint_at IS NULL OR cutoff_midpoint_at <= cutoff_at),
  CHECK (target_midpoint_at IS NULL OR target_midpoint_at >= cutoff_at + CASE horizon
    WHEN '30S' THEN interval '30 seconds' WHEN '1M' THEN interval '1 minute'
    WHEN '5M' THEN interval '5 minutes' WHEN '15M' THEN interval '15 minutes'
    WHEN '30M' THEN interval '30 minutes' WHEN '1H' THEN interval '1 hour' END),
  CHECK (target_midpoint_at IS NULL OR target_midpoint_at <= cutoff_at + CASE horizon
    WHEN '30S' THEN interval '35 seconds' WHEN '1M' THEN interval '65 seconds'
    WHEN '5M' THEN interval '305 seconds' WHEN '15M' THEN interval '905 seconds'
    WHEN '30M' THEN interval '1805 seconds' WHEN '1H' THEN interval '3605 seconds' END)
);

CREATE TRIGGER atom_historical_outcomes_reject_update_delete
BEFORE UPDATE OR DELETE ON public.atom_historical_replay_outcomes
FOR EACH ROW EXECUTE FUNCTION public.atom_historical_replay_reject_mutation();
CREATE TRIGGER atom_historical_outcomes_reject_truncate
BEFORE TRUNCATE ON public.atom_historical_replay_outcomes
FOR EACH STATEMENT EXECUTE FUNCTION public.atom_historical_replay_reject_mutation();
ALTER TABLE public.atom_historical_replay_outcomes ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.atom_historical_replay_outcomes FORCE ROW LEVEL SECURITY;

REVOKE ALL ON TABLE public.atom_historical_replay_outcomes FROM PUBLIC, anon,
  authenticated, service_role, atom_historical_replay_writer,
  atom_historical_outcome_resolver, atom_historical_score_reader;
REVOKE ALL ON TABLE public.atom_historical_replay_runs,
  public.atom_historical_replay_forecasts FROM atom_historical_outcome_resolver,
  atom_historical_score_reader;
GRANT SELECT ON TABLE public.atom_historical_replay_runs,
  public.atom_historical_replay_forecasts TO atom_historical_outcome_resolver,
  atom_historical_score_reader;
GRANT SELECT, INSERT ON TABLE public.atom_historical_replay_outcomes
  TO atom_historical_outcome_resolver;
GRANT SELECT ON TABLE public.atom_historical_replay_outcomes
  TO atom_historical_score_reader;

CREATE POLICY atom_historical_outcomes_resolver_select
ON public.atom_historical_replay_outcomes FOR SELECT
TO atom_historical_outcome_resolver USING (true);
CREATE POLICY atom_historical_outcomes_resolver_insert
ON public.atom_historical_replay_outcomes FOR INSERT
TO atom_historical_outcome_resolver WITH CHECK (true);
CREATE POLICY atom_historical_outcomes_score_select
ON public.atom_historical_replay_outcomes FOR SELECT
TO atom_historical_score_reader USING (true);
-- H2-A tables are forced-RLS, so explicit read policies are required as well.
CREATE POLICY atom_historical_runs_h2c_read ON public.atom_historical_replay_runs
FOR SELECT TO atom_historical_outcome_resolver, atom_historical_score_reader USING (true);
CREATE POLICY atom_historical_forecasts_h2c_read ON public.atom_historical_replay_forecasts
FOR SELECT TO atom_historical_outcome_resolver, atom_historical_score_reader USING (true);
