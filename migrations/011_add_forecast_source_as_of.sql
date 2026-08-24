-- Preserve provider event time on new directional evidence without rewriting history.
ALTER TABLE public.forecasts
    ADD COLUMN IF NOT EXISTS source_as_of_epoch double precision;

ALTER TABLE public.forecasts
    DROP CONSTRAINT IF EXISTS forecasts_source_as_of_causal,
    ADD CONSTRAINT forecasts_source_as_of_causal CHECK (
        source_as_of_epoch IS NULL OR (
            source_as_of_epoch > '-Infinity'::double precision
            AND source_as_of_epoch < 'Infinity'::double precision
            AND source_as_of_epoch <= cutoff_epoch
        )
    );
