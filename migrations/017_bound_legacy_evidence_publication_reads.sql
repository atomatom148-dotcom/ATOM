-- Bound legacy proof reads before joining multi-million-row evidence tables.
-- This migration creates no proof rows and mutates no evidence.
SET LOCAL lock_timeout = '2s';
SET LOCAL statement_timeout = '15s';

CREATE INDEX legacy_evidence_publications_kind_observed_id_idx
ON atom_v9_internal.legacy_evidence_publications (
    evidence_kind, commit_observed_at DESC, record_id DESC
);

-- Supabase's migration executor temporarily receives the controlled owner so
-- the SECURITY DEFINER functions can be handed off exactly as in migrations 014-015.
GRANT atom_v9_proof_owner TO postgres;
GRANT CREATE ON SCHEMA atom_v9_internal TO atom_v9_proof_owner;

CREATE FUNCTION atom_v9_internal.read_legacy_evidence_publications(
    p_kind text, p_as_of timestamptz, p_limit integer
) RETURNS TABLE(
    evidence_kind text, record_id bigint, inserting_xid xid8,
    commit_observed_at timestamptz, proof_method text,
    window_truncated boolean
)
LANGUAGE sql STABLE SECURITY DEFINER
SET search_path=pg_catalog
ROWS 65536
AS $$
    WITH bounded AS MATERIALIZED (
        SELECT p.evidence_kind, p.record_id, p.inserting_xid,
               p.commit_observed_at, p.proof_method
          FROM atom_v9_internal.legacy_evidence_publications AS p
         WHERE p.evidence_kind=p_kind
           AND p.commit_observed_at<=p_as_of
           AND p.proof_method='POST_COMMIT_DB_OBSERVATION_V1'
         ORDER BY p.commit_observed_at DESC, p.record_id DESC
         LIMIT COALESCE(LEAST(GREATEST(p_limit, 0), 65536), 0) + 1
    )
    SELECT b.evidence_kind, b.record_id, b.inserting_xid,
           b.commit_observed_at, b.proof_method,
           (SELECT count(*) > COALESCE(
                LEAST(GREATEST(p_limit, 0), 65536), 0
            ) FROM bounded) AS window_truncated
      FROM bounded AS b
     ORDER BY b.commit_observed_at DESC, b.record_id DESC
     LIMIT COALESCE(LEAST(GREATEST(p_limit, 0), 65536), 0)
$$;

-- Outcome proofs are selected only for the already-bounded forecast IDs.
-- This avoids both a per-forecast scan and an unrelated global outcome window.
CREATE FUNCTION atom_v9_internal.read_legacy_evidence_publications_for_records(
    p_kind text, p_as_of timestamptz, p_record_ids bigint[]
) RETURNS TABLE(
    evidence_kind text, record_id bigint, inserting_xid xid8,
    commit_observed_at timestamptz, proof_method text
)
LANGUAGE sql STABLE SECURITY DEFINER
SET search_path=pg_catalog
ROWS 65536
AS $$
    SELECT p.evidence_kind, p.record_id, p.inserting_xid,
           p.commit_observed_at, p.proof_method
      FROM atom_v9_internal.legacy_evidence_publications AS p
     WHERE COALESCE(pg_catalog.cardinality(p_record_ids), 0) <= 65536
       AND p.evidence_kind=p_kind
       AND p.commit_observed_at<=p_as_of
       AND p.proof_method='POST_COMMIT_DB_OBSERVATION_V1'
       AND p.record_id=ANY(COALESCE(p_record_ids, '{}'::bigint[]))
     ORDER BY p.record_id
$$;

ALTER FUNCTION atom_v9_internal.read_legacy_evidence_publications(
    text, timestamptz, integer
) OWNER TO atom_v9_proof_owner;
ALTER FUNCTION atom_v9_internal.read_legacy_evidence_publications_for_records(
    text, timestamptz, bigint[]
) OWNER TO atom_v9_proof_owner;

REVOKE ALL ON FUNCTION
    atom_v9_internal.read_legacy_evidence_publications(
        text, timestamptz, integer
    )
FROM PUBLIC, anon, authenticated, service_role;
REVOKE ALL ON FUNCTION
    atom_v9_internal.read_legacy_evidence_publications_for_records(
        text, timestamptz, bigint[]
    )
FROM PUBLIC, anon, authenticated, service_role;
GRANT EXECUTE ON FUNCTION
    atom_v9_internal.read_legacy_evidence_publications(
        text, timestamptz, integer
    )
TO atom_v9_v4_runtime;
GRANT EXECUTE ON FUNCTION
    atom_v9_internal.read_legacy_evidence_publications_for_records(
        text, timestamptz, bigint[]
    )
TO atom_v9_v4_runtime;

REVOKE CREATE ON SCHEMA atom_v9_internal FROM atom_v9_proof_owner;
REVOKE atom_v9_proof_owner FROM postgres;
