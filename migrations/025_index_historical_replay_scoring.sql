-- DB-2: operational migration. Supabase's transactional migration API cannot
-- execute CREATE INDEX CONCURRENTLY; apply this single statement directly and
-- verify pg_index before treating DB-2 as complete.
CREATE INDEX CONCURRENTLY atom_historical_replay_forecasts_scoring_idx
ON public.atom_historical_replay_forecasts
  (replay_run_id, quant_id, horizon, cutoff_at);
