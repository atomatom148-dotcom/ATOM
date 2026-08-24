-- Bound catalog locking so a busy append-only table makes this migration fail
-- cleanly for retry instead of queuing evidence writers behind unbounded DDL.
SET LOCAL lock_timeout = '2s';
SET LOCAL statement_timeout = '15s';

-- Make the session advisory owner authoritative during the first rolling
-- rollout from a legacy writer that does not yet acquire the lock in Python.
-- Its first evidence statement establishes the same session lease and keeps it
-- until that retiring connection closes.  The replacement therefore cannot
-- overtake an accepted legacy FIFO head between transactions.
CREATE FUNCTION public.atom_v9_evidence_require_runtime_owner()
RETURNS trigger
LANGUAGE plpgsql
SECURITY INVOKER
SET search_path = pg_catalog
AS $$
BEGIN
    -- bigint advisory keys are exposed by pg_locks as high/low uint32 words
    -- with objsubid=1.  Avoid growing PostgreSQL's reentrant lock count on
    -- every INSERT statement once this backend already owns the session lock.
    IF EXISTS (
        SELECT 1
        FROM pg_catalog.pg_locks AS l
        WHERE l.locktype = 'advisory'
          AND l.pid = pg_catalog.pg_backend_pid()
          AND l.mode = 'ExclusiveLock'
          AND l.granted
          AND l.classid = 1096044365::oid
          AND l.objid = 1446593868::oid
          AND l.objsubid = 1
    ) THEN
        RETURN NULL;
    END IF;
    IF NOT pg_catalog.pg_try_advisory_lock(4707474704086680908::bigint) THEN
        RAISE EXCEPTION 'ATOM evidence runtime owner is active in another session'
            USING ERRCODE = '55P03';
    END IF;
    RETURN NULL;
END
$$;

CREATE TRIGGER forecasts_require_runtime_owner
BEFORE INSERT ON public.forecasts
FOR EACH STATEMENT EXECUTE FUNCTION public.atom_v9_evidence_require_runtime_owner();
CREATE TRIGGER forecast_outcomes_require_runtime_owner
BEFORE INSERT ON public.forecast_outcomes
FOR EACH STATEMENT EXECUTE FUNCTION public.atom_v9_evidence_require_runtime_owner();
CREATE TRIGGER volatility_forecasts_require_runtime_owner
BEFORE INSERT ON public.volatility_forecasts
FOR EACH STATEMENT EXECUTE FUNCTION public.atom_v9_evidence_require_runtime_owner();
CREATE TRIGGER volatility_forecast_outcomes_require_runtime_owner
BEFORE INSERT ON public.volatility_forecast_outcomes
FOR EACH STATEMENT EXECUTE FUNCTION public.atom_v9_evidence_require_runtime_owner();
CREATE TRIGGER atom_v9_v4_forecasts_require_runtime_owner
BEFORE INSERT ON public.atom_v9_v4_forecasts
FOR EACH STATEMENT EXECUTE FUNCTION public.atom_v9_evidence_require_runtime_owner();
CREATE TRIGGER atom_v9_v4_outcomes_require_runtime_owner
BEFORE INSERT ON public.atom_v9_v4_outcomes
FOR EACH STATEMENT EXECUTE FUNCTION public.atom_v9_evidence_require_runtime_owner();

REVOKE ALL PRIVILEGES ON FUNCTION
    public.atom_v9_evidence_require_runtime_owner()
FROM PUBLIC, anon, authenticated, service_role, atom_v9_v4_runtime;
