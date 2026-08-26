-- Keep post-commit proof publication ahead of the shortest forecast horizon.
-- This migration creates no rows and mutates no evidence.
SET LOCAL lock_timeout = '2s';
SET LOCAL statement_timeout = '90s';

CREATE INDEX IF NOT EXISTS forecasts_cycle_id_forecast_id_idx
ON public.forecasts (cycle_id, forecast_id);
