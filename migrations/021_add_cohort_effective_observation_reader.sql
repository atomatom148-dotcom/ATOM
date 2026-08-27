-- Read an exact, sparse non-overlapping sample for Phase E eligibility.
-- This migration creates no proof rows and mutates no evidence.
SET LOCAL lock_timeout = '2s';
SET LOCAL statement_timeout = '90s';

CREATE INDEX IF NOT EXISTS forecasts_phase_e_cohort_cutoff_idx
ON public.forecasts (
    quant_id, formula_version, symbol, horizon, cutoff_epoch, forecast_id
);
CREATE INDEX IF NOT EXISTS volatility_forecasts_phase_e_cohort_cutoff_idx
ON public.volatility_forecasts (
    quant_id, formula_version, symbol, horizon, cutoff_epoch, forecast_id
);

GRANT atom_v9_proof_owner TO postgres;
GRANT CREATE ON SCHEMA atom_v9_internal TO atom_v9_proof_owner;

CREATE FUNCTION atom_v9_internal.read_legacy_effective_observations(
    p_kind text, p_as_of timestamptz, p_cohorts jsonb,
    p_per_cohort_limit integer DEFAULT 64
) RETURNS TABLE(
    quant_id text, formula_version text, symbol text, horizon text,
    cutoff_epoch double precision, forecast_id bigint
)
LANGUAGE plpgsql STABLE SECURITY DEFINER
SET search_path=pg_catalog
ROWS 8192
AS $$
DECLARE
    v_limit integer := COALESCE(
        LEAST(GREATEST(p_per_cohort_limit, 0), 64), 0
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
        WITH RECURSIVE requested AS MATERIALIZED (
            SELECT DISTINCT c.quant_id, c.formula_version, c.symbol, c.horizon,
                   CASE c.horizon
                     WHEN '30S' THEN 30.0 WHEN '1M' THEN 60.0
                     WHEN '5M' THEN 300.0 WHEN '15M' THEN 900.0
                     WHEN '30M' THEN 1800.0 WHEN '1H' THEN 3600.0
                   END AS horizon_seconds
            FROM jsonb_to_recordset(COALESCE(p_cohorts, '[]'::jsonb))
                 AS c(quant_id text, formula_version text, symbol text, horizon text)
            WHERE c.horizon IN ('30S', '1M', '5M', '15M', '30M', '1H')
        ), selected AS (
            SELECT c.quant_id, c.formula_version, c.symbol, c.horizon,
                   c.horizon_seconds, n.cutoff_epoch, n.forecast_id, 1 AS ordinal
            FROM requested AS c
            CROSS JOIN LATERAL (
                SELECT f.cutoff_epoch, f.forecast_id
                FROM public.forecasts AS f
                JOIN atom_v9_internal.legacy_evidence_publications AS fp
                  ON fp.evidence_kind='DIRECTIONAL_FORECAST'
                 AND fp.record_id=f.forecast_id
                 AND fp.proof_method='POST_COMMIT_DB_OBSERVATION_V1'
                 AND fp.commit_observed_at<=p_as_of
                 AND fp.commit_observed_at<to_timestamp(f.maturity_epoch)
                JOIN atom_v9_internal.legacy_evidence_publications AS op
                  ON op.evidence_kind='DIRECTIONAL_OUTCOME'
                 AND op.record_id=f.forecast_id
                 AND op.proof_method='POST_COMMIT_DB_OBSERVATION_V1'
                 AND op.commit_observed_at<=p_as_of
                JOIN public.forecast_outcomes AS o
                  ON o.forecast_id=f.forecast_id
                 AND o.resolved_epoch>=f.maturity_epoch
                 AND o.resolved_epoch<=f.maturity_epoch+5.0
                 AND o.resolved_epoch<=extract(epoch FROM p_as_of)
                WHERE f.quant_id=c.quant_id
                  AND f.formula_version=c.formula_version
                  AND f.symbol=c.symbol
                  AND f.horizon=c.horizon
                  AND f.maturity_epoch<=extract(epoch FROM p_as_of)
                ORDER BY f.cutoff_epoch, f.forecast_id
                LIMIT 1
            ) AS n
          UNION ALL
            SELECT s.quant_id, s.formula_version, s.symbol, s.horizon,
                   s.horizon_seconds, n.cutoff_epoch, n.forecast_id,
                   s.ordinal+1
            FROM selected AS s
            CROSS JOIN LATERAL (
                SELECT f.cutoff_epoch, f.forecast_id
                FROM public.forecasts AS f
                JOIN atom_v9_internal.legacy_evidence_publications AS fp
                  ON fp.evidence_kind='DIRECTIONAL_FORECAST'
                 AND fp.record_id=f.forecast_id
                 AND fp.proof_method='POST_COMMIT_DB_OBSERVATION_V1'
                 AND fp.commit_observed_at<=p_as_of
                 AND fp.commit_observed_at<to_timestamp(f.maturity_epoch)
                JOIN atom_v9_internal.legacy_evidence_publications AS op
                  ON op.evidence_kind='DIRECTIONAL_OUTCOME'
                 AND op.record_id=f.forecast_id
                 AND op.proof_method='POST_COMMIT_DB_OBSERVATION_V1'
                 AND op.commit_observed_at<=p_as_of
                JOIN public.forecast_outcomes AS o
                  ON o.forecast_id=f.forecast_id
                 AND o.resolved_epoch>=f.maturity_epoch
                 AND o.resolved_epoch<=f.maturity_epoch+5.0
                 AND o.resolved_epoch<=extract(epoch FROM p_as_of)
                WHERE f.quant_id=s.quant_id
                  AND f.formula_version=s.formula_version
                  AND f.symbol=s.symbol
                  AND f.horizon=s.horizon
                  AND f.cutoff_epoch>=s.cutoff_epoch+s.horizon_seconds
                  AND f.maturity_epoch<=extract(epoch FROM p_as_of)
                ORDER BY f.cutoff_epoch, f.forecast_id
                LIMIT 1
            ) AS n
            WHERE s.ordinal<v_limit
        )
        SELECT s.quant_id, s.formula_version, s.symbol, s.horizon,
               s.cutoff_epoch, s.forecast_id
        FROM selected AS s
        ORDER BY s.quant_id, s.formula_version, s.symbol,
                 CASE s.horizon
                   WHEN '30S' THEN 1 WHEN '1M' THEN 2 WHEN '5M' THEN 3
                   WHEN '15M' THEN 4 WHEN '30M' THEN 5 WHEN '1H' THEN 6
                 END,
                 s.cutoff_epoch, s.forecast_id;
    ELSE
        RETURN QUERY
        WITH RECURSIVE requested AS MATERIALIZED (
            SELECT DISTINCT c.quant_id, c.formula_version, c.symbol, c.horizon,
                   CASE c.horizon
                     WHEN '30S' THEN 30.0 WHEN '1M' THEN 60.0
                     WHEN '5M' THEN 300.0 WHEN '15M' THEN 900.0
                     WHEN '30M' THEN 1800.0 WHEN '1H' THEN 3600.0
                   END AS horizon_seconds
            FROM jsonb_to_recordset(COALESCE(p_cohorts, '[]'::jsonb))
                 AS c(quant_id text, formula_version text, symbol text, horizon text)
            WHERE c.horizon IN ('30S', '1M', '5M', '15M', '30M', '1H')
        ), selected AS (
            SELECT c.quant_id, c.formula_version, c.symbol, c.horizon,
                   c.horizon_seconds, n.cutoff_epoch, n.forecast_id, 1 AS ordinal
            FROM requested AS c
            CROSS JOIN LATERAL (
                SELECT f.cutoff_epoch, f.forecast_id
                FROM public.volatility_forecasts AS f
                JOIN atom_v9_internal.legacy_evidence_publications AS fp
                  ON fp.evidence_kind='VOLATILITY_FORECAST'
                 AND fp.record_id=f.forecast_id
                 AND fp.proof_method='POST_COMMIT_DB_OBSERVATION_V1'
                 AND fp.commit_observed_at<=p_as_of
                 AND fp.commit_observed_at<to_timestamp(f.maturity_epoch)
                JOIN atom_v9_internal.legacy_evidence_publications AS op
                  ON op.evidence_kind='VOLATILITY_OUTCOME'
                 AND op.record_id=f.forecast_id
                 AND op.proof_method='POST_COMMIT_DB_OBSERVATION_V1'
                 AND op.commit_observed_at<=p_as_of
                JOIN public.volatility_forecast_outcomes AS o
                  ON o.forecast_id=f.forecast_id
                 AND o.resolved_epoch>=f.maturity_epoch
                 AND o.resolved_epoch<=f.maturity_epoch+5.0
                 AND o.resolved_epoch<=extract(epoch FROM p_as_of)
                WHERE f.quant_id=c.quant_id
                  AND f.formula_version=c.formula_version
                  AND f.symbol=c.symbol
                  AND f.horizon=c.horizon
                  AND f.maturity_epoch<=extract(epoch FROM p_as_of)
                ORDER BY f.cutoff_epoch, f.forecast_id
                LIMIT 1
            ) AS n
          UNION ALL
            SELECT s.quant_id, s.formula_version, s.symbol, s.horizon,
                   s.horizon_seconds, n.cutoff_epoch, n.forecast_id,
                   s.ordinal+1
            FROM selected AS s
            CROSS JOIN LATERAL (
                SELECT f.cutoff_epoch, f.forecast_id
                FROM public.volatility_forecasts AS f
                JOIN atom_v9_internal.legacy_evidence_publications AS fp
                  ON fp.evidence_kind='VOLATILITY_FORECAST'
                 AND fp.record_id=f.forecast_id
                 AND fp.proof_method='POST_COMMIT_DB_OBSERVATION_V1'
                 AND fp.commit_observed_at<=p_as_of
                 AND fp.commit_observed_at<to_timestamp(f.maturity_epoch)
                JOIN atom_v9_internal.legacy_evidence_publications AS op
                  ON op.evidence_kind='VOLATILITY_OUTCOME'
                 AND op.record_id=f.forecast_id
                 AND op.proof_method='POST_COMMIT_DB_OBSERVATION_V1'
                 AND op.commit_observed_at<=p_as_of
                JOIN public.volatility_forecast_outcomes AS o
                  ON o.forecast_id=f.forecast_id
                 AND o.resolved_epoch>=f.maturity_epoch
                 AND o.resolved_epoch<=f.maturity_epoch+5.0
                 AND o.resolved_epoch<=extract(epoch FROM p_as_of)
                WHERE f.quant_id=s.quant_id
                  AND f.formula_version=s.formula_version
                  AND f.symbol=s.symbol
                  AND f.horizon=s.horizon
                  AND f.cutoff_epoch>=s.cutoff_epoch+s.horizon_seconds
                  AND f.maturity_epoch<=extract(epoch FROM p_as_of)
                ORDER BY f.cutoff_epoch, f.forecast_id
                LIMIT 1
            ) AS n
            WHERE s.ordinal<v_limit
        )
        SELECT s.quant_id, s.formula_version, s.symbol, s.horizon,
               s.cutoff_epoch, s.forecast_id
        FROM selected AS s
        ORDER BY s.quant_id, s.formula_version, s.symbol,
                 CASE s.horizon
                   WHEN '30S' THEN 1 WHEN '1M' THEN 2 WHEN '5M' THEN 3
                   WHEN '15M' THEN 4 WHEN '30M' THEN 5 WHEN '1H' THEN 6
                 END,
                 s.cutoff_epoch, s.forecast_id;
    END IF;
END
$$;

ALTER FUNCTION atom_v9_internal.read_legacy_effective_observations(
    text, timestamptz, jsonb, integer
) OWNER TO atom_v9_proof_owner;

REVOKE ALL ON FUNCTION atom_v9_internal.read_legacy_effective_observations(
    text, timestamptz, jsonb, integer
) FROM PUBLIC, anon, authenticated, service_role;
GRANT EXECUTE ON FUNCTION atom_v9_internal.read_legacy_effective_observations(
    text, timestamptz, jsonb, integer
) TO atom_v9_v4_runtime;

REVOKE CREATE ON SCHEMA atom_v9_internal FROM atom_v9_proof_owner;
REVOKE atom_v9_proof_owner FROM postgres;
