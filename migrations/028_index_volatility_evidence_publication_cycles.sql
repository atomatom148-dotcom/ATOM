-- Keep post-commit volatility proof publication ahead of the shortest
-- forecast horizon as the append-only ledger grows.
-- This migration creates no rows and mutates no evidence.
SET LOCAL lock_timeout = '2s';
SET LOCAL statement_timeout = '90s';

CREATE INDEX IF NOT EXISTS volatility_forecasts_cycle_id_forecast_id_idx
ON public.volatility_forecasts (cycle_id, forecast_id);
