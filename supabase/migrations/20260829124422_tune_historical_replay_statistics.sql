-- DB-1: keep planner statistics current for one-transaction replay appends.
-- The fixed thresholds are below the smallest certified session observed at
-- freeze time (743,904 forecasts and 61,992 outcomes), so every completed
-- session becomes eligible for auto-analyze without scaling out of range as
-- the append-only tables grow.
SET LOCAL lock_timeout = '5s';
SET LOCAL statement_timeout = '0';

ALTER TABLE public.atom_historical_replay_forecasts SET (
  autovacuum_analyze_scale_factor = 0.0,
  autovacuum_analyze_threshold = 100000
);

ALTER TABLE public.atom_historical_replay_outcomes SET (
  autovacuum_analyze_scale_factor = 0.0,
  autovacuum_analyze_threshold = 10000
);

ANALYZE public.atom_historical_replay_runs;
ANALYZE public.atom_historical_replay_forecasts;
ANALYZE public.atom_historical_replay_outcomes;
