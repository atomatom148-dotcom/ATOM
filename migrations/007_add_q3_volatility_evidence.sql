-- Keep Q3 volatility evidence separate from directional forecast evidence.
CREATE TABLE public.volatility_forecasts (
    forecast_id bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    quant_id text NOT NULL CHECK (quant_id = 'q3_volatility'),
    formula_version text NOT NULL,
    cycle_id text NOT NULL,
    symbol text NOT NULL,
    horizon text NOT NULL CHECK (
        horizon IN ('30S', '1M', '5M', '15M', '30M', '1H')
    ),
    cutoff_epoch double precision NOT NULL,
    maturity_epoch double precision NOT NULL,
    cutoff_midpoint double precision NOT NULL CHECK (cutoff_midpoint > 0),
    forecast_volatility_bps double precision NOT NULL CHECK (
        forecast_volatility_bps >= 0
    ),
    created_epoch double precision NOT NULL,
    data_schema_version text NOT NULL,
    source_spec_version text NOT NULL,
    CONSTRAINT volatility_forecasts_created_before_maturity
        CHECK (created_epoch <= maturity_epoch),
    CONSTRAINT volatility_forecasts_maturity_after_cutoff
        CHECK (maturity_epoch > cutoff_epoch),
    CONSTRAINT volatility_forecasts_identity UNIQUE (
        quant_id, formula_version, cycle_id, symbol, horizon
    )
);

CREATE TABLE public.volatility_forecast_outcomes (
    forecast_id bigint PRIMARY KEY
        REFERENCES public.volatility_forecasts(forecast_id),
    maturity_midpoint double precision NOT NULL CHECK (maturity_midpoint > 0),
    realized_move_bps double precision NOT NULL CHECK (realized_move_bps >= 0),
    resolved_epoch double precision NOT NULL
);

CREATE TRIGGER volatility_forecasts_no_update_or_delete
BEFORE UPDATE OR DELETE ON public.volatility_forecasts
FOR EACH ROW EXECUTE FUNCTION public.reject_evidence_mutation();

CREATE TRIGGER volatility_forecast_outcomes_no_update_or_delete
BEFORE UPDATE OR DELETE ON public.volatility_forecast_outcomes
FOR EACH ROW EXECUTE FUNCTION public.reject_evidence_mutation();

CREATE INDEX volatility_forecasts_maturity_epoch_idx
ON public.volatility_forecasts (maturity_epoch);

CREATE INDEX volatility_forecast_outcomes_resolved_epoch_idx
ON public.volatility_forecast_outcomes (resolved_epoch DESC);

REVOKE ALL PRIVILEGES
ON TABLE public.volatility_forecasts, public.volatility_forecast_outcomes
FROM PUBLIC, anon, authenticated, service_role;

REVOKE ALL PRIVILEGES
ON SEQUENCE public.volatility_forecasts_forecast_id_seq
FROM PUBLIC, anon, authenticated, service_role;

ALTER TABLE public.volatility_forecasts ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.volatility_forecast_outcomes ENABLE ROW LEVEL SECURITY;
