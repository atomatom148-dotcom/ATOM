-- DB-2: operational migration. CREATE INDEX CONCURRENTLY must be parsed and
-- executed outside a transaction by a concurrent-DDL-aware runner (for
-- example, Supabase CLI v2.113.0+). The session guards prevent a configured
-- statement timeout from leaving an interrupted INVALID index while bounding
-- lock acquisition. Verify pg_index before treating DB-2 as complete.
SET statement_timeout = '0';
SET lock_timeout = '5s';

CREATE INDEX CONCURRENTLY atom_historical_replay_forecasts_scoring_idx
ON public.atom_historical_replay_forecasts
  (replay_run_id, quant_id, horizon, cutoff_at);

RESET lock_timeout;
RESET statement_timeout;
