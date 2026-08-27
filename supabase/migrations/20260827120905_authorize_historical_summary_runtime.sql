-- Phase-E dashboard: expose only certified historical run manifests to the
-- existing live runtime.  Forecast and outcome evidence stay inaccessible.
SET LOCAL lock_timeout = '2s';
SET LOCAL statement_timeout = '15s';

REVOKE ALL PRIVILEGES ON TABLE
    public.atom_historical_replay_runs,
    public.atom_historical_replay_forecasts,
    public.atom_historical_replay_outcomes
FROM atom_v9_v4_runtime;

GRANT SELECT ON TABLE public.atom_historical_replay_runs
TO atom_v9_v4_runtime;

CREATE POLICY atom_historical_replay_runs_runtime_select
ON public.atom_historical_replay_runs
FOR SELECT TO atom_v9_v4_runtime
USING (
    execution_stage = 'REPLAY_COMPLETE'
    AND certification_status = 'CERTIFIED'
);
