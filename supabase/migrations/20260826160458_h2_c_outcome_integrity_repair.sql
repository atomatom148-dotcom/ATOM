-- H2-C.1: immutable outcome resolution lineage (follow-up; H2-C is unchanged).
SET LOCAL lock_timeout = '2s';
SET LOCAL statement_timeout = '30s';

ALTER TABLE public.atom_historical_replay_outcomes
  ADD COLUMN resolution_spec_version text NOT NULL,
  ADD COLUMN outcome_source_dataset_digest text NOT NULL,
  ADD CONSTRAINT atom_historical_outcomes_resolution_spec_frozen
    CHECK (resolution_spec_version = 'COIN_MIDPOINT_LOG_RETURN_BPS_1'),
  ADD CONSTRAINT atom_historical_outcomes_source_digest_valid
    CHECK (outcome_source_dataset_digest ~ '^[0-9a-f]{64}$');
