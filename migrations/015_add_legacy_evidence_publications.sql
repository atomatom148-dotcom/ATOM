-- POST_COMMIT_DB_OBSERVATION_V1 for legacy forecast/outcome availability.
-- Existing evidence is deliberately not backfilled and remains inadmissible.
SET LOCAL lock_timeout = '2s';
SET LOCAL statement_timeout = '15s';

CREATE TABLE atom_v9_internal.legacy_evidence_publications (
    evidence_kind text NOT NULL CHECK (evidence_kind IN (
        'DIRECTIONAL_FORECAST', 'DIRECTIONAL_OUTCOME',
        'VOLATILITY_FORECAST', 'VOLATILITY_OUTCOME'
    )),
    record_id bigint NOT NULL,
    inserting_xid xid8 NOT NULL,
    commit_observed_at timestamptz NOT NULL,
    proof_method text NOT NULL CHECK (
        proof_method = 'POST_COMMIT_DB_OBSERVATION_V1'
    ),
    PRIMARY KEY (evidence_kind, record_id)
);
REVOKE ALL ON atom_v9_internal.legacy_evidence_publications
FROM PUBLIC, anon, authenticated, service_role, atom_v9_v4_runtime;
GRANT SELECT, INSERT ON atom_v9_internal.legacy_evidence_publications
TO atom_v9_proof_owner;

CREATE TRIGGER legacy_evidence_publications_reject_update_delete
BEFORE UPDATE OR DELETE ON atom_v9_internal.legacy_evidence_publications
FOR EACH ROW EXECUTE FUNCTION atom_v9_internal.reject_commit_proof_mutation();
CREATE TRIGGER legacy_evidence_publications_reject_truncate
BEFORE TRUNCATE ON atom_v9_internal.legacy_evidence_publications
FOR EACH STATEMENT EXECUTE FUNCTION atom_v9_internal.reject_commit_proof_mutation();

-- Supabase-compatible ownership handoff for SECURITY DEFINER functions.
GRANT CREATE ON SCHEMA atom_v9_internal TO atom_v9_proof_owner;

CREATE FUNCTION atom_v9_internal.record_legacy_evidence_publication(
    p_kind text, p_id bigint
) RETURNS void
LANGUAGE plpgsql SECURITY DEFINER SET search_path=pg_catalog AS $$
DECLARE
    v_xid xid8;
    v_not_before_xid xid8;
    v_existing atom_v9_internal.legacy_evidence_publications%ROWTYPE;
BEGIN
    CASE p_kind
      WHEN 'DIRECTIONAL_FORECAST' THEN
        SELECT f.xmin::text::xid8 INTO STRICT v_xid
          FROM public.forecasts AS f WHERE f.forecast_id=p_id;
      WHEN 'DIRECTIONAL_OUTCOME' THEN
        SELECT o.xmin::text::xid8 INTO STRICT v_xid
          FROM public.forecast_outcomes AS o WHERE o.forecast_id=p_id;
      WHEN 'VOLATILITY_FORECAST' THEN
        SELECT f.xmin::text::xid8 INTO STRICT v_xid
          FROM public.volatility_forecasts AS f WHERE f.forecast_id=p_id;
      WHEN 'VOLATILITY_OUTCOME' THEN
        SELECT o.xmin::text::xid8 INTO STRICT v_xid
          FROM public.volatility_forecast_outcomes AS o WHERE o.forecast_id=p_id;
      ELSE
        RAISE EXCEPTION 'unsupported legacy evidence kind %', p_kind
            USING ERRCODE='22023';
    END CASE;

    IF v_xid = pg_catalog.pg_current_xact_id() THEN
        RAISE EXCEPTION 'legacy evidence must be observed from a later transaction'
            USING ERRCODE='25001';
    END IF;
    SELECT i.not_before_xid INTO STRICT v_not_before_xid
      FROM atom_v9_internal.commit_proof_installation AS i
     WHERE i.singleton;
    IF v_xid <= v_not_before_xid THEN
        RETURN;
    END IF;

    INSERT INTO atom_v9_internal.legacy_evidence_publications(
        evidence_kind, record_id, inserting_xid, commit_observed_at, proof_method
    ) VALUES (
        p_kind, p_id, v_xid, pg_catalog.clock_timestamp(),
        'POST_COMMIT_DB_OBSERVATION_V1'
    )
    ON CONFLICT (evidence_kind, record_id) DO NOTHING;

    SELECT * INTO STRICT v_existing
      FROM atom_v9_internal.legacy_evidence_publications AS p
     WHERE p.evidence_kind=p_kind AND p.record_id=p_id;
    IF v_existing.inserting_xid IS DISTINCT FROM v_xid
       OR v_existing.proof_method IS DISTINCT FROM
          'POST_COMMIT_DB_OBSERVATION_V1' THEN
        RAISE EXCEPTION 'existing legacy publication proof failed integrity check'
            USING ERRCODE='55000';
    END IF;
END
$$;

CREATE FUNCTION atom_v9_internal.read_legacy_evidence_publication(
    p_kind text, p_id bigint
) RETURNS TABLE(
    evidence_kind text, record_id bigint, inserting_xid xid8,
    commit_observed_at timestamptz, proof_method text
)
LANGUAGE sql STABLE SECURITY DEFINER SET search_path=pg_catalog AS $$
    SELECT p.evidence_kind, p.record_id, p.inserting_xid,
           p.commit_observed_at, p.proof_method
      FROM atom_v9_internal.legacy_evidence_publications AS p
     WHERE p.evidence_kind=p_kind AND p.record_id=p_id
       AND p.proof_method='POST_COMMIT_DB_OBSERVATION_V1'
$$;

ALTER FUNCTION atom_v9_internal.record_legacy_evidence_publication(text, bigint)
OWNER TO atom_v9_proof_owner;
ALTER FUNCTION atom_v9_internal.read_legacy_evidence_publication(text, bigint)
OWNER TO atom_v9_proof_owner;

REVOKE ALL ON FUNCTION
    atom_v9_internal.record_legacy_evidence_publication(text, bigint)
FROM PUBLIC, anon, authenticated, service_role;
REVOKE ALL ON FUNCTION
    atom_v9_internal.read_legacy_evidence_publication(text, bigint)
FROM PUBLIC, anon, authenticated, service_role;
GRANT EXECUTE ON FUNCTION
    atom_v9_internal.record_legacy_evidence_publication(text, bigint)
TO atom_v9_v4_runtime;
GRANT EXECUTE ON FUNCTION
    atom_v9_internal.read_legacy_evidence_publication(text, bigint)
TO atom_v9_v4_runtime;

REVOKE CREATE ON SCHEMA atom_v9_internal FROM atom_v9_proof_owner;
