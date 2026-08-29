-- DB-2: operational migration. Execute this complete file only through one
-- session-persistent, concurrent-DDL-aware runner (Supabase CLI v2.116.0+ or
-- psql). Do not submit it as one payload to Supabase's MCP apply_migration or
-- execute_sql tools: their transactional wrapper rejects concurrent builds.
-- The session guards prevent a configured statement timeout from leaving an
-- interrupted INVALID index while bounding lock acquisition. Verify pg_index
-- before treating DB-2 as complete.
SET statement_timeout = '0';
SET lock_timeout = '5s';

CREATE INDEX CONCURRENTLY atom_historical_replay_forecasts_scoring_idx
ON public.atom_historical_replay_forecasts
  (replay_run_id, quant_id, horizon, cutoff_at);

RESET lock_timeout;
RESET statement_timeout;
