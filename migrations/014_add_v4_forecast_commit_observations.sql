-- POST_COMMIT_DB_OBSERVATION_V1 proves only that a forecast was committed
-- no later than a subsequent database-clock observation. It creates no proofs
-- for existing forecasts and mutates no existing evidence.
SET LOCAL lock_timeout = '2s';
SET LOCAL statement_timeout = '15s';

DO $$
BEGIN
    IF EXISTS (
        SELECT 1 FROM pg_catalog.pg_roles
        WHERE rolname = 'atom_v9_proof_owner'
    ) THEN
        RAISE duplicate_object USING MESSAGE =
            'role "atom_v9_proof_owner" already exists; refusing to adopt it';
    END IF;
    CREATE ROLE atom_v9_proof_owner WITH
        NOLOGIN NOINHERIT NOSUPERUSER NOCREATEDB NOCREATEROLE
        NOREPLICATION NOBYPASSRLS;
END
$$;

-- Supabase's migration executor must temporarily be able to transfer the
-- SECURITY DEFINER functions to the controlled NOLOGIN owner.
GRANT atom_v9_proof_owner TO postgres;

CREATE SCHEMA atom_v9_internal;
REVOKE ALL ON SCHEMA atom_v9_internal
FROM PUBLIC, anon, authenticated, service_role, atom_v9_v4_runtime;
GRANT USAGE ON SCHEMA atom_v9_internal
TO atom_v9_proof_owner, atom_v9_v4_runtime;

CREATE TABLE atom_v9_internal.forecast_commit_proofs (
    forecast_record_id text PRIMARY KEY
        REFERENCES public.atom_v9_v4_forecasts(forecast_record_id),
    forecast_record_hash text NOT NULL UNIQUE
        CHECK (forecast_record_hash ~ '^[0-9a-f]{64}$'),
    inserting_xid xid8 NOT NULL,
    commit_observed_at timestamptz NOT NULL,
    target_endpoint timestamptz NOT NULL,
    proof_eligible boolean GENERATED ALWAYS AS
        (commit_observed_at < target_endpoint) STORED,
    proof_method text NOT NULL CHECK
        (proof_method = 'POST_COMMIT_DB_OBSERVATION_V1')
);

-- This transaction fence permanently excludes every forecast predating the
-- proof facility. It is control state, not evidence.
CREATE TABLE atom_v9_internal.commit_proof_installation (
    singleton boolean PRIMARY KEY DEFAULT true CHECK (singleton),
    not_before_xid xid8 NOT NULL,
    installed_at timestamptz NOT NULL
);
INSERT INTO atom_v9_internal.commit_proof_installation (
    not_before_xid, installed_at
) VALUES (
    pg_catalog.pg_current_xact_id(), pg_catalog.clock_timestamp()
);

REVOKE ALL ON TABLE atom_v9_internal.forecast_commit_proofs
FROM PUBLIC, anon, authenticated, service_role, atom_v9_v4_runtime;
REVOKE ALL ON TABLE atom_v9_internal.commit_proof_installation
FROM PUBLIC, anon, authenticated, service_role, atom_v9_v4_runtime;
GRANT SELECT, INSERT ON atom_v9_internal.forecast_commit_proofs
TO atom_v9_proof_owner;
GRANT SELECT ON atom_v9_internal.commit_proof_installation
TO atom_v9_proof_owner;
GRANT SELECT ON public.atom_v9_v4_forecasts
TO atom_v9_proof_owner;

CREATE FUNCTION atom_v9_internal.reject_commit_proof_mutation()
RETURNS trigger
LANGUAGE plpgsql
SECURITY INVOKER
SET search_path = pg_catalog
AS $$
BEGIN
    RAISE EXCEPTION 'V4 forecast commit proofs are append-only'
        USING ERRCODE = '55000';
END
$$;

CREATE TRIGGER forecast_commit_proofs_reject_update_delete
BEFORE UPDATE OR DELETE
ON atom_v9_internal.forecast_commit_proofs
FOR EACH ROW
EXECUTE FUNCTION atom_v9_internal.reject_commit_proof_mutation();

CREATE TRIGGER forecast_commit_proofs_reject_truncate
BEFORE TRUNCATE
ON atom_v9_internal.forecast_commit_proofs
FOR EACH STATEMENT
EXECUTE FUNCTION atom_v9_internal.reject_commit_proof_mutation();

-- Supabase-compatible ownership handoff: the future NOLOGIN owner needs
-- temporary CREATE on its private schema while functions are transferred.
GRANT CREATE ON SCHEMA atom_v9_internal TO atom_v9_proof_owner;

