-- Bound live resolution to forecasts matured since the last successful cycle.
CREATE INDEX IF NOT EXISTS forecasts_maturity_epoch_idx
ON public.forecasts (maturity_epoch);

CREATE INDEX IF NOT EXISTS forecast_outcomes_resolved_epoch_idx
ON public.forecast_outcomes (resolved_epoch DESC);
