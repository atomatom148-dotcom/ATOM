-- Fix the proof writer's ambiguous conflict target.  The RETURNS TABLE output
-- parameter is also named forecast_record_id, so PostgreSQL cannot resolve the
-- unqualified ON CONFLICT (forecast_record_id) expression in PL/pgSQL.
--
-- This replaces only the writer function.  It neither backfills proofs nor
-- mutates any forecast or outcome evidence.
SET LOCAL lock_timeout = '2s';
SET LOCAL statement_timeout = '15s';

-- The function is owned by this NOLOGIN role.  Supabase migrations execute as
-- postgres, so membership is granted only for this transaction and revoked
-- immediately after the replacement.
GRANT atom_v9_proof_owner TO postgres;

CREATE OR REPLACE FUNCTION atom_v9_internal.record_forecast_commit_proof(p_id text)
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
    ON CONFLICT ON CONSTRAINT forecast_commit_proofs_pkey DO NOTHING;

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

REVOKE atom_v9_proof_owner FROM postgres;
