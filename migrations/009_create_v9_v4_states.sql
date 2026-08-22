-- V4B compact mathematical states are append-only and separate from V4A evidence.
CREATE TABLE public.atom_v9_v4_states (
    state_id text PRIMARY KEY,
    state_hash text UNIQUE NOT NULL CHECK (state_hash ~ '^[0-9a-f]{64}$'),
    state_version text NOT NULL,
    model_version text NOT NULL,
    symbol text NOT NULL,
    cohort_id text NOT NULL,
    state_as_of timestamptz NOT NULL,
    evidence_first_cutoff timestamptz NULL,
    evidence_last_cutoff timestamptz NULL,
    state_json jsonb NOT NULL,
    created_at timestamptz NOT NULL
);

CREATE INDEX atom_v9_v4_states_compatible_idx
ON public.atom_v9_v4_states
    (state_version, model_version, symbol, cohort_id, state_as_of DESC);

CREATE TRIGGER atom_v9_v4_states_immutable BEFORE UPDATE OR DELETE OR TRUNCATE
ON public.atom_v9_v4_states FOR EACH STATEMENT
EXECUTE FUNCTION public.atom_v9_v4_reject_mutation();

REVOKE ALL PRIVILEGES ON TABLE public.atom_v9_v4_states FROM PUBLIC;
DO $$ BEGIN
    IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'atom_v9_v4_runtime') THEN
        REVOKE ALL PRIVILEGES ON TABLE public.atom_v9_v4_states FROM atom_v9_v4_runtime;
        GRANT SELECT, INSERT ON TABLE public.atom_v9_v4_states TO atom_v9_v4_runtime;
    END IF;
END $$;
