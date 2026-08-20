-- Immutable live Q1/Q2 forecast ledger and its one-to-one outcomes.
CREATE TABLE forecasts (
    forecast_id bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    quant_id text NOT NULL CHECK (quant_id IN ('q1_momentum', 'q2_mean_reversion')),
    formula_version text NOT NULL,
    cycle_id text NOT NULL,
    symbol text NOT NULL,
    horizon text NOT NULL CHECK (horizon IN ('30S', '1M', '5M', '15M', '30M', '1H')),
    cutoff_epoch double precision NOT NULL,
    maturity_epoch double precision NOT NULL,
    cutoff_midpoint double precision NOT NULL CHECK (cutoff_midpoint > 0),
    forecast_bps double precision NOT NULL,
    created_epoch double precision NOT NULL,
    CONSTRAINT forecasts_created_before_maturity CHECK (created_epoch <= maturity_epoch),
    CONSTRAINT forecasts_maturity_after_cutoff CHECK (maturity_epoch > cutoff_epoch),
    CONSTRAINT forecasts_identity UNIQUE (quant_id, formula_version, cycle_id, symbol, horizon)
);

CREATE TABLE forecast_outcomes (
    forecast_id bigint PRIMARY KEY REFERENCES forecasts(forecast_id),
    maturity_midpoint double precision NOT NULL CHECK (maturity_midpoint > 0),
    outcome_bps double precision NOT NULL,
    resolved_epoch double precision NOT NULL
);

CREATE FUNCTION reject_evidence_mutation() RETURNS trigger
LANGUAGE plpgsql AS $$
BEGIN
    RAISE EXCEPTION 'forecast evidence is append-only';
END;
$$;

CREATE TRIGGER forecasts_no_update_or_delete
BEFORE UPDATE OR DELETE ON forecasts
FOR EACH ROW EXECUTE FUNCTION reject_evidence_mutation();

CREATE TRIGGER forecast_outcomes_no_update_or_delete
BEFORE UPDATE OR DELETE ON forecast_outcomes
FOR EACH ROW EXECUTE FUNCTION reject_evidence_mutation();
