-- Support deterministic, unlimited-history V2 keyset pagination without
-- repeatedly sorting or scanning the remaining forecast history.
--
-- CREATE INDEX CONCURRENTLY must run outside an explicit transaction.  It
-- keeps forecast/outcome ingestion available while these production indexes
-- are built.  Supabase CLI v2.109.0+ handles this statement outside its
-- migration pipeline; when applying in SQL Editor, do not add BEGIN/COMMIT.
-- These statements intentionally omit IF NOT EXISTS: an interrupted
-- concurrent build can leave an INVALID same-name index, which must fail a
-- retry visibly instead of being mistaken for a usable access path.

SET statement_timeout = '0';
SET lock_timeout = '5s';

CREATE INDEX CONCURRENTLY forecasts_v2_external_page_idx
ON public.forecasts (
    data_schema_version,
    source_spec_version,
    horizon,
    cutoff_epoch,
    forecast_id
);

CREATE INDEX CONCURRENTLY volatility_forecasts_v2_external_page_idx
ON public.volatility_forecasts (
    data_schema_version,
    source_spec_version,
    horizon,
    cutoff_epoch,
    forecast_id
);

RESET lock_timeout;
RESET statement_timeout;
