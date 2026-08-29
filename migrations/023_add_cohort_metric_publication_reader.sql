-- Bound Phase E metric reads independently for every requested cohort.
-- This migration creates no proof rows and mutates no evidence.
SET LOCAL lock_timeout = '2s';
SET LOCAL statement_timeout = '90s';

GRANT atom_v9_proof_owner TO postgres;
GRANT CREATE ON SCHEMA atom_v9_internal TO atom_v9_proof_owner;

CREATE FUNCTION atom_v9_internal.read_legacy_evidence_publications_for_cohorts(
    p_kind text, p_as_of timestamptz, p_cohorts jsonb,
    p_per_cohort_limit integer DEFAULT 256
) RETURNS TABLE(
    evidence_kind text, record_id bigint, inserting_xid xid8,
    commit_observed_at timestamptz, proof_method text,
    window_truncated boolean
)
LANGUAGE plpgsql STABLE SECURITY DEFINER
SET search_path=pg_catalog
ROWS 65536
AS $$
DECLARE
    v_limit integer := COALESCE(
        LEAST(GREATEST(p_per_cohort_limit, 0), 256), 0
    );
BEGIN
    IF p_kind NOT IN ('DIRECTIONAL_FORECAST', 'VOLATILITY_FORECAST') THEN
        RAISE EXCEPTION 'unsupported forecast evidence kind %', p_kind
            USING ERRCODE='22023';
    END IF;
    IF jsonb_typeof(COALESCE(p_cohorts, '[]'::jsonb)) <> 'array'
       OR jsonb_array_length(COALESCE(p_cohorts, '[]'::jsonb)) > 256 THEN
        RAISE EXCEPTION 'cohorts must be an array with at most 256 entries'
            USING ERRCODE='22023';
    END IF;
    IF v_limit = 0 THEN
        RETURN;
    END IF;

    IF p_kind = 'DIRECTIONAL_FORECAST' THEN
        RETURN QUERY
        WITH requested AS MATERIALIZED (
            SELECT DISTINCT c.quant_id, c.formula_version, c.symbol, c.horizon
            FROM jsonb_to_recordset(COALESCE(p_cohorts, '[]'::jsonb))
                 AS c(quant_id text, formula_version text, symbol text, horizon text)
            WHERE c.horizon IN ('30S', '1M', '5M', '15M', '30M', '1H')
        ), ranked AS (
            SELECT p.evidence_kind, p.record_id, p.inserting_xid,
                   p.commit_observed_at, p.proof_method,
                   row_number() OVER (
                       PARTITION BY c.quant_id, c.formula_version,
                                    c.symbol, c.horizon
                       ORDER BY f.cutoff_epoch DESC, f.forecast_id DESC
                   ) AS ordinal,
                   count(*) OVER (
                       PARTITION BY c.quant_id, c.formula_version,
                                    c.symbol, c.horizon
                   ) > v_limit AS truncated
            FROM requested AS c
            CROSS JOIN LATERAL (
                SELECT f.forecast_id, f.cutoff_epoch
                FROM public.forecasts AS f
                WHERE f.quant_id=c.quant_id
                  AND f.formula_version=c.formula_version
                  AND f.symbol=c.symbol
                  AND f.horizon=c.horizon
                  AND f.created_epoch<=extract(epoch FROM p_as_of)
                ORDER BY f.cutoff_epoch DESC, f.forecast_id DESC
                LIMIT v_limit + 1
            ) AS f
            JOIN atom_v9_internal.legacy_evidence_publications AS p
              ON p.evidence_kind='DIRECTIONAL_FORECAST'
             AND p.record_id=f.forecast_id
             AND p.commit_observed_at<=p_as_of
             AND p.proof_method='POST_COMMIT_DB_OBSERVATION_V1'
        )
        SELECT r.evidence_kind, r.record_id, r.inserting_xid,
               r.commit_observed_at, r.proof_method, r.truncated
        FROM ranked AS r
        WHERE r.ordinal<=v_limit
        ORDER BY r.commit_observed_at DESC, r.record_id DESC;
    ELSE
        RETURN QUERY
        WITH requested AS MATERIALIZED (
            SELECT DISTINCT c.quant_id, c.formula_version, c.symbol, c.horizon
            FROM jsonb_to_recordset(COALESCE(p_cohorts, '[]'::jsonb))
                 AS c(quant_id text, formula_version text, symbol text, horizon text)
            WHERE c.horizon IN ('30S', '1M', '5M', '15M', '30M', '1H')
        ), ranked AS (
            SELECT p.evidence_kind, p.record_id, p.inserting_xid,
                   p.commit_observed_at, p.proof_method,
                   row_number() OVER (
                       PARTITION BY c.quant_id, c.formula_version,
                                    c.symbol, c.horizon
                       ORDER BY f.cutoff_epoch DESC, f.forecast_id DESC
                   ) AS ordinal,
                   count(*) OVER (
                       PARTITION BY c.quant_id, c.formula_version,
                                    c.symbol, c.horizon
                   ) > v_limit AS truncated
            FROM requested AS c
            CROSS JOIN LATERAL (
                SELECT f.forecast_id, f.cutoff_epoch
                FROM public.volatility_forecasts AS f
                WHERE f.quant_id=c.quant_id
                  AND f.formula_version=c.formula_version
                  AND f.symbol=c.symbol
                  AND f.horizon=c.horizon
                  AND f.created_epoch<=extract(epoch FROM p_as_of)
                ORDER BY f.cutoff_epoch DESC, f.forecast_id DESC
                LIMIT v_limit + 1
            ) AS f
            JOIN atom_v9_internal.legacy_evidence_publications AS p
              ON p.evidence_kind='VOLATILITY_FORECAST'
             AND p.record_id=f.forecast_id
             AND p.commit_observed_at<=p_as_of
             AND p.proof_method='POST_COMMIT_DB_OBSERVATION_V1'
        )
        SELECT r.evidence_kind, r.record_id, r.inserting_xid,
               r.commit_observed_at, r.proof_method, r.truncated
        FROM ranked AS r
        WHERE r.ordinal<=v_limit
        ORDER BY r.commit_observed_at DESC, r.record_id DESC;
    END IF;
END
$$;

ALTER FUNCTION atom_v9_internal.read_legacy_evidence_publications_for_cohorts(
    text, timestamptz, jsonb, integer
) OWNER TO atom_v9_proof_owner;

REVOKE ALL ON FUNCTION
    atom_v9_internal.read_legacy_evidence_publications_for_cohorts(
        text, timestamptz, jsonb, integer
    )
FROM PUBLIC, anon, authenticated, service_role;
GRANT EXECUTE ON FUNCTION
    atom_v9_internal.read_legacy_evidence_publications_for_cohorts(
        text, timestamptz, jsonb, integer
    )
TO atom_v9_v4_runtime;

REVOKE CREATE ON SCHEMA atom_v9_internal FROM atom_v9_proof_owner;
REVOKE atom_v9_proof_owner FROM postgres;
