-- Complete the least-privilege V4 proof-reader path without evidence DML.
SET LOCAL lock_timeout = '2s';
SET LOCAL statement_timeout = '15s';

DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1
        FROM pg_catalog.pg_roles
        WHERE rolname = 'atom_v9_proof_owner'
          AND NOT rolcanlogin
          AND NOT rolinherit
          AND NOT rolsuper
          AND NOT rolcreatedb
          AND NOT rolcreaterole
          AND NOT rolreplication
          AND NOT rolbypassrls
    ) THEN
        RAISE EXCEPTION
            'atom_v9_proof_owner is missing or has unsafe attributes'
            USING ERRCODE = '55000';
    END IF;
END
$$;

CREATE POLICY atom_v9_v4_forecasts_proof_owner_select
ON public.atom_v9_v4_forecasts
FOR SELECT TO atom_v9_proof_owner USING (true);

ALTER FUNCTION public.reject_evidence_mutation()
SET search_path = pg_catalog;
