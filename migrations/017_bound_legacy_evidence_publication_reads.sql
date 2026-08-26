-- Bound legacy proof reads before joining multi-million-row evidence tables.
-- This migration creates no proof rows and mutates no evidence.
SET LOCAL lock_timeout = '2s';
SET LOCAL statement_timeout = '15s';

CREATE INDEX legacy_evidence_publications_kind_observed_id_idx
ON atom_v9_internal.legacy_evidence_publications (
    evidence_kind, commit_observed_at DESC, record_id DESC
);

-- Supabase's migration executor temporarily receives the controlled owner so
-- the SECURITY DEFINER function can be handed off exactly as in migrations 014-015.
GRANT atom_v9_proof_owner TO postgres;
GRANT CREATE ON SCHEMA atom_v9_internal TO atom_v9_proof_owner;

CREATE FUNCTION atom_v9_internal.read_legacy_evidence_publications(
    p_kind text, p_as_of timestamptz, p_limit integer
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
     WHERE p.evidence_kind=p_kind
       AND p.commit_observed_at<=p_as_of
       AND p.proof_method='POST_COMMIT_DB_OBSERVATION_V1'
     ORDER BY p.commit_observed_at DESC, p.record_id DESC
     LIMIT COALESCE(LEAST(GREATEST(p_limit, 0), 65536), 0)
$$;

ALTER FUNCTION atom_v9_internal.read_legacy_evidence_publications(
    text, timestamptz, integer
) OWNER TO atom_v9_proof_owner;

REVOKE ALL ON FUNCTION
    atom_v9_internal.read_legacy_evidence_publications(
        text, timestamptz, integer
    )
FROM PUBLIC, anon, authenticated, service_role;
GRANT EXECUTE ON FUNCTION
    atom_v9_internal.read_legacy_evidence_publications(
        text, timestamptz, integer
    )
TO atom_v9_v4_runtime;

REVOKE CREATE ON SCHEMA atom_v9_internal FROM atom_v9_proof_owner;
REVOKE atom_v9_proof_owner FROM postgres;