CREATE FUNCTION atom_v9_internal.record_forecast_commit_proof(p_id text)
RETURNS TABLE (
    forecast_record_id text,
    forecast_record_hash text,
    commit_observed_at timestamptz,
    target_endpoint timestamptz,
    proof_eligible boolean,
    proof_method text
)
LANGUAGE plpgsql
SECURITY DEFINER
SET search_path = pg_catalog
AS $$
DECLARE
    v_hash text;
    v_endpoint timestamptz;
    v_xid xid8;
    v_observed timestamptz;
    v_not_before_xid xid8;
    v_existing atom_v9_internal.forecast_commit_proofs%ROWTYPE;
BEGIN
    SELECT
        f.forecast_record_hash,
        f.target_endpoint,
        f.xmin::text::xid8
      INTO STRICT v_hash, v_endpoint, v_xid
      FROM public.atom_v9_v4_forecasts AS f
     WHERE f.forecast_record_id = p_id;

    IF v_xid = pg_catalog.pg_current_xact_id() THEN
        RAISE EXCEPTION 'forecast must be observed from a later transaction'
            USING ERRCODE = '25001';
    END IF;

    SELECT i.not_before_xid
      INTO STRICT v_not_before_xid
      FROM atom_v9_internal.commit_proof_installation AS i
     WHERE i.singleton;

    IF v_xid <= v_not_before_xid THEN
        RAISE EXCEPTION 'pre-installation forecast cannot receive commit proof'
            USING ERRCODE = '55000';
    END IF;

    v_observed := pg_catalog.clock_timestamp();

    INSERT INTO atom_v9_internal.forecast_commit_proofs (
        forecast_record_id,
        forecast_record_hash,
        inserting_xid,
        commit_observed_at,
        target_endpoint,
        proof_method
    ) VALUES (
        p_id,
        v_hash,
        v_xid,
        v_observed,
        v_endpoint,
        'POST_COMMIT_DB_OBSERVATION_V1'
    )
    ON CONFLICT (forecast_record_id) DO NOTHING;

    SELECT *
      INTO STRICT v_existing
      FROM atom_v9_internal.forecast_commit_proofs AS p
     WHERE p.forecast_record_id = p_id;

    IF v_existing.forecast_record_hash IS DISTINCT FROM v_hash
       OR v_existing.inserting_xid IS DISTINCT FROM v_xid
       OR v_existing.target_endpoint IS DISTINCT FROM v_endpoint
       OR v_existing.proof_method IS DISTINCT FROM
          'POST_COMMIT_DB_OBSERVATION_V1' THEN
        RAISE EXCEPTION 'existing forecast proof failed integrity check'
            USING ERRCODE = '55000';
    END IF;

    RETURN QUERY
    SELECT
        v_existing.forecast_record_id,
        v_existing.forecast_record_hash,
        v_existing.commit_observed_at,
        v_existing.target_endpoint,
        v_existing.proof_eligible,
        v_existing.proof_method;
END
$$;

CREATE FUNCTION atom_v9_internal.read_forecast_commit_proof(p_id text)
RETURNS TABLE (
    forecast_record_id text,
    forecast_record_hash text,
    commit_observed_at timestamptz,
    target_endpoint timestamptz,
    proof_eligible boolean,
    proof_method text
)
LANGUAGE sql
STABLE
SECURITY DEFINER
SET search_path = pg_catalog
AS $$
    SELECT
        p.forecast_record_id,
        p.forecast_record_hash,
        p.commit_observed_at,
        p.target_endpoint,
        p.proof_eligible,
        p.proof_method
      FROM atom_v9_internal.forecast_commit_proofs AS p
      JOIN public.atom_v9_v4_forecasts AS f
        ON f.forecast_record_id = p.forecast_record_id
       AND f.forecast_record_hash = p.forecast_record_hash
       AND f.target_endpoint = p.target_endpoint
     WHERE p.forecast_record_id = p_id
       AND p.proof_method = 'POST_COMMIT_DB_OBSERVATION_V1'
$$;

REVOKE ALL
ON FUNCTION atom_v9_internal.reject_commit_proof_mutation()
FROM PUBLIC, anon, authenticated, service_role, atom_v9_v4_runtime;
REVOKE ALL
ON FUNCTION atom_v9_internal.record_forecast_commit_proof(text)
FROM PUBLIC, anon, authenticated, service_role;
REVOKE ALL
ON FUNCTION atom_v9_internal.read_forecast_commit_proof(text)
FROM PUBLIC, anon, authenticated, service_role;

GRANT EXECUTE
ON FUNCTION atom_v9_internal.record_forecast_commit_proof(text)
TO atom_v9_v4_runtime;
GRANT EXECUTE
ON FUNCTION atom_v9_internal.read_forecast_commit_proof(text)
TO atom_v9_v4_runtime;

ALTER FUNCTION atom_v9_internal.record_forecast_commit_proof(text)
OWNER TO atom_v9_proof_owner;
ALTER FUNCTION atom_v9_internal.read_forecast_commit_proof(text)
OWNER TO atom_v9_proof_owner;

REVOKE CREATE ON SCHEMA atom_v9_internal FROM atom_v9_proof_owner;
REVOKE atom_v9_proof_owner FROM postgres;
