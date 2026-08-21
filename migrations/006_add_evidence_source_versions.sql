-- Preserve historical evidence while versioning every forecast's input contract.
ALTER TABLE public.forecasts
    ADD COLUMN IF NOT EXISTS data_schema_version text NOT NULL
        DEFAULT 'legacy-unversioned',
    ADD COLUMN IF NOT EXISTS source_spec_version text NOT NULL
        DEFAULT 'legacy-unversioned';
