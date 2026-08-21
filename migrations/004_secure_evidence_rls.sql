-- Evidence is backend-only; remove every Supabase Data API path.
REVOKE ALL PRIVILEGES
ON TABLE public.forecasts, public.forecast_outcomes
FROM PUBLIC, anon, authenticated, service_role;

REVOKE ALL PRIVILEGES
ON SEQUENCE public.forecasts_forecast_id_seq
FROM PUBLIC, anon, authenticated, service_role;

ALTER TABLE public.forecasts ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.forecast_outcomes ENABLE ROW LEVEL SECURITY;
