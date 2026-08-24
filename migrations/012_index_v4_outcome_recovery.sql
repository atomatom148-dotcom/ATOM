-- Bound rolling-deploy recovery by durable outcome commit order without
-- scanning or rewriting append-only evidence.
CREATE INDEX IF NOT EXISTS atom_v9_v4_outcomes_recovery_idx
ON public.atom_v9_v4_outcomes (created_at DESC, outcome_record_id DESC);
